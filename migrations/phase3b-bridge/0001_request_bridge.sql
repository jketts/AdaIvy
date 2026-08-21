CREATE TABLE bridged_requests (
    bridge_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_type TEXT NOT NULL CHECK(record_type = 'phase3b_bridged_request'),
    hash_profile TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_bytes_hash TEXT NOT NULL,
    request_canonical_hash TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    semantic_alignment_id TEXT,
    lean_source_kind TEXT NOT NULL CHECK(lean_source_kind IN ('operator','model')),
    phase2_run_id TEXT NOT NULL,
    phase2_dossier_id TEXT NOT NULL,
    phase2_dossier_hash TEXT NOT NULL,
    phase2_proposal_id TEXT NOT NULL,
    phase2_artifact_hash TEXT NOT NULL,
    phase2_model_call_id TEXT,
    phase2_payload_hash TEXT NOT NULL,
    bridge_correspondence_check TEXT NOT NULL
        CHECK(bridge_correspondence_check = 'none_performed_by_bridge'),
    correspondence_state_at_build TEXT NOT NULL
        CHECK(correspondence_state_at_build = 'unattested_operator_correspondence'),
    disposition TEXT NOT NULL CHECK(disposition = 'proposal'),
    trust_effect TEXT NOT NULL CHECK(trust_effect = 'none'),
    content_hash TEXT NOT NULL UNIQUE,
    operational_hash TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    request_canonical_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE bridge_correspondence_attestations (
    attestation_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_type TEXT NOT NULL
        CHECK(record_type = 'phase3b_bridge_correspondence_attestation'),
    hash_profile TEXT NOT NULL,
    bridge_id TEXT NOT NULL REFERENCES bridged_requests(bridge_id),
    request_canonical_hash TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    attester_id TEXT NOT NULL CHECK(length(attester_id) > 0),
    attester_role TEXT NOT NULL CHECK(attester_role = 'operator'),
    basis TEXT NOT NULL CHECK(basis = 'human_reading'),
    bridge_correspondence_check TEXT NOT NULL
        CHECK(bridge_correspondence_check = 'none_performed_by_bridge'),
    correspondence_state TEXT NOT NULL
        CHECK(correspondence_state = 'operator_asserted_correspondence'),
    phase2_payload_hash TEXT NOT NULL,
    target_statement_hash TEXT NOT NULL,
    proof_fragment_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    canonical_json TEXT NOT NULL,
    attested_at TEXT NOT NULL
);

CREATE TABLE bridge_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    bridge_id TEXT NOT NULL REFERENCES bridged_requests(bridge_id),
    event_type TEXT NOT NULL
        CHECK(event_type IN ('bridged_request_recorded','correspondence_attested')),
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE INDEX bridged_requests_request_bytes_hash_idx
ON bridged_requests(request_bytes_hash, bridge_id);

CREATE INDEX bridged_requests_request_canonical_hash_idx
ON bridged_requests(request_canonical_hash, bridge_id);

CREATE INDEX bridged_requests_request_id_idx
ON bridged_requests(request_id, bridge_id);

CREATE INDEX bridge_correspondence_attestations_bridge_idx
ON bridge_correspondence_attestations(bridge_id, attestation_id);
