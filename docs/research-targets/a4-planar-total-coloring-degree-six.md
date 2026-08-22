# A4. Planar total colouring at maximum degree six — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A4 (tier A)
**Declared domain:** graph-coloring
**Intake file:** docs/research-targets/intake/a4-planar-total-coloring-degree-six-v1.json
**Frozen in one line:** Every finite simple planar graph `G` with `Delta(G) = 6`
satisfies `chi''(G) <= Delta(G) + 2 = 8`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen statement is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Novelty, significance, and source applicability are `not_assessed`, and no
statement in this file is backed by an acquired source. Whether the degree-six
planar case is currently open is unknown here and is recorded in section 6 as
the load-bearing untrusted claim.

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

**Frozen statement.** For every finite simple planar graph `G` with
`Delta(G) = 6` — meaning some vertex of `G` has degree exactly 6 and no vertex
has degree greater than 6 — it holds that

`chi''(G) <= Delta(G) + 2 = 8`.

Quantifiers, explicitly: for all `G` in that class, there exists
`c : V(G) union E(G) -> {1,...,8}` satisfying conditions 1 to 3.

**No hypothesis is added.** This is the planning dossier's candidate statement
for A4, unnarrowed. No girth condition, no forbidden configuration, no
connectivity requirement, and no cycle-type restriction is attached. The target
is the whole degree-six planar case, and it is a hard open problem if the status
report in section 6 is correct.

**The waypoint, and why it is only a waypoint.** The planning dossier's first
slice for A4 permits a narrower *slice* than the target, and the recommended
activation order asks for a specific configuration target to start from. The
first slice therefore carries a waypoint: the same bound `chi''(G) <= 8`
restricted to graphs of the target class that additionally satisfy

`T6`: no 3-cycle of `G` contains a vertex of degree 6, that is, there is no
triple `v, u, w` with `deg_G(v) = 6` and `uv`, `vw`, `uw` all in `E(G)`.

`T6` scopes the slice. It is **not** part of the frozen target, it does not
appear in the formalization of section 3, and it is not a hypothesis anywhere in
the intake file's `target_claim`. Four properties make it a useful waypoint.

- It is a single forbidden configuration, not a conjunction. Girth conditions
  such as `girth(G) >= 5` forbid both 3-cycles and 4-cycles and are therefore
  two conditions in one word; "no two adjacent triangles" and "no two triangles
  sharing a vertex" are conditions on pairs of triangles and need a second
  quantifier layer. `T6` is a condition on one triangle and one degree.
- It isolates the tight structure rather than a peripheral one. In discharging
  arguments at `Delta = 6` the hardest configurations are degree-6 vertices
  sitting on 3-faces beside low-degree vertices, because a 6-vertex plus its six
  incident edges already occupies 7 of the 8 colours. `T6` sets exactly that
  family aside, which is why the waypoint is reachable and also why the waypoint
  is far from the target: the graphs it excludes are the ones that make the
  target hard.
- Membership is decidable exactly and cheaply: for each vertex of degree 6,
  check its 15 neighbour pairs for adjacency. No embedding is needed, so the
  waypoint class is defined independently of the proof device.
- The waypoint-to-target delta is nameable. Proving the waypoint leaves exactly
  one obligation shape open — the configurations in which a degree-6 vertex lies
  on a triangle — so an unresolved outcome can state precisely what remains
  rather than gesturing at the general case.

Proving the waypoint does not prove the target, and section 10's success
criteria say so in those words.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| total colouring | proper colouring of `V union E` where two adjacent vertices, two edges sharing an endpoint, and an incident vertex-edge pair all conflict | any variant in which vertex-edge incidence does not conflict; that is a proper vertex-plus-edge colouring and a different invariant |
| `chi''(G)` | least size of a colour set admitting a total colouring | total chromatic index, list total chromatic number, equitable total chromatic number |
| `Delta(G) = 6` | some vertex has degree exactly 6 and none has degree above 6 | `Delta(G) <= 6`, which additionally asserts the claim for planar graphs of maximum degree at most 5 |
| planar | `G` admits an embedding in the plane | plane graph, that is a graph together with a supplied embedding; also rejected: outerplanar, `K_5`-minor-free stated as a separate hypothesis |
| the target class | all finite simple planar `G` with `Delta(G) = 6`, no further condition | any subclass; a subclass would be a different and weaker target and is refused |
| 3-cycle through `v` | vertices `u, w` exist with `uv`, `vw`, `uw` all edges | 3-face of some embedding; a triangle that bounds no face still counts |
| `T6` | no vertex of degree exactly 6 lies on a 3-cycle; scopes the slice waypoint only | `T6` as a hypothesis of the target; also rejected: "no 6-vertex lies on a 3-face", and "no triangle contains a vertex of degree at least 6", which drifts under `Delta <= 6` |
| waypoint | a strictly weaker statement proved en route, recorded as progress | a waypoint reported as the target, or a waypoint whose delta to the target is left unstated |
| simple | finite, loopless, no parallel edges | multigraph; loops would make incidence conflicts ill defined |
| connectivity | not assumed; disconnected graphs are in the class | connected, 2-connected, or minimum degree at least 2 |
| colour set | fixed as `{1,...,8}`; colours unlabelled, so `S_8` acts on colourings | 8 distinguished colours with a fixed role, which would break the symmetry quotient in section 7 |
| reducible configuration | subgraph `H` with a frozen interface such that every total 8-colouring of the interface extends to `H` | "`H` does not occur in a minimal counterexample" as an assumption rather than a conclusion; also rejected: reducibility with respect to an unstated interface |

## 3. Formalization and quantifiers

```
forall G,
  ( G finite and simple and planar and Delta(G) = 6 )
  implies
  exists c : V(G) union E(G) -> {1,...,8} such that
      (forall uv in E(G), c(u) != c(v))
  and (forall distinct e,f in E(G) sharing an endpoint, c(e) != c(f))
  and (forall v in V(G), forall e in E(G) incident with v, c(v) != c(e))
```

Quantifier list as recorded in the intake file:

- `forall G a finite simple planar graph with Delta(G) = 6`
- `exists c a map from V(G) union E(G) to {1,...,8}`

There is no third quantifier. The earlier `T6` clause is gone from the target;
it survives only as the waypoint scope in section 7.

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment in section 4 is still
required and is not given by this file.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- `every finite simple planar graph G with Delta(G) = 6` maps to: the same
  class, with no additional hypothesis; the frozen class is the full degree-six
  planar class.
- `Delta(G) = 6` maps to: some vertex has degree exactly 6 and no vertex has
  degree above 6; `Delta(G) <= 5` is excluded, not covered.
- `chi''(G) <= Delta(G) + 2 = 8` maps to: there exists a total colouring `c`
  with values in the fixed set `{1,...,8}`.
- `the condition T6 of the first slice` maps to: not a quantifier of the target;
  it restricts only the waypoint proved en route, namely that for all `v` with
  `deg_G(v) = 6` and all `u,w in V(G)`, not all three of `uv`, `vw`, `uw` are
  edges.

**Definition mapping.**

- `total coloring` — proper colouring of `V(G) union E(G)` where adjacency of
  vertices, sharing of an endpoint by edges, and vertex-edge incidence all
  conflict.
- `chi''(G)` — least size of a colour set admitting a total colouring; the
  target fixes that set to `{1,...,8}`.
- `planar` — admits an embedding in the plane; embeddability, not a supplied
  embedding.
- `3-cycle` — three pairwise adjacent vertices of the abstract graph; facial or
  non-facial makes no difference.
- `reducible configuration` — a subgraph `H` with a frozen interface such that
  every total 8-colouring of the interface extends to `H`, so that `H` cannot
  occur in a minimal counterexample.
- `waypoint` — a strictly weaker statement proved en route to the target,
  recorded as progress and never as the target.

**Assumption delta.**

- The frozen target adds no hypothesis to the planning dossier's candidate
  statement: it is the full class of finite simple planar graphs with
  `Delta(G) = 6`, with no girth, cycle-type, connectivity, or
  forbidden-configuration condition attached.
- `Delta(G) = 6` is read as exact equality rather than as an upper bound, so the
  `Delta <= 5` planar cases are outside the claim.
- No embedding, no connectivity, no 2-connectivity, and no minimum-degree
  hypothesis is assumed.
- No published bound, reducible configuration, or discharging rule is assumed as
  an input; anything reused from the literature becomes an acquisition item and
  an open obligation until acquired.
- The condition `T6` is not part of the target. It scopes the first slice's
  waypoint only, and the delta between waypoint and target is itself recorded as
  an open obligation.

**Edge-case delta.**

- `chi''(G) >= 7` holds on the whole class, so the target closes a gap of one
  colour rather than an unbounded gap.
- Every graph in the class has at least 7 vertices, since a degree-6 vertex
  needs six distinct neighbours.
- Disjoint unions stay in scope but a component may have maximum degree below 6,
  so any component reduction moves the hypothesis from `Delta = 6` to
  `Delta <= 6` and must be restated when used.
- Triangles are permitted anywhere in the target class, including triangles
  through vertices of degree 6; those are exactly the graphs the waypoint
  excludes and the target must still cover.
- A vertex of degree 6 together with its six incident edges already occupies 7
  of the 8 available colours, so the hardest instances of the target are
  precisely the ones the waypoint sets aside.

**Strength relation:** `unresolved`. The frozen statement is the planning
dossier's own candidate statement for A4, with no hypothesis added or removed,
so it is not weaker than it. But `equivalent` is refused: the mapping to the
cited status review cannot be settled while that review is unacquired, and under
this task no source text has been quoted from a primary source. The relation
resolves only after the section 5 acquisition rows are executed and reviewed.

## 5. Provenance and acquisition plan

No source has been acquired. Under ADR-0050 acquisition is human-planned,
exact-URL, and separately authorized, and this dossier writes the plan only.
Every row is `pending_acquisition` and its applicability is `not_assessed`.

The bibliographic strings below are operator search targets, not verified
metadata. No DOI is asserted for any of them, because none was resolved.
ADR-0051 supplies the intended first step: one operator-initiated Crossref
metadata query per target, with query terms that are exact substrings of a
supplied local context file, returning `untrusted_inspiration_candidate` records
only. Resolve identity there first, then plan acquisition per exact URL.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Operator-supplied A4 candidate notes, received 21 August 2026 | local file supplied by the operator; no external locator | claim U1, the load-bearing one: that `Delta = 6` is the exceptional and currently unproved planar case | pending_acquisition |
| Origin of the total colouring conjecture (Behzad 1965 thesis; Vizing 1964) | resolve via one ADR-0051 Crossref query on the exact title strings, then acquire the located passage | the exact statement of the `Delta + 2` conjecture and its conventions, needed to confirm the section 2 conflict relation matches the cited convention, and needed to settle the strength relation in section 4 | pending_acquisition |
| Monograph on total colourings of graphs (Yap, Lecture Notes in Mathematics series) | resolve via one ADR-0051 Crossref query; acquire the chapter covering planar graphs | the standard convention table for `chi''`, and the definition of reducible configuration used in the planar literature | pending_acquisition |
| Planar total-colouring results for large maximum degree (Borodin; Sanders and Zhao; Kowalik, Sereni and Skrekovski) | resolve each by one ADR-0051 Crossref query on author plus title; acquire the theorem statement page of each | claim U1: which maximum degrees are settled, which conventions those theorems use, and whether any covers `Delta = 6` | pending_acquisition |
| Results for planar graphs with `Delta = 6` under girth or cycle-type hypotheses | resolve by ADR-0051 Crossref queries on the exact phrase families "total coloring planar graph maximum degree six" and "girth", then acquire the located theorem statements | claim U2, whether the `T6` waypoint is already covered, and claim U3, the exact hypotheses of the published partial results | pending_acquisition |
| A discharging-method reference giving the standard charge assignment for plane graphs | resolve by ADR-0051 Crossref query; acquire the section stating the charge and Euler identity | the global argument that the target needs and that section 7 does not supply; required before any attempt at the theorem rather than at the configurations | pending_acquisition |

Each row states which section 6 claim it would settle. No row is authorized by
this dossier.

## 6. Prior-status claims to re-check

Each claim below is untrusted. None has been acquired, quoted from a primary
source, or reviewed. All of them are named as items the ADR-0055 pre-research
novelty re-check must cover, immediately before research starts, bound to the
subject hash of the intake file.

- **U1, load-bearing.** The planning notes report that `chi'' <= Delta + 2` is
  settled for planar graphs of every maximum degree except 6, leaving
  `Delta = 6` as the exceptional and currently unproved case. Untrusted. The
  frozen target *is* that case, so this claim is what decides whether the target
  is an open problem or a corollary of a known theorem. Nothing in this package
  asserts that it is open, novel, or unproved. The named acquisition targets
  that would settle it are the first and fourth rows of section 5.
- **U2.** Whether the `T6` waypoint class — planar, `Delta` exactly 6, and no
  3-cycle through a degree-6 vertex — is already settled is unknown and cannot
  be checked offline. If it is settled, the waypoint loses its value as a route
  and the slice must be re-planned; the target is unaffected either way, because
  the waypoint was never part of it. The named acquisition target is the fifth
  row of section 5.
- **U3.** The planning notes report partial results for `Delta = 6` under
  stronger hypotheses such as `girth >= 5`, absence of 4-cycles, or absence of
  adjacent triangles. The exact hypotheses, bounds, and attributions are
  untrusted, and none may be assumed as an input to a proof.
- **U4.** The planning dossier's own source-status line for A4 says the
  statement and its August 2026 status come from operator-supplied notes and
  that the cited status review must be identified and acquired. That instruction
  is inherited unchanged, and it is also why the strength relation in section 4
  is `unresolved` rather than `equivalent`.

## 7. Bounded first slice

The slice is deliberately narrower than the target. It proves reducible
configurations, or exactly refutes candidate ones, and attempts the `T6`
waypoint. It does not attempt the target, and it cannot reach it.

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
`|V(H)| <= 9`, every degree in `H` at most 6, and containing at least one vertex
of degree 6 in the ambient graph. The waypoint pass additionally restricts to
`H` satisfying `T6`; the configurations violating `T6` are enumerated too and
retained as the waypoint-to-target delta, since they are exactly what the target
still needs. Generation is by canonical augmentation from the 6-vertex star
`K_{1,6}`, with isomorph rejection by a canonical form computed exactly
(refinement plus explicit backtracking over the automorphism search tree,
integer labels only). The interface `I` is the set of elements of `H` that meet
the ambient graph: interface vertices are those with an ambient neighbour, and
interface edges are those with an interface endpoint whose other end is inside
`H`.

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
`(H, I)` supports exactly this: no counterexample to the target that is minimal
with respect to the frozen reduction order contains `(H, I)` as a
subconfiguration. It does not support the target. Even an exhaustive list of
reducible configurations does not, because the global step — a discharging
computation on a plane embedding, assigning charge by Euler's formula and
redistributing it to show that every graph in the class contains a listed
configuration — is a separate argument that this slice does not attempt and does
not possess. This dossier states plainly: **computer-checked reducibility does
not supply the global discharging argument.** Under the full degree-six target
that sentence carries more weight than it did under any subclass, not less: the
gap between "a configuration list" and "the theorem" is the entire problem.

And the waypoint is not the target either. Proving `chi''(G) <= 8` for the
graphs satisfying `T6` leaves the target untouched on exactly the graphs where a
degree-6 vertex lies on a triangle — the instances where a 6-vertex and its
incident edges already consume 7 of the 8 colours. That delta is recorded, not
narrated away.

**Realistic reach of the first slice.** Against a full open case, the honest
expectation is a handful of reducible configurations plus a precisely stated
remaining obligation. The success criteria in section 10 name the unresolved
outcome as the realistic one for that reason.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| `(H, I)` reducible | the configuration `(H, I)` with the frozen interface convention; the list of canonical interface precolourings with the orbit data used to canonicalize; for each one, an explicit total 8-colouring of `H` extending it, given as an integer label per element of `V(H) union E(H)` | replay: re-expand the `S_8` and `Aut(H,I)` orbits to the full precolouring set, confirm coverage is complete, and for each supplied extension check all three conflict conditions of section 1 by direct comparison. Integer comparisons only |
| `(H, I)` not reducible | one exhibited proper precolouring of `I` with no extension, plus a checked UNSAT proof log (DRAT or LRAT) from the CNF encoding of "this precolouring extends", plus the exact CNF and the encoding map from CNF variables to element-colour pairs | an independent proof checker replays the UNSAT log against the supplied CNF; a separate check confirms the CNF is the frozen encoding of the stated precolouring. The solver that produced the log is not trusted |
| the `T6` waypoint proved | the configuration list with a reducibility certificate of the first row for each, the discharging argument written out in full with its charge assignment and Euler identity, and the explicit statement that the result is the waypoint and not the target | human review of the discharging argument, plus replay of every embedded reducibility certificate. The record must carry the waypoint-to-target delta or it is refused |
| the target proved | a complete proof for the full class, with every computational step reduced to a first-row certificate and the discharging argument covering graphs in which a degree-6 vertex lies on a triangle | human review, plus replay of every embedded certificate. No configuration list, however large, is accepted in place of the discharging argument |
| unresolved | the exact list of configurations proved reducible, the exact list whose reducibility is undecided with the reason per configuration (envelope exceeded, search budget, encoding refused), the waypoint-to-target delta, and the discharging obligation | replay of the recorded generation to confirm the lists are exactly what the envelope produced |

**Refused as a certificate.** Floating-point output of any kind, including LP or
SDP relaxations of the colouring polytope. A model's verdict that a
configuration is reducible. A third-party program's output that has not been
replayed, including a SAT solver's bare SAT/UNSAT answer without a proof log.
The failure of a search to find a counterexample. An exhausted configuration
list presented as the theorem. The waypoint presented as the target.

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
- **The waypoint-to-target delta.** The exact set of enumerated configurations
  in which a degree-6 vertex lies on a triangle, with their reducibility status.
  This is the residue the target needs and the waypoint does not touch, and it
  is retained whether or not the waypoint is proved.
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
`unsat_proof_logs_replayed`, `waypoint_obligations_closed`,
`discharging_obligations_open`, `failed_routes_preserved`, `model_cost_usd`.

Success criteria:

- one configuration proved reducible for total 8-colouring under the frozen
  interface convention, with a replayable extension table covering every
  canonical interface precolouring, recorded as progress toward the target and
  never as the target
- the waypoint proved in full, namely `chi''(G) <= 8` for every graph of the
  target class that additionally satisfies `T6`, with every reducibility step
  carrying a replayable certificate and the discharging step written out and
  reviewed
- or, and this is the realistic outcome for a first slice against a full open
  case, an explicit unresolved outcome recording the smallest remaining
  obligation: the exact list of configurations proved reducible, the exact list
  still undecided, the waypoint-to-target delta, and the discharging obligation
  for the full class, which stays entirely open

Stopping rules:

- stop when one configuration is proved reducible with an independently replayed
  extension certificate
- stop when a claimed reducibility is refuted by a checked UNSAT proof log
  replayed by an independent proof checker
- stop when the fresh model spend reaches USD 20
- stop when no configuration has changed status for two consecutive review
  points
- never promote an exhausted configuration list into the target statement: a
  bounded enumeration constrains a minimal counterexample and supplies no
  discharging argument
- never present the waypoint as the target: proving `chi'' <= 8` under `T6`
  leaves the target untouched on exactly the graphs that make it hard

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The target is not actually open | The whole slice becomes a re-derivation, and worse, a re-derivation that could be reported as new | U1 in section 6 is named as the load-bearing claim; the ADR-0055 re-check must run before research starts, and the first and fourth acquisition rows are the named targets that settle it |
| The waypoint is reported as the target | It is a one-word edit away from the target's own sentence, and it excludes precisely the hard instances | `T6` is absent from `target_claim`, from section 3, and from the assumption delta; the last stopping rule and the last refused-certificate line both forbid the substitution; `waypoint_obligations_closed` and `discharging_obligations_open` are separate metrics |
| Reducibility read as the theorem | The tempting sentence "all configurations are reducible, so the class is 8-total-colourable" is false without discharging; under the full target this is the whole gap | Stated twice in section 7 and in assumption `reducibility_is_not_the_theorem`; `discharging_obligations_open` is a metric, so a run that closes zero of them reports zero |
| Scope creep back into a subclass | Under budget pressure the easy move is to quietly re-add a hypothesis and declare success | The target class row in section 2 records any subclass as a rejected reading; a subclass target requires a new intake file with a new canonical hash |
| Interface convention drift | A configuration reducible under "precolour boundary edges only" can fail under "precolour boundary vertices and edges"; two runs then disagree with no bug | Convention frozen in section 7 and stored inside every certificate; a reducibility record without its convention is refused at intake |
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
- Kernel-checked formalization of a discharging argument. The sealed Phase 3B
  Lean path checks a frozen theorem statement with a proposed proof fragment; a
  discharging argument over a plane embedding is far outside that shape, so a
  kernel-checked route to the target is not available and is not assumed.
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

1. The target is the full degree-six planar case, which is a hard open problem
   if U1 holds. What fraction of it can the first slice realistically move? The
   honest answer from section 7 is: a handful of reducible configurations inside
   `|V(H)| <= 9`, possibly the `T6` waypoint if the discharging argument for
   that restricted class turns out to be tractable, and no part of the
   discharging argument for the full class. The operator should confirm that
   this is acceptable reach for a first slice, because the realistic recorded
   outcome is the unresolved one in section 10.
2. Does the operator want the interface convention of section 7, or the weaker
   "precolour boundary edges only" convention that some of the literature uses?
   This decides which reducibility results are comparable with published ones.
3. Is the ADR-0051 Crossref identity-resolution step in section 5 authorized for
   this target, and with which supplied local context file as the term source?
4. Should the non-reducibility result shape be pursued at all before a SAT
   proof-checking ADR exists? If not, the slice reduces to positive reducibility
   results plus an unresolved list.
5. Is `T6` the right waypoint, or should the slice aim at a different
   intermediate condition — `girth(G) >= 5`, absence of 4-cycles, or
   pairwise-vertex-disjoint triangles? This changes the slice only; the target
   is unaffected, so it does not need a new intake file.
6. Should `Delta(G) <= 6` be frozen instead of `Delta(G) = 6`? That is a
   strictly stronger target that absorbs the settled `Delta <= 5` planar cases
   and would change the class definition, the edge cases, and the strength
   relation.
