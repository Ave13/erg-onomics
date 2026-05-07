CREATE TABLE IF NOT EXISTS workouts (
    id          INTEGER PRIMARY KEY,
    name        TEXT,
    definition  JSON,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    workout_id     INTEGER REFERENCES workouts(id),
    date           DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_distance REAL,
    total_time     INTEGER,
    avg_pace       REAL,
    avg_watts      REAL,
    avg_spm        REAL,
    max_watts      INTEGER,
    calories       INTEGER,
    raw_data       JSON
);
