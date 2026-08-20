CREATE TABLE phase4_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.phase4a-record.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0 AND sequence <= 256),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE phase4_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    record_id TEXT NOT NULL REFERENCES phase4_records(record_id),
    event_type TEXT NOT NULL CHECK(event_type = 'record_appended'),
    payload_hash TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE phase4_sources (
    source_id TEXT PRIMARY KEY,
    provenance_record_id TEXT NOT NULL UNIQUE REFERENCES phase4_records(record_id),
    artifact_hash TEXT NOT NULL,
    content_object_id TEXT NOT NULL UNIQUE,
    local_path_hash TEXT,
    content_retained INTEGER NOT NULL CHECK(content_retained IN (0,1)),
    deletion_state TEXT NOT NULL CHECK(deletion_state IN ('active','requested','removing','incomplete','completed','unavailable')),
    deletion_error TEXT,
    deletion_request_id TEXT,
    completion_recorded_at TEXT
);

CREATE TABLE phase4_suppression_projection (
    source_id TEXT PRIMARY KEY,
    suppressed INTEGER NOT NULL CHECK(suppressed IN (0,1)),
    legal_hold INTEGER NOT NULL CHECK(legal_hold IN (0,1)),
    content_retained INTEGER NOT NULL CHECK(content_retained IN (0,1)),
    last_lifecycle_id TEXT
);

CREATE TABLE phase4_verified_imports (
    content_hash TEXT PRIMARY KEY,
    operational_hash TEXT NOT NULL,
    canonical_json BLOB NOT NULL
);

CREATE INDEX phase4_records_subject_type_idx
ON phase4_records(subject_id, record_type, sequence);
