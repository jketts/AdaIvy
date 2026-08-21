# Repository Instructions

This repository implements the architecture in `README.md`,
`TECHNICAL_BLUEPRINT.md`, and `NOVELTY_LANDSCAPE.md`. Read all three plus the
current ADRs before changing architecture or phase scope.

## Current phase

Bounded Phase 4B authorized acquisition and exact-source parsing (ADR-0028) is
the current work. Its offline acquisition, persistence, deletion, replay,
strict HTML/TeX/PDF candidates, and exact Linux/arm64 OCI parser gate are
implemented. The digest-pinned OCI gate reproduces all twelve parser fixtures
with zero false admissions and demonstrates kernel memory, CPU, process, file,
network-none, read-only-root, noexec-temp, and ambient-secret controls. Network
remains off by default. The separately acknowledged live HTTPS gate is the
final activation step; its absence must never be counted as a pass.

Phases 0 through 6 remain implemented and authoritative. Phase 5 now has three
scopes and all must be stated exactly. The sealed scope is exact
scalar/diagonal `QD-FS-01`: commuting cases, computed results, deterministic
tier-0 branches. The noncommuting scope (ADR-0035) **verifies certificates
supplied to it and never discovers them**, so it is a checker and not a solver.
ADR-0049 adds a separate bounded exact solver for exactly two outcomes in
dimension two over one measured `Q(sqrt(d))(i)` field. It constructs a candidate
and submits it to the ADR-0035 verifier; only exact feasibility, zero gap, and
complementarity create the result. The dimension-three irreducible-cubic case
remains explicitly unresolved. Search tiers 2--4 stay disabled. The Phase 6
scope is still one frozen held-out case plus the generality control suite and
canonical replay.

Phase 3B now has two scopes and both must be stated exactly. The sealed
single-shot scope is unchanged. On top of it, ADR-0040 adds a **bounded repair
loop that adds submissions and no Lean capability**: it orchestrates strictly
above `FormalCheckingService.check` and holds no reference to the container
engine, image digest, launcher, fixed invocation, stdin bound, Landlock
hardener, or seccomp policy. Three bounds are load-bearing and must not be
relaxed without a new ADR. The theorem is frozen -- a proposer returns one proof
fragment, so statement, hypotheses, imports, declaration, claim, and meaning
tests cannot change, and a repair therefore cannot weaken what it claims to
prove. Only Lean's own `elaboration_failure` is repairable; a policy rejection
is never fed back, because a validator diagnostic describes how to evade the
validator, and meaning-test failures and unapproved-assumption results are
terminal for the same reason. Nothing is promoted: `epistemic_warrant_created`
is `False` unconditionally, including on a successful repair, and a repaired
proof is attributed to `MODEL` and never to the operator. ADR-0048 supplies an
opt-in Azure OpenAI implementation of the `ProofProposer` port. It requires
explicit live execution, content-hashed bounds, confirmed pricing, the pinned
SDK, and the sealed Lean image. It returns only a proof fragment and records
provider, model, usage, cost, and hashes without retaining secret or proof text
in the public call audit. The offline acceptance path still uses a scripted
proposer and makes zero model and network calls. Nothing yet measures whether
repair improves retained verified progress -- that is an
ADR-0029 retention question and is open. `docs/phase-3b-repair/` is the
normative gate package, per ADR-0026's revisit trigger.

The Phase 6 generality control suite (ADR-0034) executes. Thirteen controls drive
Phase 1 `TrustPolicy`, the exact Phase 5 engine, or the Phase 6 `HeldOutView`
over a content-hashed project-authored manifest whose hash the confirmatory
protocol freezes and verifies before the first durable write. Each control
carries one falsifiability probe -- a named single-field mutation of its own
fixture that must produce the forbidden verdict -- and `probes_flipped ==
controls_total` is a release gate alongside `controls_passed == controls_total`,
because a control that cannot be made to fail proves nothing. Two controls are
positive, so an all-reject system cannot pass. `control_corpus_provenance` is
`project_authored`: the suite demonstrates boundary enforcement on KNOWN traps
and is not evidence of generality against unseen traps, and the
`baseline_comparison` count of enforced boundaries is not a generality rate.
Held-out access and adaptation counts are computed reads of durable
`heldout_access` records, not literals. Novelty and significance remain
`not_assessed`.

ADR-0026 records the accepted delivery order for the remaining work after
Phase 4B: Phase 4C hybrid retrieval, then the noncommuting Phase 5 expansion,
then Phase 6 external evaluation.

Benchmark-scoped Phase 4C hybrid retrieval (ADR-0031, ADR-0032) is implemented
and measures all seven gates as passing on the third fixture extension: 19
documents, 17 queries, six of them applicability. Three offline signals fuse in
score space -- FTS5/BM25, a content-keyed alias table, and an exclusion-only
evidentiary self-disclaimer signal whose cues are composed from two frozen
vocabularies rather than enumerated. ADR-0031's demotion-only rule is withdrawn
as its own recorded error; ADR-0032 replaces it with exclusion under three
invariants (no score changes, retained relative order is preserved, no document
outside the candidate set is named). Exclusion removes a candidate from one
result list and is not an applicability judgement: it creates no premise,
warrant, applicability record, or graph admission, and the excluded document
stays in the report. Document scope is declared valid only where the retrieval
unit is a single-claim unit, so it must be re-derived before any multi-section
parsed unit reuses it. This slice still reads only the frozen Phase 4C fixtures
and adds no embedding, vector, or network surface.

ADR-0033 records the WP4 entry gate for the noncommuting Phase 5 expansion,
measured as a spike. `spikes/phase5_noncommuting_sdp/` now checks supplied
primal/dual certificates exactly over one real quadratic extension of the
rationals per case, `Q(sqrt(d))(i)` with `d` squarefree. The recorded `1/4` gap
on both noncommuting pure-state pairs closes to exactly zero on ensembles that
are byte-identical to the ones that left it open, with no dependency, no float,
and no tolerance. One frozen fixture is a measured boundary: a noncommuting
two-outcome ensemble in dimension three whose difference operator has an
irreducible cubic characteristic polynomial, so its optimum has degree three and
no certificate over any quadratic extension can close it. The spike verifies
certificates; it does not find them, grants no mathematical warrant, does not
integrate with the sealed Phase 5 slice, and does not enable search tiers 2--4.

ADR-0035 promotes that verification into `src/math_research/phase5/` and closes
the solver option the entry gate left live. The production slice admits a
certificate and checks primal feasibility, dual feasibility, and an exactly
closed gap over `Q(sqrt(d))(i)` for one squarefree `d` per case, with the
radicand MEASURED from the case values rather than declared. It contains no
search, no iteration toward an optimum, and no candidate generation, and a case
arriving without a certificate produces an explicit unresolved outcome rather
than an attempt. A certificate is a human input: it enters through the
authorized-human-steering boundary, records its deriving principal, and is
rejected if that principal is missing, nonhuman, or if the derivation declares a
solver, search, interval, or residual-reconstruction origin. No numerical solver
is adopted, now or as a gated adapter, and no interval or
residual-reconstruction path exists.

Read the coverage status before the gap. Every noncommuting result, export
record, and rendered report carries a machine-readable coverage status, and
`optimum_discovered` is named as forbidden and is unproducible. The honest risk
is a coverage illusion: exactly-zero gaps read as "the noncommuting case is
handled" when only two-outcome ensembles whose optimum a human already derived
in closed form are. The slice does not answer general noncommuting JRF
convergence and no report, summary, or status line may imply that it does. The
frozen fixture retains `real-noncommuting-irreducible-cubic-boundary`, a genuine
noncommuting ensemble whose optimum has degree three over `Q`, so the boundary
is visible in every run rather than inferred from an ADR. Outside the field --
two distinct surds, a cubic or higher irreducible extension, a declared
transcendental value, any float or tolerance -- every case is an explicit typed
rejection.

ADR-0036 adds the publication projection in `src/math_research/publication/`.
Results are reported as a content-addressed bundle: the records are the artifact
of record, `paper.tex` is a projection of them, and `paper.pdf` is a build
product of the projection. **Nothing flows back**, and a hand-edited `.tex` is
detectable from `MANIFEST.json`. Four boundaries carry the slice. Every rendered
content block appears in a provenance ledger with at least one resolving record
reference, and `paper.tex` is exactly the frozen template plus the ledger, checked
byte-for-byte. A claim's environment is COMPUTED from its records and never
declared: only a bare `kernel_checked` attestation on a `verified` representation
reaches `Theorem`, approved-standard-axiom outcomes and exact certificates reach
`Proposition`, and everything else reaches `Conjecture`. Demotion is the default
and no manuscript field can promote a claim -- 1,467 single-field mutations were
checked and none produced a theorem. A bibliography entry exists if and only if an
acquisition record with a content hash, an authority and publication rights backs
it; closure runs both ways, a lemma cited at work level rather than at a located
passage is refused, and unrecorded background renders as an OPEN OBLIGATION rather
than a citation. Every LaTeX-bearing field is validated against a frozen macro
allowlist that refuses file input, process output, category-code manipulation and
package loading by class, because LaTeX executes at compile time.

The offline `make publication` target renders the bundle, verifies closure, and
runs seventeen falsifiability probes; `probes_flipped == probes_total` gates it,
because a render rule that cannot be made to fail proves nothing. The fixture
renders ZERO theorems and its status block says so in words, because `make check`
excludes the sealed Lean runtime -- a nonzero theorem count on that path means the
renderer invented one. Typesetting is the separate `make check-typeset` gate:
bounded, offline, `-no-shell-escape`, `SOURCE_DATE_EPOCH` frozen, two clean
compiles that must hash identically, and undefined references or citations are
build failures. Until a compile has run, `typeset_status` stays `not_typeset` and
`pdf_sha256` stays null; its absence must never be counted as a pass. No model may
iterate on a compile error. Rendering is not publication: the bundle carries
`publication_approval: null` and the document prints the absence. Novelty and
significance stay `not_assessed`, and the projection creates no warrant,
applicability record, alignment approval, or graph admission.

ADR-0029 refines the target orchestration architecture without enabling a new
runtime. The baseline is one coherent long-horizon research lead plus a
centralized verifier, with literature, experiments, multiple branches, and
incremental formalization available inside that central loop. Higher search
tiers remain disabled. Bounded specialists require a recorded prediction and
measured retention gain in verified progress per unit cost; evolutionary search
additionally requires cheap reliable verifier-backed fitness and adversarial
calibration. Never substitute an always-on hierarchical swarm.

ADR-0047 activates only the bounded central-lead runtime. It composes distinct
one-round Phase 2 runs, carries a size-bounded proposer-only ledger between
them, and rebuilds the verifier context without that history. Session bounds
are content-hashed, replay is model-free, the target is frozen, and no warrant
or proof-obligation discharge is producible. ADR-0041 refinement is refused
inside an ADR-0047 iteration so the two loops cannot multiply each other's
bounds. The runtime measures no retention gain and activates no specialist,
parallel, evolutionary, or higher search tier.

The Phase 1 domain/trust semantics, sealed Phase 2 evidence, Phase 3A memory,
sealed Phase 3B runtime, and Phase 4A rights/applicability boundaries remain
authoritative. ADR-0048's bounded Azure proposer and ADR-0049's bounded exact
noncommuting solver are the only newly authorized model/solver paths. Do not add
a web UI or HTTP API, crawler, broader network acquisition, embeddings, PDF
parsing, another model/external API path, a broader noncommuting SDP solver,
multi-agent or evolutionary search, automated novelty/significance assessment,
or enable higher search tiers without a later explicit implementation request,
the ADR-0029 activation evidence, and measured cost-adjusted verified gain.

Two capabilities the synthesis slice supplies are boundaries, not fixes, and
must not be assumed to hold elsewhere. `synthesis/applicability.py` resolves the
effective Phase 4A review because Phase 4A itself has no resolver; if Phase 4A
later adopts its own rule the two must be reconciled. The separation-of-duty
check in `synthesis/material.py` applies only to that module's surfacing path,
because sealed Phase 5 accepts an identical originating and creating principal.
Under ADR-0035 that acceptance is now load-bearing rather than merely tolerable:
when one principal derives a noncommuting certificate and the same principal
approves its admission, no independent party stands between the derivation and
the trust record. What contains it is mathematical, not procedural -- a zero-gap
certificate is self-verifying against the ensemble, so a wrong certificate fails
the exact check rather than passing quietly. The procedural gap stays open and
is recorded in every certificate-admission record. Do not close it by inventing
a second-principal requirement; that is a separate decision.

## Engineering rules

- Treat external output as untrusted candidate artifacts.
- Compare every component with the file-based baseline using the same fixture.
- Never turn retrieval, experiments, or model agreement into proof status.
- Preserve failed attempts and missing-tool results in machine-readable output.
- Keep Phase 0 through Phase 6 runnable without network access.
- Pin direct runtime/development dependencies and record licenses before adding
  them. Prefer the standard library for the harness.
- Record any necessary departure from the blueprint in `docs/adrs/`; do not
  silently change the architecture.
- Never let vectors from different providers or different embedding models share
  a similarity space. If a second model provider is admitted, partition any
  vector projection by `(provider, model_identifier, dimension, normalization)`,
  rebuild rather than backfill on a provider or model change, and bind stored
  vector bytes into canonical identity so a deterministic rebuild replays
  artifacts instead of re-calling the provider. Mixing degrades retrieval
  silently rather than failing. See `TECHNICAL_BLUEPRINT.md` Section 12.2.1.
- Use deterministic serialization, explicit schema versions, content hashes,
  bounded subprocesses, captured stdout/stderr, and no-network execution by
  default.

## Checks

Run `make check`. It is the single offline entrypoint and needs no network, no
model provider, no container runtime, and no third-party package. Targets that
need more are separate and named for what they need: `make check-sealed`
requires the ADR-0016 v5 image, `make check-gate` requires the disposable
pinned Draft 2020-12 validator environment, `make check-typeset` requires the
pinned TeX Live engine, and `make check-all` runs both of the first two.

Changes must keep the complete earlier suite green and additionally pass exact
quantum feasibility/optimum checks, material-result persistence and steering,
frozen held-out capability boundaries, generality controls, restart/replay,
report consistency, and zero-network/model/API checks.

Output has two homes and the distinction is enforced by `.gitignore`, not by
convention. `make check` and every phase target are GATES: they render into a
mktemp directory and delete it, so a check never writes into a tracked path.
`make report` is the durable counterpart -- it runs the same work and keeps every
readable artifact under `$(OUT)`, defaulting to `reports/local/run-<stamp>`, then
writes `index.json` and `INDEX.md` hashing every file. A path under
`reports/local/` is a LOCAL RUN and is ignored; a path anywhere else under
`reports/` is RECORDED EVIDENCE that an ADR may cite and is committed
deliberately. Promote a local run by copying it to `reports/<phase>/<version>/`,
never by moving it or by loosening the ignore rule. Scratch workspaces go to
`work/`, also ignored, and a fresh workspace per run is required because
replaying an identical record into an existing workspace is refused by design.
Derived indexes and any future vector store are ignored too: they are rebuildable
from the records by definition, are never a source of truth, and a committed one
would let a stale index outlive the corpus it was built from.

The report index hashes and does not summarise, and its `recorded_at` is an
argument rather than a clock read. Two files legitimately differ between two
otherwise identical runs and both are phase properties rather than
nondeterminism: `phase1/demo-summary.json` echoes its own output paths, and the
Phase 4C report carries `operational.elapsed_ms` plus the derived
`operational_hash`, which Phase 4C separates from its stable `content_hash` on
purpose.

Under ADR-0026 each new slice ships one ADR plus an acceptance suite that
encodes its thresholds as executable assertions, rather than a separate
threshold inventory. A scenario's forbidden outcomes must be demonstrated
impossible, not merely left untested. `tests/test_repository_invariants.py`
enforces the standing structural properties: no module-level network or
third-party import in `src/`, and every lazy third-party load declared as a
gated boundary.
