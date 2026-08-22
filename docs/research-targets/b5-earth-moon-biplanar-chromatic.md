# B5. Earth-Moon problem — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B5 (tier B)
**Declared domain:** graph-theory
**Intake file:** docs/research-targets/intake/b5-earth-moon-biplanar-chromatic-v1.json
**Frozen in one line:** there exists a finite simple graph `G` whose edge set is
the union of two planar graphs on `V(G)` and which admits no proper colouring
with 9 colours.

This is a scoped intake package and nothing more. It does not approve a
formalization, does not establish that the question is open, does not authorize
source acquisition, and does not activate any capability. Novelty,
significance, and source applicability are `not_assessed`, and no statement here
creates mathematical warrant, graph admission, or proof status. The inherited
bound interval and the inherited definition of biplanar are untrusted
candidates, because no source is acquired in this task.

## 1. Frozen target

Frozen statement. There exists a finite simple undirected graph `G`, together
with a partition of `E(G)` into sets `E_1` and `E_2`, such that the spanning
subgraphs `(V(G), E_1)` and `(V(G), E_2)` are both planar and there is no
proper vertex colouring `c : V(G) -> {1,...,9}`.

Symbols and their exact meanings. `G` is finite, simple, undirected: no loops,
no multiple edges, finitely many vertices. `V(G)` is its vertex set and `E(G)`
its edge set of unordered pairs. A partition of `E(G)` into `E_1` and `E_2`
means `E_1 union E_2 = E(G)` and `E_1 intersect E_2 = empty`. A spanning
subgraph `(V(G), E_i)` carries all of `V(G)`, so a layer may contain isolated
vertices. Planar means embeddable in the sphere without crossings, certified as
in §8. A colouring `c` is proper when `c(u) != c(v)` for every edge `uv` in
`E(G)`. `chi(G) >= 10` is exactly the statement that no proper `c` into a set of
9 colours exists.

Quantifier form.

```
exists G a finite simple graph,
exists a partition E(G) = E_1 disjoint_union E_2,
  Planar(V(G), E_1) and Planar(V(G), E_2)
  and not exists c : V(G) -> {1,...,9} with (forall uv in E(G), c(u) != c(v))
```

Target scope is `existential`: one object is wanted. The problem type is
`explore`, because the frozen statement fixes no direction and a rigorous
obstruction, however unlikely, would also be an acceptable outcome.

The planning dossier framed this item as "raise the lower bound from 9 to 10".
That framing is deliberately not the target. Whether 9 is the current lower
bound is an untrusted inherited claim (§6.1), and a target that references it
would inherit that claim as a premise. The frozen target is absolute: an object
with no proper 9-colouring, whether or not anything is known about 9.

No asymptotics appear, so no epsilon form is required.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| graph | finite, simple, undirected; no loops, no multi-edges | multigraph; infinite graph; directed graph |
| biplanar | `E(G)` partitioned into `E_1` and `E_2` with both spanning subgraphs planar | layers allowed to share edges (same class, see below, but a weaker certificate); layers on different vertex sets; layers required connected |
| layer | a spanning subgraph on all of `V(G)`, isolated vertices allowed | an induced subgraph; a subgraph on only the vertices it touches |
| planar | admits a sphere embedding, certified by a rotation system with a matching Euler count | drawable "by hand"; passes a library planarity test with no replayable certificate; has a coordinate layout with no crossings found numerically |
| `chi(G) >= 10` | no proper `c : V(G) -> {1,...,9}` exists | `chi(G) = 10`; `chi(G) >= 10` in a list, fractional, circular, or local sense; a lower bound from a relaxation |
| proper colouring | `c(u) != c(v)` for every edge `uv` in `E(G)` | properness within a layer only; properness up to a bounded number of conflicts |
| graph identity | sorted labelled edge list with per-edge layer assignment plus its sha256 | an isomorphism class; a drawing; an adjacency picture |
| thickness at most two | accepted as a paraphrase only if the source means the same partition into planar spanning subgraphs | assumed synonymous with the frozen definition without checking the source |
| witness | one graph plus one partition plus three certificates | a construction recipe; a family with a parameter left open |

Why edge-disjointness is frozen. The overlapping reading and the partition
reading define the same class of graphs. Given planar layers `E_1` and `E_2`
that share edges, replace `E_2` by `E_2 \ E_1`; it is a subgraph of a planar
graph and therefore planar, and `E_1 union (E_2 \ E_1) = E_1 union E_2` is
unchanged. So nothing is lost. The partition reading is preferred because it
makes the certificate checkable in a stronger sense: the verifier confirms that
every edge of `G` is covered exactly once, which detects a layer that silently
double-counts an edge to make its own Euler count work out. Under the
overlapping reading that check is unavailable.

## 3. Formalization and quantifiers

Formal statement, in the typed informal register used by the intake file:

```
exists G a finite simple graph,
exists a partition E(G) = E_1 disjoint_union E_2,
  Planar(V(G), E_1) and Planar(V(G), E_2)
  and not exists c : V(G) -> {1,...,9}
        with (forall uv in E(G), c(u) != c(v))
```

Quantifier list, as frozen in the intake file:

- `exists G` a finite simple undirected graph.
- `exists` a partition of `E(G)` into `E_1` and `E_2`, both spanning subgraphs
  on `V(G)`.
- `forall uv in E(G)`, the edge lies in exactly one of `E_1` and `E_2`.
- `not exists c : V(G) -> {1,...,9}` proper on `G`; equivalently, `forall` such
  `c`, `exists` an edge `uv` with `c(u) = c(v)`.

The negated inner existential is the load-bearing quantifier. It is what makes
the colouring half of the witness a genuine proof obligation rather than a
lookup: exhibiting a graph is easy, and establishing that none of the `9^n`
colourings is proper is the work. Two exact discharges are admitted in §8, and
neither is a search that merely failed to find a colouring.

Two exact derived consequences constrain the search space and are used below.
Both follow from textbook facts and are recorded in the intake file as derived
consequences rather than as source reports.

- A simple planar graph on `n >= 3` vertices has at most `3n - 6` edges, so a
  biplanar graph has at most `2(3n - 6) = 6n - 12` edges.
- Hence `K_11` is not biplanar: it has `55` edges against the bound
  `6*11 - 12 = 54`. `K_10` has `45` edges against the bound `48`, so the edge
  count does not exclude it.

## 4. Semantic alignment to the source statement

Quantifier mapping.

| Planning phrase | Frozen quantifier |
|---|---|
| construct a graph | `exists G` a finite simple undirected graph |
| whose edge set is the union of two planar graphs | `exists` a partition of `E(G)` into `E_1` and `E_2` with both spanning layers planar |
| whose chromatic number is at least 10 | `not exists` a proper colouring `c : V(G) -> {1,...,9}` |
| raise the lower bound from 9 to 10 | no quantifier; an interpretation of the witness, deliberately not part of the frozen target |

Definition mapping.

| Term | Local meaning |
|---|---|
| biplanar | `E(G)` partitioned into two edge sets whose spanning subgraphs are both planar |
| planar layer | a spanning subgraph admitting a rotation system whose traced faces satisfy `V - E + F = 1 + c` |
| chromatic number at least 10 | no proper colouring with the 9 colours `1..9` exists |
| graph identity | the sorted labelled edge list with per-edge layer assignment and its sha256 content hash |
| thickness at most two | a rejected paraphrase; it coincides with the frozen definition only if the source means the same partition into planar spanning subgraphs |

Assumption delta.

- Edge-disjointness is added to the source phrasing "union of two planar
  graphs". The derived equivalence in §2 shows the class is unchanged, so the
  addition is a certificate convention rather than a strengthening.
- Both layers are spanning subgraphs on the same vertex set, so a layer may
  contain isolated vertices. The planning statement does not say this.
- Finiteness and simplicity are stated explicitly, because the planar edge bound
  and the colouring search both need them.
- Nothing is assumed about the current known lower bound. The target is an
  absolute existence statement and does not reference 9.

Edge-case delta.

- A witness with `chi(G) >= 11` also satisfies the frozen target; the target is
  a lower bound, not an equality.
- `n >= 10` is forced, because a graph on 9 or fewer vertices has a proper
  colouring with 9 colours.
- A 10-clique inside `G` is by itself an exact certificate that no proper
  9-colouring exists, and the `K_11` exclusion above shows this clique route
  caps at 10.
- An empty second layer is admitted, so a planar graph would be biplanar. No
  planar graph can satisfy the colouring condition, so this edge case is
  consistent and harmless.
- Adding an isolated vertex changes the canonical hash but neither planarity nor
  colourability, so witness identity is finer than the mathematical content.

Strength relation: `unresolved`. The source that states the 9 through 12
interval is not acquired and its definition of biplanar is unknown, so the
mapping from this frozen statement to the published problem cannot be settled
here. `equivalent` is unavailable because it would require quoting an acquired
primary source.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` and every applicability judgement is
`not_assessed`. No DOI is asserted from memory: where the locator is not known
offline the row records the exact resolution procedure instead of a guess.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Operator's supplied candidate notes, received 21 August 2026 | local artifact held by the operator; must be supplied as a file, not paraphrased | fixes §6.1 as actually received, including whether "9 through 12" was stated as bounds on one quantity | pending_acquisition, applicability not_assessed |
| Primary source for the lower bound 9 | `locator_unresolved`; resolve by one ADR-0051 Crossref query with the operator-supplied terms `Earth-Moon problem` and `biplanar graph`, both exact normalized substrings of this dossier once supplied as local context, then acquire the returned DOI under ADR-0050 | settles §6.1 and §6.2 | pending_acquisition, applicability not_assessed |
| Primary source for the upper bound 12 | `locator_unresolved`; same ADR-0051 route with the term `chromatic number of biplanar graphs`; the acquisition target is the theorem statement and its hypotheses, cited at passage level | settles §6.1 | pending_acquisition, applicability not_assessed |
| Definitional source for biplanar or graph thickness | `locator_unresolved`; the acquisition target is the definition paragraph, specifically whether layers are edge-disjoint, spanning, and required to be planar as abstract graphs | settles §6.2, and decides whether §13 Q1 changes the frozen definition | pending_acquisition, applicability not_assessed |
| Any published determination of whether `K_10` is biplanar | `locator_unresolved`; ADR-0051 route with the term `biplanarity of the complete graph` | settles §6.3, which decides whether §7 is exploration or reproduction | pending_acquisition, applicability not_assessed |
| Completeness theorem for generating planar triangulations by vertex splitting | `locator_unresolved`; the acquisition target is the theorem and its exact hypotheses on connectivity | discharges the exhaustiveness obligation in §7, without which the §7 exhaustion is only a partial cover | pending_acquisition, applicability not_assessed |
| Catalogue count of 10-vertex planar triangulations | not planned; a catalogue count would be an untrusted number that the run must reproduce anyway | would only cross-check §7's own count | out_of_scope |
| FrontierMath open-problems index, recorded in the planning dossier's source ledger | `https://epoch.ai/frontiermath/open-problems` | discovery index only; not a statement source and may settle no §6 row | pending_acquisition, applicability not_assessed |

ADR-0050 acquisition is human-planned, exact-URL, public, unauthenticated and
separately authorized. ADR-0051 discovery is one human-started request returning
at most ten untrusted inspiration candidates and creates no relevance,
applicability, acquisition, novelty, significance, graph-admission or warrant
effect. Nothing here authorizes either.

## 6. Prior-status claims to re-check

Each item is an untrusted inherited report, is used as a premise nowhere in §7
or §8, and must be covered by the ADR-0055 pre-research novelty re-check bound
to this problem definition's subject hash before research starts.

1. **Untrusted.** "The supplied notes give the current interval as 9 through
   12." Three separate claims are bundled: that the maximum chromatic number of
   a biplanar graph is at least 9, that it is at most 12, and that these are
   current. The first implies a 9-chromatic biplanar witness is known, which
   this dossier does not assume anywhere.
2. **Untrusted.** The definition of biplanar used by whichever source states
   that interval. Authors variously define it through thickness at most two,
   through a union of two planar graphs, or with additional restrictions on the
   layers. The definition in §2 is authored locally.
3. **Untrusted.** Whether the biplanarity of `K_10` is already settled. This is
   the single most decision-relevant unknown, because §7 decides exactly that
   question by finite exhaustion. If it is settled in the literature, §7 is a
   reproduction and must be reported as `independent_verification`, never as a
   new result.
4. **Untrusted.** The completeness of vertex-splitting generation for planar
   triangulations, and any catalogue count of 10-vertex triangulations. Both are
   inherited claims; §7 treats the first as an open obligation and reproduces
   the second rather than citing it.
5. **Untrusted.** The planning dossier's verification shape, namely "graph
   identity, two independently checked planar layer embeddings, and an exact
   chromatic lower-bound certificate, preferably with independent SAT proof
   checking". §8 fixes what this repository will accept, independently of
   whether that shape matches community practice.

## 7. Bounded first slice

The slice does not attempt a general search for a 10-chromatic biplanar graph.
It builds the exact verifier stack, then spends it on one finite question whose
answer either hits the frozen target outright or closes a route permanently.

Inputs. No external data. The frozen conventions of §2. One frozen decision
question: is `K_10` biplanar?

Why this question. Two exact derivations from §3 make it the right first
question. First, if `K_10` is biplanar then `G = K_10` satisfies the frozen
target: `chi(K_10) = 10`, so no proper 9-colouring exists, and the colouring
certificate is the clique itself, which is checkable by pigeonhole in one line.
Second, `K_11` is not biplanar by the edge count, so the clique route to the
target caps at `K_10`; deciding `K_10` therefore either produces a witness or
closes the entire clique route forever.

Search-space reduction, exact. For `n >= 3`, `K_n` is biplanar if and only if
some spanning maximal planar graph `T` on `n` vertices, with exactly `3n - 6`
edges, has planar complement in `K_n`. Given planar edge-disjoint layers of
`K_n`, extend the first layer to a maximal planar spanning graph `T` using only
edges already present in `K_n`; the complement of `T` lies inside the second
layer and is planar because subgraphs of planar graphs are planar. The converse
is immediate. For `n = 10` this means: enumerate 10-vertex maximal planar
graphs, each with `24` edges, and test whether the complementary `21` edges form
a planar graph.

Algorithms and arithmetic, all exact and all combinatorial.

1. Canonicalize every graph as in §2: vertices `0..9`, edges as pairs `(u, v)`
   with `u < v`, edge list sorted lexicographically, sha256 over the canonical
   bytes.
2. Generate 10-vertex maximal planar graphs. Route A is repeated vertex
   splitting from `K_4`, which is fast but whose exhaustiveness is an inherited
   theorem and therefore an open obligation. Route B is brute-force generation
   with planarity certification, which is exhaustive by construction but
   expensive. The run executes Route A and cross-checks it against Route B at
   `n = 5, 6, 7`, where brute force is cheap. If the cross-check fails at any of
   those `n`, the `n = 10` exhaustion claim is withheld entirely.
3. Certify planarity of each generated graph, and of each complement, by the
   rotation-system certificate of §8. Nothing is accepted as planar on the
   generator's word.
4. Isomorph rejection is applied only as a cost optimization, using a cheap
   invariant prefilter and a refinement-based canonical form. Correctness
   requires only that every isomorphism class is covered, so duplication is
   safe and omission is not; the implementation is required to fail towards
   duplication, and the run records both the raw and the deduplicated counts.

Envelope and size. Ten labelled vertices, `45` possible edges, `24` edges per
triangulation, `21` in each complement. Every quantity the run reports, in
particular the number of triangulations enumerated, is measured by the run and
never taken from a catalogue.

What is exhaustive versus what is partial. Steps 1 to 4 are exhaustive over
10-vertex maximal planar graphs conditional on the generation obligation of step
2. If that obligation is undischarged, the outcome is recorded as a partial
cover with the exact set of enumerated canonical hashes, not as an exhaustion.

Boundary of the claim the slice can support.

- If a triangulation with planar complement is found: the frozen target is met
  by `K_10`, subject to all three certificates of §8 being independently
  replayed. This says nothing about any bound above 10.
- If the exhaustion completes with none found: `K_10` is not biplanar, and
  therefore no complete graph supplies a witness. This closes the clique route.
  It does not bound the chromatic number of biplanar graphs, does not show that
  no witness exists, and is not evidence that none exists.
- If the generation obligation is undischarged: the outcome is a partial cover
  and supports neither of the two statements above.

Exploration lane, off the trust path. Drawings, force-directed layouts, and
crossing-number heuristics may be used to guess promising triangulations. Their
output reaches the record only after the rotation-system certificate accepts the
layer.

## 8. Certificate and verifier contract

Result shape 1: a witness graph. The certificate has three independent parts and
the verifier shares no code with the search.

- **Identity.** The canonical labelled edge list with per-edge layer assignment,
  plus its sha256. The verifier re-derives the canonical form and the hash from
  the raw edge list rather than trusting the supplied hash, checks simplicity,
  and checks that every edge is assigned to exactly one layer, so the partition
  is verified and not assumed.
- **Planarity, once per layer.** A rotation system: for every vertex, a cyclic
  order of its incident darts. The verifier traces faces with the next-dart
  permutation, checks that every dart is consumed exactly once, counts faces `F`
  per connected component, and checks `V - E + F = 1 + c` over the `c`
  components. This certifies a genus-0 embedding by exact integer counting. It
  is not a drawing, uses no coordinates, and involves no arithmetic beyond
  integers. A layer claimed non-planar would instead require an exhibited
  Kuratowski subdivision, which the verifier checks by confirming the branch
  vertices, the internally disjoint paths, and the `K_5` or `K_3,3` pattern.
- **Chromatic lower bound.** Two exact discharges are admitted. The first is a
  clique certificate: an exhibited set of 10 mutually adjacent vertices, checked
  by confirming all 45 edges are present, which forces `chi(G) >= 10` by
  pigeonhole. The second is a refutation of 9-colourability: a CNF encoding of
  proper 9-colourability with a recorded encoding hash, an UNSAT proof log in a
  checkable format, and an independent proof checker's acceptance. The second
  route needs a capability the repository does not have; see §12. In its absence
  the admitted fallback is an exhaustive exact colouring search with
  clique-anchored symmetry breaking, whose trust rests on repository-authored
  code and whose cost is exponential in `n`; it is reported with its search
  envelope stated and is not a substitute for a checked proof log.

Result shape 2: a completed exhaustion over a graph class. The certificate
records the class, the generation route, the cross-check results at small `n`,
the exact enumerated count, the sorted list of canonical hashes or its Merkle
root, and every complement-planarity verdict. The verifier replays generation
deterministically and re-derives the hashes. The verdict is scoped to the
enumerated class and the record has no field in which a general nonexistence
claim could be written.

Refused as a certificate, without exception:

- a drawing, a screenshot, a coordinate layout, or a numerically computed
  crossing count;
- a planarity-library verdict with no replayable combinatorial certificate;
- any floating-point quantity, including a spectral or relaxation-based lower
  bound on the chromatic number;
- a model's assertion that a graph is biplanar or 10-chromatic;
- an unreplayed third-party program's verdict, including a SAT solver's UNSAT
  answer with no proof log that an independent checker accepted;
- failure of a colouring search to find a proper 9-colouring;
- an exhaustion whose generator's completeness is undischarged, reported as an
  exhaustion.

## 9. Useful negative outcomes

- **Route closure.** If `K_10` is not biplanar, the clique route is closed
  permanently, since `K_11` is excluded by the exact edge bound. This is a
  durable exact result about the search space and is retained as such.
- **Exclusion set.** The enumerated canonical hashes of 10-vertex maximal planar
  graphs, each with its complement's planarity verdict. Later runs cite this
  rather than regenerating it.
- **Verifier stack.** The rotation-system planarity checker, the Kuratowski
  checker, the canonical-hash routine, and the exact colouring decision are
  reusable for any later candidate, whatever its origin. Producing them is a
  retained result even if no witness is found.
- **Frontier.** The largest exactly certified chromatic lower bound achieved by
  any biplanar graph the run examined, with its full certificate, so later work
  starts from a checked floor rather than from an inherited number.
- **Refuted route and open obligation.** If the vertex-splitting cross-check
  fails at small `n`, that failure is retained with the counterexample class, so
  the route is not re-run blind.
- **Refused route.** Any candidate accepted by a heuristic and rejected by the
  rotation-system certificate, preserved with the rejection reason.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics.

- `candidate_graphs_canonically_hashed`
- `planar_layer_certificates_verified`
- `planar_layer_certificates_rejected`
- `maximal_planar_graphs_enumerated`
- `complement_planarity_tests_completed`
- `nine_colourability_decisions_completed`
- `exact_chromatic_lower_bound_certificates_verified`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria.

- an exhibited biplanar witness whose canonical hash, two rotation-system
  planarity certificates, and exact no-9-colouring certificate are all accepted
  by an independent verifier
- a completed exhaustive decision of whether `K_10` is biplanar, reported with
  its enumeration exhaustiveness obligation either discharged or explicitly open
- a recorded closure of the clique route, namely that no complete graph can
  supply a witness beyond `K_10`, derived from the exact edge bound
- or an explicit unresolved outcome that records the smallest remaining
  obligation together with the graph classes already excluded

Stopping rules.

- stop on an exact witness whose planarity and non-9-colourability certificates
  are both independently replayed
- stop when the frozen enumeration envelope for 10-vertex maximal planar graphs
  is exhausted, recording the bounded outcome and nothing stronger
- stop when the fresh model spend reaches USD 20
- stop when no new certified layer, no new excluded class, and no new refuted
  route have been produced across two consecutive review points
- never promote a completed bounded enumeration into a claim that no biplanar
  graph has chromatic number at least 10, nor into a claim about the general
  chromatic bound

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Planarity certified by a picture | a drawing that looks crossing-free is not a proof, and a coordinate check needs floating point | rotation system with an exact integer Euler count is the only admitted planarity certificate; `exact_arithmetic_requirement` is frozen |
| Layer double-counting an edge | a layer that quietly keeps a shared edge can make its own Euler count work while the union is misreported | the partition reading is frozen so the verifier checks every edge is covered exactly once |
| Failed colouring search read as a lower bound | "we could not 9-colour it" is the most tempting non-certificate in the whole item | only a clique certificate or a checked UNSAT proof log discharges the bound; a search is admitted only as an exhaustive decision with its envelope stated, and a failure to find is never a result |
| Generator incompleteness | an exhaustion over a class that the generator did not fully cover is a false universal statement about that class | vertex-splitting exhaustiveness is an open obligation, cross-checked against brute force at `n = 5,6,7`; a failed cross-check withholds the exhaustion claim entirely |
| Isomorph rejection bug | a canonical-form error can silently drop an isomorphism class and thereby drop the witness | isomorph rejection is an optimization only, must fail towards duplication, and raw plus deduplicated counts are both recorded |
| `K_10` already settled | if published, §7 is reproduction, and reporting it otherwise would be a false novelty claim | §6.3 is named for the ADR-0055 pre-research re-check; a settled answer makes the report class `independent_verification` |
| Inherited interval used as a premise | referencing "the lower bound is 9" anywhere would import an unsourced claim into the target | the frozen target is absolute and never mentions 9; the interval lives only in §6 as untrusted |
| Definition mismatch | if the source's biplanar differs, a valid local witness answers a different question | §6.2 is a named acquisition target and the strength relation stays `unresolved` until it is settled |
| Colouring search cost | exact 9-colourability decision is exponential and can silently dominate the budget | the clique route needs no colouring search at all; any search reports its envelope, and a spend cap plus a stagnation rule apply |
| No SAT proof-checking capability | the preferred chromatic certificate cannot be produced today | §12 names it as requiring a new ADR rather than substituting a solver's bare verdict |

## 12. Capability check

Covered by existing capabilities.

- Exact integer and combinatorial computation from the standard library, as
  repository-authored code under `src/` exercised by the offline suite:
  rotation systems, face tracing, Euler counts, edge-list canonicalization,
  clique checking. No third-party package and no floating point. Ad-hoc exact
  arithmetic written and run by the driving agent in a scratch workspace is NOT
  this capability: it is an unmet AdaIvy capability and an external-origin
  contribution under ADR-0057 section 5, imported with an `external_codex` or
  `human` root and never relabelled as AdaIvy work.
- Deterministic serialization, content hashing, bounded subprocesses, captured
  output, no-network execution, and durable machine-readable retention of
  failures under `make report`.
- Declarative problem intake against
  `schemas/problem-definition-v1.schema.json`, validated offline, creating no
  trust: `logical_status unknown`, `novelty_status not_assessed`,
  `significance_status not_assessed`, zero warrants.

Would require a new ADR.

- **A SAT solver and an independent UNSAT proof checker.** This is the preferred
  chromatic certificate and the repository has neither. Admitting them means
  pinned digests, recorded licenses, a declared gated boundary, offline
  execution, and an acceptance suite in which a mutated proof log must be
  rejected. Until then a solver's bare UNSAT verdict is refused, per §8.
- **A planar-graph generation tool.** Using an external triangulation generator
  is a pinned third-party dependency and a new ADR. The repository-authored
  routes A and B in §7 avoid it at the cost of a new module with its own
  acceptance thresholds.
- **A graph isomorphism or canonical-labelling library.** Same reasoning. The
  §7 design deliberately makes isomorph rejection optional so that this
  capability is never load-bearing.
- **Execution of model-generated search code.** Disabled under ADR-0057 until
  the digest-pinned OCI sandbox gate passes. The generator and all verifiers
  must be repository-authored code exercised by the offline suite.
- **Source acquisition.** Every §5 row needs the separately authorized ADR-0050
  step, and the `locator_unresolved` rows additionally need the separately
  authorized ADR-0051 query. Neither is authorized here.

Not needed and not requested: parallel specialists, evolutionary search, higher
search tiers, embeddings, a web surface, or any additional model provider path.

## 13. Open questions before intake

1. **Definition of biplanar.** Confirm the frozen definition, in particular that
   layers are spanning subgraphs on the same vertex set and that the partition
   reading is acceptable. If the intended source defines biplanar through
   thickness with different conventions, the target must be refrozen.
2. **Scope of the first slice.** Confirm that deciding the biplanarity of
   `K_10` is the intended first spend, rather than a general search. It can hit
   the frozen target outright, and its negative closes the clique route, but it
   is a narrow question.
3. **Chromatic certificate route.** Decide whether to open the new ADR for a
   pinned SAT solver plus an independent proof checker. Without it the only
   admitted certificates are a 10-clique or a repository-authored exhaustive
   colouring decision.
4. **Generation obligation.** Decide whether the vertex-splitting completeness
   theorem is to be acquired and discharged, or whether the run must stay with
   brute-force generation and report a partial cover at `n = 10`.
5. **Re-check ordering.** Confirm that the ADR-0055 pre-research novelty
   re-check covering §6.1 to §6.4 runs before any spend, since a settled `K_10`
   answer makes this slice a reproduction that must be reported as one.
6. **Acquisition authorization.** Confirm whether the ADR-0051 discovery queries
   and the ADR-0050 acquisitions of §5 are to be planned at all, and supply this
   dossier as the local context file whose exact substrings the query terms must
   match.
