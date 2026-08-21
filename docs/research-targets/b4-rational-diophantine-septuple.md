# B4. Rational Diophantine septuple — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B4 (tier B)
**Declared domain:** number-theory
**Intake file:** docs/research-targets/intake/b4-rational-diophantine-septuple-v1.json
**Frozen in one line:** there exist seven pairwise distinct nonzero rationals
`a_1,...,a_7` such that for every pair `i != j` some `r_ij` in `Q` satisfies
`r_ij^2 = a_i a_j + 1`.

This is a scoped intake package and nothing more. It does not approve a
formalization, does not establish that the question is open, does not authorize
source acquisition, and does not activate any capability. Novelty,
significance, and source applicability are `not_assessed` and no statement here
creates mathematical warrant, graph admission, or proof status. Every external
statement it repeats is an untrusted candidate, because no source is acquired in
this task.

## 1. Frozen target

Frozen statement. There exists a set `S = {a_1, a_2, ..., a_7}` of seven
pairwise distinct nonzero rational numbers such that for every unordered pair of
distinct indices `{i, j}` there exists `r_ij` in `Q` with

```
r_ij^2 = a_i a_j + 1.
```

Symbols. `Q` is the field of rational numbers. Each `a_i` is an element of `Q`
with `a_i != 0`. Pairwise distinct means `a_i != a_j` whenever `i != j`, so `S`
has exactly seven elements. There are exactly `C(7,2) = 21` unordered pairs, so
21 witnesses `r_ij` are required. The witnesses are not required to be distinct
and their signs are immaterial, since `r` and `-r` certify the same value.

Quantifier form.

```
exists a_1,...,a_7 in Q,
  (forall i, a_i != 0)
  and (forall i != j, a_i != a_j)
  and (forall i != j, exists r_ij in Q, r_ij^2 = a_i a_j + 1).
```

Target scope is `existential`: the target asks for one object, not for a
property of all objects. The problem type is `explore`, because both an
exhibited septuple and a rigorous obstruction are acceptable outcomes and the
frozen statement does not fix the direction. The planning dossier's second
listed win, "a proved obstruction for a well-defined construction family", is an
outcome shape and not a second target: it is recorded in §9, and by
construction it says nothing about the frozen existential statement.

No asymptotics appear in this target, so no epsilon form is required.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| entry `a_i` | an element of `Q` | an integer; a real algebraic number; an element of a larger field |
| nonzero | every `a_i != 0` | zero admitted, which makes `0 * a_j + 1 = 1 = 1^2` hold for free and turns any six-element solution into a seven-element one without addressing the question |
| distinct | `a_i != a_j` as rationals, compared on the lowest-terms normal form | distinct as written expressions, so that `1/2` and `2/4` would count as two entries; a multiset of size seven |
| sign of entries | negatives admitted; the square condition then carries the side condition `a_i a_j + 1 >= 0` | all entries positive |
| square in `Q` | there exists `r` in `Q` with `r^2 = a_i a_j + 1` | the square of an integer; a square modulo some `m`; a square in `R` or in an extension field |
| the value `0` as a square | admitted, `0 = 0^2`, so a pair with `a_i a_j = -1` satisfies the condition | `r != 0` required; this stricter convention is rejected here but flagged, see below |
| the target object | an unordered seven-element set, invariant under pointwise negation `S -> -S` | an ordered tuple; a sequence in which order or repetition matters |
| normal form | `p/q` with `q > 0` and `gcd(p, q) = 1` | any representative fraction |
| height | `max(abs(p), q)` in normal form | numerator size alone; denominator alone; bit length |
| septuple | seven entries satisfying the frozen pairwise condition | a sextuple that can be extended; six entries plus a claimed extension parameter |

Two conventions are load-bearing and deserve naming twice.

Exclusion of zero is the choice that keeps the problem a problem. Under the
permissive reading, adjoining `0` to any six-element solution produces a
seven-element solution and the target would be reachable from any sextuple. The
frozen reading excludes zero.

Admitting `r_ij = 0` is the permissive choice on the other axis. It matters
only for a pair with `a_i a_j = -1`. If a search returns a septuple containing
such a pair, the result must be reported with that pair flagged, because the
rejected stricter convention would refuse it and the operator has not yet
chosen between the two. This is recorded in §13 as an open question rather than
silently resolved.

## 3. Formalization and quantifiers

Formal statement, in the typed informal register used by the intake file:

```
exists a_1,...,a_7 in Q,
  (forall i in {1,...,7}, a_i != 0)
  and (forall i, j in {1,...,7} with i != j, a_i != a_j)
  and (forall i != j, exists r_ij in Q, r_ij^2 = a_i * a_j + 1)
```

Quantifier list, as frozen in the intake file:

- `exists a_1,...,a_7 in Q`, pairwise distinct and each nonzero.
- `forall` unordered pairs `{i,j}` with `i != j`, of which there are exactly 21.
- `exists r_ij in Q` for each such pair, with `r_ij^2 = a_i * a_j + 1`.

The existential witness is finite and fully explicit: seven rationals and 21
rationals, 28 numbers in total, each a pair of integers. Nothing in the target
is asymptotic, approximate, or asymptotically parametrized, so there is no
implicit constant anywhere and no epsilon form is needed.

The reduction that makes the check exact. For a nonnegative rational written in
lowest terms as `p/q` with `q > 0` and `gcd(p, q) = 1`, the value is a square in
`Q` if and only if `p` and `q` are both perfect squares of integers. This is the
standard textbook criterion and it turns each of the 21 conditions into two
exact integer square tests, performed by an exact integer square root with a
remainder check. No floating-point square root is used anywhere.

## 4. Semantic alignment to the source statement

Quantifier mapping.

| Planning phrase | Frozen quantifier |
|---|---|
| find seven distinct rational numbers | `exists a_1,...,a_7 in Q`, pairwise distinct |
| for every `i != j` | `forall` 21 unordered pairs `{i,j}` drawn from seven indices |
| `a_i a_j + 1` is a rational square | `exists r_ij in Q` with `r_ij^2 = a_i a_j + 1` |
| nonzero entries | `forall i, a_i != 0`, frozen locally and not read off an acquired source |

Definition mapping.

| Term | Local meaning |
|---|---|
| rational square | the square of an element of `Q`; zero is admitted as `0^2` |
| distinct | distinct as rationals, compared in lowest terms with positive denominator |
| seven rationals | an unordered seven-element set, invariant under pointwise negation |
| height of an entry | `max(abs(numerator), denominator)` in lowest terms, used only to bound enumeration |
| rational Diophantine septuple | a seven-element set satisfying the frozen pairwise square condition |

Assumption delta.

- Nonzero entries are added as an explicit assumption. The candidate statement
  in the planning dossier does not say it, and without it any sextuple plus zero
  would qualify.
- Negative entries are admitted, so the square condition carries the implicit
  side condition `a_i a_j + 1 >= 0` rather than an assumed positivity of
  entries.
- The value zero is admitted as a rational square, which is a permissive choice.
  The stricter convention requiring a nonzero square root is recorded as
  rejected and flagged for operator confirmation.
- Height bounds are a device of the bounded protocol only and are not part of
  the frozen target.

Edge-case delta.

- A pair with `a_i a_j = -1` satisfies the frozen condition with `r_ij = 0` and
  must be flagged in any exhibited septuple.
- Entries with denominator 1 are admitted, so an integer septuple would also
  satisfy the frozen target.
- The 21 square roots are not required to be distinct, and their signs are
  irrelevant because `r` and `-r` certify the same value.
- A set of seven rationals containing a repeated value is not a septuple even if
  all products satisfy the square condition.

Strength relation: `unresolved`. The literature convention for a rational
Diophantine `m`-tuple is not acquired, so the mapping from this frozen statement
to the published problem cannot be settled here. In particular the frozen
statement cannot be declared `equivalent`, because that would require quoting an
acquired primary source, and none is acquired.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` and every applicability judgement is
`not_assessed`. No DOI or article identifier is asserted from memory: where the
locator is not known offline, the row records the exact resolution procedure
instead of a guess, because a fabricated identifier is worse than an unresolved
one.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Operator's supplied candidate notes, received 21 August 2026 | local artifact held by the operator; must be supplied as a file, not paraphrased | settles §6.1 and §6.2 wording as actually received | pending_acquisition, applicability not_assessed |
| Primary article reporting infinite families of rational Diophantine sextuples | `locator_unresolved`; resolve by one ADR-0051 Crossref metadata query with the operator-supplied terms `rational Diophantine sextuple` and `Diophantine m-tuple`, each an exact normalized substring of this dossier once it is the supplied local context, then acquire the returned DOI by ADR-0050 exact-URL acquisition | settles §6.1 | pending_acquisition, applicability not_assessed |
| Primary article or survey stating the current status of the septuple question | `locator_unresolved`; same ADR-0051 route with the term `rational Diophantine septuple`, then ADR-0050 acquisition of the returned DOI, targeting the section that states the status and the definition used | settles §6.2 and §6.3 | pending_acquisition, applicability not_assessed |
| Survey or textbook section fixing the standard definition of a rational Diophantine `m`-tuple | `locator_unresolved`; the acquisition target is the definition paragraph and the surrounding conventions on zero, distinctness and positivity, cited at passage level and not at work level | settles §6.3, and decides whether §13 Q1 and Q2 change the frozen conventions | pending_acquisition, applicability not_assessed |
| FrontierMath open-problems index, recorded in the planning dossier's source ledger | `https://epoch.ai/frontiermath/open-problems` | discovery index only; it is not a statement source and may not settle any §6 row | pending_acquisition, applicability not_assessed |
| Abstracting and indexing databases | not available: they require credentials, and credentialed acquisition is disabled | would otherwise help locate the above | out_of_scope |

Under ADR-0050 acquisition is human-planned, exact-URL, public and
unauthenticated, and separately authorized. Under ADR-0051 a discovery query is
one human-started request returning at most ten DOI metadata candidates, each an
untrusted inspiration candidate that creates no relevance, applicability,
acquisition, novelty, significance, graph-admission or warrant effect. Nothing
in this dossier authorizes either step.

## 6. Prior-status claims to re-check

Each item is an untrusted inherited report. None is used as a premise anywhere
in §7 or §8, and each must be covered by the ADR-0055 pre-research novelty
re-check, bound to this problem definition's subject hash, before research
starts.

1. **Untrusted.** "The notes report infinite families of rational sextuples but
   no septuple." Two separate claims are bundled here: that sextuple families
   are known, and that no septuple is known. Both are unsourced in this task.
   The second is the one that decides whether this slice is exploration or
   reproduction, and it is exactly what the re-check must settle.
2. **Untrusted.** That the existence question is open. Open status is not
   established by an empty search, by a catalogue label, or by the planning
   dossier's tiering.
3. **Untrusted.** The standard literature convention for a rational Diophantine
   `m`-tuple: whether entries must be nonzero, whether they must be distinct,
   whether they must be positive, and whether `0` counts as a square. The
   conventions in §2 are authored locally. If the acquired source differs, the
   semantic alignment must be re-approved before any result is described as a
   result about the published problem.
4. **Untrusted.** The planning dossier's verification shape, namely "normalize
   rational entries, verify distinctness, and provide the 21 exact rational
   square roots". The count 21 is arithmetic and is not a source claim, but the
   claim that this list is sufficient for the community's notion of a verified
   septuple is a source claim and is not established here. §8 fixes what this
   repository will accept, independently of that.

## 7. Bounded first slice

Inputs. A height bound `H`, frozen before the run; the frozen conventions of
§2; no external data of any kind. The run reads no acquired source, because
none is acquired.

Algorithms and arithmetic, all exact.

1. Enumerate `R(H)`, the set of nonzero rationals `p/q` in lowest terms with
   `q >= 1` and `max(abs(p), q) <= H`. Serialize each as an integer pair.
   Canonical order is by `(q, p)`. The size of `R(H)` grows like a constant
   times `H^2`; for `H = 100` it is on the order of ten thousand entries and the
   exact count is recorded by the run rather than estimated.
2. Build the compatibility graph `D(H)` on `R(H)`: an edge joins `a` and `b`
   when `a b + 1` is a square in `Q`. The test computes `a b + 1` in exact
   rational arithmetic, reduces to lowest terms, rejects negatives, and applies
   the criterion of §3 with an exact integer square root and a remainder check.
   The number of tests is `C(card R(H), 2)`, recorded exactly.
3. Search `D(H)` for a clique of size seven by exhaustive depth-first extension
   with pivoting, in the canonical order of step 1, so every clique is visited
   at most once. Cliques of size seven are the frozen target; the largest clique
   size found is recorded whatever it is.
4. Quotient by the two symmetries of §2 before reporting: sets are canonically
   ordered, and a set is reported only if it is lexicographically not greater
   than its pointwise negation. The quotient is a reporting and counting device
   and never a pruning device on the trust path, because pruning by an
   unverified symmetry argument could omit a witness.

Exhaustive versus sampled. Steps 1 to 3 are exhaustive over `R(H)`. Nothing is
sampled. If a larger envelope is later wanted, `H` is raised and the whole run
is repeated; a partially completed envelope is reported as partial with the
exact prefix of the canonical order that was covered.

Boundary of the claim the slice can support. Completing the run supports exactly
one statement: no rational Diophantine septuple exists all of whose entries have
height at most `H`. It does not entail that no septuple exists, does not bound
the height of a septuple, it is not evidence for nonexistence, and it may not be
reported as any of those. The same boundary applies to the largest clique size
found: "the largest verified tuple within height `H` has size five" is a bounded
fact about `R(H)` and nothing else.

Exploration lane, kept off the trust path. Approximate real solutions of the 21
simultaneous conditions may be used to propose candidate rationals. Such output
is labelled exploration-only, is never rounded into a result, and reaches the
record only after the exact verifier of §8 accepts a fully rational candidate.

## 8. Certificate and verifier contract

Result shape 1: a septuple. Certificate format is a canonically serialized
object with a `entries` array of seven `[p, q]` integer pairs and a `witnesses`
array of 21 records, each `{"i": i, "j": j, "r": [p, q]}` with `i < j`. The
independent verifier, which does not share code with the search, re-derives
lowest terms for every entry and every witness, checks `q > 0` and
`gcd(p, q) = 1`, checks that all seven entries are nonzero and pairwise
distinct, checks that the 21 index pairs are exactly the unordered pairs of
`{1,...,7}` each occurring once, and for each pair checks
`r_ij^2 = a_i a_j + 1` by exact rational arithmetic on integers. It reports
separately whether any witness is `0`, so the flag of §2 is raised
mechanically rather than by human attention.

Result shape 2: a bounded exhaustion. Certificate format records `H`, the exact
`card R(H)`, the sha256 content hash of the canonically serialized `R(H)`, the
exact number of square tests performed, the exact edge count of `D(H)`, the
largest clique size found, and the canonical serialization of one largest
clique. The independent verifier replays the enumeration deterministically from
`H` alone, re-derives the hash, and re-checks the reported clique. Its verdict
is a bounded exclusion carrying the height bound in the record; the record
format has no field in which a nonexistence claim could be written.

Result shape 3: an obstruction for a defined construction family. The family
must first be given by an explicit parametrization, for instance entries given
as fixed rational functions of one rational parameter `t`. The certificate is
then an exact algebraic infeasibility certificate for the resulting polynomial
system over `Q`: an explicit identity expressing `1`, or another unit, as a
polynomial combination of the system's generators, so that the verifier confirms
infeasibility by exact polynomial arithmetic and coefficient comparison rather
than by rerunning an algebra engine. The verifier's verdict is scoped to the
parametrization it was given and to nothing else.

Refused as a certificate, without exception:

- floating-point output of any kind, including a residual, a tolerance, a
  numerically found near-solution, and an approximate square root;
- a model's assertion that a set works, at any confidence;
- an unreplayed third-party program's verdict, including a computer-algebra
  transcript that the independent verifier has not re-derived;
- failure of a search, whether bounded, exhaustive, or long-running;
- a sextuple plus an argument that it "should" extend.

## 9. Useful negative outcomes

Nothing found is still a retained result, recorded machine-readably.

- **Exclusion set.** The completed height-bounded exhaustion, with `H`, the
  content hash of `R(H)`, and the largest clique size found. This is a durable
  bounded fact and later runs at larger `H` may cite it as covered ground.
- **Frontier.** The largest exactly verified tuple within the envelope, with its
  entries and its witnesses. If it is a sextuple, the record states which of the
  candidate seventh entries within height `H` failed, and against which pair.
- **Reduction.** The compatibility-graph formulation itself, including the exact
  edge density of `D(H)` as a function of `H`, which is a measured quantity and
  the input to any later argument about why cliques of size seven are rare or
  absent in low height.
- **Refuted route.** A defined construction family with an exact obstruction
  certificate. Its scope is the family and only the family, per §2 and the
  intake assumption `family_obstruction_boundary`.
- **Refused route.** Any numerical route that produced an appealing
  near-solution which the exact verifier rejected, preserved with the
  rejection reason, so the same route is not re-run blind.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics.

- `normalized_rationals_enumerated`
- `exact_rational_square_tests_performed`
- `pairwise_compatible_edges_found`
- `largest_exactly_verified_tuple_size`
- `septuple_certificates_independently_verified`
- `height_bounded_exhaustions_completed`
- `construction_families_defined_and_refuted`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria.

- an exhibited seven-element set of distinct nonzero rationals with all 21 exact
  rational square roots re-squared and accepted by an independent exact verifier
- a proved obstruction for an explicitly parametrized construction family, with
  the family definition and the exact algebraic certificate both recorded
- a completed height-bounded exhaustion reported strictly as a bounded exclusion
  with its height bound stated
- or an explicit unresolved outcome that records the smallest remaining
  obligation together with the exclusion set already established

Stopping rules.

- stop on an exact septuple certificate accepted by the independent verifier
- stop when the frozen height envelope is fully exhausted, recording the bounded
  exclusion and nothing stronger
- stop when the fresh model spend reaches USD 20
- stop when no new compatible pair, no larger verified tuple, and no new refuted
  family have been produced across two consecutive review points
- never promote a completed bounded search into a nonexistence claim, an
  asymptotic claim, or evidence for either

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Zero admitted by accident | `0 * a + 1 = 1` is a square, so a sextuple plus zero passes a careless verifier and looks like a solved target | the verifier checks `a_i != 0` before anything else, and the assumption `entries_are_nonzero_rationals` is frozen in the intake |
| Duplicate entries in different representations | `1/2` and `2/4` are one rational; a verifier comparing strings would accept six distinct values as seven | normal form with `q > 0` and `gcd(p, q) = 1` is re-derived by the verifier, not trusted from the certificate |
| Floating-point square test | `sqrt` on a large rational silently rounds and admits a non-square | exact integer square root with remainder check only; `exact_arithmetic_requirement` is frozen and the verifier shares no code with the search |
| Height-bounded exhaustion read as nonexistence | the most likely misreport of a null result, and it converts a bounded fact into a false universal claim | `bounded_exhaustion_boundary` is frozen; the exhaustion record has no nonexistence field; a stopping rule forbids the promotion explicitly |
| Family obstruction read as global obstruction | a clean proof about one parametrization reads like a proof about the problem | the family must be parametrized before the attempt, and the certificate's scope is the parametrization; `family_obstruction_boundary` is frozen |
| Coefficient growth | products of high-height rationals produce large integers, and a careless implementation reaches for floats for speed | unbounded integers throughout; cost is a metric to be reported, never a reason to relax arithmetic |
| The question is already settled | if a septuple is already published, the slice is reproduction, and reporting it as discovery would be a false novelty claim | §6.1 and §6.2 are named for the ADR-0055 pre-research re-check, which must run before any spend |
| The stricter square convention | a septuple containing a pair with product `-1` may be valid here and invalid in the literature | the verifier raises the zero-witness flag mechanically; §13 Q2 asks the operator to decide before the result is reported |
| Search cost misjudged | clique search on a dense graph can blow up well before the envelope is covered | `H` is frozen before the run, partial coverage is reported as the exact covered prefix, and stagnation is a stopping rule |

## 12. Capability check

Covered by existing capabilities.

- Exact integer and rational arithmetic with unbounded integers, from the
  standard library, consistent with the repository's standard-library-first rule
  and with the owner's rejection of floating-point solvers.
- Declarative problem intake against
  `schemas/problem-definition-v1.schema.json`, validated offline, which creates
  no trust: the intake demo reports `logical_status unknown`,
  `novelty_status not_assessed`, `significance_status not_assessed`, and zero
  warrants.
- Deterministic serialization, content hashing, bounded subprocesses, captured
  output, and no-network execution, per the standing engineering rules.
- Durable machine-readable retention of failures and unresolved outcomes under
  `make report`, which is where the exclusion set and frontier of §9 belong.

Would require a new ADR.

- **Execution of model-generated search code.** Under ADR-0057 production
  generated-code execution stays disabled until its digest-pinned OCI sandbox
  gate passes. The enumeration and the verifier of §7 and §8 must therefore be
  repository-authored code exercised by the offline suite, not a program written
  by a model and run by the campaign control plane.
- **A computer-algebra dependency.** The obstruction route of §8 needs Groebner
  or resultant machinery over `Q`. A third-party algebra package is a pinned
  dependency with a recorded license and a declared gated boundary, so it is a
  new ADR; a repository-authored exact Buchberger implementation over
  `fractions` avoids the dependency but is a new module with its own acceptance
  suite and thresholds.
- **Source acquisition.** Every row of §5 needs the separately authorized
  ADR-0050 exact-URL step, and the two `locator_unresolved` rows additionally
  need the separately authorized ADR-0051 discovery query. Neither is authorized
  by this dossier.
- **Anything numerical.** No numerical solver is adopted, now or as a gated
  adapter. If an exploration lane is wanted, it is a separate decision and its
  output is labelled exploration-only by construction.

Not needed and not requested: parallel specialists, evolutionary search, higher
search tiers, embeddings, a web surface, or any additional model provider path.

## 13. Open questions before intake

1. **Nonzero entries.** Confirm that excluding `0` is the intended reading. The
   frozen conventions rest on it; admitting `0` would make the target reachable
   from any sextuple and would need a different target.
2. **The zero square root.** Decide whether `r_ij = 0`, that is a pair with
   `a_i a_j = -1`, is admitted. This dossier admits it and flags it. The
   literature convention is unknown here and this is the one convention where
   the frozen choice could make an exhibited object acceptable locally and
   unacceptable against the source.
3. **Height envelope.** Fix `H` for the first run before it starts. The frozen
   target has no height, so `H` is a protocol parameter and must not be tuned
   after seeing which sets appear.
4. **Family for the obstruction lane.** If the obstruction outcome shape is
   wanted, supply the exact parametrization to be refuted. Without it the
   obstruction has no stated scope and cannot be certified.
5. **Acquisition authorization.** Confirm whether the ADR-0051 discovery query
   and the ADR-0050 acquisitions of §5 are to be planned at all, and supply
   this dossier as the local context file whose exact substrings the query
   terms must match.
6. **Re-check ordering.** Confirm that the ADR-0055 pre-research novelty
   re-check covering §6.1 to §6.3 runs before any search spend, since a
   settled question turns this slice into a reproduction that must be reported
   as one.
