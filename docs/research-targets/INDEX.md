# Scoped Research Target Dossiers

**Compiled:** 22 August 2026
**Planning source:** [RESEARCH_TARGET_DOSSIER_2026-08.md](../RESEARCH_TARGET_DOSSIER_2026-08.md)
**Contents:** 20 scoped dossiers, one per planning candidate, each with a
validated declarative intake file.

This directory expands the twenty candidates of the August 2026 planning
dossier into individually scoped packages. Each candidate has two artifacts: a
prose dossier that freezes one exact target and its verification contract, and
a machine-readable problem definition under `intake/` that is valid against
`schemas/problem-definition-v1.schema.json`.

None of this authorizes research. A dossier does not approve a formalization,
establish that a problem is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Every intake file measures `logical_status = unknown` with zero warrants, zero
evidence, and zero verification records, and every novelty and significance
status is `not_assessed`. The intake grammar has no field that could say
otherwise: defining a problem cannot create trust.

No source was acquired while these were written, and no network call of any
kind was made. Every claim about the literature -- open status, records,
frontiers, catalogue labels -- is carried as an `untrusted_source_report`
assumption with a named acquisition target that would settle it. Section 5 of
each dossier is the acquisition plan for the ADR-0050 human-planned exact-URL
path; section 6 is the list of claims the ADR-0055 pre-research novelty
re-check must cover. Several section 5 locators are unverified recollections
and are marked as such in place.

## Using a dossier

Validate an intake file and confirm it creates no trust:

```
PYTHONPATH=src .venv/bin/python -m math_research.cli problem validate \
  docs/research-targets/intake/<id>-v1.json

PYTHONPATH=src .venv/bin/python -m math_research.cli problem demo \
  docs/research-targets/intake/<id>-v1.json 2026-08-21T00:00:00Z --output-dir <dir>
```

All twenty files currently return `"accepted": true` and measure
`unknown not_assessed not_assessed` with zero trust-bearing records.

## The portfolio

| ID | Tier | Frozen target | Scope | Alignment | Approval |
|---|---|---|---|---|---|
| [A1](a1-erdos-128-local-density.md) | A | Erdos 128: local edge density on half the vertices forcing a triangle | `universal` | `unresolved` | `proposed` |
| [A2](a2-mub-dimension-six.md) | A | Problem 10.2: no four mutually unbiased bases exist in dimension six | `universal` | `unresolved` | `proposed` |
| [A3](a3-tuza-triangle.md) | A | Erdos 167, Tuza's triangle problem: edge covering at most twice edge-disjoint packing | `universal` | `unresolved` | `proposed` |
| [A4](a4-planar-total-coloring-degree-six.md) | A | Total 8-colouring of planar graphs with maximum degree exactly six | `universal` | `unresolved` | `proposed` |
| [A5](a5-erdos-663-least-missing-prime.md) | A | Erdos 663: the least prime missing from k consecutive integers, for every k | `universal` | `unresolved` | `proposed` |
| [A6](a6-cubic-diophantine-z2-y2z-x3.md) | A | Infinitude of the integral solution set of z^2 + y^2 z + x^3 - 2 = 0 | `particular` | `unresolved` | `proposed` |
| [B1](b1-graceful-tree-conjecture.md) | B | Graceful Tree Conjecture: every finite tree with m edges admits a graceful labelling | `universal` | `unresolved` | `proposed` |
| [B2](b2-erdos-126-pairwise-sum-prime-divisors.md) | B | Divergence of f(n)/log n for distinct prime divisors of pairwise sums | `universal` | `unresolved` | `proposed` |
| [B3](b3-dense-polynomial-sparse-square.md) | B | An explicit infinite family of dense integer polynomials with sparse squares | `existential` | `unresolved` | `needs_clarification` |
| [B4](b4-rational-diophantine-septuple.md) | B | Existence of a rational Diophantine septuple of nonzero distinct rationals | `existential` | `unresolved` | `proposed` |
| [B5](b5-earth-moon-biplanar-chromatic.md) | B | Existence of a biplanar graph with no proper nine-colouring | `existential` | `unresolved` | `proposed` |
| [B6](b6-chowla-cosine-negative-excursion.md) | B | Explicit infinite construction with negative cosine-sum excursion of smaller order than the set size | `existential` | `unresolved` | `needs_clarification` |
| [B7](b7-frankl-union-closed.md) | B | Frankl union-closed sets conjecture under frozen empty-set and ground-set conventions | `universal` | `unresolved` | `proposed` |
| [B8](b8-efx-at-least-four-agents.md) | B | EFX existence for at least four agents with additive nonnegative rational valuations and complete allocations | `universal` | `unresolved` | `proposed` |
| [B9](b9-imaginary-quadratic-3-rank.md) | B | One imaginary quadratic field whose class group has 3-rank at least nine | `existential` | `weaker` | `proposed` |
| [C1](c1-baillie-psw-pseudoprime.md) | C | A composite integer passing the frozen BPSW-SL-1000 probable-prime procedure | `existential` | `weaker` | `proposed` |
| [C2](c2-hall-ratio-record.md) | C | Positive integers with sqrt(x) exceeding 100 times the absolute value of y^2 - x^3 | `existential` | `unresolved` | `proposed` |
| [C3](c3-kissing-number-dimension-five.md) | C | Forty-one exact vectors of squared norm four in R^5 with pairwise squared distances at least four | `existential` | `weaker` | `proposed` |
| [C4](c4-ramsey-5-5-lower-bound.md) | C | A 43-vertex graph with no 5-clique and no independent 5-set, giving R(5,5) >= 44 | `existential` | `weaker` | `proposed` |
| [C5](c5-erdos-982-convex-distinct-distances.md) | C | Erdos 982: some vertex of a convex polygon has at least floor(n/2) distinct distances | `universal` | `unresolved` | `proposed` |

## Canonical hashes

A dossier's identity is its canonical problem-definition hash. Re-freezing a
target produces a new hash and is a new intake, not an edit to an approved one.

| ID | Intake file | Canonical problem-definition hash |
|---|---|---|
| A1 | `a1-erdos-128-local-density-v1.json` | `sha256:42fefd73537a6bc117c17f298873b2e8618aa30d380bb458268ea2a3eb390038` |
| A2 | `a2-mub-dimension-six-v1.json` | `sha256:eef08aeec0ee356a29c8d709d6d352b54f9deb73f3dc7de3a21fa3b7d9ddac45` |
| A3 | `a3-tuza-triangle-covering-v1.json` | `sha256:9676a748ba8fddd4a9f6fa4f51ad8e80d1fa89701f6cf2e66478572d47b9c049` |
| A4 | `a4-planar-total-coloring-degree-six-v1.json` | `sha256:e3cbf7a0714f65ba5a61ba14eef85abca029e8235bb4c863f30323748ef87cd0` |
| A5 | `a5-erdos-663-least-missing-prime-v1.json` | `sha256:7d4ee29141b9c1ee60ed12ec2cbd235473734ecb598f1ab96c9c35405eaf65b7` |
| A6 | `a6-cubic-diophantine-z2-y2z-x3-v1.json` | `sha256:fe7ddff0f6b40614eb14e148a9773b72cf61d3243f0e380a427f68faf14ca2c5` |
| B1 | `b1-graceful-tree-conjecture-v1.json` | `sha256:1078d3f3821d325046c5d6b38bf85106cea56fdafa08c27730381bd6f614d08a` |
| B2 | `b2-erdos-126-pairwise-sum-prime-divisors-v1.json` | `sha256:13b192d20d8df2aa3891f687b0859bfa486a50aa6d6f48a6c6c756fcabee14d4` |
| B3 | `b3-dense-polynomial-sparse-square-v1.json` | `sha256:8b96b27114848629027e130e49342ca22f3625e16a85501519ca5d49171f6fed` |
| B4 | `b4-rational-diophantine-septuple-v1.json` | `sha256:d9a0236066df7e822d8bea31e858a28864ac9bc2dec70eb5c81104d3c4640fcf` |
| B5 | `b5-earth-moon-biplanar-chromatic-v1.json` | `sha256:f5df632b4189c74c49f17d218b2fa3d58282a92efb1543caf7236b52d32b30ca` |
| B6 | `b6-chowla-cosine-negative-excursion-v1.json` | `sha256:672166ff614ec7319283de7bee6ae8c627888934f5bb55f153ed630c2b01e039` |
| B7 | `b7-frankl-union-closed-v1.json` | `sha256:0dc51c6a85c448d83c71f5a76dfff146ee927e68689e78ff4a8a845c8a804367` |
| B8 | `b8-efx-at-least-four-agents-v1.json` | `sha256:1048226aed86fad658d4b08f7963ff3f4ed7dfe4d11ea13032a429cd0cb4cf1e` |
| B9 | `b9-imaginary-quadratic-3-rank-v1.json` | `sha256:9f10533b33be4aeb93b4044ba08718d9dcfaa891eda2a2b9e6b51e74d6d4533c` |
| C1 | `c1-baillie-psw-pseudoprime-v1.json` | `sha256:717c11022ab5775060b1e8933bae288e7875671cc573e2495ee8d46797d6453a` |
| C2 | `c2-hall-ratio-record-v1.json` | `sha256:d11fee2cdeeab3627fa0112329a3b6c5a9e94a6ae140c981fef8bbc0734f541f` |
| C3 | `c3-kissing-number-dimension-five-v1.json` | `sha256:d95012df167d86e92535c2d9ea5fa7e99b41a950f1e16f8a875cdb8bb8d23a5a` |
| C4 | `c4-ramsey-5-5-lower-bound-v1.json` | `sha256:88057df6cb8a4c0810c8b4f3921c5515a851c304bdc4b6300531b2d6966b2b9c` |
| C5 | `c5-erdos-982-convex-distinct-distances-v1.json` | `sha256:a64516481754286722ae06f12dc8628be55889825d5e796d87c14edd20bb7580` |

## What scoping the portfolio established

These are exact results derived while freezing the targets. They are recorded
here because each one changes what a first run should do; none is a warrant.

- **A2 was frozen wrong and the error is now content.** An earlier freeze took
  the pair `{I, F_6}` as unextendible. The `Z_6` DFT equals `F_2 (x) F_3` under
  the CRT relabelling in idempotent form, so the pair extends to a triple and
  that target is false. Escalating to Problem 10.2 turned the refutation into a
  structural fact: since a triple exists, no universal-over-pairs argument can
  prove the conjecture, and the target restates as "no triple extends to a
  quadruple", equivalently "the maximum is exactly 3".
- **A5's threshold provably grows in `k`.** Every prime `p <= k` divides one of
  `k` consecutive integers, so `q(n,k) > k` always; with the target's own
  inequality this forces every admissible `N` to satisfy
  `N >= exp(k / (1 + epsilon))`. A `k`-independent threshold is unsatisfiable,
  not merely stronger, and is a rejected reading.
- **A6 has a complete-in-`x` search and a dead route.** Since `z != 0` and
  `z | x^3 - 2`, a triple is a solution iff `-(z + (x^3-2)/z)` is a perfect
  square, so the sweep is complete in `x` rather than a box. The polynomial
  identity `(m^2-17)^3 - 128 = (m^3+3m^2-21m-71)(m^3-3m^2-21m+71)` gives
  infinitely many factorizations of `x^3 - 2`, but the point condition
  `m(m^2-21)/4 = +/- y^2` is genus-one and holds only at `m = 3, 7`. Any
  polynomial-factorization family collapses the same way.
- **B5 caps the clique route exactly.** Biplanar graphs satisfy `E <= 6n - 12`,
  which excludes `K_11` (55 > 54), so the first slice decides whether `K_10` is
  biplanar: a positive answer hits the target, a negative closes the route.
- **B6 removes floating point from an analytic target.** Via
  `cos(a x) = T_a(cos x)` the excursion bound becomes minimization of an integer
  polynomial on `[-1,1]`, certified by a Sturm-sequence positivity certificate
  over `Q` plus one exact rational evaluation.
- **B9's stated verification shape was unsound.** Absent a proof that the chosen
  ideals generate the class group and that the found relations span the relation
  lattice, the relation matrix's `F_3` rank bounds `r_3` from *above* and cannot
  certify a lower bound. The unconditional route is the cubic-field count:
  `r_3 >= 9` iff there are at least `(3^9 - 1)/2 = 9841` pairwise
  non-isomorphic cubic fields of discriminant exactly `D`, which is exact
  integer work and needs no computer-algebra dependency.
- **C2 collapses to one dimension.** Since `r = isqrt(x^3) >= x`, any `y`
  outside `{r, r+1}` forces `|h| >= x` and hence `10000 h^2 > x`. A null sweep
  is therefore universal in `y` rather than sampled.
- **C5's search family omits its own sharpness example.** No rational point set
  is similar to a regular pentagon, equilateral triangle, regular hexagon, or
  regular 7-gon; only `n = 4` survives. Since counterexamples also lie on a
  proper algebraic subset of `R^(2n)`, a null rational-grid sweep is not even
  weak evidence, and that is a stopping rule rather than a caveat.

## Open operator decisions

1. **C4 is the one item to hold.** `R(5,5) = 43` is the reported conjecture, so
   the frozen existential on 43 vertices may be unachievable by construction
   rather than merely hard. The alternative is the bounded exclusion statement
   "no vertex-transitive graph on 43 vertices is a `(5,5,43)` graph", where the
   identical circulant sweep becomes the deliverable. C4 also needs operator
   confirmation of portfolio membership at all: the planning dossier records
   that its inclusion was inferred from one blank entry.
2. **A2's realistic deliverable is a certified exclusion set of pairs.** Problem
   10.2 cannot be proved by one slice. If an exclusion set is not acceptable
   output, A2 should not be scheduled.
3. **B3 and B6 are `needs_clarification` by design.** B3's one-instance
   threshold was lost in the supplied rendering and was deliberately not
   reconstructed; B6's normalization, domain, and excursion definition must come
   from the primary source. Neither should be intaken before those are supplied.
4. **B9's target rank is calibrated against an untrusted record.** Rank 9 assumes
   the reported record of 8. If the pre-research re-check finds a published
   field with `r_3 >= 9`, the dossier is void before it starts.
5. **Four dossiers retain `strength_relation: weaker`** -- B9, C1, C3, C4. Each
   instantiates a parameter the planning dossier itself left free (B9's prime and
   rank, C1's test variant) or picks one direction of an interval (C3, C4). C3
   and C4 rejected their upper-bound routes because the natural certificate is a
   floating-point SDP or a third-party exhaustive certificate; if either route is
   wanted, it needs its own ADR and its own dossier.
6. **Void-on-recheck targets.** C1, C2, C3, C4, and B9 each assume a current
   record or frontier that the pre-research re-check may overturn, in which case
   the target must be re-frozen rather than pursued.

## Note on the planning dossier's activation order

The planning dossier's recommended activation order predates these freezes and
is now partly stale. A2 escalated from one pair to the full four-MUB conjecture,
and A4, A5, B1, B7, and B8 escalated from a subclass or fixed parameter to their
full statements, so their reach per slice is smaller than that order assumed. In
every case the narrow statement survives as the first-slice waypoint in section
7, with the residual named explicitly wherever the waypoint is reported.
