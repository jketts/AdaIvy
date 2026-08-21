# C1. Baillie-PSW pseudoprime — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item C1 (tier C)
**Declared domain:** computational-number-theory
**Intake file:** docs/research-targets/intake/c1-baillie-psw-pseudoprime-v1.json
**Frozen in one line:** There exists a composite positive integer `n` on which
the single frozen probable-prime procedure `BPSW-SL-1000`, specified step by step
in section 1, returns the verdict `PROBABLE_PRIME`.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate any capability. Novelty,
significance, and source applicability are `not_assessed` and stay that way.
Nothing below has been checked against an acquired primary source; every
external statement in sections 5 and 6 is an untrusted candidate.

## 1. Frozen target

The planning dossier says the precise BPSW variant is part of the problem
statement rather than an implementation detail. That makes "the Baillie-PSW
test" a schema and not a target. Exactly one variant is frozen here and named
`BPSW-SL-1000`: trial division below `1000`, a base-2 **s**trong
probable-prime test, Selfridge Method A parameter selection, and the **s**trong
**L**ucas test. Every other variant is a different problem and is listed as a
rejected reading in section 2.

### 1.1 The frozen procedure `BPSW-SL-1000`

Domain: integers `n >= 2`. Verdict alphabet: `PRIME`, `COMPOSITE`,
`PROBABLE_PRIME`, `PARAMETER_DEGENERATE`. All arithmetic is exact integer
arithmetic; no floating point occurs at any step.

**Step 1 (small inputs).** If `n < 1000`, compute `r = isqrt(n)` by exact
integer square root and trial divide `n` by every integer `2 <= t <= r`. Return
`COMPOSITE` if some `t` divides `n`, otherwise return `PRIME`. Halt.

**Step 2 (trial division, bound 1000).** For each of the 168 primes `p < 1000`
in increasing order (`2, 3, 5, ..., 997`): if `p` divides `n`, return
`COMPOSITE` and halt. Because `n >= 1000` here, such a `p` is a nontrivial
divisor. On reaching this point `n` is odd and has no prime factor below `1000`.

**Step 3 (base-2 strong probable-prime test).** Write `n - 1 = 2^s * d` with `d`
odd and `s >= 1`; `s >= 1` because `n` is odd. Compute `x_0 = 2^d mod n` by
exact square-and-multiply modular exponentiation. If `x_0 = 1` or `x_0 = n - 1`,
go to step 4. Otherwise, for `j = 1, 2, ..., s - 1` in order, set
`x_j = x_(j-1)^2 mod n`; if `x_j = n - 1`, go to step 4. If no such `j` exists,
return `COMPOSITE` and halt.

**Step 4 (perfect-square exclusion).** Compute `r = isqrt(n)`. If `r * r = n`,
return `COMPOSITE` and halt. Since `n >= 1000` gives `r >= 31`, `r` is a
nontrivial divisor. This step is placed before the parameter search because for
a perfect square `n` no discriminant in step 5 can have Jacobi symbol `-1` and
the search of step 5 would not terminate.

**Step 5 (Selfridge Method A discriminant selection).** For
`i = 0, 1, 2, ...` let

`D_i = (-1)^i * (2*i + 5)`,

so the sequence of trial discriminants is `5, -7, 9, -11, 13, -15, 17, ...`;
each `D_i` satisfies `D_i = 1 (mod 4)`. In increasing `i`, compute the Jacobi
symbol `(D_i / n)` by the standard exact binary algorithm using quadratic
reciprocity, with the Kronecker extension `(D/n) = (-1/n)^e * (|D|/n)` for
`D < 0`, `e = 1`, and `(-1/n) = (-1)^((n-1)/2)`.

- If `(D_i / n) = 0` and `|D_i| < n`, then `gcd(|D_i|, n)` is a nontrivial
  divisor of `n`; return `COMPOSITE` and halt.
- If `(D_i / n) = -1`, stop the search with `D = D_i`.

Set `P = 1` and `Q = (1 - D) / 4`, an integer because `D = 1 (mod 4)`. Then
`P^2 - 4*Q = D`.

**Step 6 (parameter degeneracy guard).** Compute `g = gcd(n, 2 * Q * D)` by the
exact Euclidean algorithm. If `1 < g < n`, return `COMPOSITE` and halt. If
`g = n`, return `PARAMETER_DEGENERATE` and halt; this verdict is not a pass and
such an input is not a witness.

**Step 7 (strong Lucas probable-prime test with `(P, Q) = (1, (1-D)/4)`).**
Define the Lucas sequences by `U_0 = 0`, `U_1 = 1`, `V_0 = 2`, `V_1 = P` and,
for `t >= 1`, `U_(t+1) = P*U_t - Q*U_(t-1)` and `V_(t+1) = P*V_t - Q*V_(t-1)`.
Write `n + 1 = 2^k * m` with `m` odd and `k >= 1`; `k >= 1` because `n` is odd.
Compute `U_m mod n` and `V_m mod n` by the exact doubling recurrences
`U_(2t) = U_t * V_t`, `V_(2t) = V_t^2 - 2*Q^t`, together with the index-increment
step `U_(t+1) = (P*U_t + V_t) * inv2 mod n` and
`V_(t+1) = (D*U_t + P*V_t) * inv2 mod n`, where `inv2 = (n + 1) / 2` is the
exact inverse of `2` modulo the odd `n`.

- If `U_m = 0 (mod n)`, return `PROBABLE_PRIME` and halt.
- Otherwise, for `j = 0, 1, ..., k - 1` in order, compute
  `V_(m * 2^j) mod n` by repeated application of `V_(2t) = V_t^2 - 2*Q^t`; if
  `V_(m * 2^j) = 0 (mod n)`, return `PROBABLE_PRIME` and halt.
- If no such `j` exists, return `COMPOSITE` and halt.

### 1.2 The frozen statement

**Target.** There exists a composite positive integer `n` such that
`BPSW-SL-1000(n) = PROBABLE_PRIME`.

Here `n` is composite iff there are integers `a, b` with `1 < a <= b < n` and
`n = a * b`. Quantifier: a single existential over the positive integers, with
no upper bound. Scope: `existential`.

Two consequences of the frozen text are recorded because they are properties of
the target and not of an implementation. First, any witness has no prime factor
below `1000`, so, being composite, it is a product of at least two primes each
at least `1009`; hence every witness satisfies `n >= 1009^2 = 1018081`. Second,
the verdict `PARAMETER_DEGENERATE` is explicitly not a pass, so an input that
halts there is not a witness even though the procedure never called it
composite.

### 1.3 What is not claimed

No witness is known to this dossier and none may exist. The target may be false.
Nothing here asserts that the target is open, that a witness would be new, or
that the frozen variant is the variant intended by any source. The realistic
deliverable is therefore the negative one described in section 9: a certified
extension of the search frontier over exactly defined regions and families,
carrying a replayable exclusion record. That negative outcome is the expected
result and is retained as a first-class artifact rather than treated as failure.

## 2. Definitions and conventions

Every row is a load-bearing choice. The rejected reading column names a
different problem, not a worse phrasing of the same one.

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| the BPSW test | exactly the seven-step procedure `BPSW-SL-1000` of section 1.1 | any procedure differing in trial-division bound, base, discriminant rule, or Lucas variant; "the BPSW test" as an unqualified name |
| trial-division bound | every prime `p < 1000`, all 168 of them, before any other step | no trial division; bound `50`; bound `256`; bound `65536`; trial division by all integers rather than primes; trial division applied after step 3 |
| base-2 test | the strong probable-prime test to the single base `2`, as written in step 3 | the Fermat test `2^(n-1) = 1 (mod n)`; base `3`; a random base; several bases; the Miller-Rabin test with a fixed base set |
| discriminant rule | Selfridge Method A: least `i >= 0` with `(D_i/n) = -1` where `D_i = (-1)^i (2i+5)`, then `P = 1`, `Q = (1-D)/4` | Method A* (retry with `D = 5` handled specially); a rule stepping `|D|` by `4`; the extra-strong rule choosing `P` with `((P^2-4)/n) = -1` and `Q = 1`; choosing `D` by smallest `|D|` rather than by the signed sequence |
| perfect-square exclusion | exact `isqrt` test placed before the discriminant search, step 4 | omitting it, which makes the step-5 search nonterminating on squares; performing it inside the search loop after a bounded number of trials; testing squareness by a floating-point square root |
| Lucas test strength | strong: `U_m = 0` or some `V_(m 2^j) = 0`, `0 <= j <= k-1`, with `n+1 = 2^k m` | standard: `U_(n+1) = 0 (mod n)`; extra-strong, which additionally requires `V_m = +-2`; the Lucas-Lehmer test, which is a different test entirely |
| Jacobi symbol | the Kronecker-extended Jacobi symbol for odd `n > 0` and any integer `D`, computed exactly by reciprocity | the Legendre symbol, which is undefined for composite modulus; a symbol convention that leaves `(D/n)` undefined for `D < 0` |
| "passes the test" | the procedure returns `PROBABLE_PRIME` | the procedure fails to return `COMPOSITE`; in particular `PARAMETER_DEGENERATE` is not a pass |
| composite | `n = a*b` with `1 < a <= b < n` | "not prime", which would admit `n = 1`; "has at least two distinct prime factors", which would exclude prime powers |
| compositeness certificate | an exhibited factorization `n = a*b`, `1 < a <= b < n`, re-multiplied to `n` by exact big-integer arithmetic | a probable-prime test returning `COMPOSITE`; a library's `is_prime` verdict; a factorization printed without re-multiplication |
| witness | one composite `n` with `BPSW-SL-1000(n) = PROBABLE_PRIME`, both parts certified | a base-2 strong pseudoprime; a Lucas pseudoprime; a Carmichael number; an `n` passing some other BPSW variant |
| exclusion record | a machine-readable record of an exactly defined region or family, its enumeration, and the per-candidate verdict, replayable from the frozen definition | a log line saying a search found nothing |

## 3. Formalization and quantifiers

Formal language: `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment in section 4 has not been requested and
is not implied.

```
exists n : N,
  n >= 2
  and (exists a b : N, 1 < a and a <= b and b < n and n = a * b)
  and BPSW_SL_1000(n) = PROBABLE_PRIME
```

Quantifiers, explicitly:

- `exists n` ranging over the positive integers, unbounded above;
- `exists a, b` witnessing compositeness, both strictly between `1` and `n`;
- inside `BPSW_SL_1000`, all quantifiers are bounded and constructive: `forall p`
  over the 168 primes below `1000`; `exists j` with `1 <= j <= s-1` in step 3;
  `exists i >= 0` least with `(D_i/n) = -1` in step 5, whose termination for
  non-squares is the reason step 4 precedes it; `exists j` with
  `0 <= j <= k-1` in step 7.

There is no asymptotic content and therefore no implicit epsilon to make
explicit. The single non-constructive quantifier is the outer `exists n`.

## 4. Semantic alignment to the source statement

Human approval of this alignment is required and absent. The source statement
here is the planning dossier's line "find a composite positive integer that
passes the exactly specified Baillie-PSW probable-prime test", which is a schema
with the variant left open.

**Quantifier mapping.** `n` maps to "a composite positive integer". The
planning text has no other quantifier; the bounded quantifiers of section 3 are
introduced by the frozen procedure and have no counterpart in the source line.

**Definition mapping.**

- "the exactly specified Baillie-PSW probable-prime test" maps to
  `BPSW-SL-1000` as written in section 1.1 and to no other procedure.
- "passes" maps to the verdict `PROBABLE_PRIME`, with
  `PARAMETER_DEGENERATE` excluded.
- "composite positive integer" maps to `n = a*b` with `1 < a <= b < n`.
- "compositeness certificate" maps to an exhibited factorization re-multiplied
  by exact big-integer arithmetic.

**Assumption delta.** The source line fixes no trial-division bound, no base
set, no discriminant rule, and no Lucas variant; this dossier fixes all four.
The bound `1000` is not cosmetic: it changes the witness set, and it forces
`n >= 1009^2`. If an acquired primary source fixes a different variant, the
strength relation below becomes `unresolved` and the target must be re-frozen as
a new dossier rather than adjusted in place.

**Edge-case delta.** Inputs below `1000` are decided by exact trial division and
can never be witnesses. Perfect squares are rejected in step 4 before the
discriminant search, so the search terminates. The degenerate parameter case
`gcd(n, 2QD) = n` halts with its own verdict and is not a pass. `n = 1` is
outside the procedure's domain and is not composite under the frozen definition.

**Strength relation:** `weaker`. The frozen target instantiates one member of
the variant family the source line leaves open, so it is a strict special case
of that schema. It is not `equivalent`: no primary source has been acquired and
no source text is quoted here.

## 5. Provenance and acquisition plan

Nothing in this table has been fetched. Under ADR-0050 acquisition is
human-planned, exact-URL, and separately authorized, so these rows are a plan
for an operator and not a retrieval. Every locator below is an unverified
recollection written from memory; the operator must confirm each identifier
before acquisition, and a locator that does not resolve is itself a finding to
record rather than a reason to search.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Baillie and Wagstaff, "Lucas pseudoprimes", Math. Comp. 35 (1980) 1391-1417 | doi:10.1090/S0025-5718-1980-0583518-6 | the canonical definitions of Lucas and strong Lucas pseudoprime and the name and exact content of Selfridge Method A and Method A* | pending_acquisition, applicability not_assessed |
| Pomerance, "Are there counterexamples to the Baillie-PSW primality test?", Dopo le parole aangeboden aan A. K. Lenstra, Amsterdam 1984 | no DOI known; locator to be supplied by the operator | the heuristic argument that counterexamples should be plentiful, used as exploration-only route guidance in section 7 | pending_acquisition, applicability not_assessed |
| Grantham, "Frobenius pseudoprimes", Math. Comp. 70 (2001) 873-891 | doi:10.1090/S0025-5718-00-01197-2 | the variant taxonomy relating strong Lucas, extra-strong Lucas, and Frobenius tests, which decides whether a found witness is a witness for the frozen variant only | pending_acquisition, applicability not_assessed |
| Feitsma and Galway tables of base-2 strong pseudoprimes below `2^64` | exact URL unknown and to be supplied by the operator under ADR-0050 | claim 6.1, the reported absence of a witness below `2^64`, and the exact meaning of the enumerated set | pending_acquisition, applicability not_assessed |
| Crandall and Pomerance, "Prime Numbers: A Computational Perspective", 2nd ed., Springer 2005, chapter 3 sections on Lucas and BPSW testing | ISBN 978-0-387-25282-7, chapter 3, exact page range to be confirmed | an independent statement of the doubling recurrences and the strong Lucas condition, to cross-check step 7 against a second wording | pending_acquisition, applicability not_assessed |
| Nicely, "The Baillie-PSW primality test" | exact URL unknown and to be supplied by the operator | claim 6.2, the informal but widely repeated variant description, and the prize-claim context | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each item below is an untrusted candidate inherited from the planning notes or
from recollection. None is a premise of any computation. Each is named as
something the ADR-0055 pre-research novelty re-check must cover, bound to this
problem's subject hash, before any research run starts.

- **6.1** "No BPSW counterexample exists below `2^64`." Untrusted. The planning
  dossier attributes it to the operator's notes. It must be revalidated against
  the enumerated table named in section 5, and the revalidation must establish
  which BPSW variant that enumeration used, because a frontier for one variant
  is not a frontier for `BPSW-SL-1000`.
- **6.2** "Selfridge Method A is the name of the discriminant rule frozen in
  step 5." Untrusted naming. If acquisition shows the name belongs to a
  different rule, section 2's row is corrected and the frozen procedure keeps
  its written content under its own name `BPSW-SL-1000`.
- **6.3** "Infinitely many counterexamples should exist on heuristic grounds."
  Untrusted. It is a heuristic, never a premise, and it may guide the
  structured search of section 7 only as exploration.
- **6.4** "The problem is open." Untrusted and unassessed. This dossier does not
  establish open status.
- **6.5** "A base-2 strong pseudoprime that is also a Lucas pseudoprime is a
  BPSW counterexample." Untrusted as stated, and false for the frozen variant
  unless the Lucas test used is the strong one with Method A parameters. The
  re-check must not conflate the three Lucas variants.
- **6.6** "The search frontier can be extended by direct sweeping." Untrusted
  and, as section 7 shows by direct cost accounting, false for reaching `2^64`
  by the method available here.

## 7. Bounded first slice

Three sub-slices, all offline, all exact integer arithmetic, all producing
machine-readable records. Nothing in this slice calls a model or the network.
The program that performs it must be human-authored; see section 12 for why a
model-authored search program cannot be executed here.

### 7.1 Slice A — a certified exclusion sweep over one frozen interval

**Inputs.** The frozen half-open interval `I = [10^12, 10^12 + 10^7)`.

**Algorithm.** Build the primes up to `10^6` by an exact sieve of Eratosthenes.
Note `isqrt(10^12 + 10^7) < 10^6 + 1`, so every composite in `I` has a prime
factor at most `10^6` and is therefore marked by a segmented sieve of `I` using
those primes. Run that segmented sieve over a `10^7`-byte marking array,
recording for each composite its smallest prime factor. For every composite `n`
in `I`, run `BPSW-SL-1000(n)` and assert the verdict is `COMPOSITE`. Retain the
smallest prime factor as that candidate's compositeness certificate.

**Envelope and cost.** `|I| = 10^7`. The marking cost is
`sum over p <= 10^6 of |I| / p`, on the order of `3 * 10^7` byte writes. About
`92` per cent of composites in `I` have a prime factor below `1000` and are
decided by step 2 alone; the remainder, on the order of `4 * 10^5` candidates,
reach the modular exponentiation of step 3 with a `40`-bit modulus. Measured
counts replace these estimates in the record; the estimates are not premises.

**What exhaustion entails.** Exactly this: for every composite `n` in `I`,
`BPSW-SL-1000(n) = COMPOSITE`. It entails nothing about any `n` outside `I`.
Reaching `2^64` by this method would require about `1.8 * 10^12` such windows,
so this route cannot revalidate claim 6.1 and must not be presented as
progress toward it. Claim 6.1 is settled by acquisition, not by sweeping.

### 7.2 Slice B — exhaustive exclusion over one frozen construction family

**Inputs.** The Chernick form `U_3(k) = (6k+1)(12k+1)(18k+1)` for
`k = 1, 2, ..., 10^6`.

**Algorithm.** Sieve to `1.8 * 10^7` and select every `k` in range for which all
three of `6k+1`, `12k+1`, `18k+1` are prime. For each such `k`, form `n` by
exact multiplication and run `BPSW-SL-1000(n)`.

**Why this family.** The factorization is known by construction, so the
compositeness certificate is free and exact: the record stores the three factors
and the verifier re-multiplies them. The family reaches `n` of about
`1.3 * 10^21`, past `2^64 = 1.845 * 10^19`, which is crossed near
`k = 2.4 * 10^5`. A certified exclusion over this family therefore extends past
the reported frontier *within one exactly defined family*, which is a real and
narrow statement.

**Envelope and cost.** `10^6` values of `k`; the number of triple-prime `k` is
measured, not assumed, and is expected to be on the order of `10^3`. Each
surviving `n` is about `70` bits. Total cost is dominated by the sieve.

**What exhaustion entails.** Exactly this: no `n` of the form `U_3(k)` with all
three factors prime and `k <= 10^6` passes the frozen test. It entails nothing
about other `k`, other Carmichael numbers, or other composites.

### 7.3 Slice C — a congruence-filtered semiprime search

**Inputs.** Primes `p` with `1000 < p < 2^14`; primes `q` with `p < q < 2^24`.

**Filter, and its exact justification.** Every base-2 strong probable prime is a
base-2 Fermat probable prime, so a necessary condition for `n = p*q` to reach
step 7 is `2^(n-1) = 1 (mod p)`, that is `ord_p(2)` divides `n - 1 = p*q - 1`.
Writing `d_p = ord_p(2)`, and noting `d_p` divides `p - 1` so `gcd(p, d_p) = 1`,
this is exactly `q = p^(-1) (mod d_p)`. For each `p` the search therefore
enumerates only one arithmetic progression modulo `d_p`. `d_p` is computed
exactly by factoring `p - 1` by trial division, which is trivial for
`p < 2^14`.

**Algorithm.** Sieve to `2^24`. For each `p`, compute `d_p` and `p^(-1) mod d_p`
exactly, walk the progression, keep prime `q`, form `n = p*q`, and run
`BPSW-SL-1000(n)`. The pair `(p, q)` is the compositeness certificate.

**Envelope and cost.** `1732` values of `p`; the number of pairs is on the order
of `4 * 10^5`, measured at run time. Moduli are at most `38` bits.

**What exhaustion entails.** Exactly this: no semiprime `n = p*q` in the frozen
ranges satisfying the frozen congruence filter passes the test. Because the
filter is a *necessary* condition for passing, the exclusion extends to every
semiprime in those ranges, which is the one place in this slice where a filter
strengthens rather than narrows the conclusion. It entails nothing above
`2^38`, nothing for `p` outside the frozen range, and nothing for numbers with
three or more prime factors.

### 7.4 Canonicalization and what is sampled

Nothing is sampled. All three sub-slices are exhaustive over their frozen
regions. The only quotient applied is `p < q` in slice C, which is a
canonicalization of the unordered pair `{p, q}` and loses no candidate `n`.
Heuristic route guidance from claim 6.3 may shape the choice of a *future*
frozen family; it never filters within a frozen family, because a heuristic
filter would silently turn an exhaustive exclusion into a sampled one.

## 8. Certificate and verifier contract

### 8.1 Result shape R1 — a witness is found

Certificate: the triple `(n, F, T)` where `n` is the integer in exact decimal;
`F` is a list of pairs `(p_i, e_i)` with `prod p_i^e_i` intended to equal `n` and
at least two factors counted with multiplicity; and `T` is the complete
transcript of `BPSW-SL-1000(n)` recording, in order, every prime tried in step
2, the pair `(s, d)`, every residue `x_j` of step 3, the value `isqrt(n)` and
its square from step 4, every trial discriminant `D_i` with its Jacobi symbol
and the selected `D`, the derived `(P, Q)`, the value `g` from step 6, the pair
`(k, m)`, and every `U` and `V` residue computed in step 7.

Independent verifier, which shares no code with the search: re-multiply `F` by
exact big-integer arithmetic and require the product to equal `n` and every
`p_i` to satisfy `1 < p_i < n`; then recompute every step of `BPSW-SL-1000(n)`
from the frozen specification and require every recorded intermediate to equal
the freshly computed one and the final verdict to be `PROBABLE_PRIME`. The
verifier does not need to trust the search, only the arithmetic. A mismatch at
any intermediate is a rejection of the certificate, not a warning.

### 8.2 Result shape R2 — a certified exclusion

Record: the frozen region or family definition verbatim, the enumeration count,
the per-candidate verdict together with the compositeness certificate implied by
the construction (smallest prime factor for slice A, the three factors for slice
B, the pair `(p, q)` for slice C), and a canonical hash of the whole record.

Independent verifier: re-derive the candidate set from the frozen definition
alone, re-run the frozen test, and compare canonical hashes. The record's value
is that it is replayable from the definition, so a disagreement localizes to a
named candidate.

### 8.3 Result shape R3 — a proof that no witness exists

Certificate: a proof object in the repository's existing formal or
human-reviewed channel. This dossier does not predict this shape and provides no
route to it. It is listed so that the target's negation has a declared
certificate contract rather than being unrepresentable.

### 8.4 What is refused as a certificate

- Any floating-point value on the trust path, including a floating-point square
  root in step 4 or a floating-point logarithm used to size a search.
- A model's assertion that an integer is composite, prime, or a witness.
- An unreplayed third-party verdict: a primality or BPSW routine from any
  library, however well regarded, is an untrusted candidate until its verdict is
  reproduced by the independent verifier of section 8.1. Adding such a library
  is also a pinned-dependency decision under the repository's dependency rule.
- Failure of a search. Slices A, B, and C finding nothing is exactly result
  shape R2 and is never evidence for the target's negation beyond its own
  frozen region.
- A witness for a different BPSW variant reported as a witness for this one.

## 9. Useful negative outcomes

The expected outcome is negative and is retained in full:

- **Certified frontier extension.** The R2 records of slices A, B, and C are
  the deliverable: exactly defined regions and families, exhaustively excluded,
  each replayable from its frozen definition and each carrying per-candidate
  compositeness certificates.
- **A reusable exact replay harness.** The step-by-step verifier of section 8.1
  is independent of the search and outlives this slice; it is what makes any
  future candidate checkable at all.
- **A measured cost boundary.** The arithmetic in section 7.1 records, as a
  measured rather than asserted fact, that direct sweeping cannot reach `2^64`.
  That closes the "just search harder" route explicitly and is preserved as a
  refuted route.
- **The refuted-route record.** Any structured family that turns out to be
  provably incapable of producing a witness, and any filter that turns out not
  to be necessary, is preserved machine-readably with the reason, so a later
  run does not repeat it.
- **A variant-sensitivity record.** If a candidate passes some variant but not
  the frozen one, that fact is retained as a distinct outcome and never
  described as a near miss on the frozen target.

## 10. Evaluation protocol

Mirrors the intake JSON exactly. Phase: `exploratory`. Version: `1`.

Metrics:

- `candidates_tested_with_frozen_variant`
- `composite_witnesses_with_exact_factorization`
- `certified_exclusion_regions_recorded`
- `frozen_family_members_exhausted`
- `frozen_test_step_replays_verified`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- `an exhibited composite n with an exact nontrivial factorization re-multiplied to n and a fully replayed PROBABLE_PRIME transcript under the frozen BPSW-SL-1000 procedure`
- `a rigorous proof that no composite positive integer passes the frozen BPSW-SL-1000 procedure`
- `or an explicit unresolved outcome carrying a replayable certified exclusion record and a statement of the smallest remaining obligation`

Stopping rules:

- `stop on an exact certificate: a certified composite witness whose frozen-test transcript replays step by step`
- `stop when the fresh model spend reaches USD 25`
- `stop when two consecutive review points close no obligation and add no new certified exclusion region`
- `never promote exhaustion of a frozen interval or of the frozen construction family into any claim that no composite passes the frozen procedure`
- `halt and re-freeze rather than continue if a candidate passes a BPSW variant other than the frozen one`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Variant drift | A witness for the extra-strong Lucas variant, or for a different trial-division bound, would be reported as "a BPSW pseudoprime" and would be wrong for the frozen target | the variant is written out in section 1.1 and replayed step by step by the section 8.1 verifier; a pass under any other variant is a distinct recorded outcome |
| The target may be false | An unbounded existential search can consume arbitrary budget with no possible success | the deliverable is defined to be the R2 exclusion record; stopping rules cap spend and stagnation; success criteria include the unresolved outcome |
| Sweep illusion | An exhausted interval reads as progress toward `2^64` when it is `10^-12` of it | section 7.1 states the cost arithmetic and the stopping rules forbid promotion; claim 6.1 is routed to acquisition, not to search |
| Library trust | A fast third-party primality routine is the obvious accelerator and its verdict would silently become the certificate | section 8.4 refuses unreplayed third-party verdicts; the independent verifier recomputes from the frozen specification |
| Floating point creeping in | `isqrt`, `log`, and cube-root helpers are commonly float-backed, and a wrong `isqrt` in step 4 changes verdicts | exact integer `isqrt` only; the transcript records `isqrt(n)` and its square so the verifier can check it |
| Nontermination on squares | Omitting step 4 makes the step-5 discriminant search loop forever on a perfect square | step 4 precedes step 5 by construction and the ordering is part of the frozen statement |
| Degenerate parameters read as a pass | `gcd(n, 2QD) = n` leaves the procedure with no Lucas verdict, and a permissive implementation would return "not composite" | a distinct verdict `PARAMETER_DEGENERATE` exists and section 2 records that it is not a pass |
| Heuristic filter contaminating an exhaustive claim | Applying claim 6.3's heuristic inside a frozen family would turn exhaustion into sampling without changing the record's wording | section 7.4 forbids heuristic filtering inside a frozen family; only necessary conditions with written proofs are admitted as filters |
| Model-authored search program | Executing generated code is a capability ADR-0057 leaves disabled | section 12; the slice's program is human-authored, or the run does not happen |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Exact unbounded integer arithmetic
from the standard library, which is all sections 7 and 8 require. Declarative
problem intake and the Phase 1 trust policy, which is what the accompanying JSON
enters. Deterministic serialization, content hashing, and canonical records for
the R2 exclusion records. Machine-readable preservation of failed attempts, which
is what section 9 relies on. Bounded subprocess execution with captured
stdout/stderr and no network. The ADR-0055 pre-research novelty re-check, which
is the mechanism that must cover every claim in section 6 before a run. The
report homes of `make report` and `reports/`, which is where R2 records belong.

**Would require a new ADR.**

- Execution of a model-authored search program. ADR-0057 states that production
  generated-code execution remains disabled until its distinct digest-pinned OCI
  sandbox gate passes. The slice's programs must therefore be human-authored, or
  run only through the offline scripted-port path. This is a hard blocker on the
  otherwise obvious "let the model write the sieve" approach.
- Any third-party arithmetic or primality dependency. Adding one is a pinned
  dependency with a recorded license under the repository's dependency rule, and
  its verdicts remain untrusted candidates regardless.
- A durable, resumable long-running sweep store beyond the existing run-report
  conventions, if a future slice's interval no longer fits one bounded run.
- Any parallel or distributed enumeration. The current runtime is one bounded
  central lead; parallel specialists require ADR-0029 activation evidence.
- Acquisition of any source in section 5, which is a separate ADR-0050
  authorization with an exact URL.

**Explicitly not activated.** No new network path, no model call inside the
arithmetic, no higher search tier, no automated novelty or significance
assessment.

## 13. Open questions before intake

1. Is `BPSW-SL-1000` the variant the operator intends? In particular, is the
   trial-division bound `1000`, is the Lucas test the strong one, and is the
   base-2 test the strong one rather than Fermat? A different answer to any of
   the three is a different dossier.
2. Should the trial-division bound instead be omitted entirely, which would
   admit witnesses with small prime factors and enlarge the target?
3. Is the `PARAMETER_DEGENERATE` verdict acceptable as a non-pass, or should the
   procedure be frozen to reject such inputs as composite? The latter would be
   unsound as written and is not recommended, but it is the operator's call.
4. Are the frozen envelopes of section 7 the right size for a first run, given
   that none of them can reach the reported `2^64` frontier?
5. Which sources in section 5 does the operator authorize for acquisition
   first? Claim 6.1 cannot be revalidated without at least the enumerated table
   row, and the exact URL for that row is unknown to this dossier.
6. Confirm that the intended deliverable is the R2 certified exclusion record
   rather than a witness, so the run is not judged as a failure when it produces
   exactly what section 9 predicts.
