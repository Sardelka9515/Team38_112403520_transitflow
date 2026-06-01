# AI Session Context — TransitFlow

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits your codebase and is consistent with your teammates' work.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like a team contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a fictional transit operator. It queries three databases — PostgreSQL (relational + vector), Neo4j (graph) — and uses an LLM to answer user questions. Our task as students is to design the database schema and implement the query functions in `databases/relational/queries.py` and `databases/graph/queries.py`.

## Tech Stack

- Language: Python 3.11+
- Relational DB: PostgreSQL via `psycopg2` with `RealDictCursor`
- Graph DB: Neo4j via the `neo4j` Python driver
- Vector search: `pgvector` extension (already implemented — do not modify)
- Web UI: Gradio
- LLM: Google Gemini or local Ollama (configured via `.env`)

## Coding Conventions

- **Naming:** `snake_case` for all Python names and SQL identifiers
- **Docstrings:** All functions must have a docstring with `Args:` and `Returns:` sections
- **Return types:** Use type hints. Read-only functions return `list[dict]` or `Optional[dict]`
- **Empty results:** Return `[]` or `None` (as documented), never raise an exception for "not found"
- **SQL:** Use `%s` placeholders for all user inputs — never string-format into SQL
- **Relational pattern:** Use `_connect()` helper + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** Use `_driver()` helper + session:
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH ...", station_id=station_id)
          return [dict(record) for record in result]
  ```

## Agreed Relational Schema

<!-- ============================================================
  FILL THIS IN after your team completes the schema design workshop.
  Paste your final CREATE TABLE statements here.
  ============================================================ -->

```sql
-- Users Domain
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(50) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(50),
    date_of_birth DATE,
    secret_question VARCHAR(255),
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS user_passwords (
    user_id VARCHAR(50) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    secret_answer_hash VARCHAR(255)
);

-- Stations Base
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- Metro Schedules
CREATE TABLE IF NOT EXISTS metro_schedules (
    schedule_id VARCHAR(50) PRIMARY KEY,
    line VARCHAR(50) NOT NULL,
    direction VARCHAR(50) NOT NULL,
    origin_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    first_train_time TIME,
    last_train_time TIME,
    base_fare_usd NUMERIC(10, 2) NOT NULL,
    per_stop_rate_usd NUMERIC(10, 2) NOT NULL,
    frequency_min INT NOT NULL
);

CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    schedule_id VARCHAR(50) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    stop_order INT NOT NULL,
    travel_time_from_origin_min INT NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

CREATE TABLE IF NOT EXISTS metro_schedule_days (
    schedule_id VARCHAR(50) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    day_of_week VARCHAR(3) NOT NULL,
    PRIMARY KEY (schedule_id, day_of_week)
);

-- National Rail Schedules
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    schedule_id VARCHAR(50) PRIMARY KEY,
    line VARCHAR(50) NOT NULL,
    service_type VARCHAR(50) NOT NULL,
    direction VARCHAR(50) NOT NULL,
    origin_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    first_train_time TIME,
    last_train_time TIME,
    frequency_min INT NOT NULL
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    stop_order INT NOT NULL,
    travel_time_from_origin_min INT NOT NULL,
    is_passed_through BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (schedule_id, station_id)
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_fares (
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    fare_class VARCHAR(50) NOT NULL,
    base_fare_usd NUMERIC(10, 2) NOT NULL,
    per_stop_rate_usd NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (schedule_id, fare_class)
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_days (
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    day_of_week VARCHAR(3) NOT NULL,
    PRIMARY KEY (schedule_id, day_of_week)
);

-- Seat Layouts
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id VARCHAR(50) PRIMARY KEY,
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS national_rail_coaches (
    coach_id VARCHAR(50) PRIMARY KEY,
    layout_id VARCHAR(50) REFERENCES national_rail_seat_layouts(layout_id) ON DELETE CASCADE,
    coach_name VARCHAR(50) NOT NULL,
    fare_class VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS national_rail_seats (
    seat_id VARCHAR(50) NOT NULL,
    coach_id VARCHAR(50) REFERENCES national_rail_coaches(coach_id) ON DELETE CASCADE,
    row INT NOT NULL,
    seat_column VARCHAR(5) NOT NULL,
    PRIMARY KEY (coach_id, seat_id)
);

-- Transactions
CREATE TABLE IF NOT EXISTS national_rail_bookings (
    booking_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES users(user_id),
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id),
    origin_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    travel_date DATE NOT NULL,
    departure_time TIME NOT NULL,
    ticket_type VARCHAR(50) NOT NULL,
    fare_class VARCHAR(50) NOT NULL,
    coach_id VARCHAR(50),
    seat_id VARCHAR(50),
    FOREIGN KEY (coach_id, seat_id) REFERENCES national_rail_seats(coach_id, seat_id),
    stops_travelled INT NOT NULL,
    amount_usd NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'confirmed',
    booked_at TIMESTAMPTZ DEFAULT NOW(),
    travelled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS metro_travel_history (
    trip_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES users(user_id),
    schedule_id VARCHAR(50) REFERENCES metro_schedules(schedule_id),
    origin_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(50) NOT NULL,
    day_pass_ref VARCHAR(50),
    stops_travelled INT,
    amount_usd NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'completed',
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    travelled_at TIMESTAMPTZ
);

-- Payments
CREATE TABLE IF NOT EXISTS metro_payments (
    payment_id VARCHAR(50) PRIMARY KEY,
    trip_id VARCHAR(50) NOT NULL REFERENCES metro_travel_history(trip_id) ON DELETE CASCADE,
    amount_usd NUMERIC(10, 2) NOT NULL,
    method VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    paid_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS national_rail_payments (
    payment_id VARCHAR(50) PRIMARY KEY,
    booking_id VARCHAR(50) NOT NULL REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE,
    amount_usd NUMERIC(10, 2) NOT NULL,
    method VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    paid_at TIMESTAMPTZ DEFAULT NOW()
);

-- Feedbacks
CREATE TABLE IF NOT EXISTS metro_feedbacks (
    feedback_id VARCHAR(50) PRIMARY KEY,
    trip_id VARCHAR(50) NOT NULL REFERENCES metro_travel_history(trip_id) ON DELETE CASCADE,
    user_id VARCHAR(50) REFERENCES users(user_id),
    rating INT CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS national_rail_feedbacks (
    feedback_id VARCHAR(50) PRIMARY KEY,
    booking_id VARCHAR(50) NOT NULL REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE,
    user_id VARCHAR(50) REFERENCES users(user_id),
    rating INT CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

```

## Agreed Graph Schema

<!-- ============================================================
  FILL THIS IN after your team agrees on Neo4j node labels and
  relationship types.
  ============================================================ -->

```
Node labels:
- TODO

Relationship types:
- TODO

Key properties:
- TODO
```

## Function Signatures We Are Implementing

These are fixed contracts. AI-generated code must match these signatures exactly.

### Relational (`databases/relational/queries.py`)

```python
# Read-only
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]: ...
def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]: ...
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]: ...
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]: ...
def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]: ...
def query_user_profile(user_email: str) -> Optional[dict]: ...
def query_user_bookings(user_email: str) -> dict: ...  # returns {"national_rail": [...], "metro": [...]}
def query_payment_info(booking_id: str) -> Optional[dict]: ...

# Write operations
def execute_booking(user_id, schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type="single") -> tuple[bool, dict | str]: ...
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]: ...

# Auth
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]: ...
def login_user(email: str, password: str) -> Optional[dict]: ...
def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...
```

### Graph (`databases/graph/queries.py`)

```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

## Team Decisions Log

<!-- Add entries as you make decisions. Format: "Decision: X. Why: Y." -->

- [ ] Schema design: TODO — add your table/column decisions here
- [ ] Graph schema: TODO — add your node label and relationship type decisions here
- [ ] (example) Metro schedule stop ordering: using `jsonb_array_elements` approach — easier to debug than containment operators

## Prompts That Worked

<!-- Share prompts that produced good output so teammates can reuse them. -->

### Schema design prompt that worked:
```
TODO — add a prompt here after your schema design workshop
```

### Query implementation prompt that worked:
```
TODO — add after implementing your first function
```
