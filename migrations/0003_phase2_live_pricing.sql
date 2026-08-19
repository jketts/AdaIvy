CREATE TABLE pricing_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    currency TEXT NOT NULL,
    units TEXT NOT NULL,
    input_microusd_per_million_tokens INTEGER NOT NULL CHECK(input_microusd_per_million_tokens >= 0),
    output_microusd_per_million_tokens INTEGER NOT NULL CHECK(output_microusd_per_million_tokens >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE live_run_configurations (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    configuration_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    pricing_snapshot_id TEXT NOT NULL REFERENCES pricing_snapshots(snapshot_id),
    content_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE cost_estimates (
    estimate_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    call_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    pricing_snapshot_id TEXT NOT NULL REFERENCES pricing_snapshots(snapshot_id),
    input_token_estimate INTEGER NOT NULL CHECK(input_token_estimate >= 0),
    output_token_estimate INTEGER NOT NULL CHECK(output_token_estimate >= 0),
    estimated_cost_microusd INTEGER NOT NULL CHECK(estimated_cost_microusd >= 0),
    created_at TEXT NOT NULL
);

ALTER TABLE model_calls ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE model_calls ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE model_calls ADD COLUMN estimated_cost_microusd INTEGER;
ALTER TABLE model_calls ADD COLUMN pricing_snapshot_id TEXT REFERENCES pricing_snapshots(snapshot_id);
ALTER TABLE model_calls ADD COLUMN provider_request_id TEXT;
ALTER TABLE model_calls ADD COLUMN incomplete_reason TEXT;

CREATE INDEX cost_estimates_run_idx ON cost_estimates(run_id, call_id);
