# B7. Frankl union-closed sets conjecture — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B7 (tier B)
**Declared domain:** extremal-set-theory
**Intake file:** docs/research-targets/intake/b7-frankl-union-closed-v1.json
**Frozen in one line:** Every finite union-closed family `F` with at least one
nonempty member contains an element of `U(F)` belonging to at least half the
members of `F`.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish that the conjecture is open, authorize source
acquisition, assess novelty or significance, create mathematical warrant, or
activate any capability. Novelty, significance, and source applicability are
`not_assessed`. The frozen target is the full conjecture; the structural class
in section 7 is a waypoint for the bounded first slice and restricts the target
in no way.

## 1. Frozen target

Let `F` be a finite family of finite sets. `F` is **union-closed** iff

`A union B is in F for all A, B in F`, including the case `A = B`.

Let `U(F) = union of A over A in F` be the ground set, and for `x in U(F)` let

`freq_F(x) = card({A in F : x in A})`.

**Frozen claim.** For every finite union-closed family `F` that has at least one
nonempty member, there exists `x in U(F)` with

`2 * freq_F(x) >= card(F)`,

where `card(F)` is the number of *distinct* members of `F` and counts the empty
set when the empty set is a member.

Every symbol is defined above. The quantifier order is: for all `F`, there
exists `x`, for all `A in F` (membership of `x` in `A` decides the count). There
is no asymptotic in this target, so no epsilon form is needed. The bound is a
non-strict integer inequality, evaluated without division.

The hypothesis that `F` has at least one nonempty member is **explicit**. It
excludes exactly two degenerate families — `F = {}` and `F = {empty set}` — for
which `U(F)` is empty and no element exists to be exhibited. Every other finite
union-closed family is in scope. There is no upper bound on `card(F)`, on
`card(U(F))`, or on the size of any member.

`problem_type` is `explore` because a proof and an exact finite counterexample
are both acceptable outcomes, and `target_claim.scope` is
`unrestricted_universal`.

### What is *not* the target

A theorem for any bounded structural class — including the linear `3`-uniform
generated class used as the first slice's waypoint in section 7 — is progress
toward the frozen target and never its resolution. So is exhaustion of any
finite enumeration envelope. This is recorded as an explicit trap in the intake
file, because a class theorem is the most likely actual outcome and is also the
easiest thing to overstate.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| union-closed | for all `A, B in F`, including `A = B`, `A union B in F` | closure under intersection; closure only over distinct pairs; closure only over subfamilies of size `>= 3` |
| empty set as a member | permitted | families required to omit the empty set |
| `card(F)` | number of distinct members, counting the empty set when present | count that omits the empty set; the number of generators of any generating system for `F` |
| element | element of `U(F)`, the union of all members of `F` | a member of `F`; an element of an ambient ground set chosen independently of `F` |
| at least half | `2 * freq_F(x) >= card(F)`, integer comparison | strict `>`; `freq_F(x) >= ceil(card(F)/2)` evaluated by division; a rational or floating-point ratio |
| at least one nonempty member | explicit hypothesis: some `A in F` with `A != empty` | derived side condition; `F` nonempty alone, which admits `F = {empty set}`; `U(F)` nonempty stated without reference to members |
| finite | `F` finite and every member finite | infinite families; families of infinite sets |
| frequency | exact integer count of members containing `x` | weighted, normalized, or averaged frequency |
| the waypoint class | union-closures of linear `3`-uniform generating systems, used only in section 7 | treating the waypoint class as a hypothesis of the target; treating a class theorem as a resolution |
| linear `3`-uniform generating system | `G = {A_1,...,A_m}`, `m >= 1`, pairwise distinct, `card(A_i) = 3`, `card(A_i intersect A_j) <= 1` for `i != j` | pairwise disjoint (`= 0`), which is the tight subcase; `k = 2`; multiset of generators with repeats |

## 3. Formalization and quantifiers

Statement, as carried in the intake file:

```
forall F a finite family of finite sets with A union B in F for all A, B in F
  (including A = B), and with card({A in F : A != empty}) >= 1,
let U = union(A for A in F);
then exists x in U with 2 * card({A in F : x in A}) >= card(F),
where card(F) counts distinct members and counts the empty set when present
```

Quantifiers, explicitly:

- `forall F` a finite family of finite sets that is closed under the union of
  any two members, including a member with itself.
- The hypothesis `card({A in F : A != empty}) >= 1` is an **explicit
  hypothesis**, not a derived fact, and excludes exactly `F = {}` and
  `F = {empty set}`.
- `exists x in U(F)`, the union of all members of `F`.
- `forall A in F`, membership of `x` in `A` is decided exactly.

Formal language `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment is required and has not been given.

## 4. Semantic alignment to the source statement

The source statement here is the planning dossier's rendering of Frankl's
conjecture, which is itself an untrusted planning artifact; no primary source
has been acquired.

**Quantifier mapping.**

| Source | Local |
|---|---|
| every finite union-closed family `F` | `forall F` finite with `A union B in F` for all `A, B in F`, including `A = B` |
| with at least one nonempty member | explicit hypothesis `card({A in F : A != empty}) >= 1`, excluding exactly `F = {}` and `F = {empty set}` |
| contains an element | there exists `x in U(F)`, the union of all members of `F` |
| belonging to at least half the members of `F` | `2 * freq_F(x) >= card(F)` in integers |

**Definition mapping.**

| Source term | Local meaning |
|---|---|
| union-closed family | closed under the union of any two members, empty set permitted |
| element | element of the ground set `U(F)` |
| `card(F)` | number of distinct members, counting the empty set when present |
| at least half | non-strict `2 * freq_F(x) >= card(F)` |
| at least one nonempty member | some `A in F` with `A != empty`; equivalently `F` is neither empty nor `{empty set}` |

**Assumption delta.** No hypothesis is added to the target.

- No structural hypothesis is added: the frozen target is the full conjecture
  over all finite union-closed families with a nonempty member.
- The linear `3`-uniform generated class appears only as the bounded first
  slice's waypoint; it restricts the target in no way, and a theorem for it is
  progress rather than resolution.
- The empty set is admitted as a member and counted in `card(F)`, which
  strengthens the burden relative to the convention that omits it.
- The nonempty-member hypothesis is explicit rather than derived, and it
  excludes exactly the two families `F = {}` and `F = {empty set}`.
- Whether the frozen empty-set and ground-set conventions match the original
  statement cannot be settled before a primary source is acquired, so the
  strength relation is `unresolved` rather than `equivalent`.
- Novelty and significance are `not_assessed`; no claim is made that any route
  or class considered here is new.

**Edge-case delta.**

- `F = {}` and `F = {empty set}` are excluded by the explicit nonempty-member
  hypothesis, which is the only reason the conclusion is well posed.
- `F = {A}` with `A` nonempty is union-closed, has `card(F) = 1`, and every
  `x in A` has frequency `1 >= 1/2`.
- The empty member contributes to `card(F)` and to no frequency, so it works
  against the claim and is deliberately retained.
- Equality in the half condition satisfies the frozen non-strict inequality.
- Inside the waypoint class, pairwise disjoint generators attain equality for
  arbitrarily large families, so no strict-inequality strengthening is available
  even in that special case.
- A generator-based encoding never determines `card(F)`: overlapping generators
  collapse distinct unions, so `card(F)` must be read off the deduplicated
  member set.

**Strength relation:** `unresolved`. The local formalization is intended to be
the same statement as the source, but the mapping cannot be settled before the
primary source is acquired — the empty-set counting convention and the range of
"element" are exactly the points at issue. It is not `equivalent`, and cannot
be, because no source text has been quoted.

## 5. Provenance and acquisition plan

No source is acquired by this dossier. Every row is a target an operator would
acquire under ADR-0050 as a human-planned, exact-URL, separately authorized
public fetch. Volume, page, and DOI fields are deliberately left to be resolved
from the publisher record at acquisition time and are **not asserted here**;
guessing an identifier would manufacture a citation.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Original statement of the union-closed sets conjecture attributed to Frankl (1979) | primary bibliographic record for Frankl's 1979 problem statement; exact volume, pages, and identifier to be resolved by the operator, not guessed here | settles the exact original conventions: empty set membership, whether `card(F)` counts it, and what "element" ranges over — the claims in section 6 rows 1 and 2, and the only thing that can move `strength_relation` off `unresolved` | pending_acquisition, applicability not_assessed |
| Bruhn and Schaudt, survey of the union-closed sets conjecture, *Graphs and Combinatorics* (2015) | article record by author, title, journal, year; identifier to be resolved at acquisition | settles which structural classes and which proof routes are already published, which is the top risk row and section 6 row 3 | pending_acquisition, applicability not_assessed |
| Gilmer (2022) constant-fraction lower bound preprint and the immediate follow-up improvements | preprint record by author, title, year; arXiv identifier to be resolved at acquisition | settles section 6 row 4, the reported general constant below one half, and whether that route already subsumes any class the slice attacks | pending_acquisition, applicability not_assessed |
| Literature on union-closed families arising from linear hypergraphs or partial Steiner triple systems | subject search to be planned by the operator with exact terms recorded, then exact-URL acquisition of each hit | settles whether the waypoint class in section 7 is already covered, so the slice does not spend its budget re-deriving a published class theorem | pending_acquisition, applicability not_assessed |
| Literature on Frankl's conjecture for lower semimodular lattices | article record to be resolved by the operator | settles whether the pairwise-disjoint subcase, a Boolean lattice, and the overlapping cases are already covered — section 6 row 3 | pending_acquisition, applicability not_assessed |
| Literature on minimal-counterexample reductions for the conjecture | subject search planned by the operator, then exact-URL acquisition | settles whether any reduction the slice proves is already known, which is the shape of progress most likely to be rediscovered | pending_acquisition, applicability not_assessed |

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
   both readings; the freeze is a choice, not a finding, and it is why
   `strength_relation` is `unresolved`.
3. **Untrusted, and unsourced recollection carried into this dossier:** the
   conjecture is settled for families containing a member of size one or two,
   for families realizable as lower semimodular lattices, and for sufficiently
   small ground sets. Each must be revalidated, and any class the slice attacks
   must be compared against every one of them.
4. **Untrusted, and unsourced recollection:** there is a general positive-
   fraction partial result strictly below one half. If true it does not settle
   the frozen target, but it may already subsume the waypoint class, which is
   precisely the rediscovery risk.
5. **Untrusted:** the planning dossier's own risk statement, that this item has
   extensive literature and a deceptively simple statement creating high
   rediscovery and hidden-hypothesis risk.
6. **Untrusted:** that the waypoint class in section 7 has not already been
   published under another name — partial Steiner triple system closures,
   linear hypergraph closures, or triple-system generated lattices. A negative
   search result never means novel.
7. **Untrusted:** that the disconnected-factorization reduction in section 7 is
   not already known. It is elementary enough that it probably is, and it is
   retained for its use in the slice rather than for any claim about it.

## 7. Bounded first slice

**Waypoint, not target.** The frozen target is the full conjecture. The first
slice attacks one exactly defined class inside it, chosen because it is tight
and exactly checkable, and everything the slice produces is bounded progress
whose boundary is stated with it.

**The waypoint class.** Let `m >= 1` and let `G = {A_1, ..., A_m}` be pairwise
distinct sets with `card(A_i) = 3` for every `i` and
`card(A_i intersect A_j) <= 1` for every `i != j` — a *linear `3`-uniform
generating system*. Its union-closure is

`F(G) = { union of A_i over i in S : S subset of {1,...,m} }`,

where `S = empty` contributes the empty set. Every `F(G)` is a finite
union-closed family with at least one nonempty member, so every `F(G)` is an
*instance* of the frozen target.

**Why this class is worth attacking.** Three reasons, none of which is a
novelty claim.

1. *Exactly checkable.* Membership is decided by two integer conditions on a
   finite list of triples; there is no hidden analytic or lattice-theoretic
   side condition to discover later.
2. *The bound is attained inside it.* When the `m` generators are pairwise
   disjoint, the `2^m` subfamily unions are pairwise distinct, so
   `card(F) = 2^m`, and every `x in U(F)` lies in exactly the unions indexed by
   sets containing the one generator that contains `x`, giving
   `freq_F(x) = 2^(m-1) = card(F)/2` for every `x`. Equality is attained for
   arbitrarily large families, so the class is tight rather than slack and the
   conclusion cannot be strengthened to a strict inequality even here.
3. *It avoids the two hypotheses that make the recalled special cases easy.*
   For `k = 3` no member has size one or two unless generators collapse, and
   the family is exponentially small in its ground set
   (`card(F) <= 2^m`, `card(U(F)) <= 3m`), so it is neither a small-member case
   nor a large-family case.

The pairwise-disjoint subcase is a Boolean lattice and is therefore likely
inside known lattice-theoretic results; the overlapping systems need not be,
and that gap is where content would live. This is a reason for choosing the
waypoint, not a finding about it.

**Envelope E1 — full enumeration up to isomorphism, `1 <= m <= 6`.** Enumerate
isomorphism classes of linear `3`-uniform generating systems with `m` generators
and no isolated ground-set points, by orderly generation: extend a canonical
system by one triple lexicographically greater than the last under a fixed total
order on triples, keep the extension only if the result is its own canonical
form, prune otherwise. The canonical form is the lexicographically least edge
list over all injections of the ground set into `{1, ..., 3m}`, computed by
exact backtracking over ground-set relabelings. No isomorphism library is used;
see section 12.

Naive filtering is not an option and the arithmetic says why: with
`card(U) <= 3m <= 18`, the ambient triple count is `C(18,3) = 816`, so the raw
space of `6`-subsets is `C(816,6)`, astronomically large. Orderly generation
with canonical pruning is therefore required rather than preferred. The measured
number of isomorphism classes per `m` is an output of the run, not a prediction
of this dossier, and the run carries a hard cap of `10^6` enumerated classes and
records an explicit abort rather than exceeding it.

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
falsifiability probe against unrestricted data before E2 relies on it. The
reduction is elementary and may well be known; it is used for its effect on the
slice, not claimed as a result.

**Exhaustive versus sampled.** E1 and E2 are exhaustive over their stated
envelopes. Nothing is sampled and no random number generator is used, so the run
is byte-reproducible. Everything is exact integer arithmetic; there is no
floating-point value anywhere in the slice.

**Canonicalization and symmetry quotient.** The quotient is by the symmetric
group acting on the ground set, which is sound because relabeling the ground set
permutes members of `F` bijectively and preserves both `card(F)` and the
multiset of frequencies. The canonical-form routine is itself probed: on
`m <= 4` the slice enumerates with and without canonical pruning and asserts
that the class counts agree, because a wrong canonical form silently deletes
systems and would turn a missed counterexample into a false empty result.

**Boundary of the claim the slice can support.** Exhaustion of E1 and E2
entails exactly this: no counterexample to the frozen conjecture exists among
union-closures of linear `3`-uniform generating systems with at most `8`
generators, and at most `6` in the disconnected case. It entails nothing about
`m >= 9`, nothing about the waypoint class as a whole, nothing about `k != 3`,
and — most importantly — nothing about the frozen target, which quantifies over
all finite union-closed families with a nonempty member. The waypoint class is
a vanishing fraction of that space. Even a full theorem for the waypoint class
would leave the frozen target open, and the run record must say so in words.

## 8. Certificate and verifier contract

**Result shape 1: a counterexample to the frozen conjecture.** Certificate: a
canonical family record containing the family itself as a deduplicated sorted
member list over the relabeled ground set `1..card(U)`, an explicit
union-closure check over all ordered pairs of members, the witness that some
member is nonempty, `card(F)`, the full frequency vector, `max_x freq_F(x)`,
and the witnessing integer inequality `2 * max_x freq_F(x) < card(F)`, plus a
sha256 content hash over the canonical serialization. If the family came from a
generating system, that system is recorded too, but the certificate must stand
on the member list alone. Independent verifier: a separate program that reads
only the member list, re-checks union closure over all pairs, re-checks the
nonempty-member hypothesis, recomputes every frequency, recomputes the
inequality, and recomputes the hash.

**Result shape 2: a proof of the frozen conjecture.** Certificate: a proof
artifact listing every assumption used, with the frozen conventions from
section 2 restated in the proof's own hypotheses, so a proof under the
empty-set-excluded convention cannot pass as a proof of this target. If a
kernel-checked form is ever attempted, the frozen statement, the empty-set
counting convention, and the explicit nonempty-member hypothesis must appear in
the meaning tests. That path is not activated here; see section 12.

**Result shape 3: a class theorem.** Certificate: the proof, the class stated
exactly, and a machine-readable statement of what remains — namely the frozen
target. Recorded with `class_theorems_proved` incremented and with the class
name in the record, never as a resolution of the conjecture.

**Result shape 4: a reduction lemma.** Certificate: the proof, its direction of
use stated explicitly, and a falsifiability probe — a named single-field
mutation of the lemma's hypothesis that must produce a counterexample inside
E1. A reduction lemma with no probe that can make it fail is not accepted,
following the Phase 6 control-suite rule.

**Result shape 5: an exhaustion record.** Certificate: the envelope definition,
the measured class counts per `m`, the slack distribution, the canonical-form
probe results, and the content hash of the whole record. Its entailment is the
narrow statement in section 7 and nothing wider.

**Refused as a certificate, in all five shapes:** any floating-point value; a
model's assertion that a statement holds; the output of an unreplayed
third-party program; the failure of a search to find a counterexample;
agreement between two model runs; a class theorem presented as a resolution;
and a bounded exhaustion presented as support for the frozen conjecture.

## 9. Useful negative outcomes

If no counterexample and no full proof appear — the realistic case for a
full-conjecture target — the following are retained machine-readably rather
than discarded.

- **The connectedness reduction.** Proved or refuted, with its probe. If
  proved, it permanently halves the waypoint class and may generalize.
- **Any class theorem.** Recorded as bounded progress with the class stated
  exactly and the remaining obligation named.
- **The equality frontier.** The exact set of enumerated systems attaining
  slack `0`. The pairwise-disjoint systems attain it; whether they are the
  *only* ones inside the envelope is a bounded classification the slice can
  settle, and the answer is retained either way with no promotion beyond the
  envelope.
- **The slack distribution.** For each `m`, the minimum slack over enumerated
  classes and a witness attaining it. A minimum slack that stays at `0` and is
  attained only by disjoint systems is a different research situation from one
  where overlapping systems come close, and the record must distinguish them.
- **The exclusion set.** Every enumerated class is recorded as checked, so the
  next run starts from a hashed frontier instead of re-enumerating.
- **Refuted routes.** Any averaging or weight-function argument attempted and
  found to have a gap is preserved with the gap named, following the
  Graffiti-322 precedent of recording the specific unproved steps rather than
  the attempt alone.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics:

- `generating_systems_canonically_enumerated`
- `families_exactly_checked`
- `equality_cases_recorded`
- `near_equality_cases_recorded`
- `counterexample_candidates_exactly_refuted`
- `class_theorems_proved`
- `reduction_lemmas_proved`
- `reduction_probes_flipped`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- a rigorous proof of the frozen conjecture under the frozen conventions
- an exact counterexample: a canonical content-hashed union-closed family with
  at least one nonempty member, exact integer frequencies, and a replayed
  independent check that no element reaches half
- a proved theorem for an exactly stated structural class, recorded as bounded
  progress toward the conjecture and never as its resolution
- a proved reduction that replaces the conjecture by an exactly stated smaller
  class of potential minimal counterexamples, with preservation of union
  closure and of the target property proved in the direction used
- or an explicit unresolved outcome that records the smallest remaining
  obligation, which is the realistic outcome for a full-conjecture target and
  is not a failure

Stopping rules:

- stop on an exact certificate: a replayed counterexample family or a completed
  proof of the frozen conjecture
- stop when fresh model spend for this target reaches USD 20
- stop when no proof obligation has been discharged and no new exclusion
  recorded for two consecutive review points
- never promote a theorem for a bounded structural class, or exhaustion of the
  bounded enumeration envelope, into the frozen conjecture, and never present
  the absence of a counterexample as evidence for it

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Rediscovery.** Any route or class the slice reaches is already published. | This is the dominant risk for the item, and freezing the **full conjecture** raises it rather than lowering it: the target now sits under the whole literature, so every partial route in that literature is a route this work can unknowingly repeat, and every class theorem the slice might prove is a candidate for having been proved already. A subclass target would at least have been narrow. | ADR-0055 pre-research re-check is mandatory before any work, with terminology and equivalent-formulation checks over all six acquisition rows in section 5. Novelty stays `not_assessed` regardless of outcome, and an empty search never means novel. Section 6 row 7 pre-registers the expectation that the elementary reduction is already known. |
| Class theorem overstated as a resolution. | A theorem for the waypoint class is the most likely real outcome and the easiest thing to misreport, especially in a summary line. | Recorded as an explicit trap in the intake file; result shape 3 in section 8 requires the remaining obligation to be stated in the record; a stopping rule forbids the promotion; ADR-0036 renders the frozen claim as `Conjecture` absent a kernel-checked attestation. |
| Hidden hypothesis in the source statement. | If the original statement excludes the empty set from `card(F)`, or quantifies "element" over an ambient ground set, the frozen target answers a different question. | Both conventions are frozen explicitly in section 2 with rejected readings named; the primary-source row in section 5 exists to settle it; `strength_relation` stays `unresolved` until it is settled, and can never become `equivalent` without an acquired quotation. |
| The waypoint class has no content. | If every member of the class is a lower semimodular lattice, a class theorem may follow from a known result and buy nothing toward the target. | The overlapping subcase is where content would live; the slice measures slack separately for disjoint and overlapping systems so an empty content region shows up as data rather than as a surprise later. |
| Enumeration blow-up. | Class counts grow fast in `m`; an unbounded run would stall the slice. | Hard cap of `10^6` enumerated classes with an explicit recorded abort; envelope split into E1 and E2; connectedness reduction proved before it is used to prune. |
| Wrong canonical form. | A buggy canonical form silently deletes isomorphism classes, so a missed counterexample looks like a clean sweep. | Cross-check against unpruned enumeration for `m <= 4` as a falsifiability probe, with the agreement asserted rather than inspected. |
| Reduction that preserves closure but not the target. | The standard trap: a reduction can map union-closed families to union-closed families while creating a half-frequency element the original lacked, proving nothing. | Every reduction states its direction, proves preservation of both properties, and ships a mutation probe that must fail inside E1. |
| Bounded search promoted to the conjecture. | Section 7's exhaustion covers a vanishing fraction of the target's scope; a report that omits the boundary would misstate the result class. | Explicit stopping rule; the exhaustion record carries its own entailment statement in words; the counterexample certificate is required to stand on the member list alone, so it is checkable against the full statement rather than against the waypoint class. |
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

1. Does the operator accept the full conjecture as the frozen target, given
   that the realistic outcome is an unresolved record plus at most a class
   theorem, and that this is stated as such in the success criteria?
2. Should the empty set be counted in `card(F)`? This dossier counts it, which
   is the harder convention. A primary source may settle it the other way, in
   which case the target changes and the alignment must be redone.
3. Is the linear `3`-uniform class the right waypoint, or should the slice
   start at `k = 2` (graphs) as an easier calibration target?
4. Is `m <= 8` the right envelope, or should E2 be dropped until the
   connectedness reduction is proved?
5. Should the equality-frontier classification inside the envelope be promoted
   to its own dossier, or stay a retained observation under section 9?
6. Which of the six acquisition rows in section 5 does the operator authorize,
   in what order, and with which exact URLs?
