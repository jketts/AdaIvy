CREATE TABLE research_memory_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    disposition TEXT,
    source_artifact_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(record_type, canonical_hash)
);

CREATE TABLE research_memory_commands (
    command_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','cancelled','timed_out')),
    attempts INTEGER NOT NULL CHECK(attempts >= 0),
    max_attempts INTEGER NOT NULL CHECK(max_attempts > 0),
    deadline_at TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE research_memory_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE research_memory_import_proposals (
    proposal_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    package_hash TEXT NOT NULL UNIQUE,
    source_label TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK(disposition = 'proposal'),
    canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE evidence_fts USING fts5(
    evidence_unit_id UNINDEXED,
    source_artifact_id UNINDEXED,
    normalized_start UNINDEXED,
    title,
    body,
    unit_type,
    tokenize='unicode61 remove_diacritics 0'
);

CREATE INDEX research_memory_records_type_idx
ON research_memory_records(record_type, record_id);

CREATE INDEX research_memory_records_source_idx
ON research_memory_records(source_artifact_id, record_type);

CREATE INDEX research_memory_events_aggregate_idx
ON research_memory_events(aggregate_id, sequence);
