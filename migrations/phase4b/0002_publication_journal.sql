CREATE TABLE phase4b_pending_publications (
    source_id TEXT PRIMARY KEY,
    artifact_hash TEXT NOT NULL,
    content_object_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

