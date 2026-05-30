-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================

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
    CONSTRAINT national_rail_bookings_seat_pair_chk CHECK (
        (coach_id IS NULL AND seat_id IS NULL) OR
        (coach_id IS NOT NULL AND seat_id IS NOT NULL)
    ),
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

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS policy_documents_embedding_idx ON policy_documents USING hnsw (embedding vector_cosine_ops);
