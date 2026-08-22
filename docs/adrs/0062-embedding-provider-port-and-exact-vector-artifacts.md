# ADR-0062: Embedding provider port and exact content-hashed vector artifacts

- **Status:** proposed; second of three slices. Requires ADR-0061's processor-bound
  rights decision. Produces no retrieval change on its own.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 12.2.1 (provider binding for vector
  projections); Section 12.2 (derived indexes are rebuildable projections);
  Section 2 C7 (reproducibility); ADR-0030 (multi-provider gateways); ADR-0008
  (pinned pricing snapshots)
- **Decision owners:** repository owner and researcher

## Context

Section 12.2.1 imposes four obligations on any vector projection. Quoted:

> "A vector index is partitioned by the tuple `(provider, model_identifier,
> dimension, normalization)`. A query vector is only ever compared against
> vectors in its own partition. There is no default or fallback partition."
> (`TECHNICAL_BLUEPRINT.md:1661-1663`)

> "Changing the embedding provider or model is a full rebuild of the affected
> projection, never an incremental or mixed backfill." (`:1664-1666`)

> "A remote embedding API is not bit-reproducible, and providers reversion models
> behind stable aliases. To satisfy a deterministic-rebuild gate, produced
> vectors are stored as immutable content-hashed artifacts whose bytes are bound
> into canonical identity. A rebuild replays those artifacts and does not call
> the provider again." (`:1667-1671`)

> "Each provider carries its own pinned pricing snapshot. Embedding models are
> input-token-only, which the general request/response cost shape does not
> express." (`:1676-1678`)

Two independent constraints turn out to demand the same architecture, which is
the main finding behind this ADR.

The blueprint wants replay-from-bytes because a remote API is not
bit-reproducible. Phase 4C's acceptance path independently forbids the live call
outright: `tests/test_phase4c_hybrid_retrieval.py` monkey-patches
`socket.socket` and `socket.getaddrinfo` to raise during a real
`evaluate_hybrid()` call, gates `external_spend_usd` at *exactly* zero, sweeps
every module in `phase4c/` against a literal stdlib import allowlist, and bans
the substrings `socket`, `urllib`, `http`, `requests` from module text. So the
retrieval side can only ever see replayed bytes. **Embedding is an ingestion-time
act, retrieval is a read over frozen artifacts, and the two never share a
process.** Everything below follows from that split.

A third constraint comes from this repository rather than the blueprint: the
owner rejects floating-point numerics on a trust path, and ADR-0035 records that
no solver, interval, or residual-reconstruction path exists. A cosine similarity
computed in IEEE-754 doubles is deterministic for a fixed summation order, so it
would pass the hash-seed and cross-process tests -- but every ranking comparison
would sit on machine noise, and a tie at the boundary would be undecidable in
exactly the way `exact_graph` refuses to be.

### Why `ModelGateway` cannot carry this

The existing port is chat-completion-shaped end to end.
`ModelRequest.response_schema` is mandatory (`records.py:165-179`) and exists to
negotiate a JSON-Schema-constrained response; `validate_structured_output`
recognises only `purpose in {"proposer", "verifier"}` and raises otherwise
(`model_gateway.py:83`); `ModelResult.structured_output` is a JSON string, which
cannot hold a vector. `LiveRunConfiguration` requires
`per_call_output_token_reserve > 0` (`live_config.py:138`), `preflight_live_gate`
checks a two-call output budget (`live_gate.py:164`), and `execute_live_gate`
asserts exactly two calls with `total_tokens > 0` (`live_gate.py:248`). An
input-only single call violates all four. The Bedrock adapter already
fail-closes against embedding model ids by prefix
(`bedrock_gateway.py:640-658`), which is the existing code agreeing with this
reading.

## Options considered

| Option | Evidence | Benefits | Cost/risk | Decision |
|---|---|---|---|---|
| Route embeddings through `ModelGateway` | one port to maintain | no new protocol | requires a fake `response_schema`, a fake output-token reserve, and a `structured_output` string holding a vector; defeats four validators by lying to each | Rejected |
| Live embedding call inside the retrieval path | simplest data flow | no artifact store | violates §12.2.1's replay rule and every Phase 4C network/spend/stdlib gate simultaneously | Rejected |
| Float vectors, float cosine, fixed summation order | IEEE-754 is deterministic for `+ * sqrt` | matches provider output exactly; no quantization decision | every ranking comparison rests on machine noise; a boundary tie is undecidable; contradicts the standing exactness rule | Rejected |
| Sibling `EmbeddingGateway`; quantize once at ingestion; exact integer similarity over content-hashed artifacts | §12.2.1; `exact_graph` precedent; `estimate_cost_microusd` already accepts `output_tokens=0` | replay is byte-exact; similarity and ties are exactly decidable; retrieval needs no network, so every Phase 4C gate survives untouched; quantization is *recorded in the partition key* the blueprint already requires | **Selected** |

## Decision

Add `src/math_research/embedding/` containing a sibling provider port, an exact
vector representation, and a partitioned content-hashed artifact store. Add no
retrieval behaviour.

### The port

```
class EmbeddingGateway(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
```

`EmbeddingRequest` carries the text, the `processor_id`, and a token bound.
`EmbeddingResult` carries the raw provider coordinates, the reported input token
usage, the provider request id, and `output_tokens = 0` as a stated constant
rather than an accident. `EmbeddingRunConfiguration` is a new content-hashed
record with an input-only budget: no output-token reserve, no two-call
assumption. `PricingSnapshot` is reused unchanged with
`output_microusd_per_million_tokens = 0` -- `pricing.py:141-142` already permits
zero and `estimate_cost_microusd` (`pricing.py:114-121`) already zeroes the term,
so this is the one place the existing cost shape does fit.

Credential resolution, `provider_secret_variables`, `redact_secrets`,
`scan_persisted_secret`, and the SDK pin/version-probe machinery are reused from
`phase2/` rather than reimplemented. Both providers with working credentials
(`openai`, `azure_openai`) reach embeddings through the `openai` SDK, which is
already declared in `GATED_DYNAMIC_IMPORTS`, so **no new gated-import
declaration is required** and `tests/test_repository_invariants.py` needs no
exception.

### Exact vectors

A provider returns floats. Those floats are converted **once, at ingestion**, to
exact integers by round-half-even scaling at a declared power of two, and the
integers are what the artifact stores. No float is retained, and no float is
ever constructed in the retrieval path.

Similarity is then exact. For integer vectors `u`, `v` at a common scale,
ranking by cosine is ranking by `(u.v)^2 * sign` against `|u|^2 * |v|^2`, all in
`int`; the comparison of two candidates' cosines is a cross-multiplication of
integers. There is no square root, no division, and no epsilon. Two candidates
whose exact cosines are equal are ordered by `document_id` ascending, matching
the tie-break already used at `fusion.py:204` and `lexical.py:42`.

The quantization scheme is not a free parameter hidden in code: it is the
`normalization` component of the partition tuple the blueprint already requires.
A change of scale is a change of partition, and therefore a full rebuild.

### Partitioning and the artifact store

The partition key is exactly `(provider, model_identifier, dimension,
normalization)`. Enforced properties:

- A similarity call whose two operands carry different partition keys raises.
  There is no default partition, no fallback, and no coercion.
- An artifact is immutable and content-hashed; writing a different body to an
  existing artifact path is refused, following `write_recheck`'s
  overwrite-refusal precedent at `novelty.py:395-404`.
- A partition manifest binds the partition key, every artifact hash, and the
  source `content_hash` each vector was derived from, so canonical identity
  includes the vector bytes as `:1667-1671` requires.
- A rebuild replays the manifest. The provider is not called, and a rebuild that
  cannot find an artifact fails closed rather than re-embedding.
- Changing provider, model, dimension, or normalization produces a *new*
  partition. There is no code path that backfills or merges one partition into
  another; the absence is the enforcement.

### Rights

No text is sent to a provider without an ADR-0061 rights decision that is live at
the moment of the call and names the exact `processor_id` being called.
`require_rights(source_id, RightsUse.EMBEDDING, processor_id=..., at=...)` is
called before the text is read from disk, following the ordering already used at
`service.py:185`. A missing, expired, revoked, or differently-addressed decision
raises `RightsBlocked` and no call is made.

### Named boundaries

- **Ingestion and retrieval never share a process.** The live path is a separate
  CLI verb requiring `--execute` and an exact acknowledgement string. The
  retrieval path reads artifacts and has no provider, no credential, and no
  network surface.
- **A vector is not evidence.** An artifact records that a text was embedded by a
  named processor. It creates no applicability record, no premise, no graph
  admission, and no warrant. `NOVELTY_LANDSCAPE.md:62-64` -- "A retrieval hit is
  therefore not a theorem dependency" -- is the governing reading.
- **Quantization is lossy and is recorded as such.** The artifact stores the
  scale and the count of coordinates that saturated, if any. A saturating
  coordinate is a fault, not a rounding detail, and halts ingestion.
- **Cost is measured, not estimated after the fact.** Reported input tokens,
  the pinned snapshot, and the derived cost close into the ingestion record.

## What this decision does not license

No retrieval change: Phase 4C is untouched by this slice and its seven gates,
report hashes, and fixture cardinalities are unmodified. No corpus expansion, no
acquisition, no crawling, no citation traversal, no query generation. No second
embedding provider without its own ADR-0061 decision. No novelty, significance,
or applicability assessment, no mathematical warrant, no graph admission. An
artifact store full of vectors is not a literature search and must not be
reported as one.

## Consequences

- One new sub-package, one new CLI module, one new offline `make` target. `make
  check` gains the offline replay path only; the live path is a separate named
  target requiring credentials, as `check-sealed` and `check-typeset` already are.
- Ingestion is billable and irreversible in the sense that a provider has seen
  the text. This is why ADR-0061 precedes it and why the acknowledgement string
  is exact.
- Artifacts are durable bytes under `reports/`-style evidence rules, not `work/`
  scratch, because a rebuild depends on them. They are content-addressed, so a
  corrupted artifact is detectable rather than silently wrong.
- Quantization means the stored vector is not the provider's vector. Any future
  comparison against a provider-side similarity score will differ, and that is
  expected rather than a defect.

## Blueprint deviation

None. Section 12.2.1 is implemented as written, including the clause that a
rebuild must not re-call the provider. The exact-integer representation is
stricter than the blueprint requires and is recorded here so it is not mistaken
for a provider-fidelity claim.

## Falsifiability probes

`probes_flipped == probes_total` gates the slice.

- `pr.cross-partition-similarity-refused` -- comparing vectors whose
  `model_identifier` differs must raise, not return a number.
- `pr.dimension-mismatch-refused` -- same provider and model, different
  dimension, must raise.
- `pr.normalization-mismatch-refused` -- same provider, model, and dimension,
  different quantization scale, must raise. This is the probe that proves
  `normalization` is really in the key.
- `pr.no-fallback-partition` -- a query against an absent partition must fail
  closed, never fall back to another partition.
- `pr.rebuild-makes-no-provider-call` -- a rebuild with a gateway that raises on
  any call must still reproduce the manifest hash exactly.
- `pr.missing-artifact-fails-closed` -- a rebuild with one artifact removed must
  fail, not re-embed.
- `pr.artifact-overwrite-refused` -- writing different bytes to an existing
  artifact path must refuse.
- `pr.embedding-without-rights-refused` -- ingestion with no live ADR-0061
  decision must raise `RightsBlocked` before the source file is opened.
- `pr.embedding-wrong-processor-refused` -- a decision naming processor A must
  not authorize a call to processor B.
- `pr.no-float-in-retrieval-path` -- an AST sweep of the retrieval modules must
  find no `float` construction and no division on the similarity path.
- `pr.saturating-coordinate-halts` -- a coordinate exceeding the declared scale
  must halt ingestion rather than clamp.
- `pr.tie-broken-by-document-id` -- two exactly-equal cosines must order by
  `document_id` ascending, deterministically across hash seeds.
- `pr.output-tokens-are-zero` -- an ingestion record claiming nonzero output
  tokens must refuse.

## Validation and revisit trigger

Valid while: the partition tuple stays exactly the blueprint's four components;
retrieval constructs no float and makes no call; rebuild replays bytes; every
ingestion is preceded by a processor-matched rights check; every probe flips.

Reconsider if a provider ships a model whose coordinates cannot be represented
at the declared scale without saturation -- that is a new partition and possibly
a new scale, not a clamp.

Revisit with a new ADR before: adding a second embedding provider; introducing
approximate nearest-neighbour search, which trades exactness for speed and would
reintroduce every problem this ADR closes; caching a query vector across
partitions; or letting a retrieval process hold a credential.

## Explicit deferrals

- The Phase 4C semantic signal and any fusion change: ADR-0063.
- Corpus ingestion beyond the frozen fixture set: ADR-0063's context; this is
  the actual limit on "wide" retrieval and no amount of embedding fixes it.
- Approximate nearest neighbour, dimensionality reduction, and any index
  structure beyond linear exact scan over a partition: not needed at fixture
  scale, and each would need its own exactness argument.
- Deletion of vectors whose rights decision was later revoked: ADR-0021
  question, open.
