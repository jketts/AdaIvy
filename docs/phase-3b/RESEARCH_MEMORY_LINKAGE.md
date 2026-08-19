# Future Formal-Result Linkage Design

Status: design only; no entity, schema, migration, or repository code created

A future formal obligation record should reference, without embedding mutable
trust projections:

- `claim_id`;
- ordered `evidence_unit_ids` from Phase 3A where relevant;
- exact theorem statement bytes and hash;
- formal language and backend (`lean4`, backend policy/version);
- submitted source/proof artifact hash;
- generated trusted-wrapper hash;
- toolchain-manifest and Lake-lock hashes;
- import-allowlist and sandbox-policy hashes;
- deterministic checker-invocation hash;
- sorted axiom-dependency set;
- terminal result classification;
- stdout/stderr hashes, byte lengths, and bounded retained artifacts;
- checker event IDs and idempotency key; and
- semantic-alignment and representation-bridge obligation IDs.

The formal-check record is append-only. Imported/model-created proof text enters
as a proposal. The workflow engine, not Lean or a model, requests checking and
commits the resulting finding. Domain policy alone may later create a narrowly
scoped warrant.

Formal checking establishes the encoded theorem relative to its imports and
axioms. It does not show that:

- the theorem faithfully represents the researcher-approved informal target;
- evidence units entail the premises;
- source hypotheses and definitions apply;
- a representation map preserves edge cases;
- the result is novel or significant; or
- a particular human/model/tool deserves a contribution claim.

Those remain orthogonal records and open review obligations. A future production
schema requires its own ADR, backward-compatibility tests, and explicit mapping
to the existing Phase 1 and Phase 3A interchange contracts.
