# C4. Ramsey number `R(5,5)`, lower-bound route — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item C4 (tier C)
**Declared domain:** ramsey-theory
**Intake file:** docs/research-targets/intake/c4-ramsey-5-5-lower-bound-v1.json
**Frozen in one line:** Exhibit one finite simple undirected graph on 43
vertices containing neither a clique of size 5 nor an independent set of size 5,
which would establish `R(5,5) >= 44`.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish that `R(5,5)` is open at any particular value,
authorize source acquisition, assess novelty, significance, or source
applicability, create mathematical warrant, admit anything to a claim graph, or
activate a capability. Novelty, significance, and source applicability are
`not_assessed`, and every external statement quoted or paraphrased below is an
untrusted candidate that the ADR-0055 pre-research novelty re-check must cover
before any work starts.

## 1. Frozen target

Let `G = (V, E)` be a finite simple undirected graph: `V` is a finite set, `E`
is a set of unordered pairs of distinct elements of `V`, there are no loops and
no repeated pairs, and edges carry no direction or weight.

For `S subset V`, say `S` is a **clique** of `G` if every unordered pair of
distinct elements of `S` lies in `E`, and say `S` is an **independent set** of
`G` if no unordered pair of distinct elements of `S` lies in `E`.

The frozen target is the following existential statement.

> There exists a finite simple undirected graph `G = (V, E)` with `|V| = 43`
> such that for every `S subset V` with `|S| = 5`, `S` is not a clique of `G`
> and `S` is not an independent set of `G`.

Quantifiers, fully explicit:

`exists G = (V,E) simple, |V| = 43, forall S subset V with |S| = 5 :`
`(exists {u,v} subset S, u != v, {u,v} not in E) and`
`(exists {u,v} subset S, u != v, {u,v} in E)`

The inner conjunction is the negated-clique and negated-independence condition
written in the form the verifier actually tests: some pair of `S` is a
non-edge, and some pair of `S` is an edge.

A graph with this property is written `(5,5,43)` in the small-Ramsey-number
literature convention: a `(s,t,n)` graph is a graph on `n` vertices with no
clique of size `s` and no independent set of size `t`.

**Consequence, and the only consequence claimed.** By the equivalence spelled
out in section 2.1, the existence of such a `G` gives `R(5,5) > 43`, that is
`R(5,5) >= 44`. It gives no upper bound, does not determine `R(5,5)`, and does
not by itself say anything about graphs on 44 or more vertices.

**Why this member of the planning item.** The planning dossier states item C4
as a disjunction over three routes: construct a 43-vertex witness, prove
`R(5,5) >= 44`, or prove `R(5,5) <= 45`. A disjunction is not a target. The
lower-bound existential is frozen because it is the only one of the three whose
positive outcome is a single finite object that an independent verifier can
replay end to end in exact integer arithmetic with no third-party trust. The
second route as phrased is the same statement as the first by section 2.1 and
is therefore not a separate route. The third route is deliberately excluded and
section 12 records why.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| graph | finite simple undirected graph: no loops, no multi-edges, no directions, no weights, no vertex or edge labels beyond the vertex names used for serialization | multigraph; digraph; graph with loops; weighted graph; infinite graph |
| `V` | the fixed labelled vertex set `{0,1,...,42}`, so `|V| = 43` | an unspecified 43-element set; an isomorphism class treated as the object of record (the property is isomorphism-invariant, but the certificate is a specific labelled edge list) |
| clique of size 5 | a set of 5 vertices pairwise adjacent | a `K_5` subdivision; a `K_5` minor; a topological `K_5`; a clique in the complement; a maximal clique |
| independent set of size 5 | a set of 5 vertices pairwise non-adjacent | an induced matching; a maximal independent set; a dominating set; an independent set in a line graph |
| "no clique of size 5" | clique number `omega(G) <= 4` | "no clique of size exactly 5 but a clique of size 6 permitted" — impossible, see the monotonicity row |
| clique-size monotonicity | a graph containing a clique of size `k >= 5` contains a clique of size exactly 5, namely any 5 of its vertices; identically for independent sets | treating "at least 5" and "exactly 5" as different conditions |
| `R(s,t)` | the least `n >= 1` such that every assignment of one of two colours red/blue to each edge of the complete graph `K_n` yields a red clique on `s` vertices or a blue clique on `t` vertices | the least `n` such that *some* colouring has that property; a vertex-colouring Ramsey number; a hypergraph Ramsey number `R^(3)(s,t)`; a multicolour number `R(s,t,u)`; an off-diagonal size-Ramsey or Ramsey-minimal parameter |
| 2-colouring | a total function from the edge set of `K_n` to `{red, blue}`; every edge gets exactly one colour; colourings are not required to be proper | a partial colouring; a proper edge colouring; a colouring of vertices |
| the number 43 | the exact vertex count of the sought object, chosen so that a witness yields `R(5,5) >= 44` | 42 (a 42-vertex witness yields only `R(5,5) >= 43`, which the supplied range already reports); 44; 45 |
| `R(5,5) >= 44` | the arithmetic consequence of a 43-vertex witness, and nothing more | "`R(5,5) = 44`"; "`R(5,5)` determined"; "the lower bound improved by one in general" without naming which bound |
| supplied range `43 <= R(5,5) <= 46` | an untrusted planning-note figure, not a premise of the frozen target | a trusted fact; a licence to skip the pre-research re-check |
| circulant graph on `Z_43` | for `S subset {1,...,21}`, the graph on `Z_43` with `i` adjacent to `j` iff the class `{+-(i-j) mod 43}` is named by `S` | a Cayley graph on a nonabelian group of order 43 (there is none, 43 is prime); a circulant on a composite order; a general vertex-transitive graph (see the Turner row) |
| the frozen search family | exactly the circulant graphs on `Z_43`, enumerated as in section 7 | all 43-vertex graphs; all regular 43-vertex graphs; all Cayley graphs on all groups |
| exhaustion of the family | a universal statement about that finite family only | a bound on `R(5,5)`; a nonexistence statement about 43-vertex graphs |

### 2.1 The colouring/graph equivalence, spelled out

The frozen target is stated about graphs, while `R(5,5)` is defined about
edge-colourings. The two formulations are interchangeable, and because the
substitution is the load-bearing step between the target and its consequence it
is written out here rather than cited.

Fix `n` and the vertex set `[n] = {1,...,n}`. Let `K_n` have edge set `E_n`, the
set of all unordered pairs of distinct elements of `[n]`.

*Map from colourings to graphs.* Given a 2-colouring `c : E_n -> {red, blue}`,
define `G_c = ([n], E)` with `{u,v} in E` iff `c({u,v}) = red`.

*Map from graphs to colourings.* Given a graph `G = ([n], E)`, define
`c_G({u,v}) = red` if `{u,v} in E` and `blue` otherwise.

These two maps are mutually inverse, so they are a bijection between the
2-colourings of `E_n` and the graphs on `[n]`.

Under the bijection, a set `S subset [n]` with `|S| = s` spans a red clique in
`c` if and only if every pair inside `S` is red, if and only if every pair
inside `S` is an edge of `G_c`, if and only if `S` is a clique of `G_c`.
Symmetrically `S` spans a blue clique in `c` if and only if no pair inside `S`
is an edge of `G_c`, if and only if `S` is an independent set of `G_c`.

Therefore, for each `n`:

> every 2-colouring of `E_n` contains a red clique on `s` vertices or a blue
> clique on `t` vertices
> **iff** every graph on `[n]` contains a clique of size `s` or an independent
> set of size `t`.

Negating and taking the least `n` in the definition of `R(s,t)`:

> `R(s,t) > n` **iff** there exists a graph on `n` vertices with no clique of
> size `s` and no independent set of size `t`.

With `s = t = 5` and `n = 43`: the frozen existential holds iff `R(5,5) > 43`,
i.e. iff `R(5,5) >= 44`. Note also that complementation `E -> E_n \ E`
corresponds to swapping the two colours, so for the diagonal case `s = t` the
family of `(5,5,43)` graphs is closed under complementation; section 7 uses
this as an exact symmetry quotient.

## 3. Formalization and quantifiers

Formal language: `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment in section 4 is still required and is
not implied by this document.

```
exists G : SimpleGraph,
  VertexSet(G) = {0,1,...,42}
  and forall S subset VertexSet(G), Card(S) = 5 ->
        (exists u v in S, u != v and {u,v} notin EdgeSet(G))
        and (exists u v in S, u != v and {u,v} in EdgeSet(G))
```

Quantifier list, in the order the verifier consumes it:

1. `exists G` a finite simple undirected graph with vertex set `{0,...,42}`.
2. `forall S` a 5-element subset of `{0,...,42}`; there are exactly
   `C(43,5) = 962598` such subsets.
3. `exists {u,v} subset S` a non-adjacent pair, witnessing that `S` is not a
   clique.
4. `exists {u,v} subset S` an adjacent pair, witnessing that `S` is not
   independent.

Arithmetic type discipline: the whole target is decidable by finite Boolean and
integer operations on a `43 x 43` symmetric zero/one adjacency matrix. No
rational, algebraic, or real arithmetic appears anywhere on the trust path, and
therefore no floating point can appear either. The exact-arithmetic assumption
claim in the intake file records this as a hard constraint rather than an
implementation preference.

Size figures on the record, all exact:

- vertex pairs: `C(43,2) = 903`, so an edge list has at most 903 entries.
- five-subsets to check per candidate graph: `C(43,5) = 962598`.
- pair lookups for a full unpruned check: `962598 * 10 = 9625980`.
- graphs on 43 labelled vertices: `2^903`, a 272-digit integer. Unstructured
  search over this space is not a plan and is named as a forbidden route.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- planning "a graph on 43 vertices" -> `exists G` with vertex set `{0,...,42}`,
  finite simple undirected.
- planning "neither a 5-clique nor an independent set of size 5" -> `forall S`
  with `|S| = 5`, `S` is neither a clique nor an independent set.
- planning "proving `R(5,5) >= 44`" -> not a separate quantifier structure; by
  section 2.1 it is the same statement as the witness clause.

**Definition mapping.**

- "5-clique" -> a set of 5 pairwise adjacent vertices.
- "independent set of size 5" -> a set of 5 pairwise non-adjacent vertices.
- "`R(5,5)`" -> the least `n` such that every 2-colouring of `E(K_n)` contains a
  red clique on 5 vertices or a blue clique on 5 vertices.
- "improve the supplied range" -> not mapped; the range is untrusted planning
  data and is not part of the frozen statement.

**Assumption delta.**

- The planning item is a three-way disjunction; this dossier freezes one
  disjunct, the 43-vertex existential. The other two are out of scope and
  section 12 records the capability reason for excluding the upper-bound route.
- The planning item presents the supplied interval `43 <= R(5,5) <= 46` as
  context. This dossier does not assume either endpoint. The interval enters
  only as an untrusted source report that the pre-research re-check must
  revalidate.
- The vertex set is fixed to `{0,...,42}` so that the certificate is a concrete
  serializable object with a content hash, rather than an isomorphism class.
- Vertex-transitivity, regularity, and circulant structure are properties of the
  *first search family*, not hypotheses of the frozen target. The target admits
  any 43-vertex graph.

**Edge-case delta.**

- A graph on 43 vertices with no clique of size 5 and no independent set of size
  5 necessarily has `omega(G) <= 4` and `alpha(G) <= 4`; the two conditions are
  the same condition stated for `G` and for its complement.
- The empty graph on 43 vertices and the complete graph on 43 vertices both fail
  immediately, the first on independence and the second on cliques; no
  degenerate case survives.
- No `S` with `|S| < 5` is examined. A clique of size 4 is permitted and
  expected.
- Because 5 is odd and the case is diagonal, self-complementary candidates are
  admissible and are not excluded by the symmetry quotient in section 7.

**Strength relation:** `weaker`. The frozen target is a strict special case of
the planning item's disjunction: one direction, one vertex count, one result
shape. The relation is recorded as `weaker` rather than `equivalent` because no
primary source has been acquired and quoted in this task, so no equivalence
claim to any source text is available.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` with applicability `not_assessed`. No row has
been fetched, and this dossier authorizes no fetch. Under ADR-0050, acquisition
is human-planned, public-unauthenticated, exact-URL, and separately authorized.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Radziszowski, *Small Ramsey Numbers*, Electronic Journal of Combinatorics dynamic survey DS1, current revision | `https://www.combinatorics.org/ojs/index.php/eljc/article/view/DS1`, the diagonal table row for `R(5,5)` and its cited lower-bound reference | settles claim S1 (the current published lower bound) and claim S3 (the current published upper bound) | pending_acquisition |
| Exoo, lower bound for `R(5,5)` (a 42-vertex construction), *Journal of Graph Theory* | journal article page for the `R(5,5) >= 43` construction, cited from DS1's `R(5,5)` row; volume, year, and page range to be read off DS1 rather than assumed | settles claim S1 and supplies the 42-vertex base graph for the extension route in section 7 | pending_acquisition |
| Angeltveit and McKay, upper bound `R(5,5) <= 46` | arXiv abstract page for the 2024 preprint of that title; the exact arXiv identifier must be read from DS1's citation and not reconstructed | settles claim S3, and documents why the upper-bound route needs a third-party exhaustive certificate | pending_acquisition |
| McKay's combinatorial data pages, Ramsey graph section | `https://users.cecs.anu.edu.au/~bdm/data/ramsey.html`, the `(5,5,42)` graph file listing | settles claim S4 (existence and count of `(5,5,42)` graphs) and supplies extension-route inputs as data | pending_acquisition |
| Radziszowski and McKay, determination of `R(4,5) = 25` | journal article cited for `R(4,5)` in DS1's off-diagonal table | settles claim S5, on which the degree-window pruning in section 7 is conditional | pending_acquisition |
| Turner, point-symmetric graphs with a prime number of points, *Journal of Combinatorial Theory* (1967) | journal article page; exact volume and pages to be confirmed from a secondary index before acquisition | confirms the hypotheses of the vertex-transitive strengthening in section 9 | pending_acquisition |
| Post-2025 literature on `R(5,5)` bounds | to be assembled by the operator under ADR-0055 as the pre-research novelty re-check protocol, using terminology and equivalent-formulation searches for "Ramsey graph", "(5,5,43)", "clique-independent set", and "diagonal Ramsey lower bound" | settles claim S2 (whether the frozen target is already achieved, already refuted, or void) | pending_acquisition |

Locator honesty note. Only the two web locators above are given as complete
URLs; every bibliographic row names the work and the field it must be looked up
in rather than a volume/page/DOI string. Volume numbers, page ranges, years, and
arXiv identifiers reconstructed from memory would be fabricated locators, and a
fabricated locator is worse than a missing one because it looks acquirable. The
operator resolves each row from the DS1 citation list at acquisition time.

## 6. Prior-status claims to re-check

Every claim in this section is an **untrusted source report**. None is a premise
of the frozen target. Each is named here so that the ADR-0055 pre-research
novelty re-check has an explicit checklist, and each is carried into the intake
file as an `untrusted_source_report` assumption with scope `particular`.

- **S1 — the lower bound is 43.** The planning dossier supplies
  `43 <= R(5,5) <= 46`, which means the best published lower bound corresponds
  to a 42-vertex witness. Untrusted. **This claim is void-triggering**: if the
  published lower bound is already 44 or more, then a 43-vertex witness is
  either already known or already excluded, the frozen target is void, and it
  must be re-frozen at `n` equal to the confirmed lower bound or higher before
  any work begins. The re-check must therefore report the exact current lower
  bound as a number, not as an interval.
- **S2 — the conjecture `R(5,5) = 43`.** It is widely reported that `R(5,5)` is
  conjectured to equal 43. Untrusted, and load-bearing in the adversarial
  direction: if that conjecture is true, then no `(5,5,43)` graph exists and the
  frozen existential is **false**. The frozen target is therefore an existential
  that the field is reported to expect to fail. This is recorded plainly rather
  than smoothed over: section 9 exists because the negative branch is the likely
  branch, and section 13 asks the operator to confirm that an
  expected-to-be-false existential is an acceptable target.
- **S3 — the upper bound is 46.** Reported in the planning notes; commonly
  attributed to a 2024 preprint. Untrusted. Not a premise. It matters only for
  section 12's account of why the upper-bound route is out of scope.
- **S4 — `(5,5,42)` graphs exist and are numerous.** Implied by S1 and by the
  existence of published Ramsey-graph data files. Untrusted, including any count.
  The extension route in section 7 depends on it and is labelled accordingly.
- **S5 — `R(4,5) = 25`.** A computational determination from the literature.
  Untrusted. It implies the degree window `18 <= deg(v) <= 24` for every vertex
  of a `(5,5,43)` graph, derived in section 7. Because the window rests on a
  literature value rather than a replayed proof, the pruning it licenses is
  **exploration-only**: the coverage claim in section 7 is computed over the
  unpruned family, and the pruned run may be used only to find candidates
  faster, never to justify a nonexistence statement.
- **S6 — tier placement of `R(5,5)` rests on an inference.** The planning
  dossier states, in its own words, that the Tier C request contained one blank
  entry, that `R(5,5)` was included because it was the only item in the supplied
  N1-N15 notes not otherwise represented, and that this inference requires
  operator confirmation before canonical intake. This is not a mathematical
  claim but it is a blocking intake condition, and it is carried to section 13
  as such.
- **S7 — the circulant family may already be settled.** No claim either way is
  inherited, but if the nonexistence of a cyclic `(5,5,43)` graph is already
  published, then the negative outcome of section 7 is a reproduction. Under
  ADR-0055 that outcome would carry report class `independent_verification` and
  must never be presented as new. The re-check must search for it explicitly.

None of S1 through S7 creates novelty status, significance, applicability, graph
admission, or mathematical warrant, and an empty search never means novel.

## 7. Bounded first slice

The first slice does not search the space of 43-vertex graphs. It exhausts one
frozen finite family in exact arithmetic and records what that exhaustion does
and does not entail.

**Frozen family.** The circulant graphs on `Z_43`. For `S subset {1,...,21}`,
define `G_S` on vertex set `Z_43` by making `i` and `j` adjacent iff the
difference class `{+-(i-j) mod 43}` is named by `S`. Since 43 is an odd prime,
the 42 nonzero residues fall into exactly 21 classes `{i, 43-i}` for
`i = 1,...,21`, so the family has exactly `2^21 = 2097152` members, each
`2|S|`-regular and vertex-transitive.

**Inputs.** The prime 43; the class set `{1,...,21}`; nothing else. No acquired
source, no model output, and no external file is an input to the slice. The
slice is fully reproducible from those two constants.

**Exact symmetry quotient, and its verification.** Two group actions preserve
the property of being a `(5,5,43)` graph.

1. *Multipliers.* For a unit `u` in `Z_43^*`, the map `x -> u x` is a graph
   isomorphism from `G_S` to `G_{uS}`, where `uS` is the image of `S` under the
   induced permutation of the 21 classes. The kernel of that induced action is
   `{+-1}`, so the acting group is `Z_43^* / {+-1}`, cyclic of order 21, and it
   acts on the 21 classes as the regular representation of a cyclic group of
   order 21. This was confirmed by direct computation: the 42 units induce
   exactly 21 distinct permutations of the class set.
2. *Complementation.* `G_S` is a `(5,5,43)` graph iff its complement
   `G_{{1,...,21} \ S}` is, by the colour-swap remark at the end of section 2.1.

Orbit count under the group of order 42 generated by both, computed two
independent ways that must agree exactly before any coverage claim is made:

- Burnside over the multiplier action alone gives
  `(1/21) * sum_{d | 21} phi(21/d) * 2^d`
  `= (1/21) * (12*2 + 6*8 + 2*128 + 1*2097152) = 2097480 / 21 = 99880`
  orbits. Adjoining complementation contributes no new fixed points, because a
  set fixed by "permute then complement" would satisfy `|S| = 21 - |S|` and 21
  is odd, so the count becomes `2097480 / 42 = 49940`.
- Direct union-find over all `2^21` subsets, applying all 21 multiplier
  permutations and complementation, returns **49940** classes.

Both computations return 49940. That agreement is the coverage proof and is
recorded as a datum of the run; a coverage claim made on one computation alone
is refused, because a silent off-by-one in the orbit partition would drop
candidates without any visible failure.

**Per-candidate exact test.** Represent `G_S` as 43 integers, each a 43-bit
adjacency row; all operations are integer bit operations.

- *Reference test, authoritative.* Enumerate all `C(43,5) = 962598` five-subsets
  and for each check its 10 pairs, `9625980` lookups, asserting that at least
  one pair is present and at least one pair is absent. This is the test whose
  output is admitted.
- *Vertex-transitive reduction.* Every member of the family is
  vertex-transitive, so a clique or independent 5-set exists iff one exists
  containing vertex 0. That reduces the reference test to `C(42,4) = 111930`
  four-subsets per candidate. The reduction is exact but is valid **only**
  because the family is vertex-transitive; it must be disabled the moment any
  non-transitive candidate enters, and the intake file records this as a trap.
- *Accelerator, exploration-only.* A bitset-pruned depth-5 clique search on
  `G_S` and on its complement finds a witness far faster. It is used to reject
  candidates quickly. Any candidate that survives the accelerator is re-run
  through the reference test before it is called a witness.

**Exhaustive upper bound on cost, on the record.** `49940 * 111930 = 5589784200`
four-subset tests if no candidate short-circuits. Realized cost is far lower
because almost every candidate yields a witness within the first few subsets,
but the exhaustive figure is the number that must fit inside the frozen
wall-clock and CPU envelope, and section 11 treats a truncated run as an
unresolved outcome with a recorded frontier rather than as a partial result.

**Conditional pruning, exploration-only.** If S5 holds, that is if
`R(4,5) = 25`, then in any `(5,5,43)` graph the neighbourhood of a vertex `v`
induces a graph with no clique of size 4 and no independent set of size 5, so
`deg(v) <= 24`; and the non-neighbourhood of `v` induces a graph with no clique
of size 5 and no independent set of size 4, so `42 - deg(v) <= 24`, giving
`deg(v) >= 18`. Hence `18 <= deg(v) <= 24`, and for a circulant with
`deg = 2|S|` this leaves `|S| in {9,10,11,12}`, that is
`293930 + 352716 + 352716 + 293930 = 1293292` subsets, a set closed under
complementation since `21 - 9 = 12` and `21 - 10 = 11`. This is a genuine
reduction but it inherits the untrusted status of S5, so it may only order the
search. The coverage claim is computed over all 49940 unpruned classes.

**What is enumerated exhaustively versus not.** The 49940 classes are
enumerated exhaustively. Nothing else in this dossier is exhaustive. A second
route is available and is explicitly non-exhaustive:

*Extension route, non-exhaustive.* Let `G` be a `(5,5,42)` graph and let
`N subset V(G)`. Form `G + v` with `N_{G+v}(v) = N`. Then `G + v` has no clique
of size 5 iff `G` has none and `N` induces no clique of size 4; and `G + v` has
no independent set of size 5 iff `G` has none and `V(G) \ N` induces no
independent set of size 4. Both directions are immediate: any offending set
either avoids `v`, and is then an offending set of `G`, or contains `v`, and its
remaining four vertices lie in `N` in the clique case and in `V(G) \ N` in the
independence case. This is an exact reduction and it is retained as a lemma
regardless of outcome. It does not make the route feasible: there are `2^42`
candidate neighbourhoods per base graph. Expressing the condition as a
propositional formula and demanding a checked UNSAT proof log per base graph
would turn a failed search into a certificate, and section 12 records that this
needs a new ADR because no proof-log verifier exists in this repository.

**Boundary of the claim the slice can support.** Exhausting the frozen family
supports exactly one universal statement, and it is universal over a finite
family rather than over graphs: *no circulant graph on `Z_43` is a `(5,5,43)`
graph.* Given the Turner hypotheses confirmed, it upgrades to: *no
vertex-transitive graph on 43 vertices is a `(5,5,43)` graph.* It does **not**
support `R(5,5) = 43`, does **not** support the nonexistence of a `(5,5,43)`
graph, does **not** yield any bound on `R(5,5)`, and does **not** become
evidence for the conjecture S2. A finite search never becomes a universal claim
about the unrestricted target, and a report, summary, or status line that
implies otherwise is a defect.

## 8. Certificate and verifier contract

**Result shape A — a witness graph is found.**

Certificate format, a single UTF-8 text file, LF line endings, no trailing
whitespace:

```
n 43
e <u> <v>          # one line per edge, 0 <= u < v <= 42, ascending
                   # lexicographically by (u,v), at most 903 lines
```

plus a sidecar record giving the SHA-256 of the canonical bytes of that file,
the family the candidate came from, and, if it is a circulant, the generator set
`S`. Independent verifier: a program that reads only the certificate file,
recomputes the SHA-256 and compares it, rebuilds the adjacency matrix,
enumerates all `C(43,5) = 962598` five-subsets with the reference test, and
asserts for each that at least one pair is present and at least one is absent.
The verifier does not receive the search code, the generator set, or any
intermediate state, and it must not read the accelerator's output. It uses
integer arithmetic only. Its verdict plus the hash is the whole trust path.

**Result shape B — the frozen family is exhausted with no witness.**

Certificate format, a machine-readable exclusion log:

```
family: circulant graphs on Z_43, S subset {1,...,21}
orbit_count_burnside: 49940
orbit_count_unionfind: 49940
records: one per class, each carrying
  representative S (sorted list of classes)
  witness_kind: clique | independent_set
  witness: the 5 vertices, ascending
```

Independent verifier: for every record, rebuild `G_S`, confirm the recorded
five-set really is a clique of `G_S` or really is an independent set of `G_S`,
and confirm the recorded `witness_kind` matches. Then re-derive the orbit
partition from `S`-space independently, confirm that the 49940 representatives
cover all `2^21` subsets exactly once up to the declared group, and confirm both
orbit counts. Coverage failure is a hard failure. Note the asymmetry that makes
this shape cheap and honest: each exclusion is certified by an exhibited
offending 5-set, so the verifier never has to trust the search.

**Result shape C — an unresolved outcome.** The retained artifact is the
frontier: which classes were checked, their witnesses, which were not reached,
the exact envelope consumed, and the smallest remaining obligation. It is a
record, not a certificate, and it is labelled as such.

**Refused as a certificate, without exception.**

- Any floating-point output, at any point on the trust path. There is no
  legitimate use for floating point in this problem; its appearance is a defect,
  not a tolerance question.
- A model's assertion that a graph works, a model-written proof sketch, or a
  model's summary of a search. Under ADR-0040 and ADR-0057 a model may propose
  and may write a bounded program; it never creates the result.
- An unreplayed third-party program or its output, including a published
  exhaustive computation. Admitting one would need its own ADR; see section 12.
- Failure of any search, heuristic, SAT solver timeout, or truncated run, as a
  nonexistence claim. Exhaustion of the frozen family is a statement about the
  family only, per section 7's boundary.
- A witness whose vertex count is not exactly 43, or whose edge list does not
  hash to the recorded value.
- Human or model agreement, replication across runs, or "the accelerator and
  the reference test agree" in place of the reference test itself.

Under ADR-0036 the environment of any resulting claim is computed from its
records and never declared: an exactly verified witness reaches `Proposition`,
and nothing in this slice can reach `Theorem`, because that requires a bare
`kernel_checked` attestation on a `verified` representation and no Lean
formalization is in scope here.

## 9. Useful negative outcomes

The negative branch is the expected branch, per S2. It is designed to be the
deliverable rather than the residue.

- **The exclusion set with witnesses.** 49940 classes, each with an exhibited
  offending five-set. This is a reusable, independently checkable object: any
  later search over circulants on `Z_43`, for this or a related Ramsey
  parameter, starts from it rather than repeating it.
- **A genuine universal statement over a finite family.** "No circulant graph on
  `Z_43` is a `(5,5,43)` graph" is proved, not estimated, by the exhaustion, and
  it is a legitimate universal claim precisely because the family is finite and
  fully covered. With the Turner hypotheses confirmed against a primary source,
  it strengthens to "no vertex-transitive graph on 43 vertices is a `(5,5,43)`
  graph", because 43 is prime and every vertex-transitive graph on a prime
  number of vertices is a circulant. That strengthening is retained separately
  from the exhaustion result so that a failure of the attribution check does not
  contaminate the exhaustion result.
- **The extension lemma.** The exact characterization of when `G + v` remains a
  `(5,5)` graph, stated and proved in section 7, is retained whether or not it
  is used. It reduces the lower-bound question at 43 to a purely local condition
  on one neighbourhood of one added vertex.
- **The degree window.** `18 <= deg(v) <= 24` for every vertex of a `(5,5,43)`
  graph, conditional on `R(4,5) = 25`, is retained with its dependency named. A
  conditional structural constraint recorded with its condition is worth more
  than an unconditional one asserted without provenance.
- **The refuted-route record.** Unstructured search over `2^903` graphs, and
  random or heuristic search without a certificate contract, are recorded as
  routes not to repeat, with the reason.
- **The frontier**, machine-readable, if the envelope truncates the run.

Every one of these is preserved in machine-readable output, per the repository
engineering rule that failed attempts and missing-tool results are retained
rather than discarded.

## 10. Evaluation protocol

Version 1, phase `exploratory`. The strings below are the same strings as the
intake file's `evaluation_protocol`.

**Metrics.**

- `candidate_graphs_exactly_checked`
- `circulant_multiplier_orbits_exhausted`
- `five_subsets_exactly_enumerated`
- `exclusion_witnesses_recorded`
- `failed_routes_preserved`
- `model_cost_usd`

**Success criteria.**

- an exhibited 43-vertex graph, given as a canonical hashed edge list, whose
  exhaustive exact check of all 962598 five-subsets finds no clique of size 5
  and no independent set of size 5
- an exact exclusion certificate covering every one of the 49940 multiplier-and-
  complement classes of circulant graphs on Z_43, each class carrying a witness
  five-subset, which settles the circulant family and settles nothing else
- or an explicit unresolved outcome that records the smallest remaining
  obligation, the exclusion set reached, and the exact frontier of the
  enumerated family

**Stopping rules.**

- stop on an exact certificate: a hashed 43-vertex edge list whose independent
  verifier replay finds no clique of size 5 and no independent set of size 5
- stop when the frozen circulant family is exhausted, recording one witness
  five-subset per class
- stop when the fresh model spend reaches USD 20
- stop when no new exclusion witness, reduction, or family extension has been
  recorded for two consecutive review points
- never promote exhaustion of the frozen finite family into a bound on R(5,5) or
  into a nonexistence claim about 43-vertex graphs; a stopped search records an
  unresolved outcome

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The frozen existential may simply be false, since `R(5,5) = 43` is the reported conjecture (S2) | A target expected to fail produces no positive outcome however much is spent, and the temptation is then to dress the negative up | The negative branch is the designed deliverable (section 9); the exclusion certificate is a first-class success criterion; section 13 asks the operator to confirm the target rather than assuming it |
| The supplied lower bound 43 may be stale (S1) | If the published bound is already 44 or more, the target is void and every hour spent is wasted or, worse, is a rediscovery | S1 is marked void-triggering; the ADR-0055 pre-research re-check must report the current lower bound as an exact number before the first run, and a bound of 44 or more forces a re-freeze |
| `2^903` labelled graphs | Any unstructured, random, or heuristic sweep is futile at this scale, and a futile sweep still produces logs that look like work | Only exactly enumerable families are admitted; the family is frozen before search; unstructured search is recorded as a forbidden route in the intake file |
| Rediscovery: the circulant family may already be excluded in the literature (S7) | An exhaustion that duplicates a published result presented as new is a provenance failure, not a mathematical one | Section 5 acquisition plus the ADR-0055 re-check search for it explicitly; if found, the outcome carries report class `independent_verification`, exactly as the Graffiti 197 regression does |
| The degree-window pruning depends on the literature value `R(4,5) = 25` (S5) | A wrong literature value silently removes candidates, and the resulting "exhaustion" would cover less than it claims | Pruning is exploration-only and may reorder the search; the coverage claim is computed over all 49940 unpruned classes |
| Orbit-partition error | An off-by-one in the symmetry quotient drops candidates with no visible failure, and the coverage claim becomes false while every test still passes | Two independent orbit counts, Burnside and union-find, both returning 49940; the verifier re-derives the partition and refuses on mismatch |
| Envelope overrun: `5589784200` four-subset tests in the worst case | A truncated exhaustive run reported as an exhaustion is the classic bounded-search-to-universal-claim error | Frozen wall-clock and CPU caps; per-class checkpointing; a truncated run yields result shape C, an unresolved outcome with a recorded frontier |
| The vertex-transitive reduction to `C(42,4)` subsets | It is exact for circulants and wrong for anything else; carrying it into a general checker would produce false witnesses | The reduction is bound to the family in the intake file as a named trap, and the reference test over all `C(43,5)` subsets is the only test whose output is admitted |
| Third-party exhaustive certificates | Admitting a published exhaustive computation would let an unreplayed program create trust | Refused in section 8; admitting one requires its own ADR, per section 12 |
| Certificate drift or hand editing | A hand-edited edge list or a hand-edited projection would break the record-to-report chain | SHA-256 over canonical certificate bytes; ADR-0036 makes a hand-edited `.tex` detectable from `MANIFEST.json`, and nothing flows back from the projection to the records |
| Publication overclaim | "Improved the Ramsey lower bound" or "determined `R(5,5)`" from a `>= 44` result is a straightforward misstatement | A witness licenses exactly `R(5,5) >= 44` and nothing else (section 1); ADR-0036 computes the claim environment from records, so no manuscript field can promote it |

## 12. Capability check

**Covered by existing, already-authorized AdaIvy capabilities.**

- Phase 1 declarative problem intake and trust policy: the intake file is
  exactly a Phase 1 `problem-definition-v1` document, and it creates no trust.
- Deterministic serialization, explicit schema versions, content hashes, and
  bounded subprocesses with captured stdout/stderr and no network, per the
  standing engineering rules. The whole slice is integer arithmetic in the
  standard library and needs no third-party package.
- Machine-readable preservation of failed attempts, which is what section 9's
  exclusion set is.
- ADR-0055 pre-research novelty re-check, which is the mechanism that consumes
  section 6 and which must precede the first run by construction.
- ADR-0047 bounded central-lead runtime, if the lead loop is used to propose
  families; and ADR-0057 campaign provenance closure if a model writes the
  enumerator, with the caveat below.
- ADR-0036 publication projection, which would render an exactly verified
  witness as a `Proposition` and anything weaker as a `Conjecture`, and which
  cannot be made to render a `Theorem` here.

**Would require a new ADR, and is therefore not assumed.**

- **Admitting a third-party exhaustive certificate.** This is the reason the
  upper-bound route is excluded, and it is stated plainly. Proving
  `R(5,5) <= 45` means showing that *every* graph on 45 vertices contains a
  clique of size 5 or an independent set of size 5. Two things could establish
  that: a complete exact proof, which nothing in this repository is positioned
  to produce, or an independently checked exhaustive certificate at a scale far
  beyond anything this repository has authorized — the published upper-bound
  work is a large machine computation. Section 8 refuses an unreplayed
  third-party program as a certificate, so admitting such a computation as
  evidence is not a matter of trusting the authors; it is a new trust boundary,
  and it needs its own ADR fixing what an external exhaustive certificate is,
  how it is replayed or partially replayed, what its failure modes are, and what
  it may and may not license. Until that ADR exists, the upper-bound direction
  is out of scope for this slice, and this dossier does not treat the reported
  bound `R(5,5) <= 46` as a premise.
- **A checked SAT/UNSAT proof-log verifier** (DRAT or LRAT). Required if the
  extension route's per-base-graph search is to yield an exclusion certificate
  rather than a timeout. No such verifier exists here, and no SAT solver is
  pinned.
- **Production execution of generated code.** Under ADR-0057 this remains
  disabled until its distinct digest-pinned OCI sandbox gate passes. If the
  enumerator is model-written it must run under that gate or be replaced by an
  operator-authored program; the offline path uses injected scripted ports only.
- **An execution envelope beyond the current bounded-subprocess limits**, for
  the `5.6e9`-test worst case. This is a bound change, not a new mechanism, but
  it must be authorized explicitly rather than absorbed.
- **Acquisition of the `(5,5,42)` graph corpus.** Even as pure data rather than
  as a certificate, this is an acquisition and falls under ADR-0050's
  human-planned exact-URL authorization; it is not activated here.

**Explicitly not activated by this dossier:** any numerical or SDP solver, any
network access, any crawler or result-following, any parallel specialist,
evolutionary, or higher search tier, any embeddings or vector store, and any
automated novelty or significance assessment.

## 13. Open questions before intake

1. **Blocking, non-mathematical.** Does the operator confirm that `R(5,5)`
   belongs in the portfolio at all? The planning dossier records that item C4
   was inserted because the Tier C request contained one blank entry and
   `R(5,5)` was the only item in the supplied N1-N15 notes not otherwise
   represented, and it states that this inference requires operator
   confirmation before canonical intake. Until that confirmation exists, this
   dossier is a scoped package for a candidate whose membership is inferred, and
   intake must not proceed on the inference alone.
2. **Blocking.** What is the exact current published lower bound for `R(5,5)`?
   The frozen target assumes only that it is 43, that is that the best known
   witness has 42 vertices. If it is 44 or more, the target is void and must be
   re-frozen at the confirmed bound or higher. The answer must be a number with
   an evidence link, per ADR-0055.
3. **Blocking, scoping.** Given S2, that `R(5,5) = 43` is the reported
   conjecture, does the operator accept an existential target that the field
   expects to be false, with the exclusion certificate as the realistic
   deliverable? The alternative is to re-freeze the target as the exclusion
   statement itself — "no vertex-transitive graph on 43 vertices is a `(5,5,43)`
   graph" — which is a `bounded` universal target over a finite family and is
   achievable within this slice. This dossier freezes the existential as
   directed, and records the alternative so the choice is auditable.
4. What wall-clock, CPU, and memory envelope is authorized for the exhaustive
   run, and what spend cap replaces the placeholder USD 20 in section 10?
5. May a DRAT or LRAT proof-log verifier be introduced under a new ADR, to make
   the extension route capable of producing exclusion certificates? If not, the
   extension route is exploration-only and should be labelled so at intake.
6. Turner's theorem — that every vertex-transitive graph on a prime number of
   vertices is a circulant — is used only to strengthen the negative outcome.
   Its exact hypotheses and attribution must be confirmed against a primary
   source. Does the operator want the strengthening stated conditionally in the
   interim, or omitted until confirmed?
7. May the published `(5,5,42)` graph corpus be acquired as data under ADR-0050,
   and does the operator agree that treating it as *input to a search* is
   distinct from treating it as *a certificate*, the latter being refused?
8. Is `ramsey-theory` the intended `declared_domain`, or should the item be
   filed under a broader combinatorics domain already in use elsewhere in the
   repository?
