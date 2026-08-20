CREATE TABLE phase4b_replay_artifacts (
    artifact_id TEXT PRIMARY KEY,
    owner_record_id TEXT NOT NULL REFERENCES phase4b_records(record_id),
    artifact_type TEXT NOT NULL CHECK(artifact_type IN ('acquisition_attempt_trace','parse_proposal')),
    schema_version TEXT NOT NULL CHECK(schema_version = 'adaivy.phase4b-replay-artifact.v1'),
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 0)
);

CREATE INDEX phase4b_replay_artifacts_owner_idx
ON phase4b_replay_artifacts(owner_record_id, artifact_type);

CREATE TRIGGER phase4b_replay_artifacts_no_update
BEFORE UPDATE ON phase4b_replay_artifacts
BEGIN
    SELECT RAISE(ABORT, 'phase4b_replay_artifacts are append-only');
END;

CREATE TRIGGER phase4b_replay_artifacts_no_delete
BEFORE DELETE ON phase4b_replay_artifacts
BEGIN
    SELECT RAISE(ABORT, 'phase4b_replay_artifacts are append-only');
END;
