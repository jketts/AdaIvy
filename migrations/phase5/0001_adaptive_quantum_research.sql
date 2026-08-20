CREATE TABLE phase5_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.phase5-record.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE phase5_material_projection (
    event_id TEXT PRIMARY KEY REFERENCES phase5_records(record_id),
    objective_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    current_validity TEXT NOT NULL CHECK(current_validity IN ('valid','corrected','superseded','invalidated')),
    latest_steering_action TEXT,
    latest_lifecycle_id TEXT,
    original_content_hash TEXT NOT NULL
);

CREATE TABLE phase5_verified_exports (
    content_hash TEXT PRIMARY KEY,
    canonical_json BLOB NOT NULL
);

CREATE INDEX phase5_records_subject_type_idx
ON phase5_records(subject_id, record_type, sequence);
