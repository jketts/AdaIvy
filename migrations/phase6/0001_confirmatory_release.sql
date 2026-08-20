CREATE TABLE phase6_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.phase6-record.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE phase6_verified_exports (
    content_hash TEXT PRIMARY KEY,
    canonical_json BLOB NOT NULL
);

CREATE INDEX phase6_records_subject_type_idx
ON phase6_records(subject_id, record_type, sequence);
