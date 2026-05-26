# TransitFlow — Comprehensive Design Plan

A planning document covering all four tasks end-to-end: schema, graph topology, query layer, RAG content, plus testing strategy, team workflow, and risks. No code — decisions and rationale only.

---

## 0. Scope and success criteria

**In scope (required tasks)**
1. Relational schema + seeders for PostgreSQL
2. Graph topology + seeders for Neo4j
3. Query/transaction functions in both `databases/*/queries.py` modules
4. Policy document content for the pgvector RAG layer

**Out of scope (do not touch)**
- `skeleton/agent.py`, `skeleton/ui.py`, `skeleton/llm_provider.py`, `skeleton/config.py` — already wired up
- The `policy_documents` table definition itself
- Vector seeding mechanics (only the JSON content we feed it)

**Definition of done**: every query in the README "Try These Queries" section returns a correct, helpful answer in the chat UI, both logged-out and logged-in.

---

## 1. Guiding principles

| Principle | What it means in practice |
|---|---|
| **Right tool for the job** | Topology in Neo4j; transactional records in PostgreSQL; fuzzy text in pgvector. No duplication across stores. |
| **Natural keys over surrogate keys** | Mock data already provides stable IDs (`MS01`, `NR_SCH01`, `BK001`). Use them as PKs — easier to debug, no `currval()` gymnastics in seeders. |
| **Normalise nested JSON arrays** | Lists inside JSON records (lines, stops, adjacencies) become child tables in SQL or relationships in Neo4j. Never store JSON arrays in columns unless they are truly opaque. |
| **Idempotent seeders** | `ON CONFLICT DO NOTHING` (Postgres) and `MERGE` (Cypher), so re-runs are safe and a teammate's `git pull → re-seed` workflow never corrupts state. |
| **Schema first, then seed, then query** | Don't write query functions before the tables they read exist — feedback loops are slow when you have to reset the DB. |
| **No premature features** | Build only what the README's example queries need. Skip the "extension ideas" until the baseline works. |

---

## 2. Data model — PostgreSQL relational

### 2.1 Domains
Four logical groupings, each forming a small cluster of tables:

1. **Infrastructure** — stations, schedules, schedule stops, seat layouts
2. **Identity** — users + auth fields
3. **Transactions** — national rail bookings, metro trips, payments
4. **Feedback** — passenger ratings and comments

### 2.2 Table inventory (relational only — vector table stays untouched)

| Cluster | Table | Purpose | Key relationships |
|---|---|---|---|
| Infra | `metro_stations` | Station catalog | — |
| Infra | `metro_station_lines` | Many-to-many: station ↔ line | FK → metro_stations |
| Infra | `national_rail_stations` | Station catalog | — |
| Infra | `national_rail_station_lines` | M2M station ↔ line | FK → national_rail_stations |
| Infra | `metro_schedules` | Per-line schedule header + fare structure | — |
| Infra | `metro_schedule_stops` | Stop sequence (order matters) | FK → schedule, station |
| Infra | `national_rail_schedules` | Schedule header, normal vs express, dual fare classes | — |
| Infra | `national_rail_schedule_stops` | Stop sequence + departure_time per stop | FK → schedule, station |
| Infra | `seat_layouts` | Coach/row/column/fare_class per schedule | FK → schedule |
| Identity | `users` | Profile + auth + secret Q/A | — |
| Tx | `national_rail_bookings` | Advance bookings w/ assigned seat | FK → user, schedule, origin, destination |
| Tx | `metro_travels` | Same-day tap-in trips | FK → user, schedule, origin, destination |
| Tx | `payments` | Payment records for both networks | FK → user; one-of(booking, trip) |
| Feedback | `feedback` | Post-travel ratings | FK → user; one-of(booking, trip) |

### 2.3 Key design decisions and why

**Decision: split station-lines into a junction table rather than a TEXT[] column.**
The JSON has `"lines": ["M1", "M2"]`. A junction table lets us index by line and join cleanly when answering "which stations are on line M1?". TEXT[] would work but blocks normal JOIN-based queries.

**Decision: schedules and schedule_stops are separate tables.**
Each schedule has an ordered list of stops with timing. The `stop_order` integer is the discriminator and forms a composite PK with `schedule_id`. Availability queries (`origin.stop_order < destination.stop_order`) are then a self-join on the stops table — clean and fast.

**Decision: seat_layouts is a static reference table per schedule, not per booking.**
Layouts are templates ("schedule NR_SCH01 has 40 standard + 8 first seats"). Availability for a *specific date* is computed by LEFT JOIN'ing `national_rail_bookings` on `(schedule_id, travel_date, seat_id)` and filtering for NULL. This avoids duplicating layout rows per date.

**Decision: keep metro and national rail in *separate* tables rather than one unified `journeys` table.**
The two networks differ structurally: rail has seats, fare classes, advance booking, return tickets; metro has none of these. A unified table would be sparse and full of `NULL`s. The query layer can `UNION` them when the agent needs combined history.

**Decision: payments table uses a "one-of" constraint, not a polymorphic `journey_type` discriminator.**
Two nullable FKs (`booking_id`, `trip_id`) with a CHECK constraint that exactly one is set. This preserves referential integrity, which a polymorphic string column cannot.

**Decision: store user passwords as plaintext, per the file's explicit teaching note.**
Not a security choice — an educational one called out in the existing code comments. Production would use bcrypt/argon2.

### 2.4 Indexing strategy (minimal, justified)

| Index | Why |
|---|---|
| `national_rail_bookings(schedule_id, travel_date)` | Hot path: seat occupancy lookup |
| `national_rail_bookings(user_id)` | "Show my bookings" |
| `metro_travels(user_id)` | Same |
| `users(email)` UNIQUE | Login lookup |
| Composite PKs on schedule_stops `(schedule_id, stop_order)` | Implicit, but supports ORDER BY |

Skip exotic indexes until query patterns prove they're needed.

### 2.5 What we deliberately do NOT model in PostgreSQL

- **Adjacency / topology** — belongs in Neo4j. Putting `adjacent_stations` into a SQL table would force route-finding to be a recursive CTE, which is exactly the awkwardness the three-database design is meant to avoid.
- **Policy text** — pgvector handles it; relational has no role here.

---

## 3. Data model — Neo4j graph

### 3.1 Nodes

| Label | Properties | Source |
|---|---|---|
| `MetroStation` | `station_id`, `name` | `metro_stations.json` |
| `NationalRailStation` | `station_id`, `name` | `national_rail_stations.json` |

Keep node properties lean — name and ID are enough. Line membership is a property of the *edge*, not the node, because a station can sit on multiple lines.

### 3.2 Relationships

| Type | Direction | Properties | Purpose |
|---|---|---|---|
| `METRO_LINK` | directed, seeded both ways | `line`, `travel_time_min`, `fare_usd` | Metro adjacency |
| `RAIL_LINK` | directed, seeded both ways | `line`, `travel_time_min`, `fare_standard`, `fare_first` | National rail adjacency |
| `INTERCHANGE_TO` | undirected (seed both ways) | `walk_time_min` (default ~5) | Cross-network walking interchange |

### 3.3 Key design decisions

**Decision: line is an edge property, not a separate `Line` node.**
A `Line` node would force `(station)-[:ON_LINE]->(line)<-[:ON_LINE]-(station)` patterns just to find neighbours, doubling hops in every route query. Treating the line as edge metadata keeps shortest-path queries one-hop-per-link.

**Decision: bake fare into the edge.**
Cheapest-route queries reduce to Dijkstra with a different weight property. If fares lived only in SQL, the graph could not answer cost-based routing without round-tripping to Postgres per edge — defeating the point of the graph.

**Decision: `INTERCHANGE_TO` is a first-class relationship, not implicit via shared name.**
Makes cross-network routing a clean `[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*]` pattern. APOC Dijkstra can include or exclude it depending on the question.

**Decision: seed edges in both directions explicitly.**
APOC Dijkstra respects direction. Real rail links are bidirectional, so we MERGE the reverse edge as part of seeding.

### 3.4 What lives in Neo4j vs. PostgreSQL

| Question | Database | Why |
|---|---|---|
| "Fastest route from X to Y" | Neo4j | Dijkstra |
| "Cheapest route from X to Y" | Neo4j | Dijkstra (different weight) |
| "Alternative route avoiding Z" | Neo4j | Path predicate filtering |
| "Which trains *serve* a station on date D?" | PostgreSQL | Schedule + booking facts |
| "Is seat B05 free on NR_SCH01 / 2026-06-01?" | PostgreSQL | Transactional state |
| "Stations within 2 hops of NR03 (delay ripple)" | Neo4j | Variable-length pattern |

---

## 4. Query / function layer

### 4.1 Mapping README example queries → tools → functions

This table is the acceptance checklist. If every row works, the project is done.

| Example chat question | Tool selected | Backing function | DB |
|---|---|---|---|
| "Trains from NR01 to NR05 today?" | `check_national_rail_availability` | `query_national_rail_availability` | PG |
| "Fastest metro route MS01 → MS14" | `find_route` | `query_shortest_route` | Neo4j |
| "MS01 → NR05 (cross-network)" | `find_route` | `query_interchange_path` | Neo4j |
| "If NR03 closed, alternatives NR01→NR05?" | `find_alternative_routes` | `query_alternative_routes` | Neo4j |
| "45-min delay — compensation?" | `search_policy` | (existing) | pgvector |
| "Bicycles on rail?" | `search_policy` | (existing) | pgvector |
| "Show my bookings" | `get_user_bookings` | `query_user_bookings` | PG |
| "Book NR01→NR05 on 2026-06-01" | `check_availability` → `get_available_seats` → `make_booking` | `query_national_rail_availability`, `query_available_seats`, `execute_booking` | PG |
| "Cancel BK-XXXXXX" | `cancel_booking` | `execute_cancellation` | PG |

### 4.2 Relational query functions — design notes

| Function | Strategy |
|---|---|
| `query_national_rail_availability` | Self-join `national_rail_schedule_stops` so origin.stop_order < destination.stop_order on the same schedule. LEFT JOIN bookings on `(schedule_id, travel_date)` to count seats sold per fare class. |
| `query_national_rail_fare` | `base_fare_<class> + per_stop_rate_<class> * stops_travelled`. Return both components so the LLM can explain the breakdown. |
| `query_metro_schedules` / `query_metro_fare` | Same shape as rail but no fare-class branching. |
| `query_available_seats` | `seat_layouts LEFT JOIN bookings USING (schedule_id, seat_id) WHERE booking.booking_id IS NULL AND travel_date = $date`. |
| `query_user_profile`, `query_user_bookings`, `query_payment_info` | Straightforward SELECTs. `query_user_bookings` returns `{national_rail: [...], metro: [...]}` to match the existing agent's expected shape. |
| `execute_booking` | Transaction: lock the seat row (`SELECT … FOR UPDATE` on the layout row + check no booking exists for that date), INSERT booking, INSERT payment, COMMIT. Generate `BK-XXXXXX` / `PM-XXXXXX` via existing helpers. |
| `execute_cancellation` | Look up booking + service type (normal/express). Compute hours until `travel_date + departure_time`. Apply RF001 (normal) or RF002 (express) bands. UPDATE booking status, INSERT refund payment (negative amount). Return refund value and the policy reference quoted. |
| Auth functions | Plain SELECT/UPDATE against `users`. Plaintext password comparison (per file's note). Secret-answer match is case-insensitive (`LOWER(stored) = LOWER(input)`). |

### 4.3 Graph query functions — design notes

| Function | Strategy |
|---|---|
| `query_shortest_route` | APOC Dijkstra over `METRO_LINK\|RAIL_LINK\|INTERCHANGE_TO` with weight `travel_time_min`. Auto-infer label set from ID prefix when `network="auto"`. |
| `query_cheapest_route` | Same Dijkstra, weight = `fare_usd` (metro) or `fare_<class>` (rail). For mixed-network paths, the `INTERCHANGE_TO` edge gets weight 0 (or a token transfer fee). |
| `query_alternative_routes` | `allShortestPaths` or k-shortest via APOC, filter with `NONE(n IN nodes(path) WHERE n.station_id = $avoid)`. Return up to `max_routes`. |
| `query_interchange_path` | Dijkstra explicitly permitting `INTERCHANGE_TO`. Annotate which node is the interchange point in the result. |
| `query_delay_ripple` | `MATCH (s {station_id:$id})-[*1..$hops]-(n) WITH n, shortestPath(...) RETURN n.station_id, n.name, length, collect(DISTINCT lines)`. |
| `query_station_connections` | One-hop neighbours with the line(s) of each connection. |

### 4.4 Function-level concerns

- **Auth-gated functions** receive `user_id` from the agent (already injected by `skeleton/agent.py`). The query layer must trust the caller and not re-validate — that's the agent's contract.
- **Return shapes must be JSON-serialisable** because the agent's `_normalise_result` flattens dicts/lists recursively. No tuples, no `Decimal` without conversion, no `date` objects without `.isoformat()`.
- **Errors are returned, not raised**, for `execute_*` functions: `(False, "message")` is the contract per the docstrings.

---

## 5. RAG content (Task 3 — policy JSONs)

The four existing files cover the baseline. Audit which README example queries the current content can already answer, and only add what's missing.

| Example question | Existing? | Action |
|---|---|---|
| 45-min delay → RF005 50% refund | Already present in `refund_policy.json` | None |
| Bicycle on national rail | Present in `travel_policies.json` | None — verify content quality |
| Lost property | Likely missing | Add entry to `travel_policies.json` |
| Group bookings (10+) | Likely missing | Add to `booking_rules.json` |
| Accessibility / assisted travel | Check first | Add if missing |

**Content style guide for new entries**
- Lead with the rule, then the conditions, then the action. The LLM cites the document — write text it can quote cleanly.
- Include a stable identifier (`RF005`, `TP-LP-01`) so the assistant's answer is auditable.
- One concept per entry. Splitting "refund 0–29 min" from "refund 30–59 min" into separate entries gives the vector search better targeting than one mega-entry.

**Trap to avoid**: switching LLM provider invalidates all stored embeddings (Ollama=768 dim, Gemini=3072 dim). Decide as a team before seeding. If we switch later, `schema.sql` must be updated and the database fully reset.

---

## 6. Seeder design

### 6.1 PostgreSQL seeder (`skeleton/seed_postgres.py`)

**Insertion order** (FK dependencies):
1. `metro_stations`, `national_rail_stations` (both before the lines/interchange tables that reference them)
2. `*_station_lines`
3. `*_schedules`
4. `*_schedule_stops`, `seat_layouts`
5. `users`
6. `national_rail_bookings`, `metro_travels` (depend on users + schedules + stations)
7. `payments`, `feedback`

**Handling nested JSON**: each `seed_*` function reads its JSON, flattens nested arrays into row tuples, and calls `insert_many`. The function bodies stay small and uniform.

**Re-runnability**: every insert uses `ON CONFLICT DO NOTHING`. A teammate pulling new mock data can re-run without resetting.

### 6.2 Neo4j seeder (`skeleton/seed_neo4j.py`)

**Two passes**: nodes first (all `MERGE`), then relationships (all `MERGE`). Avoids "no such node" failures when an adjacency references a station not yet created.

**`seed.cypher` vs Python**: keep static graph constants in `seed.cypher` if convenient, but the adjacency lists are easier to load via Python iteration over the JSONs. Both are acceptable per the README; pick one and be consistent.

---

## 7. Testing and verification strategy

This project has no automated tests. Verification is manual but should be *systematic*:

| Phase | Check | Tool |
|---|---|---|
| After schema apply | All tables exist, FKs valid, no syntax errors | pgAdmin → schema viewer |
| After Postgres seed | Row counts match JSON record counts | `SELECT count(*)` per table |
| After Neo4j seed | Node and edge counts match expected | `MATCH (n) RETURN labels(n), count(*)` |
| After query implementation | Each README example query returns a sensible answer | Chat UI with debug panel **on** |
| Booking flow | Book → query bookings → cancel → verify refund payment row | Chat UI + pgAdmin |
| Cross-network routing | MS01 → NR05 uses an `INTERCHANGE_TO` edge | Neo4j Browser visualisation |

**Debug panel discipline**: keep "Show database debug panel" on while developing. It shows tool selection, raw results, and the normalised summary — the fastest way to spot whether the LLM is calling the wrong tool vs the function returning wrong data.

---

## 8. Team workflow

Per the README's "Working as a Team" section, the critical rule is **whoever changes a seed file commits it; everyone else re-seeds on pull**.

| File changed | Recipient action |
|---|---|
| `schema.sql` | `docker compose down -v && docker compose up -d` then re-seed all three |
| `seed_postgres.py` or any `train-mock-data/*.json` (non-policy) | Re-run `seed_postgres.py` |
| `seed.cypher` or `seed_neo4j.py` | Re-run `seed_neo4j.py` |
| Policy JSONs | Re-run `seed_vectors.py` |
| `.env` (LLM provider) | Coordinate as a team; never commit. Switching provider → full reset. |

**Branch hygiene**: one task per branch (`task-1-schema`, `task-2-graph`, etc.). Schema changes go through PR review because they invalidate everyone's local DB.

---

## 9. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Embedding dimension mismatch after provider switch | Medium | Lock provider before first seed; document it in the team channel |
| Seat-booking race condition (two users grab same seat) | Low (single-user demo) | `SELECT … FOR UPDATE` on the layout row in `execute_booking` |
| Schedule self-join returns wrong direction | Medium | Enforce `origin.stop_order < destination.stop_order`; unit-verify with a known pair |
| Neo4j route includes interchange when user wanted single-network | Low | Honour the `network` parameter — restrict relationship types accordingly |
| Plaintext passwords leaking via `query_user_profile` | Medium | Never SELECT the password column in profile/booking queries — only in `login_user` |
| Graph and SQL station IDs drift | Low | Both seeded from the same `train-mock-data/*.json` files |
| Re-seeding wipes test bookings created via UI | Expected | Only an issue mid-demo — schedule reseeds for the start of work sessions |

---

## 10. Suggested execution order

1. **Schema** — write `schema.sql`, apply, verify in pgAdmin (no data yet).
2. **Postgres seeder** — implement function-by-function, checking row counts after each.
3. **Read-only query functions** — `query_national_rail_availability`, fare functions, `query_user_*`. Test each via chat UI.
4. **Graph seed** — `seed.cypher` + `seed_neo4j.py`. Verify in Neo4j Browser.
5. **Graph queries** — routes first, then alternative/interchange/ripple.
6. **Transactional functions** — `execute_booking`, `execute_cancellation`. Hardest to debug; do them with both pgAdmin and the chat UI open.
7. **Auth functions** — register/login/secret-answer/password reset.
8. **Policy content** — fill gaps the README example queries exposed.
9. **End-to-end pass** — run every README example query in sequence, both logged-out and logged-in.

---

## 11. Deliverables checklist

- [ ] `databases/relational/schema.sql` — all relational tables defined
- [ ] `databases/relational/queries.py` — every `query_*` and `execute_*` implemented, no `NotImplementedError`
- [ ] `databases/graph/seed.cypher` — nodes, links, interchanges
- [ ] `databases/graph/queries.py` — all six graph functions
- [ ] `skeleton/seed_postgres.py` — all `seed_*` functions
- [ ] `skeleton/seed_neo4j.py` — `seed()` implemented
- [ ] `train-mock-data/*.json` policy files — extended to cover the README questions
- [ ] All "Try These Queries" examples return correct answers in the UI
