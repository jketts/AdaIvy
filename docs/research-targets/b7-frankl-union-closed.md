# B7. Frankl union-closed sets, linear triple-generated class — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B7 (tier B)
**Declared domain:** extremal-set-theory
**Intake file:** docs/research-targets/intake/b7-frankl-union-closed-v1.json
**Frozen in one line:** For every union-closed family `F` obtained as the
union-closure of `m >= 1` pairwise distinct `3`-element sets whose pairwise
intersections have size at most one, some element of the ground set lies in at
least half the members of `F`.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish that any statement is open, authorize source
acquisition, assess novelty or significance, create mathematical warrant, or
activate any capability. Novelty, significance, and source applicability are
`not_assessed`, and in particular this dossier does not claim that the frozen
structural class is new. Whether the class is already covered by a published
special case is an untrusted status question with a named acquisition target in
section 5 and the top row of the risk register in section 11.

## 1. Frozen target

Let `m >= 1` be an integer. Let `G = {A_1, ..., A_m}` be a family of `m`
pairwise distinct sets such that

- `card(A_i) = 3` for every `i in {1,...,m}`, and
- `card(A_i intersect A_j) <= 1` for every `i != j`.

Call such a `G` a *linear `3`-uniform generating system*. Define its
union-closure

`F(G) = { union of A_i over i in S : S subset of {1,...,m} }`,

where the empty index set `S = empty` contributes the empty set. Let
`U(F) = union of A over A in F(G)` be the ground set, and for `x in U(F)` let

`freq_F(x) = card({A in F(G) : x in A})`.

**Frozen claim.** For every `m >= 1` and every linear `3`-uniform generating
system `G` there exists `x in U(F)` with

`2 * freq_F(x) >= card(F(G))`,

where `card(F(G))` is the number of *distinct* members of `F(G)` and counts the
empty set.

Every symbol is defined above. The quantifier order is: for all `m`, for all
`G`, there exists `x`, for all `A in F(G)` (membership of `x` in `A` decides the
count). There is no asymptotic in this target, so no epsilon form is needed.
The bound is a non-strict integer inequality, evaluated without division.

The headline conjecture — every finite union-closed family with at least one
nonempty member has an element in at least half its members — is **not** the
target. The frozen target is the same conclusion restricted to one exactly
defined structural class, which makes it a strict special case.

### Why this class, and why the parameter is pinned at 3

Three properties make the class a defensible freeze rather than an arbitrary
restriction.

1. *It is closed and exactly checkable.* Membership in the class is decided by
   two integer conditions on a finite list of triples. There is no hidden
   analytic or lattice-theoretic side condition to discover later.
2. *The bound is attained inside the class.* When the `m` generators are
   pairwise disjoint, `card(F) = 2^m` and every ground-set element has
   frequency exactly `2^(m-1) = card(F)/2`. Equality is therefore attained for
   arbitrarily large families in the class, so the claim cannot be strengthened
   to a strict inequality and the class is not a case where the conclusion has
   slack to spare.
3. *It avoids the two structural hypotheses that make the classical special
   cases easy.* For `k = 3` no member of `F` has size one or two unless
   generators collapse, and the family is exponentially small in its ground set
   (`card(F) <= 2^m` with `card(U(F)) <= 3m`), so it is neither a
   small-member case nor a large-family case.

`k` is pinned at `3` because `k = 2` makes `G` the edge set of a simple graph,
which is a visibly different and more classical object, and because "for all
`k >= 2`" is a disjunction over parameters rather than one target. Both
readings are recorded as rejected in section 2.

Plausibility that the class is not a restatement of a classical case is argued,
not asserted: the pairwise-disjoint subcase is a Boolean lattice and is
therefore expected to be inside known lattice-theoretic results, while a
system with overlaps need not be, and that gap is exactly where the target has
content. This is an argument for choosing the freeze, not a novelty finding.
Novelty stays `not_assessed`.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| union-closed | for all `A, B in F`, including `A = B`, `A union B in F` | closure under intersection; closure only over distinct pairs; closure only over nonempty subfamilies of size `>= 3` |
| empty set as a member | permitted, and present in every family of the class as the empty union | families required to omit the empty set |
| `card(F)` | number of distinct members, counting the empty set when present | count that omits the empty set; `2^m`; the number of generators |
| element | element of `U(F)`, the union of all members of `F` | a member of `F`; an element of a fixed prescribed ground set larger than `U(F)` |
| at least half | `2 * freq_F(x) >= card(F)`, integer comparison | strict `>`; `freq_F(x) >= ceil(card(F)/2)` evaluated by division; a rational or floating-point ratio |
| structural condition | `F` is the union-closure of `m >= 1` pairwise distinct `3`-element sets with pairwise intersections of size `<= 1` | union-closure of arbitrary generators; `k`-uniform for all `k >= 2` at once; `k = 2`; multiset of generators with repeats; generators allowed to be equal |
| linear | `card(A_i intersect A_j) <= 1` for `i != j` | pairwise disjoint (`= 0`), which is the tight subcase, not the class; `<= 2`, which imposes nothing on triples |
| `m` | number of generators, `m >= 1`, finite | `m = 0`, which would give `F = {empty set}` and no nonempty member |
| generating system identity | a *set* of triples, so duplicates are impossible | a list or multiset of triples |
| ground set | `U(F)`, determined by `G`, with no isolated points | an ambient `{1,...,n}` chosen independently of `G` |
| at least one nonempty member | automatic, since `A_1 in F` and `card(A_1) = 3` | a live hypothesis that has to be assumed separately |
| frequency | exact integer count of members containing `x` | weighted, normalized, or averaged frequency |

## 3. Formalization and quantifiers

Statement, as carried in the intake file:

```
forall m in Z with m >= 1,
forall G = {A_1,...,A_m} pairwise distinct sets with card(A_i) = 3 for all i
  and card(A_i intersect A_j) <= 1 for all i != j,
let F = { union(A_i for i in S) : S subset of {1,...,m} }
and U = union(A for A in F);
then exists x in U with 2 * card({A in F : x in A}) >= card(F),
where card(F) counts distinct members and includes the empty set from S = empty
```

Quantifiers, explicitly:

- `forall m` an integer with `m >= 1`.
- `forall G` a family of `m` pairwise distinct `3`-element sets with
  `card(A_i intersect A_j) <= 1` for every `i != j`.
- `forall S subset of {1,...,m}`, the union of `A_i` over `i in S` is a member
  of `F`, the empty `S` giving the empty set.
- `exists x in U(F)`.
- `forall A in F`, membership of `x` in `A` is decided exactly.

Formal language `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment is required and has not been given.

Two facts about the formalization are worth stating because they remove
hypotheses rather than add them. First, `F(G)` is union-closed for free: the
union of the union over `S` and the union over `T` is the union over
`S union T`. Second, `m >= 1` forces a nonempty member, so the headline
hypothesis is never a live side condition inside the class.

## 4. Semantic alignment to the source statement

The source statement here is the planning dossier's rendering of Frankl's
conjecture, which is itself an untrusted planning artifact; no primary source
has been acquired.

**Quantifier mapping.**

| Source | Local |
|---|---|
| every finite union-closed family `F` with at least one nonempty member | every `F = F(G)` for `G` a linear `3`-uniform generating system with `m >= 1` |
| there is an element | there exists `x in U(F)` |
| belonging to at least half of its sets | `2 * freq_F(x) >= card(F)` in integers |
| closed under union | closed under the union of any two members, including a member with itself |

**Definition mapping.**

| Source term | Local meaning |
|---|---|
| union-closed family | closed under the union of any two members, empty set permitted |
| element | element of the ground set `U(F)` |
| `card(F)` | number of distinct members, counting the empty set |
| structural condition | union-closure of `m >= 1` distinct triples with pairwise intersections `<= 1` |
| at least half | non-strict `2 * freq_F(x) >= card(F)` |

**Assumption delta.**

- The headline conjecture assumes only union closure plus one nonempty member;
  the frozen target adds the linear `3`-uniform generating condition, so it is
  a strict special case.
- The uniformity parameter is frozen at `3`; the all-`k` statement and the
  `k = 2` statement are separate targets and are not claimed.
- The empty set is admitted as a member and counted in `card(F)`, which
  strengthens the burden relative to the convention that omits it.
- No novelty is asserted for the frozen class; whether it is already covered by
  a published special case is `not_assessed`.

**Edge-case delta.**

- `m = 1` gives `F = {empty set, A_1}`, `card(F) = 2`, and every `x in A_1` has
  frequency `1 = card(F)/2`: equality.
- Pairwise disjoint generators give `card(F) = 2^m` and frequency `2^(m-1)` for
  every ground-set element: equality for arbitrarily large `m`.
- `F = {empty set}` is outside the class because `m >= 1` forces a `3`-element
  member.
- Overlapping generators collapse distinct index sets to equal unions, so
  `card(F) < 2^m` in general and `card(F)` must be read off the deduplicated
  member set, never computed as `2^m`.
- The empty member contributes to `card(F)` and to no frequency, so it works
  against the claim and is deliberately retained.

**Strength relation:** `weaker`. The frozen target is a strict special case of
the headline problem. It is not `equivalent`, and cannot be, because no primary
source has been acquired or quoted.

## 5. Provenance and acquisition plan

No source is acquired by this dossier. Every row is a target an operator would
acquire under ADR-0050 as a human-planned, exact-URL, separately authorized
public fetch. Volume, page, and DOI fields are deliberately left to be resolved
from the publisher record at acquisition time and are **not asserted here**;
guessing an identifier would manufacture a citation.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Original statement of the union-closed sets conjecture attributed to Frankl (1979) | primary bibliographic record for Frankl's 1979 problem statement; exact volume, pages, and identifier to be resolved by the operator, not guessed here | settles the exact original conventions: empty set membership, whether `card(F)` counts it, and what "element" ranges over — the claims in section 6 rows 1 and 2 | pending_acquisition, applicability not_assessed |
| Bruhn and Schaudt, survey of the union-closed sets conjecture, *Graphs and Combinatorics* (2015) | article record by author, title, journal, year; identifier to be resolved at acquisition | settles which structural classes are already published, which is the top risk row and section 6 row 3 | pending_acquisition, applicability not_assessed |
| Gilmer (2022) constant-fraction lower bound preprint and the immediate follow-up improvements | preprint record by author, title, year; arXiv identifier to be resolved at acquisition | settles section 6 row 4, the reported general constant below one half, and whether any of those methods already covers the frozen class | pending_acquisition, applicability not_assessed |
| Literature on union-closed families arising from linear hypergraphs or partial Steiner triple systems | subject search to be planned by the operator with exact terms recorded, then exact-URL acquisition of each hit | settles whether the frozen class is a restatement — the top risk row | pending_acquisition, applicability not_assessed |
| Literature on Frankl's conjecture for lower semimodular lattices | article record to be resolved by the operator | settles whether the pairwise-disjoint subcase, a Boolean lattice, and the overlapping cases are already covered — section 6 row 3 | pending_acquisition, applicability not_assessed |

Under ADR-0051 an operator may run one Crossref metadata query whose terms are
exact-normalized substrings of a supplied local context file. That query would
produce inspiration-only candidates. It does not acquire anything, does not
satisfy the ADR-0055 re-check, and creates no relevance or applicability.

## 6. Prior-status claims to re-check

Each of these is **untrusted**. None is acquired, quoted, or verified. Each is
named as a claim the ADR-0055 pre-research novelty re-check must cover before
any research on this target starts.

1. **Untrusted:** the planning dossier's rendering of the conjecture — "every
   finite union-closed family with at least one nonempty member contains an
   element belonging to at least half of its sets" — is faithful to the
   original statement, including the empty-set conventions.
2. **Untrusted:** the original statement counts the empty set in `card(F)` and
   quantifies "element" over the union of all members. This dossier freezes
   both readings; the freeze is a choice, not a finding.
3. **Untrusted, and unsourced recollection carried into this dossier:** the
   conjecture is settled for families containing a member of size one or two,
   for families realizable as lower semimodular lattices, and for sufficiently
   small ground sets. Each must be revalidated, and the frozen class must be
   compared against every one of them.
4. **Untrusted, and unsourced recollection:** there is a general positive-
   fraction partial result strictly below one half. If true it does not settle
   the frozen target, but it may already cover the frozen class, which is
   precisely the rediscovery risk.
5. **Untrusted:** the planning dossier's own risk statement, that this item has
   extensive literature and a deceptively simple statement creating high
   rediscovery and hidden-hypothesis risk.
6. **Untrusted:** that the frozen class has not already been published under
   another name — partial Steiner triple system closures, linear hypergraph
   closures, or triple-system generated lattices. This is the claim the
   re-check most needs to resolve, and a negative search result never means
   novel.

## 7. Bounded first slice

**Inputs.** No external input. The slice generates its own objects.

**Envelope E1 — full enumeration up to isomorphism, `1 <= m <= 6`.**
Enumerate isomorphism classes of linear `3`-uniform generating systems with `m`
generators and no isolated ground-set points, by orderly generation: extend a
canonical system by one triple that is lexicographically greater than the last
under a fixed total order on triples, keep the extension only if the result is
its own canonical form, and prune otherwise. The canonical form is the
lexicographically least edge list over all injections of the ground set into
`{1, ..., 3m}`, computed by exact backtracking over ground-set relabelings.
No isomorphism library is used; see section 12.

Naive filtering is not an option and the arithmetic says why: with
`card(U) <= 3m <= 18`, the ambient triple count is `C(18,3) = 816`, so the raw
space of `6`-subsets is `C(816,6)`, astronomically large. Orderly generation
with canonical pruning is therefore required rather than preferred. The
measured number of isomorphism classes per `m` is an output of the run, not a
prediction of this dossier, and the run carries a hard cap of `10^6` enumerated
classes and records an explicit abort rather than exceeding it.

**Per-system work.** For each `G`: verify `3`-uniformity and linearity in
integers; compute the `2^m <= 64` subfamily unions as sorted tuples; deduplicate
to get `F` and `card(F)`; compute `freq_F(x)` for each of the at most `18`
ground-set points; compute `max_x freq_F(x)` and the integer *slack*
`2 * max_x freq_F(x) - card(F)`. At most `64 * 18 = 1152` membership decisions
per system, all exact integer work.

**Envelope E2 — connected systems, `7 <= m <= 8`.** Restricted to systems whose
generator hypergraph is connected. The restriction is licensed by a reduction
this slice must prove first, not assumed: if `G = G_1 disjoint-union G_2` on
disjoint ground sets then `F(G) = { A union B : A in F(G_1), B in F(G_2) }` with
all pairs distinct, so `card(F) = card(F_1) * card(F_2)` and, for `x` in the
ground set of `G_1`, `freq_F(x) = freq_{F_1}(x) * card(F_2)`. Hence
`2 * freq_F(x) >= card(F)` if and only if `2 * freq_{F_1}(x) >= card(F_1)`, so
the class reduces exactly to its connected members. E1 is enumerated *without*
the connectedness restriction precisely so this reduction can be checked as a
falsifiability probe against unrestricted data before E2 relies on it.

**Exhaustive versus sampled.** E1 and E2 are exhaustive over their stated
envelopes. Nothing is sampled and no random number generator is used, so the
run is byte-reproducible. Everything is exact integer arithmetic; there is no
floating-point value anywhere in the slice.

**Canonicalization and symmetry quotient.** The quotient is by the symmetric
group acting on the ground set, which is sound because relabeling the ground set
permutes members of `F` bijectively and preserves both `card(F)` and the
multiset of frequencies. The canonical-form routine is itself probed: on
`m <= 4` the slice enumerates with and without canonical pruning and asserts
that the class counts agree, because a wrong canonical form silently deletes
systems and would turn a missed counterexample into a false empty result.

**Boundary of the claim the slice can support.** Exhaustion of E1 and E2
entails exactly this: no counterexample to the frozen target exists among
linear `3`-uniform generating systems with at most `8` generators, and at most
`6` in the disconnected case. It entails nothing whatever about `m >= 9`,
nothing about the frozen class as a whole, nothing about `k != 3`, and nothing
about the headline conjecture. It is not evidence *for* the frozen target
beyond its own envelope and may not be reported as such.

## 8. Certificate and verifier contract

**Result shape 1: a counterexample inside the frozen class.** Certificate: a
canonical family record containing the generating system as a sorted tuple of
sorted triples over the relabeled ground set `1..card(U)`, the deduplicated
sorted member list, `card(F)`, the full frequency vector, `max_x freq_F(x)`,
and the witnessing integer inequality `2 * max_x freq_F(x) < card(F)`, plus a
sha256 content hash over the canonical serialization. Independent verifier: a
separate program that reads only the generating system, re-derives `F` from
scratch, re-checks `3`-uniformity and linearity, recomputes every frequency,
recomputes the inequality, and recomputes the hash. A counterexample here is
also a counterexample to the headline conjecture, so the verifier must pass
before the result is described in any other terms.

**Result shape 2: a proof of the frozen target for the whole class.**
Certificate: a proof artifact listing every assumption used, with the frozen
conventions from section 2 restated in the proof's own hypotheses. If a
kernel-checked form is ever attempted, the frozen statement, the empty-set
counting convention, and `k = 3` must appear in the meaning tests, so a proof
of a weaker statement cannot pass as a proof of this one. That path is not
activated here; see section 12.

**Result shape 3: a reduction lemma.** Certificate: the proof, its direction of
use stated explicitly, and a falsifiability probe — a named single-field
mutation of the lemma's hypothesis that must produce a counterexample inside
E1. A reduction lemma with no probe that can make it fail is not accepted,
following the Phase 6 control-suite rule.

**Result shape 4: an exhaustion record.** Certificate: the envelope definition,
the measured class counts per `m`, the slack distribution, the canonical-form
probe results, and the content hash of the whole record. Its entailment is the
narrow statement in section 7 and nothing wider.

**Refused as a certificate, in all four shapes:** any floating-point value; a
model's assertion that a statement holds; the output of an unreplayed
third-party program; the failure of a search to find a counterexample;
agreement between two model runs; and a bounded exhaustion presented as
support for a universal claim.

## 9. Useful negative outcomes

If no counterexample and no proof appear, the following are retained
machine-readably rather than discarded.

- **The connectedness reduction.** Proved or refuted, with its probe. If
  proved, it permanently halves the class that must be considered.
- **The equality frontier.** The exact set of enumerated systems attaining
  slack `0`. The pairwise-disjoint systems attain it; whether they are the
  *only* ones inside the envelope is a bounded classification the slice can
  settle, and the answer is retained either way as a structural observation
  about the class, with no promotion beyond the envelope.
- **The slack distribution.** For each `m`, the minimum slack over enumerated
  classes and a witness attaining it. A minimum slack that stays at `0` and is
  attained only by disjoint systems is a different research situation from one
  where overlapping systems come close, and the record must distinguish them.
- **The exclusion set.** Every enumerated class is recorded as checked, so the
  next run starts from a hashed frontier instead of re-enumerating.
- **Refuted routes.** Any averaging or weight-function argument attempted and
  found to have a gap is preserved with the gap named, following the
  Graffiti-322 precedent of recording the two unproved steps rather than the
  attempt alone.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics:

- `generating_systems_canonically_enumerated`
- `families_exactly_checked`
- `equality_cases_recorded`
- `near_equality_cases_recorded`
- `counterexample_candidates_exactly_refuted`
- `reduction_lemmas_proved`
- `reduction_probes_flipped`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- a rigorous proof of the frozen target for the whole frozen class under the
  frozen conventions
- an exact counterexample inside the frozen class, given as a canonical
  content-hashed family with exact integer frequencies and a replayed
  independent check
- a proved reduction lemma that shrinks the frozen class to an exactly stated
  smaller class, with its preservation of union closure and of the target
  property proved in the direction used
- or an explicit unresolved outcome that records the smallest remaining
  obligation

Stopping rules:

- stop on an exact certificate: a replayed counterexample family or a completed
  proof for the frozen class
- stop when fresh model spend for this target reaches USD 20
- stop when no proof obligation has been discharged and no new exclusion
  recorded for two consecutive review points
- never promote exhaustion of the bounded enumeration envelope into the
  unrestricted universal claim, and never present the absence of a
  counterexample in the envelope as evidence for the headline conjecture

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Rediscovery.** The frozen class is already a published special case, possibly under another name. | This is the dominant risk for the item and it would make the whole slice a re-derivation presented as progress. The class is simple enough to have been studied under "partial Steiner triple system", "linear hypergraph closure", or a lattice-theoretic name. | ADR-0055 pre-research re-check is mandatory before any work, with terminology and equivalent-formulation checks over the four acquisition rows in section 5. Novelty stays `not_assessed` regardless of outcome, and an empty search never means novel. |
| Hidden hypothesis in the source statement. | If the original statement excludes the empty set from `card(F)`, or quantifies "element" over an ambient ground set, the frozen target answers a different question. | Both conventions are frozen explicitly in section 2, both rejected readings are named, and the primary-source row in section 5 exists to settle it. `strength_relation` stays `weaker`, never `equivalent`. |
| The class is inside the tight Boolean case only. | If every member of the class is a lower semimodular lattice, the target may follow from a known result and have no content. | The overlapping subcase is exactly where content would live; the slice measures slack separately for disjoint and overlapping systems so an empty content region shows up as data rather than as a surprise later. |
| Enumeration blow-up. | Class counts grow fast in `m`; an unbounded run would stall the slice. | Hard cap of `10^6` enumerated classes with an explicit recorded abort; envelope split into E1 and E2; connectedness reduction proved before it is used to prune. |
| Wrong canonical form. | A buggy canonical form silently deletes isomorphism classes, so a missed counterexample looks like a clean sweep. | Cross-check against unpruned enumeration for `m <= 4` as a falsifiability probe, with the agreement asserted rather than inspected. |
| Reduction that preserves closure but not the target. | The standard trap: a reduction can map union-closed families to union-closed families while creating a half-frequency element the original lacked, proving nothing. | Every reduction states its direction, proves preservation of both properties, and ships a mutation probe that must fail inside E1. |
| Bounded search promoted to a universal claim. | Section 7's exhaustion is narrow; a report that omits the boundary would misstate the result class. | Explicit stopping rule forbidding the promotion; the exhaustion record carries its own entailment statement; ADR-0036 renders anything without a kernel-checked attestation as `Conjecture`. |
| Floating point entering the trust path. | A ratio `freq/card(F)` computed as a float would make the decisive comparison inexact. | The comparison is `2 * freq >= card(F)` in integers, with no division anywhere; the exactness requirement is an explicit assumption in the intake file. |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Phase 1 declarative problem intake and trust policy: the intake file
  validates against `schemas/problem-definition-v1.schema.json` and creates no
  warrant, novelty, or significance.
- Exact integer arithmetic with the Python standard library. The whole slice is
  integer set manipulation; nothing needs a third-party numeric package, which
  matches the engineering rule preferring the standard library for the harness.
- Deterministic serialization, explicit schema versions, and content hashing
  for the canonical family records and the exhaustion record.
- Bounded subprocess execution with captured stdout and stderr, no network, for
  the enumeration and the independent verifier.
- Machine-readable preservation of failed attempts and unresolved outcomes, as
  required for section 9.
- ADR-0047 bounded central-lead runtime, if a model is used at all, to propose
  routes inside content-hashed session bounds with a proposer-only ledger and
  model-free replay. It discharges no obligation and produces no warrant.
- ADR-0055 pre-research novelty re-check, which is a precondition rather than a
  capability this slice adds, and is mandatory here.
- ADR-0036 publication projection if a report is rendered. With no kernel-
  checked attestation the frozen claim renders as `Conjecture`, which is the
  correct class for this slice.

**Would require a new ADR and is not activated by this dossier.**

- Any source acquisition. ADR-0050 permits only public, unauthenticated,
  human-planned, exact-URL fetches, separately authorized. Section 5 is a plan,
  not an authorization.
- Any Lean formalization of this target. The sealed Phase 3B scope is one
  frozen theorem with a supplied proof fragment; admitting a new frozen
  statement, its imports, and its meaning tests is a separate decision.
- Any third-party graph or hypergraph isomorphism dependency. The slice uses a
  standard-library orderly-generation canonical form precisely to avoid one;
  adding a dependency needs pinning, license recording, and an ADR.
- Any parallel, specialist, evolutionary, or higher search tier. ADR-0029
  requires a recorded prediction and measured retention gain first.
- Any automated novelty or significance assessment.

## 13. Open questions before intake

1. Does the operator accept `k = 3` as the frozen uniformity, or should the
   freeze be `k = 2` (graphs) as an easier calibration target first?
2. Should the empty set be counted in `card(F)`? This dossier counts it, which
   is the harder convention. A primary source may settle it the other way, in
   which case the target changes and the alignment must be redone.
3. Is `m <= 8` the right envelope, or should E2 be dropped until the
   connectedness reduction is proved?
4. Should the equality-frontier classification inside the envelope be promoted
   to a second target claim in its own dossier, or stay a retained observation
   under section 9?
5. Which of the five acquisition rows in section 5 does the operator authorize,
   in what order, and with which exact URLs?
