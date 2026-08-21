# A4. Planar total colouring at maximum degree six — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A4 (tier A)
**Declared domain:** graph-coloring
**Intake file:** docs/research-targets/intake/a4-planar-total-coloring-degree-six-v1.json
**Frozen in one line:** Every finite simple planar graph `G` with `Delta(G) = 6`
in which no vertex of degree 6 lies on a 3-cycle satisfies `chi''(G) <= 8`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen statement is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Novelty, significance, and source applicability are `not_assessed`, and no
statement in this file is backed by an acquired source. Whether the frozen
subclass is already settled in the literature is unknown here and is recorded in
section 6 as the load-bearing untrusted claim.

## 1. Frozen target

Let `G` be a finite simple graph: finite vertex set `V(G)`, no loops, no
parallel edges. Let `E(G)` be its edge set and `deg_G(v)` the number of edges
incident with `v`.

A **total `k`-colouring** of `G` is a map

`c : V(G) union E(G) -> {1,...,k}`

such that

1. `c(u) != c(v)` for every edge `uv in E(G)`,
2. `c(e) != c(f)` for every two distinct edges `e, f` sharing an endpoint,
3. `c(v) != c(e)` for every vertex `v` and every edge `e` incident with `v`.

`chi''(G)` is the least `k` for which a total `k`-colouring exists.

**Frozen statement.** For every finite simple planar graph `G` such that

- `Delta(G) = 6`, meaning some vertex of `G` has degree exactly 6 and no vertex
  has degree greater than 6, and
- there is no triple of vertices `v, u, w` with `deg_G(v) = 6` and with `uv`,
  `vw`, `uw` all in `E(G)`,

it holds that `chi''(G) <= 8`.

Quantifiers, explicitly: for all `G` in the class described above, there exists
`c : V(G) union E(G) -> {1,...,8}` satisfying conditions 1 to 3. The class
condition is itself universally quantified over `v, u, w` in `V(G)`.

Call the second condition `T6`. In words: no 3-cycle of `G` passes through a
vertex of degree 6.

**Why this subclass and not another.** The planning dossier requires a specific
unsettled subclass rather than the degree-six case, and the recommended
activation order says A4 begins only after one is selected. Four properties
drove the choice of `T6`.

- It is a single forbidden configuration, not a conjunction. Girth conditions
  such as `girth(G) >= 5` forbid both 3-cycles and 4-cycles and are therefore
  two conditions in one word; "no two adjacent triangles" and "no two triangles
  sharing a vertex" are conditions on pairs of triangles and need a second
  quantifier layer. `T6` is a condition on one triangle and one degree.
- It is strictly weaker than triangle-freeness and than `girth(G) >= 5`, so the
  frozen class strictly contains the triangle-free planar graphs of maximum
  degree exactly 6. A weaker hypothesis makes the target a stronger theorem,
  which is what "weaken one published hypothesis" in the planning dossier's
  first slice asks for. This is a statement about the definitions, not a claim
  about what any paper proves; see section 6.
- It couples the extremal degree to the forbidden configuration. In discharging
  arguments at `Delta = 6` the tight configurations are degree-6 vertices
  sitting on 3-faces beside low-degree vertices, because a 6-vertex plus its six
  incident edges already occupies 7 of the 8 colours. `T6` removes exactly that
  family and leaves triangles among vertices of degree at most 5 untouched, so
  the reducible-configuration search has somewhere to bite.
- Membership is decidable exactly and cheaply: for each vertex of degree 6,
  check its 15 neighbour pairs for adjacency. No embedding is needed to decide
  membership, which keeps the class definition independent of the proof device.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| total colouring | proper colouring of `V union E` where two adjacent vertices, two edges sharing an endpoint, and an incident vertex-edge pair all conflict | any variant in which vertex-edge incidence does not conflict; that is a proper vertex-plus-edge colouring and a different invariant |
| `chi''(G)` | least size of a colour set admitting a total colouring | total chromatic index, list total chromatic number, equitable total chromatic number |
| `Delta(G) = 6` | some vertex has degree exactly 6 and none has degree above 6 | `Delta(G) <= 6`, which additionally asserts the claim for planar graphs of maximum degree at most 5 |
| planar | `G` admits an embedding in the plane | plane graph, that is a graph together with a supplied embedding; also rejected: outerplanar, `K_5`-minor-free stated as a separate hypothesis |
| 3-cycle through `v` | vertices `u, w` exist with `uv`, `vw`, `uw` all edges | 3-face of some embedding; a triangle that bounds no face still counts |
| `T6` | no vertex of degree exactly 6 lies on a 3-cycle | "no triangle contains a vertex of degree at least 6", which is the same set here but drifts under `Delta <= 6`; also rejected: "no 6-vertex lies on a 3-face" |
| simple | finite, loopless, no parallel edges | multigraph; loops would make incidence conflicts ill defined |
| connectivity | not assumed; disconnected graphs are in the class | connected, 2-connected, or minimum degree at least 2 |
| colour set | fixed as `{1,...,8}`; colours unlabelled, so `S_8` acts on colourings | 8 distinguished colours with a fixed role, which would break the symmetry quotient in section 7 |
| reducible configuration | subgraph `H` with a frozen interface such that every total 8-colouring of the interface extends to `H` | "`H` does not occur in a minimal counterexample" as an assumption rather than a conclusion; also rejected: reducibility with respect to an unstated interface |

## 3. Formalization and quantifiers

```
forall G,
  (   G finite and simple and planar
  and Delta(G) = 6
  and not exists v,u,w in V(G) with deg_G(v) = 6
        and uv in E(G) and vw in E(G) and uw in E(G) )
  implies
  exists c : V(G) union E(G) -> {1,...,8} such that
      (forall uv in E(G), c(u) != c(v))
  and (forall distinct e,f in E(G) sharing an endpoint, c(e) != c(f))
  and (forall v in V(G), forall e in E(G) incident with v, c(v) != c(e))
```

Quantifier list as recorded in the intake file:

- `forall G a finite simple planar graph with Delta(G) = 6`
- `forall v in V(G) with deg_G(v) = 6 and forall u,w in V(G): not (uv, vw, uw all in E(G))`
- `exists c a map from V(G) union E(G) to {1,...,8}`

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment in section 4 is still
required and is not given by this file.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- `every finite simple planar graph G with Delta(G) = 6` maps to the same class
  intersected with `T6`; the frozen class is a proper subclass.
- `Delta(G) = 6` maps to: some vertex has degree exactly 6 and no vertex has
  degree above 6; `Delta(G) <= 5` is excluded, not covered.
- `chi''(G) <= Delta(G) + 2 = 8` maps to: there exists a total colouring `c`
  with values in the fixed set `{1,...,8}`.
- the subclass condition maps to: for all `v` with `deg_G(v) = 6` and all
  `u, w in V(G)`, not all three of `uv`, `vw`, `uw` are edges.

**Definition mapping.**

- `total coloring` — proper colouring of `V(G) union E(G)` where adjacency of
  vertices, sharing of an endpoint by edges, and vertex-edge incidence all
  conflict.
- `chi''(G)` — least size of a colour set admitting a total colouring; the
  target fixes that set to `{1,...,8}`.
- `planar` — admits an embedding in the plane; embeddability, not a supplied
  embedding.
- `3-cycle` — three pairwise adjacent vertices of the abstract graph; facial or
  non-facial makes no difference to the condition.
- `reducible configuration` — a subgraph `H` with a frozen interface such that
  every total 8-colouring of the interface extends to `H`, so that `H` cannot
  occur in a minimal counterexample.

**Assumption delta.**

- The headline problem quantifies over all planar graphs with `Delta(G) = 6`;
  the frozen target adds the forbidden configuration and is therefore strictly
  weaker than the headline problem.
- `Delta(G) = 6` is read as exact equality rather than as an upper bound, so the
  `Delta <= 5` planar cases are outside the claim.
- No embedding, no connectivity, no 2-connectivity, and no minimum-degree
  hypothesis is assumed.
- No published bound, reducible configuration, or discharging rule is assumed as
  an input; anything reused from the literature becomes an acquisition item and
  an open obligation until acquired.

**Edge-case delta.**

- `chi''(G) >= 7` holds on the whole class, so the target closes a gap of one
  colour rather than an unbounded gap.
- Every graph in the class has at least 7 vertices, since a degree-6 vertex
  needs six distinct neighbours.
- Disjoint unions stay in scope but a component may have maximum degree below 6,
  so any component reduction moves the hypothesis from `Delta = 6` to
  `Delta <= 6` and must be restated when used.
- Triangles among vertices of degree at most 5 are permitted; the condition
  restricts only triangles containing a vertex of degree 6.
- A degree-6 vertex whose two neighbours are adjacent is forbidden even when the
  resulting triangle bounds no face in a given embedding.

**Strength relation:** `weaker`. The frozen target is a strict special case of
the degree-six planar total-colouring statement: it is implied by that statement
and does not imply it.

## 5. Provenance and acquisition plan

No source has been acquired. Under ADR-0050 acquisition is human-planned,
exact-URL, and separately authorized, and this dossier writes the plan only.
Every row is `pending_acquisition` and its applicability is `not_assessed`.

The bibliographic strings below are operator search targets, not verified
metadata. No DOI is asserted for any of them, because none was resolved. ADR-0051
supplies the intended first step: one operator-initiated Crossref metadata query
per target, with query terms that are exact substrings of a supplied local
context file, returning `untrusted_inspiration_candidate` records only. Resolve
identity there first, then plan acquisition per exact URL.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Operator-supplied A4 candidate notes, received 21 August 2026 | local file supplied by the operator; no external locator | the claim that `Delta = 6` is the exceptional planar case (section 6, claim U1) | pending_acquisition |
| Origin of the total colouring conjecture (Behzad 1965 thesis; Vizing 1964) | resolve via one ADR-0051 Crossref query on the exact title strings, then acquire the located passage | the exact statement of the `Delta + 2` conjecture and its conventions, needed to confirm the section 2 conflict relation matches the cited convention | pending_acquisition |
| Monograph on total colourings of graphs (Yap, Lecture Notes in Mathematics series) | resolve via one ADR-0051 Crossref query; acquire the chapter covering planar graphs | the standard convention table for `chi''`, and the definition of reducible configuration used in the planar literature | pending_acquisition |
| Planar total-colouring results for large maximum degree (Borodin; Sanders and Zhao; Kowalik, Sereni and Skrekovski) | resolve each by one ADR-0051 Crossref query on author plus title; acquire the theorem statement page of each | claim U1: which maximum degrees are settled and which conventions those theorems use | pending_acquisition |
| Results for planar graphs with `Delta = 6` under girth or cycle-type hypotheses | resolve by ADR-0051 Crossref queries on the exact phrase families "total coloring planar graph maximum degree six" and "girth", then acquire the located theorem statements | claim U2, the load-bearing one: whether the frozen subclass `T6` is already covered, and claim U3, the exact hypotheses of the published results | pending_acquisition |
| A discharging-method reference giving the standard charge assignment for plane graphs | resolve by ADR-0051 Crossref query; acquire the section stating the charge and Euler identity | the global argument named as out of scope in section 7; needed before any attempt at the theorem rather than at the configurations | pending_acquisition |

Each row states which section 6 claim it would settle. No row is authorized by
this dossier.

## 6. Prior-status claims to re-check

Each claim below is untrusted. None has been acquired, quoted from a primary
source, or reviewed. All of them are named as items the ADR-0055 pre-research
novelty re-check must cover, immediately before research starts, bound to the
subject hash of the intake file.

- **U1.** The planning notes report that `chi'' <= Delta + 2` is settled for
  planar graphs of every maximum degree except 6, leaving `Delta = 6` as the
  exceptional case. Untrusted. If false, the target may be a corollary of a
  known theorem.
- **U2, load-bearing.** Whether the frozen subclass — planar, `Delta` exactly 6,
  and no 3-cycle through a degree-6 vertex — is already settled is unknown and
  cannot be checked offline. The target is frozen as a *statement*; nothing in
  this package asserts that it is open, novel, or unproved. The named
  acquisition target that would settle it is the fifth row of section 5:
  the located theorem statements of the `Delta = 6` planar results carrying
  girth or cycle-type hypotheses. If one of those theorems has a hypothesis
  implied by `T6`, the frozen target is settled and this dossier retires.
- **U3.** The planning notes report partial results for `Delta = 6` under
  stronger hypotheses such as `girth >= 5`, absence of 4-cycles, or absence of
  adjacent triangles. The exact hypotheses, bounds, and attributions are
  untrusted. That `T6` is weaker than triangle-freeness is a fact about the
  definitions; that `T6` is weaker than any *published* hypothesis is not
  claimed here.
- **U4.** The planning dossier's own source-status line for A4 says the
  statement and its August 2026 status come from operator-supplied notes and
  that the cited status review must be identified and acquired. That instruction
  is inherited unchanged.

## 7. Bounded first slice

The slice proves one additional reducible configuration, or exactly refutes a
candidate one. It does not attempt the theorem.

**Frozen interface convention.** A configuration is a pair `(H, I)` where `H` is
a simple graph and `I` is a subset of `V(H) union E(H)` called the interface. A
precolouring is a total 8-colouring of `I` alone, proper on `I`. `(H, I)` is
*reducible* iff every proper precolouring of `I` extends to a total 8-colouring
of `H`. This convention — precolour interface vertices *and* interface edges,
extend to all of `H`, no vertex identification or deletion permitted — is frozen
before search and is recorded inside every certificate. Section 11 records why.

**Inputs.** Project-authored exact encodings: `H` as an adjacency structure with
integer vertex labels, plus, where an embedding is needed to describe the
configuration, a rotation system given as a cyclic order of incident edges per
vertex. Colours are the integers `1..8`. No floating-point value appears.

**Search envelope and its size.** Enumerate candidate configurations `H` with
`|V(H)| <= 9`, every degree in `H` at most 6, containing at least one vertex of
degree 6 in the ambient graph, and satisfying `T6` in `H`. Generation is by
canonical augmentation from the 6-vertex star `K_{1,6}`, with isomorph rejection
by a canonical form computed exactly (refinement plus explicit backtracking over
the automorphism search tree, integer labels only). The interface `I` is the set
of elements of `H` that meet the ambient graph: interface vertices are those
with an ambient neighbour, and interface edges are those with an interface
endpoint whose other end is inside `H`.

For each `(H, I)` the precolouring count is at most `8^{|I|}`. Two quotients cut
it. First, colours are unlabelled, so the `S_8` action reduces precolourings to
canonical forms; the count of canonical precolourings of an interface of size
`m` is the number of set partitions of the conflict-consistent assignments, at
most `Bell(m)`, and for `m <= 8` that is at most 4140 rather than `8^8`. Second,
`Aut(H, I)` acts on precolourings and only orbit representatives are checked.
Both quotients are computed exactly and both are recorded in the certificate, so
a verifier can re-expand the orbit rather than trust the reduction.

**What is exhaustive and what is not.** For a fixed `(H, I)`, the precolouring
enumeration and the extension search are both exhaustive: every canonical
precolouring is checked, and for each one the extension search is complete
backtracking over the finite domain `1..8` per uncoloured element. The
configuration *generation* is exhaustive only up to the stated bound
`|V(H)| <= 9`; configurations above that bound are not enumerated and not
sampled.

**Boundary of the claim the slice can support.** A reducible configuration
`(H, I)` supports exactly this: no counterexample to the frozen target that is
minimal with respect to the frozen reduction order contains `(H, I)` as a
subconfiguration. It does not support the frozen target. Even an exhaustive
list of reducible configurations does not, because the global step — a
discharging computation on a plane embedding, assigning charge by Euler's
formula and redistributing it to show that every graph in the class contains a
listed configuration — is a separate argument that this slice does not attempt
and does not possess. This dossier states plainly: **computer-checked
reducibility does not supply the global discharging argument.**

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| `(H, I)` reducible | the configuration `(H, I)` with the frozen interface convention; the list of canonical interface precolourings with the orbit data used to canonicalize; for each one, an explicit total 8-colouring of `H` extending it, given as an integer label per element of `V(H) union E(H)` | replay: re-expand the `S_8` and `Aut(H,I)` orbits to the full precolouring set, confirm coverage is complete, and for each supplied extension check all three conflict conditions of section 1 by direct comparison. Integer comparisons only |
| `(H, I)` not reducible | one exhibited proper precolouring of `I` with no extension, plus a checked UNSAT proof log (DRAT or LRAT) from the CNF encoding of "this precolouring extends", plus the exact CNF and the encoding map from CNF variables to element-colour pairs | an independent proof checker replays the UNSAT log against the supplied CNF; a separate check confirms the CNF is the frozen encoding of the stated precolouring. The solver that produced the log is not trusted |
| one published hypothesis weakened | the exact prior hypothesis as acquired, the exact new hypothesis, the subfamily on which the weakening holds, and a proof whose every computational step is one of the two certificates above | human review of the proof, plus replay of every embedded certificate |
| unresolved | the exact list of configurations whose reducibility is undecided, with the reason per configuration (envelope exceeded, search budget, encoding refused) | replay of the recorded generation to confirm the list is exactly what the envelope produced |

**Refused as a certificate.** Floating-point output of any kind, including LP or
SDP relaxations of the colouring polytope. A model's verdict that a
configuration is reducible. A third-party program's output that has not been
replayed, including a SAT solver's bare SAT/UNSAT answer without a proof log.
The failure of a search to find a counterexample. An exhausted configuration
list presented as the theorem.

## 9. Useful negative outcomes

Nothing here is discarded, and every item is written machine-readably in the
same record set as a positive result.

- **A refuted reducibility.** A precolouring with no extension, with its checked
  UNSAT log, is a permanent exact fact about the configuration. It removes that
  configuration from every future discharging attempt and from any published
  configuration list that contains it.
- **The exclusion set.** The set of configurations inside the envelope that are
  *not* reducible under the frozen interface convention. This is the reusable
  artifact: any future discharging argument must avoid relying on them.
- **The frontier.** The exact envelope reached: `|V(H)| <= 9`, the generation
  count, the isomorph-rejection counts, and the per-configuration precolouring
  and orbit counts. The next slice resumes from a recorded frontier rather than
  a remembered one.
- **A refuted interface convention.** If a configuration is reducible under one
  interface convention and not under the frozen one, that discrepancy is
  recorded as a fact about the conventions, and is exactly the trap in section
  11.
- **A reduction, not a theorem.** If the slice shows that a minimal
  counterexample must contain a specific structure — for instance that it has
  minimum degree at least 3 — that is retained as a reduction with its own proof
  obligation and never reported as progress on `chi''`.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics: `configurations_enumerated`, `configurations_proved_reducible`,
`configurations_refuted_reducible`, `interface_precolourings_checked`,
`unsat_proof_logs_replayed`, `discharging_obligations_open`,
`failed_routes_preserved`, `model_cost_usd`.

Success criteria:

- one configuration proved reducible for total 8-colouring under the frozen
  interface convention, with a replayable extension table covering every
  canonical interface precolouring
- one published hypothesis for planar graphs with `Delta = 6` weakened to the
  frozen condition on an exactly identified subfamily, with the weakened
  hypothesis and the surviving hypotheses both stated
- or an explicit unresolved outcome recording the smallest remaining obligation,
  namely the exact list of configurations whose reducibility is undecided
  together with the discharging obligation that stays open

Stopping rules:

- stop when one configuration is proved reducible with an independently replayed
  extension certificate
- stop when a claimed reducibility is refuted by a checked UNSAT proof log
  replayed by an independent proof checker
- stop when the fresh model spend reaches USD 20
- stop when no configuration has changed status for two consecutive review
  points
- never promote an exhausted configuration list into the universal statement: a
  bounded enumeration constrains a minimal counterexample and supplies no
  discharging argument

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The frozen subclass is already a published theorem | The whole slice becomes a re-derivation, and worse, a re-derivation that could be reported as new | U2 in section 6 is named as the load-bearing claim; the ADR-0055 re-check must run before research starts, and the fifth acquisition row is the named target that settles it |
| Interface convention drift | A configuration reducible under "precolour boundary edges only" can fail under "precolour boundary vertices and edges"; two runs then disagree with no bug | Convention frozen in section 7 and stored inside every certificate; a reducibility record without its convention is refused at intake |
| Reducibility read as the theorem | The tempting sentence "all configurations are reducible, so the class is 8-total-colourable" is false without discharging; it is exactly the failure the planning dossier warns about | Stated in section 7 and in assumption `reducibility_is_not_the_theorem`; `discharging_obligations_open` is a metric, so a run that closes zero of them reports zero |
| Embedding conventions differ from the cited theorems | "Planar" as embeddability versus "plane graph" as a supplied embedding changes what a configuration even is, and face-based configurations are not subgraph-based ones | `planarity_convention` fixes embeddability for the statement and requires any embedding used in a proof to be recorded as a device with its independence argument |
| `Delta = 6` versus `Delta <= 6` | Component reduction silently moves between them, and a proof for `Delta <= 6` is a different theorem | `maximum_degree_exactly_six` and the third edge case require restating the hypothesis at every component reduction |
| SAT proof checking is treated as available | A bare UNSAT verdict is not a certificate, and adopting a solver plus proof checker is a new third-party boundary | Section 12 lists proof checking as requiring a new ADR; until then, a non-reducibility result is recorded as unresolved rather than as refuted |
| Combinatorial blow-up in generation | `8^{|I|}` precolourings and unbounded configuration growth make the envelope quietly meaningless | Envelope, both quotients, and their exact counts are recorded per configuration; the frontier in section 9 is the resumption point |
| Isomorph rejection bug | A wrong canonical form silently drops configurations, and the "exhaustive" claim becomes false | Generation counts and canonical forms are recorded so a verifier can re-run isomorph rejection independently; the exhaustiveness claim is scoped to the recorded envelope only |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Declarative problem intake and the trust boundary: the intake file validates
  against `schemas/problem-definition-v1.schema.json` and creates no warrant,
  novelty, or significance, as measured in the validation step.
- Exact finite-domain combinatorial computation implemented as project-authored
  standard-library code under `src/`, with deterministic serialization, content
  hashes, and captured output, per the repository engineering rules.
- Preservation of failed attempts and unresolved outcomes in machine-readable
  form, which section 9 relies on.
- Publication projection under ADR-0036 if any result is ever rendered, with a
  claim's environment computed from its records; a reducibility certificate
  without a kernel-checked attestation reaches `Proposition` at best, and the
  discharging obligation renders as an OPEN OBLIGATION rather than a citation.
- ADR-0055 pre-research novelty re-check, which section 6 requires.
- ADR-0051 one-shot Crossref metadata query for the identity-resolution step in
  section 5, inspiration-only, with terms drawn from a supplied local file.

**Would require a new ADR.**

- A SAT solver and a DRAT/LRAT proof checker. Both are third-party binaries and
  a new gated boundary; the repository has a sealed Lean image for formal
  checking and no SAT or proof-checking gate. Until such an ADR exists, the
  non-reducibility row of section 8 cannot be produced, and that result shape is
  recorded as unresolved rather than as refuted.
- Execution of model-generated code. Under ADR-0057 production generated-code
  execution stays disabled until its digest-pinned OCI sandbox gate passes, so
  every program in this slice is project-authored and reviewed, not generated
  and run.
- Any acquisition of the section 5 sources, which is ADR-0050 territory and
  requires per-URL human planning and separate authorization.
- A graph-theory or computer-algebra third-party library. Not needed: the slice
  is exact integer and finite-domain work and stays in the standard library.

**Explicitly not activated.** Parallel specialists, evolutionary search, higher
search tiers, crawling, result following, and automated novelty or significance
assessment.

## 13. Open questions before intake

1. Is `T6` the subclass the operator wants frozen? The alternatives considered
   and rejected are in section 1: `girth(G) >= 5`, absence of 4-cycles, and
   pairwise-vertex-disjoint triangles. Any of them can be substituted, but the
   substitution changes the target and needs a new intake file.
2. Does the operator want the interface convention of section 7, or the
   weaker "precolour boundary edges only" convention that some of the literature
   uses? This decides which reducibility results are comparable with published
   ones.
3. Is the ADR-0051 Crossref identity-resolution step in section 5 authorized for
   this target, and with which supplied local context file as the term source?
4. Should the non-reducibility result shape be pursued at all before a SAT
   proof-checking ADR exists? If not, the slice reduces to positive reducibility
   results plus an unresolved list.
5. Should `Delta(G) <= 6` be frozen instead of `Delta(G) = 6`? That is a
   strictly stronger target that absorbs the settled `Delta <= 5` planar cases
   and would change the class definition, the edge cases, and the strength
   relation.
