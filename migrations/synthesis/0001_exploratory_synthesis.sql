CREATE TABLE synthesis_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.synthesis-record.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    operational_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE synthesis_verified_exports (
    content_hash TEXT PRIMARY KEY,
    canonical_json BLOB NOT NULL
);

CREATE TABLE synthesis_admission_projection (
    subject_id TEXT PRIMARY KEY,
    subject_kind TEXT NOT NULL CHECK(subject_kind IN ('structured_result','result_relation','composition')),
    current_admission TEXT NOT NULL CHECK(current_admission IN ('proposed','admitted_under_policy','excluded_under_policy','invalidated_by_later_record')),
    admission_record_id TEXT NOT NULL REFERENCES synthesis_records(record_id),
    influence_closure_id TEXT NOT NULL,
    latest_invalidation_id TEXT
);

CREATE INDEX synthesis_records_subject_type_idx
ON synthesis_records(subject_id, record_type, sequence);
