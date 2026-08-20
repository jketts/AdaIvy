CREATE TABLE phase4b_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL CHECK(record_type IN ('acquisition_candidate','parse_candidate','failure','invalidation')),
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.phase4b-record.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    operational_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE phase4b_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    record_id TEXT NOT NULL UNIQUE REFERENCES phase4b_records(record_id),
    event_type TEXT NOT NULL CHECK(event_type = 'candidate_record_appended'),
    content_hash TEXT NOT NULL,
    operational_hash TEXT NOT NULL
);

CREATE TABLE phase4b_candidate_projection (
    record_id TEXT PRIMARY KEY REFERENCES phase4b_records(record_id),
    subject_id TEXT NOT NULL,
    record_type TEXT NOT NULL CHECK(record_type IN ('acquisition_candidate','parse_candidate','failure')),
    current_state TEXT NOT NULL CHECK(current_state IN ('active_candidate','invalidated_candidate')),
    latest_invalidation_id TEXT REFERENCES phase4b_records(record_id)
);

CREATE TABLE phase4b_verified_exports (
    content_hash TEXT PRIMARY KEY,
    operational_hash TEXT NOT NULL,
    canonical_json BLOB NOT NULL
);

CREATE INDEX phase4b_records_subject_type_idx
ON phase4b_records(subject_id, record_type, sequence);

CREATE TRIGGER phase4b_records_no_update
BEFORE UPDATE ON phase4b_records
BEGIN
    SELECT RAISE(ABORT, 'phase4b_records are append-only');
END;

CREATE TRIGGER phase4b_records_no_delete
BEFORE DELETE ON phase4b_records
BEGIN
    SELECT RAISE(ABORT, 'phase4b_records are append-only');
END;

CREATE TRIGGER phase4b_events_no_update
BEFORE UPDATE ON phase4b_events
BEGIN
    SELECT RAISE(ABORT, 'phase4b_events are append-only');
END;

CREATE TRIGGER phase4b_events_no_delete
BEFORE DELETE ON phase4b_events
BEGIN
    SELECT RAISE(ABORT, 'phase4b_events are append-only');
END;
