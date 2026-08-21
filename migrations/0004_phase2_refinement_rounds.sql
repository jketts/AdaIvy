-- adaivy-migration: rebuild-tables
--
-- ADR-0041 bounded refinement rounds, plus the per-role model boundary the same
-- ADR needs for measured verifier independence.
--
-- The directive on line 1 is read by SQLiteWorkspace._migrate. It runs this
-- file with foreign keys off and legacy_alter_table on, which is the only way
-- SQLite can widen a CHECK constraint on a table other tables reference, and
-- then verifies PRAGMA foreign_key_check afterwards. Nothing else in this
-- repository is permitted to disable foreign keys.

ALTER TABLE budgets ADD COLUMN max_refinement_rounds INTEGER NOT NULL DEFAULT 1 CHECK(max_refinement_rounds >= 1);
ALTER TABLE budgets ADD COLUMN used_refinement_rounds INTEGER NOT NULL DEFAULT 0 CHECK(used_refinement_rounds >= 0);

ALTER TABLE jobs ADD COLUMN round_index INTEGER NOT NULL DEFAULT 1 CHECK(round_index >= 1);

CREATE TABLE runs_adr0041 (
    run_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    dossier_id TEXT NOT NULL REFERENCES dossiers(dossier_id),
    dossier_hash TEXT NOT NULL,
    budget_id TEXT NOT NULL REFERENCES budgets(budget_id),
    status TEXT NOT NULL CHECK(status IN ('queued','running','paused','awaiting_review','unresolved','cancelled','completed','refinement_exhausted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO runs_adr0041(run_id,schema_version,dossier_id,dossier_hash,budget_id,status,created_at,updated_at)
    SELECT run_id,schema_version,dossier_id,dossier_hash,budget_id,status,created_at,updated_at FROM runs;

DROP TABLE runs;

ALTER TABLE runs_adr0041 RENAME TO runs;

CREATE TABLE verifier_manifests_adr0041 (
    manifest_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    round_index INTEGER NOT NULL CHECK(round_index >= 1),
    canonical_json TEXT NOT NULL,
    serialized_context_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, round_index)
);

INSERT INTO verifier_manifests_adr0041(manifest_id,schema_version,run_id,round_index,canonical_json,serialized_context_hash,created_at)
    SELECT manifest_id,schema_version,run_id,1,canonical_json,serialized_context_hash,created_at FROM verifier_manifests;

DROP TABLE verifier_manifests;

ALTER TABLE verifier_manifests_adr0041 RENAME TO verifier_manifests;

CREATE TABLE live_run_configurations_adr0041 (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    role TEXT NOT NULL CHECK(role IN ('proposer','verifier')),
    configuration_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    pricing_snapshot_id TEXT NOT NULL REFERENCES pricing_snapshots(snapshot_id),
    content_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, role)
);

INSERT INTO live_run_configurations_adr0041(run_id,role,configuration_id,schema_version,provider,model_identifier,pricing_snapshot_id,content_hash,canonical_json,created_at)
    SELECT run_id,'proposer',configuration_id,schema_version,provider,model_identifier,pricing_snapshot_id,content_hash,canonical_json,created_at FROM live_run_configurations;

DROP TABLE live_run_configurations;

ALTER TABLE live_run_configurations_adr0041 RENAME TO live_run_configurations;

CREATE TABLE refinement_rounds (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    round_index INTEGER NOT NULL CHECK(round_index >= 1),
    schema_version TEXT NOT NULL,
    candidate_artifact_hash TEXT NOT NULL,
    finding_artifact_hash TEXT NOT NULL,
    outcome_class TEXT NOT NULL CHECK(outcome_class IN ('supporting','refuting','defective','indeterminate')),
    result_type TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    refinement_warranted INTEGER NOT NULL CHECK(refinement_warranted IN (0,1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, round_index)
);

CREATE TABLE run_stop_records (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    schema_version TEXT NOT NULL,
    terminal_status TEXT NOT NULL,
    stop_reason TEXT NOT NULL CHECK(stop_reason IN ('no_refinement_warranted','refinement_round_cap','budget_bound','non_success')),
    stop_bound TEXT,
    binding_bounds_json TEXT NOT NULL,
    rounds_used INTEGER NOT NULL CHECK(rounds_used >= 0),
    max_refinement_rounds INTEGER NOT NULL CHECK(max_refinement_rounds >= 1),
    created_at TEXT NOT NULL
);

CREATE INDEX jobs_round_idx ON jobs(run_id, kind, round_index, status);

CREATE INDEX refinement_rounds_run_idx ON refinement_rounds(run_id, round_index);

CREATE INDEX verifier_manifests_run_idx ON verifier_manifests(run_id, round_index)
