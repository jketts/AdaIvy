# B8. EFX allocation for exactly four agents — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B8 (tier B)
**Declared domain:** discrete-fair-division
**Intake file:** docs/research-targets/intake/b8-efx-four-agents-v1.json
**Frozen in one line:** Every finite instance with exactly four agents, additive
nonnegative rational valuations over a finite set of indivisible goods, admits a
complete allocation that is envy-free up to any good.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish that the four-agent case is open, authorize source
acquisition, assess novelty or significance, create mathematical warrant, or
activate any capability. Novelty, significance, and source applicability are
`not_assessed`. In particular this dossier does not assert that EFX existence
for four agents is an open problem; that is an untrusted status claim recorded
in section 6 with a named acquisition target in section 5.

## 1. Frozen target

Let `N = {1, 2, 3, 4}` be the agent set — exactly four agents. Let `M` be a
finite set of indivisible goods. For each `i in N` let `v_i` be a valuation on
subsets of `M` that is **additive**:

`v_i(S) = sum of v_i({g}) over g in S`, and `v_i(empty) = 0`,

with each singleton value `v_i({g})` a **nonnegative rational**.

A **complete allocation** is an ordered tuple `X = (X_1, X_2, X_3, X_4)` of
pairwise disjoint subsets of `M` with

`X_1 union X_2 union X_3 union X_4 = M`.

Every good is allocated to exactly one agent. There is no charity pile, no
donated set, and no unallocated remainder. Bundles may be empty.

`X` is **EFX** iff

`for all i, j in N with i != j, for all g in X_j with v_i({g}) > 0:`
`v_i(X_i) >= v_i(X_j minus {g})`.

**Frozen claim.** For every finite `M` and every such `(v_1, v_2, v_3, v_4)`
there exists a complete allocation `X` that is EFX.

The `i = j` case is omitted because it is vacuous: `v_i(X_i) >= v_i(X_i minus
{g})` holds by nonnegativity. Under additivity the inequality is equivalent to
`v_i(X_i) >= v_i(X_j) - v_i({g})`; the two forms are interchangeable *only*
because valuations are additive, and the subtraction form is not used outside
that class.

There is no asymptotic and no parameter left free: the agent count is a
constant, the direction is existence of an allocation, and `problem_type` is
`explore` because an exact finite counterexample and a proof are both
acceptable outcomes.

### Why this freeze

The planning dossier says "at least four agents", which is a disjunction over
agent counts, and it explicitly defers "the precise convention for unallocated
goods fixed at intake". Both are resolved here: the count is fixed at exactly
four, and the allocation is complete with no donated pile. Complete allocation
is the more demanding side of the axis the planning dossier names as the main
variant risk, and it is the reading under which a counterexample would be
meaningful rather than an artifact of a permissive convention.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| agent count | exactly four, `N = {1,2,3,4}` | at least four; at least three; a parameter `n >= 4`; asymptotically many agents |
| valuation | additive, `v_i(S) = sum of v_i({g})` over `g in S` | monotone non-additive; submodular; subadditive; general combinatorial; cancelable |
| value range | nonnegative rationals, so zero-valued goods exist | strictly positive values; arbitrary reals; integers only as a *hypothesis* rather than as a derived normal form |
| EFX quantifier over goods | every `g in X_j` with `v_i({g}) > 0` | EFX_0: every `g in X_j` including `v_i({g}) = 0` (strictly stronger); EF1: *some* `g in X_j` (strictly weaker) |
| EFX inequality | `v_i(X_i) >= v_i(X_j minus {g})`, non-strict | strict `>`; approximate `v_i(X_i) >= c * v_i(X_j minus {g})` for `c < 1`; the subtraction form applied outside additive valuations |
| envy pairs | all ordered pairs `i != j` | unordered pairs; only pairs where `i` currently envies `j`; only adjacent pairs in some order |
| allocation | complete ordered partition of `M` into four pairwise disjoint parts whose union is `M` | partial allocation; allocation with a fifth donated or charity part; allocation of a subset of `M`; fractional or randomized allocation |
| empty bundles | permitted | forbidden; required to be nonempty; required to have equal cardinality |
| goods | indivisible, finite, distinguishable | divisible goods; chores with negative value; mixed goods and chores; infinitely many goods |
| instance identity | the `4 x card(M)` matrix of singleton values in integer normal form, plus `card(M)` | the matrix before normalization; the matrix with zero columns deleted |
| ties | equality in an EFX inequality satisfies it | equality treated as a violation |

Two normalizations are used and their status differs, which matters:

- **Sound and lossless.** Relabeling agents, relabeling goods, and multiplying
  one agent's values by a positive rational all preserve the EFX property of
  every allocation, because each EFX inequality involves a single agent's
  valuation on both sides. Clearing denominators per agent therefore yields an
  equivalent instance with nonnegative integer values.
- **A genuine restriction, not a normalization.** Bounding the *values* to a
  finite alphabet such as `{0,1,2}` is a real restriction on the instance
  space. It is used in section 7 only to define a finite envelope and it is
  never described as without loss of generality.

## 3. Formalization and quantifiers

Statement, as carried in the intake file:

```
forall finite M,
forall (v_1,v_2,v_3,v_4) with v_i({g}) in Q and v_i({g}) >= 0 for all g in M
  and v_i(S) = sum(v_i({g}) for g in S),
exists (X_1,X_2,X_3,X_4) with X_i pairwise disjoint, union of X_i equal to M,
such that forall i,j in {1,2,3,4} with i != j,
          forall g in X_j with v_i({g}) > 0: v_i(X_i) >= v_i(X_j minus {g})
```

Quantifiers, explicitly:

- `forall M` a finite set of indivisible goods, `card(M) >= 0`.
- `forall i in N = {1,2,3,4}`, `forall v_i` additive with nonnegative rational
  singleton values.
- `exists X = (X_1, X_2, X_3, X_4)` a complete ordered partition of `M` into
  possibly empty bundles.
- `forall` ordered pairs `(i,j)` in `N x N` with `i != j`.
- `forall g in X_j` with `v_i({g}) > 0`.

Formal language `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment is required and has not been given.

## 4. Semantic alignment to the source statement

The source statement is the planning dossier's rendering, which is itself an
untrusted planning artifact; no primary source has been acquired.

**Quantifier mapping.**

| Source | Local |
|---|---|
| every finite instance with at least four agents | every finite instance with exactly four agents, `N = {1,2,3,4}` |
| additive valuations | `v_i(S) = sum of v_i({g})` with `v_i({g})` a nonnegative rational |
| admits an allocation | there exists a complete ordered partition `(X_1,...,X_4)` with possibly empty parts |
| envy-free up to any good | for all `i != j` and all `g in X_j` with `v_i({g}) > 0`, `v_i(X_i) >= v_i(X_j minus {g})` |
| the precise convention for unallocated goods fixed at intake | there are no unallocated goods: the allocation is complete and no charity pile exists |

**Definition mapping.**

| Source term | Local meaning |
|---|---|
| EFX | own bundle at least the other bundle minus any positively valued good, over all ordered distinct pairs |
| EFX_0 | rejected: also quantifies over goods the envying agent values at zero |
| EF1 | rejected: quantifies over *some* removable good |
| allocation | complete ordered partition into four pairwise disjoint possibly empty bundles |
| charity or donated pile | rejected: a fifth unallocated part is not permitted |
| valuation positivity | nonnegative rational singleton values; strict positivity rejected |
| agent count | exactly four; at least four rejected |

**Assumption delta.**

- The planning statement says at least four agents; the frozen target fixes
  exactly four, so it is a strict special case of the planning statement.
- Valuations are nonnegative rather than strictly positive, so zero-valued
  goods exist and the EFX quantifier is restricted to positively valued goods;
  this is the weaker of the two EFX readings and is frozen deliberately.
- The allocation must be complete, which is strictly more demanding than the
  charity-pile variants the planning notes mention.
- Empty bundles are permitted, so an allocation giving one agent nothing is
  admissible provided every EFX inequality holds.
- No claim is made about the open status of the four-agent case; open status is
  `not_assessed`.

**Edge-case delta.**

- `card(M) = 0` gives the all-empty allocation, which is EFX because every
  inner quantifier is empty.
- `card(M) < 4` forces at least one empty bundle, which is admissible.
- A good valued zero by every agent is inert: it generates no inequality and
  can sit in any bundle without changing whether an allocation is EFX.
- A good valued zero by `i` but positively by `j` generates no inequality for
  `i` on that good; `j`'s own inequalities are unaffected by `i`'s valuation.
- Two agents may have identical valuations; the instance space is not
  restricted to distinct valuations.
- Equality in an EFX inequality satisfies the frozen non-strict form.

**Strength relation:** `weaker`. The frozen target is a strict special case of
the planning statement. It is not `equivalent`, and cannot be, because no
primary source has been acquired or quoted.

## 5. Provenance and acquisition plan

No source is acquired by this dossier. Every row is a target an operator would
acquire under ADR-0050 as a human-planned, exact-URL, separately authorized
public fetch. Volume, page, and DOI fields are left to be resolved from the
publisher record at acquisition time and are **not asserted here**.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| The paper that introduced EFX (Caragiannis, Kurokawa, Moulin, Procaccia, Shah, Wang, on maximum Nash welfare) | article record by authors, title, venue; identifier to be resolved by the operator | settles the original EFX definition and in particular whether the good quantifier is over positively valued goods or all goods — section 6 rows 1 and 2 | pending_acquisition, applicability not_assessed |
| The three-agent EFX existence result (Chaudhury, Garg, Mehlhorn) | article record by authors, title, venue; identifier to be resolved | settles section 6 row 3, the claim that three agents are settled and four are open, and fixes which conventions that result uses | pending_acquisition, applicability not_assessed |
| The charity or donated-pile results (Chaudhury, Kavitha, Mehlhorn, Sgouritsa and successors) | article records by authors, titles, venues; identifiers to be resolved | settles section 6 row 4 and supplies the exact assumption delta between charity variants and the frozen complete-allocation target | pending_acquisition, applicability not_assessed |
| A current survey of fair division of indivisible goods listing open questions | survey record by authors, title, journal, year; identifier to be resolved | settles which agent counts and which variants are reported open as of acquisition date — section 6 rows 3 and 5 | pending_acquisition, applicability not_assessed |
| Any published four-agent partial result, restricted-valuation result, or counterexample search | subject search planned by the operator with exact terms recorded, then exact-URL acquisition of each hit | settles whether the frozen target is already resolved, and whether any published counterexample search already covers the envelope in section 7 | pending_acquisition, applicability not_assessed |

Under ADR-0051 an operator may run one Crossref metadata query whose terms are
exact-normalized substrings of a supplied local context file. Its results are
inspiration-only, acquire nothing, and do not satisfy the ADR-0055 re-check.

## 6. Prior-status claims to re-check

Each is **untrusted**. None is acquired, quoted, or verified. Each is named as
a claim the ADR-0055 pre-research novelty re-check must cover before any
research starts.

1. **Untrusted:** that the standard EFX definition quantifies only over goods
   the envying agent values positively. This dossier freezes that reading; the
   freeze is a choice, not a finding.
2. **Untrusted:** that EFX and EFX_0 are genuinely different problems and that
   the literature uses both names for both readings. The planning dossier's
   risk note about variant divergence is the only basis for this here.
3. **Untrusted, and unsourced recollection carried into this dossier:** EFX
   existence with additive valuations is settled for two and three agents and
   open from four upward. The planning dossier's phrase "at least four agents"
   inherits this. The frozen four-agent target must not be described as open on
   the strength of it.
4. **Untrusted, and unsourced recollection:** results exist for EFX with a
   charity or donated pile, and for approximate EFX. If true they do not settle
   the frozen complete-allocation target, but they may bound what a
   counterexample can look like, which changes the search design.
5. **Untrusted:** the planning dossier's own risk statement, that EFX variants
   differ on positivity, zero-valued goods, charity goods, and complete versus
   partial allocation.
6. **Untrusted:** that no published exhaustive counterexample search already
   covers the envelope defined in section 7. If one does, the slice is a
   re-run and must be relabelled as independent verification rather than new
   work, exactly as ADR-0055 requires for the Graffiti 197 regression.

## 7. Bounded first slice

**Inputs.** No external input. The slice generates its own instances.

**Instance normal form.** An instance is a `4 x m` matrix of nonnegative
integers, `m = card(M)`, row `i` giving agent `i`'s singleton values. Integer
normal form is reached by clearing denominators per agent, which is lossless.

**Enumeration method.** Agent rows are enumerated as a *multiset* of four rows,
which quotients by the `4! = 24` agent relabelings at generation time rather
than by post-hoc filtering. The remaining `m!` goods relabelings are quotiented
by keeping only matrices that are the lexicographically least image under
column permutations. No random number generator is used anywhere, so the run is
byte-reproducible.

**Envelope E1 — exhaustive, `m in {0,1,2,3,4}`, value alphabet `{0,1,2}`.**
Each row is one of `3^m` vectors, so the number of agent-multiset instances is
`C(3^m + 3, 4)`: `1` for `m = 0`, `C(6,4) = 15` for `m = 1`,
`C(12,4) = 495` for `m = 2`, `C(30,4) = 27405` for `m = 3`, and
`C(84,4) = 1929501` for `m = 4`. Total `1957417` before column
canonicalization, which removes up to a further factor of `m! = 24`. Per
instance the slice enumerates all `4^m <= 256` complete allocations, checking at
most `4 * 3 * m = 48` EFX inequalities each, with early exit on the first EFX
allocation found. Worst case, without early exit, is about `9.2 x 10^8` exact
integer comparisons.

**Envelope E2 — exhaustive, `m = 5`, value alphabet `{0,1}`.** Rows are one of
`2^5 = 32` binary vectors, giving `C(35,4) = 52360` agent-multiset instances
before column canonicalization. Per instance: `4^5 = 1024` complete
allocations, at most `4 * 3 * 5 = 60` inequalities each. Worst case about
`3.2 x 10^9` comparisons, far less with early exit.

**Envelope E3 — declared NON-exhaustive, `m in {5,6,7,8}`, value alphabet
`{0,1,2,3}`.** A deterministic structured subfamily: instances in which at most
two distinct valuation rows occur, so the four agents fall into at most two
valuation types, and each row uses at most three distinct nonzero values. The
subfamily is generated deterministically with no sampling. Its purpose is to
reach larger `m` where a counterexample is more plausible, and it is recorded
as non-exhaustive in the run record. It supports no statement of the form "no
counterexample exists with `m <= 8`".

**Per-instance decision.** An instance is *decided* only when all `4^m`
complete allocations have been checked exactly. Anything less is recorded as
undecided for that instance. The failure of the enumeration to find an EFX
allocation is a nonexistence result for that instance if and only if the full
`4^m` space was checked; otherwise it is nothing.

**Canonicalization probe.** For `m <= 3` the slice enumerates with and without
canonical pruning and asserts that the decided-instance counts and the set of
undecided instances agree. A wrong canonical form silently deletes instances
and would turn a missed counterexample into a false clean sweep, so the
canonical form is treated as a falsifiability probe target, not as trusted code.

**Boundary of the claim the slice can support.** If E1 and E2 complete with no
counterexample, the entailment is exactly: every four-agent instance with at
most four goods and values in `{0,1,2}`, and every four-agent instance with
five goods and values in `{0,1}`, admits a complete EFX allocation. It entails
nothing about larger `m`, nothing about richer value alphabets, and nothing
about the frozen universal claim. The value-alphabet restriction is emphatically
*not* a normalization: unlike per-agent scaling and relabeling, capping values
at `2` or at `1` discards instances that cannot be recovered by any invariance,
so E1 and E2 are not "all small instances" but "all small instances over a
small alphabet". Any report that blurs the two misstates the result.

## 8. Certificate and verifier contract

**Result shape 1: a counterexample instance.** Certificate: the instance in
integer normal form (the `4 x m` matrix), `m`, a content hash over the canonical
serialization, and an exhaustive violation table with one row per complete
allocation — all `4^m` of them — each naming a violated triple `(i, j, g)` and
the two exact integers `v_i(X_i)` and `v_i(X_j minus {g})` with
`v_i(X_i) < v_i(X_j minus {g})`. Independent verifier: a separate program that
reads only the matrix, re-enumerates all `4^m` complete allocations from
scratch, re-checks that each carries a genuine violation, verifies that the
allocation list is complete and duplicate-free, and recomputes the hash. For
`m = 8` the table has `65536` rows, which is small enough to store and replay
in full.

**Result shape 2: an existence proof for exactly four agents.** Certificate: a
proof artifact listing every assumption used, with the frozen conventions from
section 2 restated as the proof's own hypotheses, so that a proof of the
charity-pile variant or of EF1 cannot be mistaken for a proof of this target.

**Result shape 3: a constructive algorithm with a correctness proof.**
Certificate: the algorithm, the proof that its output is EFX on every instance
in the frozen class, plus exact replay of the algorithm on every decided
instance of E1 and E2 with the EFX check reverified independently. The replay
is a consistency check on the implementation, never a substitute for the proof.

**Result shape 4: an exhaustion record.** Certificate: the envelope definitions
verbatim, per-envelope decided and undecided instance counts, the
canonicalization probe results, and a content hash over the whole record. Its
entailment is the narrow statement in section 7.

**Refused as a certificate, in all four shapes:** the failure of any heuristic,
greedy rule, local search, or model-guided procedure to find an EFX allocation;
any floating-point value; the output of a linear or integer programming solver
that reports a real-valued objective; the output of an unreplayed third-party
solver; a SAT or ILP "unsatisfiable" verdict without a machine-checked proof
log, which is a capability this repository does not have (section 12); a model's
assertion; and agreement between two model runs.

## 9. Useful negative outcomes

- **The EFX-critical set.** Every decided instance whose EFX allocations are
  unique up to the symmetry group. These rigid instances are the natural seeds
  for extension to `m + 1` goods, because a counterexample, if one exists, is
  most likely a rigid instance that loses its last EFX allocation when one good
  is added. Retained with hashes so the next run extends instead of restarting.
- **The difficulty frontier.** For each decided instance, the number of
  allocations examined before the first EFX allocation was found under a fixed
  deterministic order. This is a bounded structural measure, not a hardness
  claim, and it ranks candidates for E3.
- **Inertness and collapse reductions.** Proved or refuted: that globally
  zero-valued goods can be assigned arbitrarily, and that agents with identical
  valuations can be handled by a symmetry argument. Each with a mutation probe
  that must fail inside E1.
- **The decided/undecided ledger.** Every instance recorded as decided or
  undecided with its envelope, so no later run silently reuses an undecided
  instance as if it were decided.
- **Refuted routes.** Any existence argument attempted and found to have a gap
  is preserved with the gap named, following the Graffiti-322 precedent of
  recording the specific unproved steps.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics:

- `canonical_instances_enumerated`
- `instances_exhaustively_decided`
- `complete_allocations_exactly_checked`
- `efx_inequalities_exactly_evaluated`
- `instances_with_no_efx_allocation`
- `canonicalization_probes_flipped`
- `reduction_lemmas_proved`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- an exact counterexample instance in integer normal form together with an
  exhaustive replayed check that none of its `4^card(M)` complete allocations
  is EFX
- a rigorous proof of existence for every instance with exactly four agents
  under the frozen conventions
- a proved reduction that replaces the frozen class by an exactly stated
  smaller class of instances, with the reduction's direction and convention
  preservation proved
- or an explicit unresolved outcome that records the smallest remaining
  obligation

Stopping rules:

- stop on an exact certificate: a replayed exhaustive nonexistence instance or
  a completed existence proof for exactly four agents
- stop when fresh model spend for this target reaches USD 20
- stop when no proof obligation has been discharged and no new exclusion
  recorded for two consecutive review points
- never promote exhaustion of the declared enumeration envelope into the
  unrestricted universal claim, and never record the failure of a heuristic as
  a nonexistence result

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Variant substitution. | EFX, EFX_0, EF1, approximate EFX, and charity variants all get called EFX in different places. Aligning an acquired result to the wrong variant would silently change the target or make a refuted route look open. | Every axis is pinned in section 2 with the rejected reading named. Any acquired source gets an explicit assumption-delta row before its statements are aligned. `strength_relation` stays `weaker`. |
| Search failure read as nonexistence. | The planning dossier names this directly. An instance where a heuristic fails looks like a counterexample and is not one. | An instance is decided only when all `4^m` complete allocations are checked; the certificate contract in section 8 refuses heuristic failure outright; the stopping rules repeat the prohibition. |
| Alphabet restriction mistaken for a normalization. | Per-agent scaling and relabeling *are* lossless, which makes it easy to also treat the `{0,1,2}` cap as lossless. It is not, and the resulting overclaim would be invisible in the numbers. | Section 2 separates the two explicitly; section 7 states the entailment in terms of "small instances over a small alphabet"; the exhaustion record carries the alphabet in the envelope definition. |
| Envelope blow-up. | The instance space grows as `card(V)^(4m)`; `m = 6` over `{0,1,2,3}` is already out of reach exhaustively. | E1 and E2 are exhaustive and small; E3 is declared non-exhaustive and structured with no RNG; the concrete instance counts are computed in section 7 rather than hoped for. |
| Wrong canonical form. | Silently deletes instances, so a missed counterexample reads as a clean sweep. | Cross-check against unpruned enumeration for `m <= 3` as an asserted probe. |
| Rediscovery of a published counterexample search. | If a published search already covers E1 and E2, the slice is independent verification, not new work. | Acquisition row 5 in section 5 exists for this; ADR-0055 re-check is mandatory; a re-run must be reported with report class `independent_verification`, following the Graffiti 197 precedent. |
| Charity results mis-cited. | A charity-pile existence result reads as settling the problem and does not settle the frozen complete-allocation target. | Recorded as a known trap in the intake file; every such citation needs an assumption-delta row naming the violated convention. |
| Floating point or solver output entering the trust path. | An LP or ILP relaxation would produce real-valued bounds that look decisive. | All arithmetic is exact integer after normalization; solver output is refused as a certificate and no solver dependency is added (section 12). |
| Bounded search promoted to a universal claim. | The frozen claim is `unrestricted_universal`; the slice is finite. | Explicit stopping rule; the exhaustion record carries its own entailment; ADR-0036 renders the claim as `Conjecture` absent a kernel-checked attestation. |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Phase 1 declarative problem intake and trust policy; the intake file
  validates and creates no warrant, novelty, or significance.
- Exact integer and exact rational arithmetic from the Python standard library,
  including `fractions` for the normalization step. No third-party numeric
  package is needed, matching the standard-library preference for the harness.
- Deterministic serialization, explicit schema versions, and content hashing
  for instances, violation tables, and the exhaustion record.
- Bounded subprocess execution with captured stdout and stderr, no network, for
  the enumerator and the independent verifier.
- Machine-readable preservation of failed attempts, undecided instances, and
  unresolved outcomes, as required for section 9.
- ADR-0047 bounded central-lead runtime if a model proposes routes, inside
  content-hashed session bounds with a proposer-only ledger and model-free
  replay. It discharges no obligation and produces no warrant.
- ADR-0055 pre-research novelty re-check, mandatory before work starts.
- ADR-0036 publication projection if a report is rendered; the frozen claim
  renders as `Conjecture` absent a kernel-checked attestation.

**Would require a new ADR and is not activated by this dossier.**

- Any SAT, SMT, or ILP solver, and any DRAT or LRAT proof-log checker. The
  repository has no propositional proof-checking capability; the only sealed
  external checker is the ADR-0016 Lean image, which is a different tool.
  Encoding per-instance nonexistence as UNSAT with a checked proof log is an
  attractive route and is explicitly *not* available here.
- Any source acquisition. ADR-0050 permits only public, unauthenticated,
  human-planned, exact-URL fetches, separately authorized. Section 5 is a plan.
- Any Lean formalization of this target. The sealed Phase 3B scope is one
  frozen theorem with a supplied proof fragment; a new frozen statement with
  its imports and meaning tests is a separate decision.
- Any parallel, specialist, evolutionary, or higher search tier; ADR-0029
  requires a recorded prediction and measured retention gain first.
- Any automated novelty or significance assessment.

## 13. Open questions before intake

1. Is EFX the right freeze, or does the operator want EFX_0, the stronger
   reading that also removes zero-valued goods? The two are different problems
   and only one can be the target.
2. Should nonnegative be relaxed to strictly positive? Strict positivity
   removes the zero-good edge cases entirely and collapses EFX and EFX_0, at
   the cost of a narrower class.
3. Is exactly four the right agent count, or should the freeze be exactly five
   to sit further from any reported three-agent result?
4. Is E3 worth running at all given that it supports no exhaustion statement,
   or should the slice stop at E1 and E2 plus the EFX-critical extension work?
5. Does the operator want to pursue a SAT-based per-instance nonexistence route
   later? If so, the proof-log checker is a new ADR and should be scoped before
   the first run rather than after.
6. Which of the five acquisition rows in section 5 is authorized, in what
   order, and with which exact URLs?
