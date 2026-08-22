# Candidate Research Dossier — Flagship and Follow-on Targets

**Compiled:** 21 August 2026
**Portfolio size:** 20 candidate problems
**Purpose:** record a ranked research portfolio for later, one-problem-at-a-time
AdaIvy intake and human approval.

This is a planning dossier, not a canonical Phase 1 `ResearchDossier`. It does
not approve a formalization, establish that a problem is open, authorize source
acquisition, assess novelty or significance, create mathematical warrant, or
activate a new runtime capability. Before work starts on any item, its exact
statement, definitions, open status, source rights, evaluation protocol, and
stopping rules must be frozen in a separate declarative problem definition and
reviewed under the existing trust policy.

**Expanded 22 August 2026.** All twenty candidates below have been expanded into
individually scoped dossiers with validated declarative intake files; see
[docs/research-targets/INDEX.md](research-targets/INDEX.md). Those dossiers
freeze one exact target each and supersede the candidate descriptions here where
the two differ -- six targets were escalated from a subclass or single parameter
to their full statements, and A2 was re-frozen after the pair it named was shown
to be extendible. This planning dossier is unchanged otherwise and remains the
record of the original tiering. Expansion authorizes nothing.

The ranking and most candidate descriptions below come from the operator's
supplied notes. The five numbered Erdős statements were checked against the
Erdős Problems catalogue on the compilation date. The MUB subproblem was checked
against McNulty and Weigert's 2026 review. All literature-status statements are
still `not_assessed` for AdaIvy purposes until a proper source-applicability and
novelty review is recorded.

## Portfolio at a glance

| ID | Tier | Candidate | Initial result shape |
|---|---|---|---|
| A1 | A | Erdős #128 | proof, counterexample, or improved constant |
| A2 | A | Dimension-six MUB review, Problem 10.6 | exact unextendibility certificate for one frozen pair |
| A3 | A | Erdős #167 (Tuza's triangle problem) | proof, counterexample, or improved covering bound |
| A4 | A | Total coloring of planar graphs with maximum degree 6 | reducible configuration or theorem for a frozen subclass |
| A5 | A | Erdős #663 | theorem for fixed small `k` or sharper asymptotic bound |
| A6 | A | A remaining small cubic Diophantine equation | integral point, infinite family, or finiteness obstruction |
| B1 | B | Graceful Tree Conjecture | new infinite family, reduction, or exact finite extension |
| B2 | B | Erdős #126 | improved lower bound for the prime-divisor function |
| B3 | B | Dense polynomials with sparse squares | exact construction improving the upper bound |
| B4 | B | Rational Diophantine septuple | exact septuple or a rigorous obstruction |
| B5 | B | Earth–Moon problem | certified biplanar graph with chromatic number at least 10 |
| B6 | B | Chowla's cosine problem | explicit family with improved negative excursion |
| B7 | B | Frankl's union-closed sets conjecture | theorem for a new class or exact finite obstruction search |
| B8 | B | EFX allocation existence for at least four agents | exact allocation theorem or finite counterexample |
| B9 | B | Large `ell`-rank in imaginary quadratic class groups | explicit field with independently checked class-group data |
| C1 | C | Baillie–PSW pseudoprime | one exact composite witness |
| C2 | C | Hall-ratio record | one exact integer witness with ratio above 100 |
| C3 | C | Kissing number in dimension 5 | upper bound 43 or lower-bound configuration 41 |
| C4 | C | Ramsey number `R(5,5)` | improved upper or lower bound with certificate |
| C5 | C | Erdős #982 | proof, counterexample, or improved guaranteed distance bound |

Tier A means credible first flagship research target. Tier B means excellent but
higher-risk. Tier C means stretch or computationally expensive. Tier placement
is a portfolio decision, not a significance assessment.

## Tier A — credible first flagship research target

### A1. Erdős #128 — local edge density forcing a triangle

**Candidate statement.** Let `G` be a graph on `n` vertices. If every induced
subgraph on at least `floor(n/2)` vertices has more than `n^2/50` edges, must
`G` contain a triangle?

**Why it fits.** The question combines extremal graph theory with finite search,
flag-algebra or SDP exploration, stability analysis, and exact verification.
The constant 50 is reported as best possible, with blow-ups of `C_5` and the
Petersen graph supplying the boundary examples.

**First bounded slice.** Reproduce the known boundary constructions and earlier
constants exactly, then search small graphs for extremal triangle-free local
density profiles. Any computation may support a conjecture or refute a universal
claim but cannot establish the asymptotic theorem by itself.

**Primary risks.** The catalogue labels the problem `FALSIFIABLE` rather than
`OPEN` and lists a claimed proof. Both the claim thread and post-2025 literature
must be reviewed before activation. A search result must not be promoted into a
proof of the universal statement.

**Checked catalogue source:** [Erdős Problem #128](https://www.erdosproblems.com/128).

### A2. Mutually unbiased bases in dimension 6 — Problem 10.6

**Selected subproblem.** Use Problem 10.6 from McNulty and Weigert's review:
show that a given pair of mutually unbiased bases in `C^6` cannot be extended
to a triple (or quadruple). The first run must freeze one exact algebraic member
of a review-listed pair family, such as `{I, M_6^(1)}`, `{I, K_6^(2)}`, or
`{I, K_6^(3)}`. Choosing the family name alone is not a complete target when it
contains parameters.

**Why this subproblem.** It is a strict stepping stone below Problem 10.2, the
headline conjecture that no four MUBs exist in dimension 6. It still exercises
complex Hadamard matrices, polynomial systems, algebraic geometry, numerical
search, SDP/SOS methods, and exact certificates, while allowing a finite,
auditable first target.

**First bounded slice.** Select one algebraic parameter value with strong
published numerical evidence of unextendibility; encode the unbiasedness
constraints; seek an exact Positivstellensatz, Gröbner-basis, interval-exclusion,
or exhaustive algebraic certificate; and verify that certificate independently.
The parameter value, coefficient field, normalization, symmetry quotient, and
meaning of “extend” must be fixed before search.

**Primary risks.** Numerical failure to find an extension is not an
unextendibility proof. A certificate for one pair says nothing about all pairs,
all members of its family, or the full four-MUB conjecture.

**Checked review source:** Daniel McNulty and Stefan Weigert, [“Mutually Unbiased
Bases in Composite Dimensions — A Review”](https://doi.org/10.22331/q-2026-04-01-2051),
Problem 10.6; see also Problem 10.2 for the headline dimension-six question.

### A3. Erdős #167 — Tuza's triangle problem

**Candidate statement.** If a graph contains at most `k` edge-disjoint
triangles, can it always be made triangle-free by deleting at most `2k` edges?

Equivalently, writing `nu_3(G)` for the maximum number of pairwise edge-disjoint
triangles and `tau_3(G)` for the minimum number of edges meeting every triangle,
is `tau_3(G) <= 2 nu_3(G)` for every finite graph?

**Why it fits.** The problem has exact finite witnesses, mature LP and
combinatorial formulations, natural reductions, and a clean proof/counterexample
bifurcation. `K_4` and `K_5` show that the factor 2 would be best possible.

**First bounded slice.** Build exact packing and covering checkers, reproduce
the sharp examples and best general bounds, and search for new reducible graph
classes or minimal counterexample constraints. A finite sweep remains bounded
evidence only.

**Primary risks.** The statement is broad and well studied. Definitions must
distinguish edge-disjoint triangle packing from vertex-disjoint packing and edge
deletion from vertex deletion.

**Checked catalogue source:** [Erdős Problem #167](https://www.erdosproblems.com/167).

### A4. Total coloring of planar graphs with maximum degree 6

**Candidate statement.** Prove that every finite simple planar graph `G` with
maximum degree `Delta(G) = 6` has total chromatic number
`chi''(G) <= Delta(G) + 2 = 8`.

**Why it fits.** The exceptional degree-six planar case offers a natural chain
from known reducible configurations through automated configuration search,
exact coloring/SAT checks, discharging rules, and a human- or kernel-checked
proof. Partial progress on a broader graph class can remain mathematically
meaningful.

**First bounded slice.** Freeze a planar subclass defined by one currently
unsettled forbidden-configuration condition, then prove an additional reducible
configuration or weaken one published hypothesis. Store the planar embedding,
total-coloring encoding, and any unsatisfiability certificate separately.

**Primary risks.** “Planar,” “maximum degree 6,” and “total coloring” must be
mapped exactly to the cited theorem conventions. Computer-checked reducibility
does not supply the global discharging argument.

**Source status:** statement and August 2026 status are from the operator-supplied
notes; identify and acquire the cited status review before intake.

### A5. Erdős #663 — a small prime missing consecutive integers

**Candidate statement.** For `k >= 2`, let `q(n,k)` be the least prime that does
not divide `product_(1 <= i <= k) (n+i)`. For every fixed `k`, is

`q(n,k) < (1 + o(1)) log n`

as `n -> infinity`? For formal intake, use the equivalent epsilon formulation
rather than leave the asymptotic quantifiers implicit.

**Why it fits.** It supports symbolic and computational exploration while the
target remains a precise asymptotic number-theory claim. Fixed small values of
`k` offer credible intermediate theorems and exact searches for extremal `n`.

**First bounded slice.** Reproduce the easy `(1 + o(1)) k log n` bound, freeze a
small `k`, and seek a sharper theorem or structural characterization of long
initial-prime coverage among `k` consecutive integers.

**Primary risks.** Large computation alone cannot prove the asymptotic claim.
The dependence of thresholds and error terms on fixed `k` must be explicit.

**Checked catalogue source:** [Erdős Problem #663](https://www.erdosproblems.com/663).

### A6. A remaining small cubic Diophantine equation

**Selected candidate.** Determine the integral solutions, and in particular the
finiteness or infinitude of the integral solution set, of

`z^2 + y^2 z + x^3 - 2 = 0`, where `x,y,z in Z`.

**Why it fits.** The target combines exact search for enormous points,
substitution and descent, arithmetic geometry, family detection, and proof of
finiteness or infinitude. A new integral point, an infinite parametrized family,
or a rigorous obstruction can each be retained without being mislabeled as a
complete classification.

**First bounded slice.** Reproduce the known search envelope, normalize obvious
symmetries, test modular and local obstructions, and investigate whether the
surface admits a useful fibration or reduction to curves whose integral points
can be certified.

**Primary risks.** The supplied notes say that this is one of six equations
remaining after three of nine were settled in 2026. That membership and the
precise intended finiteness question must be verified against the original
Epoch problem statement before intake.

**Source status:** candidate equation and status are from the operator-supplied
notes; primary-source verification is pending.

## Tier B — excellent but higher-risk

### B1. Graceful Tree Conjecture

**Candidate statement.** Every tree with `m` edges admits a bijection from its
vertices to `{0,...,m}` such that the absolute differences across its edges are
exactly `{1,...,m}`.

**Useful progress:** a new infinite family, a reduction rule preserving
gracefulness, or a certified extension of the exhaustive frontier. Merely
checking the next vertex count is a capability result, not the preferred
research contribution.

**Verification shape:** an exhibited labeling is checked directly; exhaustive
claims require canonical tree generation, independently checked coverage, and
replayable certificates.

**Source status:** the operator notes report exhaustive verification through 35
vertices as of July 2026; revalidate that frontier before work begins.

### B2. Erdős #126 — prime divisors among pairwise sums

**Candidate statement.** Let `f(n)` be maximal such that for every `n`-element
set `A` of natural numbers, the product of `a+b` over distinct `a,b in A` has at
least `f(n)` distinct prime divisors. Is `f(n)/log n -> infinity`?

**Useful progress:** improve the known lower bound, establish the limit for a
structured class of sets, or find and certify unexpectedly sparse examples.

**Verification shape:** exact prime-divisor sets for finite constructions plus a
separate symbolic proof for any universal or asymptotic claim.

**Checked catalogue source:** [Erdős Problem #126](https://www.erdosproblems.com/126).

### B3. Dense polynomials whose squares are sparse

**Candidate statement.** Let `p(x) = a_0 + a_1 x + ... + a_n x^n` have nonzero
integer coefficients. Construct such polynomials whose squares have
asymptotically few nonzero coefficients, improving the reported upper exponent
`0.811` for the associated extremal function.

**Useful progress:** an exact recursive construction, a better infinite-family
upper bound, or a structural cancellation lemma. Every proposed polynomial and
coefficient cancellation is exactly checkable.

**Verification shape:** sparse integer convolution followed by a proof that the
construction works for the full claimed family.

**Source status:** the supplied rendering loses part of the one-instance
threshold. Freeze the original FrontierMath statement and definition of its
extremal function before formalization; do not infer that threshold from the
damaged typography.

### B4. Rational Diophantine septuple

**Candidate statement.** Find seven distinct rational numbers
`a_1,...,a_7` such that `a_i a_j + 1` is a rational square for every `i != j`.

**Useful progress:** one exact septuple; alternatively, a proved obstruction for
a well-defined construction family. The notes report infinite families of
rational sextuples but no septuple.

**Verification shape:** normalize rational entries, verify distinctness, and
provide the 21 exact rational square roots.

**Primary risk:** a septuple may not exist, and failure within a searched family
does not imply global nonexistence.

### B5. Earth–Moon problem — raise the lower bound from 9 to 10

**Candidate statement.** Construct a graph whose edge set is the union of two
planar graphs and whose chromatic number is at least 10.

**Useful progress:** a single explicit witness raises the stated lower bound for
the chromatic number of biplanar graphs.

**Verification shape:** graph identity, two independently checked planar layer
embeddings, and an exact chromatic lower-bound certificate, preferably with
independent SAT proof checking.

**Source status:** the supplied notes give the current interval as 9 through 12;
revalidate it and the exact definition of biplanar before intake.

### B6. Chowla's cosine problem

**Candidate statement.** For
`f_A(x) = sum_(a in A) cos(ax)`, construct arbitrarily large finite sets `A` in
the domain fixed by the original problem such that the magnitude of the negative
excursion is `o(|A|)`.

**Useful progress:** an explicit infinite construction with an improved
constant or asymptotic bound, supported by exact or certified analytic bounds.

**Primary risk:** the operator notes refer to a concrete FrontierMath version
and compare constants `1` and `1/20`; its normalization, domain for `x`, and
definition of negative excursion must be copied from the primary source before
formalization.

### B7. Frankl's union-closed sets conjecture

**Candidate statement.** Every finite union-closed family with at least one
nonempty member contains an element belonging to at least half of its sets.

**Useful progress:** a theorem for a genuinely new structural class, a reduction
to smaller minimal counterexamples, or an exact finite classification that
advances the known frontier.

**Verification shape:** canonical set-family encoding, exact frequency counts,
and a proof that any claimed reduction preserves union closure and the target.

**Primary risk:** extensive literature and deceptively simple statement create
high rediscovery and hidden-hypothesis risk.

### B8. EFX allocation existence for four or more agents

**Candidate statement.** For additive valuations, determine whether every
finite instance with at least four agents admits an allocation that is
envy-free up to any good (EFX), using the precise convention for unallocated
goods fixed at intake.

**Useful progress:** an exact finite counterexample, an existence proof for a
new valuation class, or a verifiable reduction of minimal counterexamples.

**Verification shape:** rational valuations, a complete allocation, and direct
checking of every EFX inequality; nonexistence needs exhaustive coverage or a
proof, not failure of a search heuristic.

**Primary risk:** EFX variants differ on positivity, zero-valued goods,
charity/unallocated goods, and complete versus partial allocation.

### B9. Large `ell`-rank in imaginary quadratic class groups

**Candidate statement.** For a fixed prime `ell` and a frozen target rank,
construct an imaginary quadratic field whose ideal class group has `ell`-rank
at least that target.

**Useful progress:** one record field or a construction family with a certified
rank lower bound. The operator notes report a record of rank 8 when `ell = 3`
and multiple unachieved target pairs.

**Verification shape:** exact discriminant and defining field, ideal arithmetic,
class-group relation data, and an independently replayed rank certificate.

**Primary risk:** serious algebraic-number-theory tooling is required and must
be separately pinned, licensed, and gated before use.

## Tier C — stretch or expensive

### C1. A Baillie–PSW pseudoprime

**Candidate statement.** Find a composite positive integer that passes the
exactly specified Baillie–PSW probable-prime test.

**Verification shape:** compositeness certificate plus replay of the frozen
base-2 strong probable-prime and Lucas-test variants. The precise BPSW variant
is part of the problem statement, not an implementation detail.

**Primary risk:** no witness is known and none may exist. The supplied notes say
none exists below `2^64`; revalidate the current search frontier before work.

### C2. Beat the Hall-ratio record

**Candidate statement.** Find positive integers `x,y` with `y^2 != x^3` such
that

`sqrt(x) / |y^2 - x^3| > 100`.

The inequality should be checked without floating point, for example as
`x > 10000 |y^2 - x^3|^2`.

**Verification shape:** the two integers and direct big-integer arithmetic.

**Primary risk:** the reported record ratio, about 46.6 from Elkies's 1998
example, and the exact sign and normalization of the ratio must be checked
against the primary benchmark statement before activation.

### C3. Kissing number in dimension 5

**Candidate statement.** Improve the reported interval `40 <= tau_5 <= 44` by
either constructing 41 unit spheres tangent to a central unit sphere in
five-dimensional Euclidean space or proving `tau_5 <= 43`.

**Verification shape:** the lower-bound route needs exact or certified algebraic
coordinates and pairwise-distance checks; the upper-bound route needs a
rigorous analytic, LP, or SDP certificate with an exact trust path.

**Primary risk:** both directions are difficult, and a floating-point SDP bound
is evidence rather than a theorem.

### C4. Ramsey number `R(5,5)`

**Candidate statement.** Improve the supplied range `43 <= R(5,5) <= 46` by
either constructing a graph on 43 vertices with neither a 5-clique nor an
independent set of size 5, proving `R(5,5) >= 44`, or proving that every graph on
45 vertices has one of those configurations, proving `R(5,5) <= 45`.

**Verification shape:** a lower-bound graph is directly checkable; an upper
bound needs a complete exact proof or independently checked exhaustive
certificate.

**Primary risk:** computational cost and contest density are both high.

**Operator-input note:** the Tier C request contained one blank entry. `R(5,5)`
is included here because it is the only item in the supplied N1–N15 notes not
otherwise represented. This inference requires operator confirmation before
canonical intake.

### C5. Erdős #982 — distinct distances from a convex-polygon vertex

**Candidate statement.** Among any `n` distinct points in the plane that form a
convex polygon, is there a vertex having at least `floor(n/2)` distinct distances
to the other vertices?

**Why it is a stretch target.** Finite configurations and exact distance
comparisons are searchable, but the universal geometry statement is not closed
by finite experiments. The regular polygon shows that `floor(n/2)` would be
best possible.

**First bounded slice.** Reproduce the known lower bounds, classify extremal
small configurations up to an exact equivalence, and seek a structural lemma
that raises the guaranteed fraction.

**Primary risks.** The catalogue labels the problem `FALSIFIABLE` and lists a
claimed proof. Review that claim and all post-2025 literature before activation.

**Checked catalogue source:** [Erdős Problem #982](https://www.erdosproblems.com/982).

## Cross-cutting acceptance rules

Every candidate promoted from this planning dossier must have its own problem
definition and must pass all of the following before research execution:

1. Freeze one exact target. A family name, informal direction, or disjunction of
   possible wins is not yet a formal target.
2. Locate the original problem statement and independently re-check current
   open status. A catalogue label, review article, or benchmark page is an
   untrusted source candidate until acquired and reviewed.
3. Record definitions, quantifiers, assumptions, edge cases, and the mapping
   from the source statement to the local formalization. Human approval of that
   semantic alignment remains required.
4. Freeze a bounded exploratory protocol with useful negative outcomes and
   explicit stopping rules. Do not turn finite search into a universal claim.
5. Specify the expected certificate and an independent verifier before scaling
   search. Floating-point evidence may guide exploration but cannot silently
   enter an exact trust path.
6. Keep novelty, significance, acquisition rights, graph admission, and
   mathematical warrant separate. They begin `not_assessed` or absent.
7. Preserve failures and unresolved outcomes in machine-readable form.

## Recommended activation order

1. **A2 / MUB Problem 10.6:** strongest fit to existing quantum-information
   context and a clean bounded subproblem, once one exact pair is frozen.
2. **A1 / Erdős #128:** strongest flagship graph target, after the pending proof
   claim and current literature are checked.
3. **A3 / Erdős #167:** excellent exact packing-versus-covering test bed with
   several useful intermediate result shapes.
4. **A4 / planar total coloring at degree 6:** begin only after selecting a
   specific unsettled subclass or reducible-configuration target.
5. **A5 / Erdős #663:** start with a fixed small `k`, keeping the asymptotic
   quantifiers explicit.
6. **A6 / cubic Diophantine equation:** activate after the six-equation source
   list and the selected equation's still-open status are revalidated.

This order is a recommendation for target intake, not authorization for
parallel agents, higher search tiers, new external APIs, crawlers, numerical
solvers, or new formal/runtime capabilities.

## Source ledger

- Operator-supplied candidate notes, received 21 August 2026: primary source for
  the requested tiering and for the N1–N15 descriptions; treated as untrusted
  planning input.
- [Erdős Problem #126](https://www.erdosproblems.com/126),
  [#128](https://www.erdosproblems.com/128),
  [#167](https://www.erdosproblems.com/167),
  [#663](https://www.erdosproblems.com/663), and
  [#982](https://www.erdosproblems.com/982), accessed 21 August 2026. These are
  current catalogue renderings, not substitutes for the original Erdős sources
  or a literature review.
- Daniel McNulty and Stefan Weigert, [“Mutually Unbiased Bases in Composite
  Dimensions — A Review”](https://doi.org/10.22331/q-2026-04-01-2051),
  *Quantum* 10, 2051 (2026), especially Problems 10.2 and 10.6.
- [FrontierMath: Open Problems](https://epoch.ai/frontiermath/open-problems),
  accessed 21 August 2026, as a discovery index for several supplied candidates;
  exact individual statements and verifier contracts still require acquisition.
