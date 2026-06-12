# TASK 6 — Optional Extension: Bonus Features

**Team 38** · Author: 李宥寬 (Sardelka9515)

This document lists every file added or modified for the Task 6 extension, with the
specific tables, functions, and tools introduced in each. Full design rationale,
example queries, and testing evidence are in **Section 7** of `Team38_DESIGN_DOC.md`.

Each modified source file carries a `TASK 6 EXTENSION:` comment near the top so the
new code can be located unambiguously.

---

## Summary of Features

| # | Feature | Database | Agent tool |
| - | ------- | -------- | ---------- |
| 1 | Platform Assignments | PostgreSQL (relational) | `get_platform` |
| 2 | Service Delay Records | PostgreSQL (relational) | `get_service_delays` |
| 3 | Loyalty Points | PostgreSQL (relational) | `get_loyalty_points` |
| 4 | Extended Policy Documents | PostgreSQL (pgvector / RAG) | `search_policy` |
| 5 | Metro Fare-Zone Properties | Neo4j (graph) | `get_stations_by_zone` |

---

## Files Modified

### `databases/relational/schema.sql`
New schema objects:
- **`platform_assignments`** table — composite PK `(schedule_id, station_id)`, FKs to
  `national_rail_schedules` and `national_rail_stations` with `ON DELETE CASCADE`.
- **`delay_records`** table — surrogate `SERIAL` PK + unique `delay_id`,
  `CHECK (delay_minutes > 0)`, and index `delay_records_schedule_date_idx` on
  `(schedule_id, travel_date)`.
- **`users.loyalty_points`** column — added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.
- **`loyalty_transactions`** table — ledger of point awards/redemptions, FK to `users`,
  index `loyalty_transactions_user_idx` on `(user_id)`.

### `databases/relational/queries.py`
New functions:
- **`query_platform_assignment(schedule_id, station_id)`** — joins `platform_assignments`
  to `national_rail_stations` and `national_rail_schedules`.
- **`query_service_delays(schedule_id=None, travel_date=None)`** — dynamic `WHERE` clause;
  both filters optional.
- **`query_loyalty_balance(user_email)`** — returns balance + last 5 `loyalty_transactions`.

Modified function:
- **`execute_booking(...)`** — awards loyalty points (`UPDATE users.loyalty_points` +
  `INSERT INTO loyalty_transactions`) inside the existing booking transaction, so points
  are granted atomically with the booking and payment.

### `databases/graph/queries.py`
New function:
- **`query_stations_by_zone(zone)`** — Cypher `MATCH (s:MetroStation {zone: $zone})`,
  returns stations ordered by `station_id`.

### `skeleton/agent.py`
- Imports for the three new relational queries and `query_stations_by_zone`.
- Four new tool schemas + `_execute_tool` dispatch branches + `TOOLS_SCHEMA` entries +
  Ollama routing hints: **`get_platform`**, **`get_service_delays`**,
  **`get_loyalty_points`**, **`get_stations_by_zone`**.
- Regex parameter-correction and a delay-history fallback so the local router model
  (`llama3.2:1b`) populates the new tools' parameters reliably; `search_policy` guarded
  against the router echoing its own parameter schema.

### `skeleton/seed_postgres.py`
New seed functions (idempotent via `ON CONFLICT DO NOTHING`), both called in `main()`:
- **`seed_platform_assignments(cur)`**
- **`seed_delay_records(cur)`**

### `skeleton/seed_neo4j.py`
- The `MetroStation` `MERGE` now also writes the bonus **`zone`** property.

### `skeleton/seed_vectors.py`
- **`build_documents()`** extended to embed the new top-level policy sections
  `group_bookings`, `lost_property`, and `accessibility` (corpus grew 13 → 18 documents).

### `train-mock-data/booking_rules.json`
- Added **`group_bookings`** (BR-GRP-01) policy section.

### `train-mock-data/refund_policy.json`
- Added **`Penalty Fares`** (RF-PF-01) and **`Engineering Works Compensation`** (RF-EW-01).

### `train-mock-data/travel_policies.json`
- Added **`lost_property`** (TP-LP-01) and **`accessibility`** (TP-ACC-01) policy sections.

### `train-mock-data/metro_stations.json`
- Added a **`zone`** field (1–3) to all 20 metro stations.

> Note: JSON files cannot carry comments without becoming invalid, so the
> `TASK 6 EXTENSION:` marker is omitted from the data files; their changes are
> listed here instead.

---

## Files Added

### `train-mock-data/platform_assignments.json`
36 rows mapping each national rail schedule to a platform number at each station it serves.

### `train-mock-data/delay_records.json`
15 historical delay records (DL001–DL015) across schedules NR_SCH01–NR_SCH08.

---

## Verification (LLM bypassed — tests the data layer)

| Feature | Result |
| ------- | ------ |
| Platform | `NR_SCH01@NR01 → Platform 1`; express `NR_SCH05@NR03 → Platform 5` |
| Delays | `NR_SCH01` → 3 records; date `2026-06-10` → DL015; no filter → all 15 |
| Loyalty | booking of \$8.50 awarded **8 points** + matching ledger row, atomically |
| RAG | all 5 new policy documents retrieve in top-3 for topical queries |
| Zones | zone 1 → 4 stations, zone 2 → 4, zone 3 → 12 |
