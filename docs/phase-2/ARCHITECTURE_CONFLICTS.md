# Phase 2 Architecture Conflicts and Resolutions

Date: 2026-08-19

| Existing state or conflict | Phase 2 resolution | Trust impact | ADR |
|---|---|---|---|
| Repository instructions still identified Phase 1 and prohibited databases and model calls. | Advance the repository instructions only to the explicitly requested Phase 2 boundary. | None; Phase 1 rules remain compatibility gates. | ADR-0006 |
| The blueprint's production default is PostgreSQL, while this bounded local phase needs only one transactional adapter. | Use SQLite with WAL, foreign keys, explicit transactions, and versioned migrations behind ports. | None; canonical entities remain persistence-independent. | ADR-0006 |
| No persistence, artifact, or model-gateway ports exist yet. | Add inward-facing protocols and outward adapters without imports from the Phase 1 domain into adapter-specific packages. | Preserves dependency direction. | ADR-0006 and ADR-0007 |
| Phase 1 `VerificationRecord.independent_from_proposer` is a single historical boolean; Phase 2 requires seven independent dimensions. | Preserve the Phase 1 field and add a Phase 2 `VerifierIndependence` record plus manifest. Never reinterpret the boolean as provider or full independence. | Avoids silently changing Phase 1 meaning. | ADR-0007 |
| The Phase 1 demonstration dossier contains a resolved theorem, but the baseline loop needs an honest unresolved target. | Create a separate Phase 2 accepted-state fixture with the same immutable entity vocabulary and an open obligation; do not mutate the Phase 1 fixture. | Prevents a model loop from overwriting trusted history. | ADR-0007 |
| The architecture anticipates a real provider but no provider credentials or SDK dependency are guaranteed. | Provide an opt-in standard-library OpenAI Responses adapter selected by environment configuration; keep all tests on the deterministic gateway. Record the live gate as blocked when credentials are absent. | Provider output remains proposal-only. | ADR-0007 |
| The first live failure showed that the standard-library transport discarded supported failure diagnostics and conflated canonical and provider schemas. | Use the pinned optional SDK at the adapter boundary and deterministically project into the provider subset. | Canonical validation and proposal-only import remain mandatory. | ADR-0010 |
| The v2 provider schema rejected type-less scalar const/enum terminals. | Add deterministic provider-only terminal type inference and fail-closed recursive linting. | Canonical schema bytes and trust semantics remain unchanged. | ADR-0011 |

No Phase 1 trust-policy rule is revised. Any later need to promote verifier
findings, add PostgreSQL, or replace the provider transport requires a new ADR.
