DROP TABLE IF EXISTS request CASCADE;
DROP TABLE IF EXISTS engineer CASCADE;
DROP TABLE IF EXISTS region CASCADE;


CREATE TABLE region (
    id SERIAL PRIMARY KEY,
    title VARCHAR(128) NOT NULL UNIQUE,
    office_address TEXT NOT NULL,
    office_lat DOUBLE PRECISION NOT NULL,
    office_lon DOUBLE PRECISION NOT NULL
);


CREATE TABLE engineer (
    id SERIAL PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES region(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,

    transport VARCHAR(16) NOT NULL DEFAULT 'transit'
    CHECK (transport IN ('transit', 'bike', 'car')),

    skills JSONB NOT NULL DEFAULT '[]'::jsonb,

    shift_start TIME NOT NULL DEFAULT '09:00',
    shift_end TIME NOT NULL DEFAULT '22:00',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (region_id, name),
    CHECK (shift_end > shift_start)
);
CREATE INDEX ix_engineer_region ON engineer (region_id);


CREATE TABLE request (
    id SERIAL PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES region(id) ON DELETE CASCADE,
    external_id VARCHAR(32) NOT NULL,
    address TEXT NOT NULL,
    district VARCHAR(128),
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    work_type VARCHAR(48) NOT NULL,
    hd_type VARCHAR(128),
    skill VARCHAR(16) NOT NULL
    CHECK (skill IN ('local', 'install', 'emergency')),
    duration_min SMALLINT NOT NULL CHECK (duration_min > 0),
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 100,
    required_transport VARCHAR(16)
    CHECK (required_transport IN ('foot', 'transit', 'bike', 'car')),
    equipment JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32),
    fact_engineer_id INTEGER REFERENCES engineer(id) ON DELETE SET NULL,
    UNIQUE (region_id, external_id, window_start),
    CHECK (window_end > window_start)
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_request_planning ON request (region_id, window_start);
CREATE INDEX ix_request_skill ON request (skill);
CREATE INDEX ix_request_fact ON request (fact_engineer_id);


CREATE TABLE IF NOT EXISTS route_cache (
                                           id           SERIAL PRIMARY KEY,
                                           transport    VARCHAR(16)      NOT NULL,
    from_lat     DOUBLE PRECISION NOT NULL,
    from_lon     DOUBLE PRECISION NOT NULL,
    to_lat       DOUBLE PRECISION NOT NULL,
    to_lon       DOUBLE PRECISION NOT NULL,
    departure_at TIMESTAMP        NOT NULL,
    minutes      SMALLINT         NOT NULL,
    km           DOUBLE PRECISION NOT NULL,
    payload      JSONB            NOT NULL,
    created_at   TIMESTAMP        NOT NULL DEFAULT now(),
    CONSTRAINT uq_route_cache_leg
    UNIQUE (transport, from_lat, from_lon, to_lat, to_lon, departure_at)
    );

CREATE INDEX IF NOT EXISTS ix_route_cache_departure ON route_cache (departure_at);

