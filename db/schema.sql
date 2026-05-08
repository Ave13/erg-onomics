CREATE TABLE IF NOT EXISTS workouts (
    id          INTEGER PRIMARY KEY,
    name        TEXT,
    definition  JSON,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    workout_id     INTEGER REFERENCES workouts(id),
    started_at     REAL,
    ended_at       REAL,
    status         TEXT    DEFAULT 'active',
    total_distance REAL,
    total_time     INTEGER,
    avg_pace       REAL,
    avg_watts      REAL,
    avg_spm        REAL,
    max_watts      INTEGER,
    calories       INTEGER,
    avg_hr         INTEGER,
    max_hr         INTEGER,
    tcx_path       TEXT,
    raw_data       JSON
);

CREATE TABLE IF NOT EXISTS stroke_log (
    id                INTEGER PRIMARY KEY,
    stroke_num        INTEGER NOT NULL,
    elapsed_secs      REAL    NOT NULL,
    interval_secs     REAL    NOT NULL,
    speed_mm_s        INTEGER NOT NULL,
    logged_at         REAL    NOT NULL,
    drive_time_secs   REAL,
    recovery_secs     REAL,
    drive_length_cm   INTEGER,
    avg_force_n       REAL,
    peak_force_n      REAL,
    session_id        INTEGER REFERENCES sessions(id),
    hr_bpm            INTEGER,
    work_per_stroke_j REAL,
    stroke_distance_m REAL
);
