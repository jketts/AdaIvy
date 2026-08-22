# B2. Erdos #126 — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B2 (tier B)
**Declared domain:** number-theory
**Intake file:** docs/research-targets/intake/b2-erdos-126-pairwise-sum-prime-divisors-v1.json
**Frozen in one line:** For every rational `C > 0` there is a threshold `N` such
that every `n > N` satisfies `f(n) > C ln n`, where `f(n)` is the least
number of distinct prime divisors of the product of the pairwise sums of an
`n`-element set of positive integers.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen target is open, authorize acquisition of any source, assess
novelty or significance, create mathematical warrant, or activate a capability.
Novelty, significance, and source applicability are `not_assessed`. Every
external statement recorded below, including the catalogue rendering of the
problem and the existence of a "known lower bound", is an untrusted candidate.

## 1. Frozen target

Fix the following.

For a positive integer `N`, `omega(N)` is the number of distinct primes dividing
`N`, with `omega(1) = 0`.

For a finite set `A` of positive integers with `|A| = n >= 2`, define

`S(A) = prod over { {a,b} : a, b in A, a != b } of (a + b)`,

a product of exactly `binom(n,2)` factors, one for each unordered pair of
distinct elements. Every factor is a positive integer at least `3`, so
`S(A) >= 1` and `omega(S(A))` is defined.

For an integer `n >= 2` define

`f(n) = min { omega(S(A)) : A a set of positive integers with |A| = n }`.

The minimum exists because the set of attained values is a nonempty set of
non-negative integers. Equivalently, `f(n)` is the largest integer `k` such that
every `n`-element set `A` of positive integers satisfies `omega(S(A)) >= k`; the
two descriptions define the same number and the planning dossier's "maximal
`f(n)` such that for every `A` ..." is the second one.

`ln` denotes the natural logarithm, base `e`.

**Frozen target claim.**

`for every rational C > 0 there exists an integer N >= 2 such that`
`for every integer n > N, f(n) > C * ln n.`

This is the explicit threshold form of `f(n)/ln n -> infinity`. It is one claim
with one universally quantified parameter, and its scope is
`unrestricted_universal` because it asserts something about every sufficiently
large `n` for every `C`.

Two remarks that are part of the freeze rather than commentary. First,
quantifying `C` over positive rationals is not a weakening: for a real `C > 0`
choose a rational `C' >= C`, and the threshold for `C'` serves for `C`.
Rationals are used so that `C` is an exact object. Second, the choice of
logarithm base changes both sides by a positive constant factor and therefore
cannot change the truth of the claim; the base is nevertheless pinned to `e` so
that any recorded inequality has one meaning.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| `A` | a set of positive integers, so elements are distinct and at least `1`; `|A| = n` | a multiset; a set of non-negative integers, admitting `0` and hence the factors `0 + b = b`; a set of integers, admitting negatives and hence non-positive or zero factors; a sequence with repetitions |
| natural number | positive integer, `1, 2, 3, ...` | `0` included, which changes `S(A)` and may change `f(n)` |
| pair range | unordered pairs `{a,b}` with `a != b`, exactly `binom(n,2)` factors | ordered pairs, which squares `S(A)`; pairs with `a = b` allowed, adding the factors `2a` and enlarging the prime set; only pairs of consecutive elements in some ordering |
| `S(A)` | the product of `a + b` over those pairs | the sum of `a + b`; the product of `a * b + 1`; the least common multiple of the sums |
| `omega(N)` | number of distinct primes dividing `N`; `omega(1) = 0` | `Omega(N)`, the number of prime factors with multiplicity; the number of divisors; the largest prime factor |
| `f(n)` | `min` over all `n`-element sets of positive integers of `omega(S(A))` | a minimum over sets inside a bounded window, which is a different and larger function, written `f_M(n)` in section 7; a maximum; an average over sets |
| `n` | an integer `n >= 2` | `n >= 1`, where the empty product gives `omega(1) = 0` and the statement degenerates; `n` real |
| `log n` | natural logarithm of `n`, base `e` | base 2 or base 10, which rescales both sides by a constant and cannot change the truth value but does change every recorded numeric inequality; iterated logarithm |
| the limit statement | for every rational `C > 0` there is `N` with `f(n) > C ln n` for all `n > N` | `f(n) > C ln n` for all `n` with no threshold; `f(n) >= C ln n` with a non-strict inequality at the threshold; `limsup` instead of `lim`; `f(n) / ln n` bounded below by a fixed constant, which is a strictly weaker statement |
| improvement of a lower bound | a proved inequality `f(n) >= g(n)` valid for all `n` beyond an explicit threshold | a table of exactly computed values of `f_M(n)`, which bounds `f(n)` from above and never from below |
| exact comparison with `ln n` | either a symbolic derivation, or a comparison against an exact rational enclosure of `ln n` with a proved remainder bound, used only in the excluding direction | a floating-point evaluation of `math.log(n)`; a decimal approximation of `ln n` treated as its value |

## 3. Formalization and quantifiers

Typed informal statement, as it appears in the intake file:

`forall C : Q, C > 0 ->`
`exists N : N, N >= 2 and`
`forall n : N, n > N -> f(n) > C * ln(n)`

with

`f(n) = min { omega(prod_{ {a,b} subset A, a != b } (a + b)) : A subset Z_{>=1}, card(A) = n }`

and `omega(N)` the number of distinct primes dividing `N`.

Quantifiers, in order and with their ranges:

- `forall C` a rational with `C > 0`;
- `exists N` an integer with `N >= 2`, allowed to depend on `C`;
- `forall n` an integer with `n > N`;
- inside `f(n)`: `min over all A`, that is, `forall A` a set of positive
  integers with `|A| = n` the inequality `omega(S(A)) >= f(n)` holds, and
  `exists A` attaining it;
- inside `S(A)`: `forall` unordered pairs `{a,b}` of distinct elements of `A`.

The dependence order is fixed: `N` may depend on `C`, and nothing may depend on
`n` except through `f(n)`. No uniformity in `C` is claimed.

The only transcendental object in the statement is `ln n`. It never appears
inside `f`, which is integer-valued, and it is never evaluated numerically on
the trust path: an inequality involving `ln n` is either derived symbolically or
checked against an exact rational enclosure of `ln n` obtained from a truncated
series with a proved remainder bound and used only in the direction that
excludes. Everything else, including every prime-divisor count, is an exact
integer.

## 4. Semantic alignment to the source statement

The source statement, as rendered in the planning dossier, is: let `f(n)` be
maximal such that for every `n`-element set `A` of natural numbers, the product
of `a+b` over distinct `a,b in A` has at least `f(n)` distinct prime divisors;
is `f(n)/log n -> infinity`?

**Quantifier mapping.** "for every `n`-element set `A`" maps to `forall A` a set
of positive integers of cardinality `n`, and the "maximal `f(n)`" formulation
maps to the minimum over those sets, which is the same number. The implicit
asymptotic in `f(n)/log n -> infinity` maps to the explicit pair
`forall C exists N forall n > N`, with `C` rational. "distinct `a,b in A`" maps
to unordered pairs with `a != b`.

**Definition mapping.** "natural numbers" maps to positive integers. "the
product of `a+b`" maps to `S(A)`, a product of `binom(n,2)` factors. "at least
`f(n)` distinct prime divisors" maps to `omega(S(A)) >= f(n)`. "`log n`" maps to
`ln n`, base `e`.

**Assumption delta.** The frozen target pins three things the source rendering
leaves open: that `A` consists of positive integers rather than non-negative or
arbitrary integers; that pairs are unordered with `a != b`; and the logarithm
base. It adds no hypothesis on the structure of `A` — no bound, no residue
condition, no smoothness. It weakens nothing.

**Edge-case delta.** `n = 1` is excluded, because the empty product gives
`omega(1) = 0` and the statement carries no content there. `n = 0` is excluded
for the same reason. If `0` were admitted into `A` then for `n >= 2` every
factor `0 + b = b` would still be positive, so `omega` would remain defined but
`f` could take a different value; that is a different problem and is listed as a
rejected reading rather than an edge case of this one. Allowing `a = b` only
enlarges the prime set, so it can only increase `f`; the frozen reading is
therefore the smaller of the two.

An observation that removes one class of ambiguity entirely: because the primes
dividing a product are exactly the union of the primes dividing its factors,
`omega(S(A))` equals the number of primes dividing at least one pairwise sum.
Multiplicity conventions and the ordered-versus-unordered choice therefore
cannot change `omega(S(A))`, and the only convention that does change it is
whether `a = b` is admitted.

**Strength relation:** `unresolved`. The frozen statement is intended as the
explicit form of the planning dossier's question, but whether it is the
statement Erdos asked cannot be settled before the catalogue entry and the
original source are acquired, and `equivalent` is unavailable because no primary
source has been quoted here.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` with applicability `not_assessed`.
Acquisition is human-planned, exact-URL, and separately authorized under
ADR-0050; nothing here authorizes a fetch. Rows marked `locator_unknown` cannot
be turned into a locator without acquiring an earlier row first.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue, entry 126 | `https://www.erdosproblems.com/126` — one public unauthenticated page, within the shape ADR-0050 activates, still requiring its own human-planned authorization | settles claims 6.1, 6.2, and 6.5: the catalogue's exact rendering, its status label, and the references it cites | pending_acquisition |
| The original Erdos statement cited by that entry | `locator_unknown` until the row above is acquired; the entry's own reference list is the intended route | settles claim 6.4: whether "natural numbers", the pair range, and the logarithm base in the frozen reading match Erdos's own statement | pending_acquisition |
| The paper establishing the best known lower bound for `f(n)` | `locator_unknown` until the catalogue entry is acquired | settles claim 6.3, and decides whether "improve the known lower bound" is a live route at all or already far above anything a bounded slice touches | pending_acquisition |
| Related work on prime divisors of products of pairwise sums | `locator_unknown`; identified only by topic, since this dossier can name no reference offline without risking a fabricated citation | would settle whether the structured-family stage of section 7 duplicates a known construction | pending_acquisition |
| ADR-0051 bounded Crossref metadata discovery | one operator-initiated query whose terms are exact-normalized substrings of this file, for example `distinct prime divisors` and `pairwise sums` | a discovery route only, to help identify the two `locator_unknown` rows; every result is an untrusted inspiration candidate with relevance, applicability, novelty, and significance `not_assessed`, and it neither performs nor satisfies the ADR-0055 re-check | pending_acquisition |

None of these rows is required for the slice to run. All of them are required
before any statement about status, novelty, or improvement of a known bound.

## 6. Prior-status claims to re-check

Each claim is untrusted and none is a premise of the slice. The ADR-0055
pre-research novelty re-check must cover all of them, with evidence hashes, and
each found source needs a human-supplied relationship to the frozen target.

**6.1 The catalogue rendering was checked on the compilation date.** The
planning dossier states that the five numbered Erdos statements were checked
against the Erdos Problems catalogue on 21 August 2026. That check is untrusted
here: no retained bytes, no content hash, and no acquisition record back it.

**6.2 The problem is open.** Inherited from the framing of B2 as a candidate.
Note what the planning dossier does not say: for items A1 and C5 it records a
`FALSIFIABLE` catalogue label and a claimed proof, and for #126 it records no
label at all. The absence of a recorded label is not evidence of an `OPEN`
label, and the re-check must obtain the actual label rather than infer it from
silence.

**6.3 A "known lower bound" exists and is improvable.** The planning dossier
lists "improve the known lower bound" as useful progress but states no bound.
Its value, its form, its threshold, and its attribution are unknown to this
dossier. No claim of improvement may be made until this claim is resolved
against an acquired source.

**6.4 The catalogue rendering is faithful to Erdos's statement.** Untrusted, and
the specific risks are named in section 2: "natural numbers" may or may not
include `0`, and the pair range may or may not admit `a = b`.

**6.5 The question asked is the divergence of `f(n)/log n`.** Untrusted. Nearby
questions exist — bounded ratio, a specific growth rate, or the analogous
question for the largest prime factor rather than the count of prime divisors —
and the re-check must confirm which one the source asks before the frozen form
is described as the source's question.

## 7. Bounded first slice

Offline, deterministic, exact-integer, human-authored. No model on the trust
path, no network, no model-generated program executed.

**Inputs.** Two integers fixing the exhaustive envelope: the set-size range
`2 <= n <= n_max`, frozen at `n_max = 8`, and the element bound `M`, frozen at
`M = 64`. One integer fixing the structured stage: the element bound `2^40` on
any pairwise sum, which is the exact factorization cost boundary stated below.
No table, published value, or prior computation is an input.

**Exact factorization on the trust path.** For the exhaustive stage every
pairwise sum lies in `[3, 2M - 1]`, so the slice precomputes a smallest-prime-
factor sieve over `[2, 2M]`. Factorization is then table lookup with no
primality test of any kind, and `omega` of a sum is read off exactly. For the
structured stage, where elements may be large, a sum `N <= 2^40` is factored by
trial division over the primes up to `isqrt(N)`, computed with exact integer
square root; that procedure is its own certificate, since a cofactor with no
prime factor at or below its integer square root is prime. The per-number cost
is at most `pi(2^20)` exact divisions, a count the slice computes by sieve
rather than quoting. Above `2^40` nothing enters the trust path without a
certificate: Pollard rho and elliptic-curve factorization may guide exploration,
and their output is admitted only as a complete factorization in which every
claimed prime carries a primality certificate that the verifier replays
independently. No Miller-Rabin, Baillie-PSW, or other probabilistic primality
verdict is admissible on the trust path. The repository's own C1 candidate is a
search for a Baillie-PSW pseudoprime, which is the standing reminder of why.

**Stage 1, exhaustive minimum inside a window.** For `M >= 1` define

`f_M(n) = min { omega(S(A)) : A subset {1,...,M}, |A| = n }`.

The slice computes `f_M(n)` exactly for `2 <= n <= n_max` and for an increasing
sequence of `M` up to the frozen bound. The enumeration is depth-first over
increasing elements, carrying the running union of prime indices as an exact
integer bitset over the primes up to `2M`. The pruning rule is: if the running
union already has at least as many elements as the best complete value found so
far, prune. It is sound because adding an element to a set can only add pairwise
sums and therefore can only enlarge the union — the union size is monotone along
the depth-first path. For `n <= 4` and `M <= 24` the pruned search is
cross-checked against unpruned enumeration of all `binom(M,n)` subsets, and any
divergence halts the run. The unpruned envelope size is
`sum over n of binom(M,n)`, which for `M = 64` and `n <= 8` is on the order of
`10^9` before pruning; the number of nodes actually visited is a measured
output, capped below.

**Stage 2, structured families.** Evaluate `omega(S(A))` exactly for
parameterized families whose elements may exceed `M`: arithmetic progressions
`{a + i d}`, geometric-shaped sets `{c r^i}`, sets inside one residue class
modulo a small `q`, sets built to make many sums share small prime factors, and
the initial segment `{1,...,n}`. Each family is enumerated over an explicit
bounded parameter box, every parameter box is recorded, and every sum is kept
below the `2^40` factorization boundary or is skipped and recorded as skipped.
This stage is exhaustive over its stated parameter boxes and is sampling
nothing; what it is not is exhaustive over sets.

**Stage 3, minimizer structure.** For every `(n, M)` in Stage 1, retain every
set attaining `f_M(n)`, canonicalized as a sorted tuple, and record
machine-readable observations about them: the multiset of prime divisors used,
whether the minimizers lie in one residue class, whether they are in arithmetic
progression, and the largest prime used. These are observations. They are not
lemmas and no fitted pattern is reported as a structural theorem.

**Canonicalization and symmetry.** The only symmetry is the ordering of
elements, which is quotiented by representing a set as a strictly increasing
tuple. There is no useful group action: translating `A` changes every sum by a
constant and scaling `A` by `d` multiplies every sum by `d`, and neither
preserves the prime support in a way the search can exploit. Scaling by `d` does
give one exact relation the slice records — the prime support of `S(dA)` is the
support of `S(A)` together with the primes dividing `d` — so scaled copies are
never searched twice.

**Resource caps.** The run halts when visited search nodes exceed `10^{10}`,
when sieve memory would exceed the stated cap, or under any stopping rule in
section 10. The reached `(n_max, M)` is a measured output.

**Boundary of the claim the slice can support.** Because `{1,...,M}` is a
subfamily of all sets, `f(n) <= f_M(n)`, so every exactly computed `f_M(n)` is
an upper bound on `f(n)` and never a lower bound. The slice can therefore
establish: the exact value of the bounded quantity `f_M(n)` for the reached
parameters, with a witness set; and hence exact upper bounds on `f(n)`. It
cannot establish any lower bound on `f(n)`, because that quantifies over
infinitely many sets. It follows that the slice cannot prove the frozen target,
which is a lower-bound statement, and — this is the part that is easy to get
wrong — it also cannot refute it: refuting divergence requires an infinite
sequence of sets whose `omega(S(A))` stays below `C ln n` for a fixed `C`, which
is a construction with a proof, not a table. A finite table of unexpectedly
sparse examples is consistent with both answers. Two exact facts about `f` do
transfer without qualification and the slice uses them as consistency checks:
`f` is non-decreasing, since for `A' subset A` the product `S(A')` divides
`S(A)`; and `f(n) <= f_M(n)` for every `M`.

## 8. Certificate and verifier contract

**S1, exact value of a bounded minimum.** Certificate: the parameters `n` and
`M`; the value `f_M(n)`; one attaining set as a strictly increasing integer
tuple; the complete factorization of every one of its `binom(n,2)` pairwise sums
as exact prime-exponent lists; the sorted list of distinct primes; and the
exhaustion record, namely the pruning rule with its soundness lemma and the
visited-node count. Verifier: recompute every sum by exact integer addition;
recompute each factorization independently by sieve lookup and confirm the
product of prime powers equals the sum exactly; recompute the union of primes
and its size; confirm the size equals the claimed value; and replay the
exhaustion. The verifier shares no code with the search.

**S2, an exact upper bound on `f(n)`.** Certificate: one set `A` with `|A| = n`,
the factorizations of its pairwise sums, and the resulting `omega(S(A)) = k`.
Verifier: as in S1, minus the exhaustion. This certifies `f(n) <= k` and nothing
more. It is the strongest shape the slice can produce about `f` itself.

**S3, a certified sparse family.** Certificate: an explicit family `A_n` given
by an algorithm, an explicit rational `C`, an explicit threshold `N`, a symbolic
proof that `omega(S(A_n)) <= C ln n` for all `n > N`, and exact verification of
the inequality for every `n <= K` for a stated `K` using rational enclosures of
`ln n` with proved remainder bounds. Verifier: replay the finite checks exactly,
then require the symbolic proof to be reviewed as a proof. The finite checks are
a consistency check on the proof and are not the family result. This is the only
shape that could bear on the frozen target negatively.

**S4, a lower-bound theorem.** Certificate: a symbolic proof only, with every
lemma discharged. No computation contributes to it. The slice cannot produce
this shape and does not pretend to.

**S5, refuted construction.** Certificate: the family, the parameter box, the
exact `n` at which the computed `omega` first exceeded the intended bound, and
the factorizations at that `n`. Retained permanently.

**Refused as a certificate, in every shape.** Floating-point output, including
any use of a floating-point logarithm in a comparison. A probabilistic primality
verdict, whether Miller-Rabin, Baillie-PSW, or a library `isprime` whose
algorithm is not pinned. A factorization from an external tool that has not been
re-multiplied and re-certified inside the verifier. A model's assertion that a
family is sparse or that a pattern continues. A published value of `f(n)` or of
the known lower bound, used without acquisition and replay. Failure of a search,
in either direction.

## 9. Useful negative outcomes

- The exact table of `f_M(n)` for every reached `(n, M)`, each with a witness
  set and its full factorization data, content-hashed. This is a permanent exact
  upper-bound record for `f`, independent of how the target resolves.
- Every set attaining a bounded minimum, canonicalized. Any future claim about
  the shape of extremal sets must be consistent with this list, and a future run
  need not re-search it.
- The machine-readable structure observations of Stage 3, explicitly labelled
  observations, which are the honest input to a later structural conjecture.
- Every structured family whose exact `omega` grew faster than intended, with
  the exact parameter at which it broke. A refuted sparse-family route is the
  most transferable negative outcome available here, because the target's
  negative direction can only ever be reached by such a family.
- The recorded fact of which pairwise sums had to be skipped at the `2^40`
  factorization boundary, which is the exact measurement of what a certified
  factorization capability would buy.
- The measured cost profile of the sieve and of the pruned search, as the only
  honest input to an ADR-0029 request for a larger envelope.
- The two exact consistency relations, monotonicity of `f` and `f(n) <= f_M(n)`,
  checked on every run; a violation would indicate a defect and is retained as
  an acceptance fixture.

## 10. Evaluation protocol

Mirrors the intake file exactly.

Phase: `exploratory`. Version: `1`.

Metrics:

- `bounded_minima_computed_exactly`
- `witness_sets_certified`
- `pairwise_sums_factored_exactly`
- `sums_skipped_at_factorization_boundary`
- `structured_families_evaluated`
- `sparse_family_routes_refuted`
- `independent_verifier_replays_passed`
- `proof_obligations_opened`
- `proof_obligations_closed`
- `model_cost_usd`

Success criteria:

- `an exact certified family of sets witnessing that f(n) stays below C ln n for a fixed rational C beyond an explicit threshold, with a symbolic proof and not a table`
- `a symbolic proof of a lower bound on f(n) valid beyond an explicit threshold, with every lemma discharged`
- `an exactly computed bounded minimum f_M(n) that contradicts a published value once that value has been acquired and replayed`
- `an explicit unresolved outcome that names the smallest remaining obligation, together with the retained upper-bound table and every refuted sparse-family route`

Stopping rules:

- `stop on an exact symbolic proof in either direction and open no further search`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no proof obligation and refute no route`
- `stop when visited search nodes exceed 10^10 or a pairwise sum exceeds the frozen factorization boundary without a replayable certificate`
- `never promote a bounded table to a statement about f(n) for all n; an exactly computed f_M(n) is an upper bound on f(n) and is never a lower bound`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Direction confusion between `f` and `f_M` | The bounded search produces upper bounds on `f`, while the target is a lower-bound statement. Reading a sparse example as evidence against divergence is the single most likely error | Section 7 states the boundary; a stopping rule names it; the monotonicity and `f(n) <= f_M(n)` relations are checked every run; the metric names say `bounded_minima` and not `f` |
| A finite table read as an asymptotic | Sparse examples at small `n` are compatible with divergence, since divergence is about every large `n` | Refuting divergence is admissible only in shape S3, which requires a symbolic proof over an infinite family; the finite checks in S3 are labelled a consistency check |
| Probabilistic primality on the trust path | An `isprime` call whose algorithm is unpinned silently converts a certificate into a probabilistic claim, and the repository's own C1 candidate is a hunt for exactly such a failure | The exhaustive stage uses a sieve and performs no primality test at all; the structured stage uses trial division to the exact integer square root, which is self-certifying; anything larger needs a replayed certificate |
| Floating-point logarithm in a comparison | The only transcendental in the statement is `ln n`, and a float comparison would put it on the trust path against the repository owner's standing rule | Comparisons with `ln n` are symbolic, or use exact rational enclosures with proved remainder bounds in the excluding direction only |
| Rediscovery of the known lower bound | Claim 6.3 is unresolved, so the slice could reproduce a published bound and read it as progress | No improvement claim before the ADR-0055 re-check resolves 6.3 with an acquired source; the success criteria mention a published value only after acquisition and replay |
| The problem may be settled or labelled otherwise | The planning dossier records no catalogue label for #126, unlike A1 and C5 | The re-check must obtain the actual label; silence is explicitly not read as `OPEN` in claim 6.2 |
| Convention drift in `A` | Admitting `0`, admitting `a = b`, or changing the logarithm base each defines a different `f` or a different inequality | Section 2 freezes all three and lists the alternatives as rejected readings; the alignment relation is `unresolved` until the source is acquired |
| Combinatorial explosion | The unpruned envelope at `M = 64` is on the order of `10^9` subsets, and a naive run consumes the budget with nothing retained | Monotone-union pruning with a stated soundness lemma, an explicit node cap, and a cross-check against unpruned enumeration on a small window |
| Model-generated search code executed | The sieve and the search are the whole coverage argument | Both, and both verifiers, are human-authored repo code; ADR-0057 keeps production generated-code execution disabled |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Declarative problem intake with
canonical hashing. Exact arbitrary-precision integer arithmetic and exact
integer square root from the standard library, which is everything the sieve,
the search, and both verifiers need, as repository-authored code under `src/`
exercised by the offline suite — ad-hoc exact arithmetic written and run by the
driving agent in a scratch workspace is NOT this capability, but an unmet AdaIvy
capability and an external-origin contribution under ADR-0057 section 5,
imported with an `external_codex` or `human` root and never relabelled as AdaIvy
work. Deterministic serialization, content
hashing, and the append-only record path for certificates and preserved
failures. The offline `make check` harness, which needs no network, model
provider, or container runtime. The ADR-0047 bounded central-lead runtime for
the structured-family stage, driven as composed one-round Phase 2 runs with a
size-bounded proposer-only ledger and model-free replay. The ADR-0036
publication projection, with claim environments computed rather than declared.
The ADR-0055 pre-research novelty re-check, which is mandatory before execution.

**Available but separately authorized, not activated by this dossier.** The
ADR-0050 public unauthenticated exact-URL acquisition path is the right shape
for the catalogue row in section 5, and that row still needs its own
human-planned authorization. The ADR-0051 bounded Crossref metadata query is the
right shape for identifying the two `locator_unknown` rows, requires the exact
acknowledgement and query hash, and yields untrusted inspiration candidates
only.

**Would require a new ADR.**

- Certified factorization above `2^40`: an integer-factorization capability with
  replayable primality certificates does not exist in the repository, and
  neither Pollard rho nor elliptic-curve factorization may be added to a trust
  path without one.
- A certified rational enclosure routine for `ln n` with proved remainder
  bounds, if any numeric comparison against `ln n` is ever needed. There is no
  such exact-analysis capability today.
- Execution of any model-generated sieve, search, or verifier. ADR-0057 keeps
  production generated-code execution disabled pending its own sandbox gate.
- A kernel-checked symbolic proof of any lower bound. Phase 3B checks a frozen
  theorem supplied to it, and there is no formalization of `f` in the
  repository.
- Any parallel, specialist, evolutionary, or higher-tier search over the subset
  enumeration, which requires the ADR-0029 recorded prediction and measured
  retention gain first.

## 13. Open questions before intake

1. Does the operator accept positive integers as the reading of "natural
   numbers"? If `0` is intended to be admissible, `f` changes and this dossier
   must be reissued rather than edited.
2. Does the operator accept the frozen threshold form with `C` ranging over
   positive rationals, given that the real-`C` form follows and rationals keep
   `C` exact?
3. Claim 6.3 leaves the known lower bound unknown. Should the slice run at all
   before that claim is resolved, given that the structured-family stage might
   simply reproduce a published construction?
4. Is `n_max = 8` and `M = 64` the intended envelope? A larger `M` is cheap for
   small `n` and expensive for `n = 8`, and the trade could be frozen
   differently.
5. Should a certified-factorization ADR be requested now, so that the structured
   stage can use sets whose pairwise sums exceed `2^40`? Without it the
   structured stage is confined to small elements, which is exactly where sparse
   examples are least likely.
