CREATE TABLE formal_check_attempts (
    finding_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request_byte_length INTEGER NOT NULL CHECK(request_byte_length >= 0),
    request_canonical_json TEXT,
    request_retained_utf8 TEXT NOT NULL,
    request_truncated INTEGER NOT NULL CHECK(request_truncated IN (0,1)),
    outcome TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK(disposition = 'proposal'),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE formal_check_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    finding_id TEXT NOT NULL REFERENCES formal_check_attempts(finding_id),
    event_type TEXT NOT NULL CHECK(event_type = 'formal_check_recorded'),
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE INDEX formal_check_attempts_outcome_idx
ON formal_check_attempts(outcome, finding_id);
