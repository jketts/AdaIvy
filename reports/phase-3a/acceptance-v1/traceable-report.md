# Phase 3A Traceable Research-Memory Report

Schema version: `1.0.0`
Aggregate ID: `memory.phase3a.synthetic.v1`

## Acceptance result

Status: **passed**
Network/model/external API calls: **0**
Recall@5: `1.0` (required `1.0`)
MRR: `1.0` (required `>= 0.75`)
Citation resolution precision: `1.0` (required `1.0`)
Quarantined evidence retrieved: `0` (required `0`)
Repeated/restart ordering stable: `true`

## Canonical hashes

- `corpus_index_manifest_hash`: `sha256:473dadcf3f48cf4aa61e443e74dd9a9600708d712046341a8705b8d5a8e2473d`
- `event_replay_hash`: `sha256:66998142ca524886b021958c54a80cfbb77002ce1035892f4c26ea54ba362e6c`
- `evidence_manifest_hash`: `sha256:d7541ba0952407d1248b8d01ca177ebffdb95c83e8cbe02f776c84dbd73686b3`
- `evidence_pack_manifest_hash`: `sha256:0586e955336e2e7322168f784662ac5beafaaac26259e07933c1af1deb7b5631`
- `research_memory_export_hash`: `sha256:99891f3b0acd8493adae7976caad8d493995adf2c68522bca2e8da6845e21e4c`
- `retrieval_manifest_hash`: `sha256:fe5e9da683bd1c858cee102306a6818f245760ff02575471d49ec08bd3092ae1`
- `source_manifest_hash`: `sha256:8a1be7f6009b5fded8b7dc37adf473030115c73f5ef9c8f05f9675959e986d8e`

## Quarantine and licensing

- `contradictory`: `{"artifact_id":"artifact.cd50a003848c060749fcaceb","quarantined":false,"reasons":[]}`
- `malformed`: `{"artifact_id":"artifact.ce19fe8df2158532ec2df55d","quarantined":true,"reasons":["pdf_unsupported","unsupported_declared_media_type","unsupported_file_extension"]}`
- `primary`: `{"artifact_id":"artifact.f561fe3d16db4b0be1b26727","quarantined":false,"reasons":[]}`
- `prompt_injection`: `{"artifact_id":"artifact.54d9ff97c89131cf1a828aad","quarantined":true,"reasons":["prompt_injection"]}`
- `related`: `{"artifact_id":"artifact.d66ab4323f57bab804953aeb","quarantined":false,"reasons":[]}`

The indexed corpus consists only of project-authored synthetic UTF-8 plain-text fixtures with explicit local retrieval and evidence-pack rights.
The malformed PDF-shaped fixture and prompt-injection fixture remain immutable quarantined artifacts and produced no evidence units.
The quantum-state-discrimination paper is an unresolved metadata-only locator with a null content hash; no paper bytes or extracted text are present.

## Trust boundary

Parser-derived evidence and scripted model-shaped claims remain proposals. Citation validation establishes exact pack membership only; it creates no warrant, closes no obligation, and does not establish applicability.

## Scope stop

No crawler, DNS/HTTP operation, embeddings, PDF extraction, model provider, external API, formal tool, Phase 3B feature, Phase 4 feature, or quantum convergence solver was invoked.
