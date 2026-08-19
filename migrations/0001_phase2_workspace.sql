CREATE TABLE dossiers (
    dossier_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE budgets (
    budget_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    max_input_tokens INTEGER NOT NULL CHECK(max_input_tokens >= 0),
    max_output_tokens INTEGER NOT NULL CHECK(max_output_tokens >= 0),
    max_cost_microusd INTEGER NOT NULL CHECK(max_cost_microusd >= 0),
    max_wall_milliseconds INTEGER NOT NULL CHECK(max_wall_milliseconds >= 0),
    max_attempts INTEGER NOT NULL CHECK(max_attempts >= 0),
    used_input_tokens INTEGER NOT NULL DEFAULT 0,
    used_output_tokens INTEGER NOT NULL DEFAULT 0,
    used_cost_microusd INTEGER NOT NULL DEFAULT 0,
    used_attempts INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    dossier_id TEXT NOT NULL REFERENCES dossiers(dossier_id),
    dossier_hash TEXT NOT NULL,
    budget_id TEXT NOT NULL REFERENCES budgets(budget_id),
    status TEXT NOT NULL CHECK(status IN ('queued','running','paused','awaiting_review','unresolved','cancelled','completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','retryable','succeeded','failed','cancelled','timed_out')),
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    deadline_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_until TEXT,
    result_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE semantic_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE proposals (
    proposal_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    proposal_kind TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_claim_id TEXT,
    disposition TEXT NOT NULL CHECK(disposition = 'proposal'),
    created_at TEXT NOT NULL,
    UNIQUE(run_id, artifact_hash, proposal_kind)
);

CREATE TABLE verifier_manifests (
    manifest_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    canonical_json TEXT NOT NULL,
    serialized_context_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    purpose TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    result_hash TEXT,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_microusd INTEGER NOT NULL,
    retry_classification TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

