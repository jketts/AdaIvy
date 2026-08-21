CREATE TABLE review_decisions (
    decision_id TEXT PRIMARY KEY,
    decision_kind TEXT NOT NULL CHECK(decision_kind IN (
        'review_verdict','semantic_alignment_decision','warrant_grant','obligation_discharge'
    )),
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.review-decision.v1'),
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    reviewer_id TEXT NOT NULL,
    reviewer_kind TEXT NOT NULL CHECK(reviewer_kind = 'human'),
    idempotency_key TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL UNIQUE,
    operational_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE review_refusals (
    refusal_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.review-refusal.v1'),
    code TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0),
    content_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX review_decisions_subject_idx
ON review_decisions(subject_id, decision_kind, sequence);

CREATE INDEX review_refusals_subject_idx
ON review_refusals(subject_id, code, sequence);
