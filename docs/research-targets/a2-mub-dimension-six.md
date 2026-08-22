# A2. Dimension-six MUB conjecture, Problem 10.2 — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A2 (tier A)
**Declared domain:** quantum-information-theory
**Intake file:** docs/research-targets/intake/a2-mub-dimension-six-v1.json
**Frozen in one line:** No four mutually unbiased bases exist in `C^6`; that
is, for every four orthonormal bases of `C^6`, some pair among them is not
mutually unbiased.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate a capability. Novelty,
significance, and source applicability are `not_assessed`. The McNulty and
Weigert review is **not acquired**, so every statement attributed to it is an
untrusted candidate. Nothing here grants graph admission or proof status.

**Re-freeze notice.** An earlier version of this dossier froze the single pair
`{I, F_6}` and asked whether it extends to a triple. That pair is now known to
extend, by the exact derivation retained in section 9, so the pair-level target
was false. On operator instruction the target is not weakened but **escalated**
to the headline conjecture Problem 10.2. The refutation is retained as a
finding, not discarded, and it changes the shape of every admissible route:
see section 9 and the refused route in section 8.

## 1. Frozen target

Let `C^6` carry the standard Hermitian inner product. An orthonormal basis is a
sequence of six pairwise orthogonal unit vectors. Two orthonormal bases
`(x_0,...,x_5)` and `(y_0,...,y_5)` are **mutually unbiased** iff

```
abs2(inner(x_a, y_b)) = 1/6   for all 0 <= a,b <= 5
```

where `abs2` is squared modulus. All 36 conditions are required.

The frozen target is

> for every four orthonormal bases `B_1, B_2, B_3, B_4` of `C^6` there exist
> indices `s != t` such that `B_s` and `B_t` are not mutually unbiased,

equivalently: **there exists no set of four pairwise mutually unbiased bases of
`C^6`**. Four bases means an unordered set of four, required to be unbiased
**pairwise**, so all six pairs and all 36 conditions per pair are constrained.

`target_claim.scope` is `unrestricted_universal`: the claim quantifies over
all four-tuples of bases, with no object held fixed. `problem_type` is
`explore`: an explicit quadruple would refute the conjecture and is an equally
acceptable outcome.

**The equivalence group is not part of the frozen statement.** A universal
nonexistence needs no quotient. The group of global unitaries, per-basis
reordering, and per-vector phases preserves pairwise unbiasedness, so a
quadruple exists iff one exists with `B_1` the standard basis and the rest in
dephased form; that is used **only** to normalize the search. This is a
deliberate change from the earlier pair-level freeze, where the quotient sat
inside a `particular` claim and had to be part of it.

**Concrete algebraic form.** By the complex-Hadamard criterion recorded as a
lemma, a quadruple exists iff there are three `6x6` complex Hadamard matrices
`H_1, H_2, H_3` (entries of modulus 1, `conj(H)^T H = 6 I`) such that
`(1/sqrt(6)) conj(H_s)^T H_t` is complex Hadamard for every `s != t`. After
dephasing each `H_t` (first row and first column all ones) that is about **75
unknown unit-modulus entries** subject to three Hadamard conditions and three
mutual conditions. Section 7 explains plainly why one slice does not reach it.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| dimension | exactly 6; the space is `C^6` with the standard Hermitian inner product | any other composite dimension; a general `d = m n` statement; a real or quaternionic analogue |
| mutually unbiased | `abs2(inner(x, y)) = 1/6` exactly, for every one of the 36 cross pairs | equality within a numerical tolerance; unbiasedness on a subset of index pairs; a different constant, i.e. quasi-unbiasedness |
| four mutually unbiased bases | four orthonormal bases that are **pairwise** unbiased: all six pairs, 36 conditions each | a **star** configuration in which three bases are each unbiased to one fixed basis but not to one another — generally easier to satisfy and **not** a witness against the frozen statement; an ordered quadruple; a complete set of seven, which is the maximal-set question |
| the equivalence group | global unitary applied to all bases at once, independent per-basis reordering, independent per-vector unit-modulus rescaling. Used **only** to normalize the search | treating it as part of the frozen statement (a universal nonexistence needs no quotient); including entrywise complex conjugation; including permutation of the roles of the bases. The last two change solution counts, not the answer, so the exclusion is stated wherever a count is reported |
| coefficient field | `Q(zeta_12)`, degree 4 over `Q`, minimal polynomial `Phi_12(x) = x^4 - x^2 + 1`; contains `zeta_6 = zeta_12^2`, `i = zeta_12^3`, `sqrt(3) = zeta_12 + zeta_12^(-1)` | `Q(zeta_6)` alone, which cannot represent the tensor-constructed third basis of section 9; `Q(sqrt(6))`; `R` or `C` with floating-point entries |
| normalization | a basis given by a unit-modulus matrix carries the exact **rational** scalar `1/6`; `sqrt(6)` is never represented | absorbing `1/sqrt(6)` into the entries, which forces an irrational into the coefficient field |
| entries of an unknown basis | unrestricted: they range over all of `C`. The field constrains the **equations and certificates**, not the solutions | restricting unknowns to `Q(zeta_12)`, which is the restricted sub-question of section 7 and not the frozen target |
| dephasing | unique: a matrix with all entries nonzero has unique diagonal `D_1, D_2` (with `D_1[0] = 1`) making `D_1 M D_2` have first row and column all ones | treating dephasing as a choice, which would break the finite equivalence check |
| root-of-unity envelope | bounded searches restrict entries to `mu_12`, optionally widened to `mu_24`. A strict restriction, not the target | treating envelope exhaustion as nonexistence over `C` |
| `F_6` | the `Z_6` discrete Fourier matrix, entries `zeta_6^(j k)`, 0-based. Appears only as the subject of the section 9 finding, never as a target | any `6x6` complex Hadamard matrix; a target of this dossier |
| `M_6^(1)`, `K_6^(2)`, `K_6^(3)` | review-listed family names, not acquired, not instantiated | treating a family name, or a family with free parameters, as a frozen target |
| waypoint pair | a bounded-slice device whose resolution excludes only the quadruples containing it | the frozen target; a stepping stone that "mostly" settles Problem 10.2 |

## 3. Formalization and quantifiers

```
not ( exists B1 B2 B3 B4 : orthonormal_basis(C^6),
        forall s t in {1,2,3,4}, s != t ->
          (forall a b in {0..5}, abs2(inner(B_s[a], B_t[b])) = 1/6) )

equivalently

forall B1 B2 B3 B4 : orthonormal_basis(C^6),
  exists s t in {1,2,3,4} with s != t,
  exists a b in {0..5}, abs2(inner(B_s[a], B_t[b])) != 1/6
```

Quantifier structure: the frozen statement is a **negated existential over four
bases**, equivalently a universal over four-tuples with a doubly existential
failure witness. Nothing is held fixed and no quotient is applied. Inside, the
`s != t` quantifier ranges over all six unordered pairs and the `a, b`
quantifiers over all 36 index pairs per pair of bases.

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment is still required.

**A consequence of the section 9 finding, stated as a restatement rather than a
new claim.** Since a triple of pairwise mutually unbiased bases of `C^6` exists,
the frozen statement is equivalent to

> no triple of pairwise mutually unbiased bases of `C^6` extends to a
> quadruple,

and also to "the maximum number of pairwise mutually unbiased bases of `C^6` is
exactly 3". The lower bound in that last form is supplied by section 9; the
upper bound is the whole open problem. This restatement is what makes the
refused route in section 8 precise.

## 4. Semantic alignment to the source statement

The mapping is now to **Problem 10.2**, the headline conjecture. Problem 10.6,
the pair-level stepping stone, appears only as an untrusted claim in section 6
and as a slice device in section 7.

**Quantifier mapping.** "No four mutually unbiased bases exist in dimension 6"
maps to the universal over four-tuples of orthonormal bases of `C^6` with a
failing pair. "Four bases" maps to an unordered set of four required to be
pairwise unbiased, so all six pairs are constrained. The 36 index pairs per
basis pair are all retained. The equivalence group is **not quantified in the
frozen statement at all**; it acts on candidate quadruples and normalizes the
search. "A given pair", from Problem 10.6, maps to nothing in the frozen
statement — it is a waypoint only.

**Definition mapping.** "Mutually unbiased" maps to exact equality of squared
moduli with `1/6`. "Four mutually unbiased bases" maps to the pairwise
condition, with the star configuration explicitly rejected. "Dimension 6" maps
to `C^6` and to no other composite dimension. "Coefficient field" maps to
`Q(zeta_12)`, needed because a tensor-constructed basis of `C^6` has entries in
`mu_12`. "Normalization" maps to the `1/6` rational scalar. "Exact certificate"
maps to exactly three admissible replayable identity forms (section 8). "The
maximum number of MUBs in `C^6`" is not the frozen statement but is related to
it: section 9 fixes the lower bound at 3, so the frozen statement is equivalent
to that maximum being exactly 3.

**Assumption delta.**

- The target is escalated from a single frozen pair to Problem 10.2 on operator
  instruction, so the claim is a universal nonexistence and the scope moves
  from `particular` to `unrestricted_universal`.
- The equivalence group is removed from the frozen statement and retained only
  as a search normalization, with its soundness recorded as a definitional
  assumption.
- The previously frozen pair `{I, F_6}` is refuted as an unextendibility target
  by the retained derivation in section 9, and is now a finding, not a target.
- Consequently the route "no pair extends to a triple" is refused outright, and
  the frozen statement is restated as "no triple extends to a quadruple".
- The "or quadruple" disjunct of the stepping-stone problem is absorbed:
  quadruples are now the subject rather than an alternative to triples.
- The bounded slice no longer claims to attack the frozen statement directly.
  It is explicitly a waypoint programme, and its waypoint pair must be
  certified tensor-inequivalent or acquisition becomes the gating step.

**Edge-case delta.**

- Unbiasedness of a dephased basis to the standard basis is automatic once
  every entry has modulus 1, collapsing 36 conditions to a modulus condition.
- Zero is not a permitted entry of a complex Hadamard matrix, so no degenerate
  column satisfies the conditions vacuously.
- A quadruple is a set; reordering the four bases, or reordering and rephasing
  vectors inside any of them, gives the same solution. Counts are meaningful
  only modulo the frozen group, which excludes conjugation and role
  permutation.
- A star configuration around one fixed basis is generally easier to satisfy
  and does **not** witness the negation of the frozen statement.
- The retained derivation shows the negation cannot be approached by pair
  unextendibility alone: at least one pair in `C^6` is extendible, so any
  universal-over-pairs route is already refuted.
- If the exact stabilizer of a waypoint pair is larger than expected, the
  search space shrinks without losing solutions, because it is computed rather
  than assumed.

**Strength relation: `unresolved`.** The review is not acquired, so
`equivalent` is forbidden by the spec regardless of how close the wording
looks; and the planning dossier's own rendering of Problem 10.2 is itself an
untrusted report. The frozen statement is no longer `weaker`, since it is no
longer one pair against a family — it is the headline conjecture as understood
from an unacquired secondary description. `unresolved` is the honest value and
resolving it is item 1 of section 13.

## 5. Provenance and acquisition plan

No acquisition is performed by this dossier. Under ADR-0050 acquisition is
public, unauthenticated, human-planned, exact-URL, one request at a time, and
separately authorized. Every row is `pending_acquisition` with applicability
`not_assessed`.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| McNulty and Weigert, "Mutually Unbiased Bases in Composite Dimensions — A Review", Quantum 10, 2051 (2026) | `https://doi.org/10.22331/q-2026-04-01-2051` — the statement of Problem 10.2 | settles R1, that Problem 10.2 says what the planning notes report, which is what the strength relation turns on | pending_acquisition, applicability not_assessed |
| The same review, Problem 10.6 and the section defining the pair families `M_6^(1)`, `K_6^(2)`, `K_6^(3)` | same DOI | settles R2 and R3: the stepping-stone statement, the family names and parametrizations, and whether any listed member is certifiably **not** tensor-equivalent. This is the gating input for the section 7 waypoint if the source-free construction fails | pending_acquisition, applicability not_assessed |
| The same review, its conventions section | same DOI — definitions of complex Hadamard matrix, dephased normal form, and the MUB equivalence group | settles R4, whether the frozen group matches the community convention, which is what makes any reported count comparable | pending_acquisition, applicability not_assessed |
| The same review, the section reporting numerical evidence for unextendibility of specific pairs | same DOI | settles R5. Acquiring it changes nothing on the trust path: numerical evidence is refused as a certificate whatever the source | pending_acquisition, applicability not_assessed |
| The primary sources the review cites for the dimension-six searches and for the classification of `6x6` complex Hadamard matrices | to be identified from the acquired bibliography; deliberately not guessed, since guessing a locator is not human-planned acquisition | settles R5 in detail and R6, the state of the `6x6` Hadamard classification, which bounds how far any exact route can reach | pending_acquisition, applicability not_assessed |
| Post-2025 literature on four MUBs in dimension six | no exact locator can be written before the review and its bibliography are acquired; recorded as an ADR-0055 obligation rather than a URL | settles R1 and R7, in particular whether the conjecture has been settled since the review | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each item is **untrusted**, inherited from the planning notes or from unsourced
background, and must be covered by the ADR-0055 pre-research novelty re-check
bound to this problem's subject hash immediately before research starts. None
creates open status, novelty, significance, applicability, graph admission, or
warrant.

- **R1 — Problem 10.2 exists and is the headline conjecture.** The planning
  notes report the review contains it, asserting that no four MUBs exist in
  dimension 6, and that it is open. Unacquired.
- **R2 — Problem 10.6 as the stepping stone.** The planning notes report a
  Problem 10.6 asking that a given pair be shown non-extendible to a triple or
  quadruple. Unacquired. It is retained here **only** as an untrusted
  stepping-stone claim and as the shape of the section 7 waypoint; the section
  8 refused route bounds exactly how much any such result can contribute.
- **R3 — the listed pair families.** The names `M_6^(1)`, `K_6^(2)`,
  `K_6^(3)`, their parametrizations, their contents, and crucially whether any
  member is certifiably not tensor-equivalent are all unverified. This dossier
  instantiates none of them.
- **R4 — the community equivalence convention.** Whether the frozen group
  matches the review's is unknown. It affects reported counts, not the
  yes-or-no answer.
- **R5 — reported numerical evidence.** The planning notes report strong
  published numerical evidence of unextendibility for some parameter values.
  Untrusted, and irrelevant to the trust path regardless of source.
- **R6 — the `6x6` complex Hadamard classification.** Whether a complete
  classification exists is not stated by the planning dossier and is not
  asserted here. It bounds how far any exact nonexistence route can reach, so
  the re-check must establish it rather than leaving the slice to guess.
- **R7 — how many MUBs are known in dimension 6.** The planning dossier does
  not state this. Section 9 now supplies the **lower** bound 3 by derivation,
  independently of any source. Any recollection about the upper side remains an
  unsourced recollection, is asserted nowhere, and is left to the re-check.

## 7. Bounded first slice

**The frozen target is not reachable by one bounded slice, and this section
does not pretend otherwise.** With `B_1` normalized to the standard basis, a
quadruple is three dephased `6x6` complex Hadamard matrices: roughly 75
unknown unit-modulus entries, hence about 150 real unknowns or 150 polynomial
variables once conjugates are carried as companion variables, subject to three
Hadamard conditions and three mutual-Hadamard conditions. None of the three
certificate routes in section 8 is known to scale to a system of that size, and
the reach of any exact route additionally depends on R6, the state of the `6x6`
Hadamard classification, which is unacquired. Claiming a first slice that
settles Problem 10.2 would be dishonest. The slice below is a **waypoint
programme** whose contribution to the frozen target is a partial exclusion,
quantified exactly in section 8.

**Arithmetic.** Exact throughout. Elements of `Z[zeta_12]` and `Q(zeta_12)` are
integer or rational coefficient vectors of length 4 in
`(1, zeta_12, zeta_12^2, zeta_12^3)`, multiplied and reduced by
`Phi_12(x) = x^4 - x^2 + 1`. Squared modulus is the exact product with the
conjugate, reduced to a rational; for entries in `mu_12` every squared modulus
arising is a rational integer, so the conditions are exact integer equalities.
No square root, tolerance, residual, or float occurs anywhere.

**Stage 0 — replay the retained triple (cheap, decisive, discharges an
obligation).** Construct the section 9 triple explicitly over `Q(zeta_12)`: the
standard basis, the tensor basis equivalent to `F_6`, and the third tensor
basis, together with the CRT index permutation. Verify all three pairwise
relations exactly: for each of the three pairs, the 36 unbiasedness
conditions plus the 21 orthonormality conditions per basis. Cost: a few
thousand exact multiplications. This discharges the replay obligation attached
to the section 9 finding and simultaneously certifies the lower bound 3. It
must run first, because every later step's framing depends on it.

**Stage 1 — enumerate and classify the `mu_12` Hadamard matrices.**

- Enumerate all dephased columns: first entry `1`, five free entries in
  `mu_12`, exactly `12^5 = 248832` candidates. Filter for the exact conditions
  in `Z[zeta_12]`. Record the surviving set, its cardinality, and a content
  hash in canonical order.
- Find all six-tuples of pairwise orthogonal columns by depth-first search in
  the frozen canonical order with exact orthogonality tests, under a frozen
  node budget; on exceeding it, abandon and record the frontier. This yields
  every dephased `6x6` complex Hadamard matrix with entries in `mu_12`.
- Partition those matrices into Hadamard-equivalence classes using the **exact
  finite check** recorded as a lemma: dephasing is unique, so `H ~ H'` iff some
  permutation pair `(P_1, P_2)` gives `dephase(P_1 H P_2) = H'`, a complete
  check over `(6!)^2 = 518400` pairs with 36 exact entries each. No numerical
  invariant and no floating point is involved anywhere in the classification.
- Identify the class containing `F_2 tensor F_3`, equivalently `F_6`.

**Stage 2 — select a waypoint pair, or make acquisition the gate.** This is a
**measured branch, not a guess**:

- If stage 1 yields a class distinct from the tensor class, take `H*` to be the
  lexicographically first member of a frozen distinct class. The waypoint pair
  is `{I, H*/sqrt(6)}`, and its non-tensor-equivalence is **certified by the
  exact finite check**, not recalled from a source. This is the source-free
  construction, and it is the only admissible way to pick a waypoint here.
- If every dephased `mu_12` Hadamard matrix turns out equivalent to the tensor
  one, then **no waypoint pair can be exactly specified without the review**,
  the slice says so outright, and acquisition of the review (section 5, row 2)
  becomes the **gating step** of the whole programme rather than a convenience.
  The optional `mu_24` widening at `24^5 = 7962624` columns may be tried first,
  on explicit authorization, but a wider envelope is not a stronger claim and
  may simply return the same verdict.

Under no circumstances is a waypoint pair adopted on a recalled claim of
inequivalence. Adopting a tensor-equivalent pair guarantees a wasted slice,
because section 9 proves such a pair extendible.

**Stage 3 — attempt unextendibility of the certified waypoint pair.** With one
basis normalized and the second frozen, the unknown third basis is a dephased
`H` with 30 unknown entries. Encode the conditions as a polynomial system over
`Q(zeta_12)`, carrying each unknown's conjugate as a companion variable `g`
with `h g = 1` so modulus conditions become polynomial. Attempt the section 8
routes in order; the declared first attempt is Gröbner / Nullstellensatz. Also
run the finite `mu_12` clique search restricted to columns unbiased to the
waypoint pair, which is a complete answer to the restricted sub-question and
costs almost nothing given stage 1's output.

**What is exhaustive and what is not.** Stage 1's column enumeration is
exhaustive over `mu_12` by construction, being a complete product set; the
clique search and the classification are exhaustive only if they finish inside
the node budget, and the frontier record distinguishes "exhausted" from
"abandoned". Stage 3's polynomial routes search no finite set and carry no
exhaustiveness claim. Nothing is randomly sampled, so there is no statistical
claim in the slice.

**Boundary of the claim the slice can support.**

- Stage 0 certifies that at least three pairwise MUBs exist in `C^6`. It says
  nothing about four.
- Stage 1 certifies the exact set and equivalence classes of dephased `mu_12`
  Hadamard matrices. It says nothing about matrices outside `mu_12`.
- Stage 2 certifies that a specific pair is not tensor-equivalent, or reports
  that none can be so certified within the envelope.
- Stage 3, if it succeeds, certifies that one specific pair does not extend.
  That **excludes exactly the quadruples containing that pair** and nothing
  else. It does not resolve Problem 10.2, does not settle any family, and says
  nothing about other pairs.
- If a quadruple is found at any point, the frozen conjecture is **refuted
  outright** by one exact object.
- A numerical search finding nothing supports nothing at all.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| A quadruple exists (frozen conjecture refuted) | three `6x6` matrices with every entry an exact element of `Q(zeta_12)` (or a named larger field) as coefficient vectors, plus the normalization scalar | a second implementation reconstructs the matrices from coefficient vectors alone and re-derives every condition: for each of the six pairs the 36 unbiasedness conditions, plus the 21 orthonormality conditions per basis. Every equality exact in the named field. This is the one decisive positive certificate |
| The retained triple (lower bound 3) | the three bases as exact `Q(zeta_12)` matrices, the CRT index permutation, and the tensor factors | replay of all three pairwise relations and all orthonormality conditions, rebuilding `F_6` from `zeta_6` and the index formula rather than reading a stored matrix. Until this replay runs, the section 9 finding's status is `derived, not machine-replayed` |
| `mu_12` Hadamard enumeration and classification | the frozen enumeration order, the exact filter predicate, the surviving column set with cardinality and content hash, the matrix list, the equivalence-class partition, and the node counts | a second implementation replays the enumeration and the `(6!)^2` dephasing check and must reproduce the cardinalities, the content hashes, and the identical class partition. Certifies the restricted sub-question only |
| Waypoint pair is not tensor-equivalent | the pair, plus the exhaustive `(6!)^2` permutation-pair check showing no dephasing of `P_1 H P_2` equals the tensor representative | independent replay of the finite check. Complete and exact; no numerical invariant is admitted as a substitute |
| Waypoint pair unextendibility, route (a) — **attempted first** | a Nullstellensatz cofactor representation: an explicit identity `1 = sum of p_i * f_i` with the `f_i` the encoded generators and the `p_i` explicit polynomials over `Q(zeta_12)` | exact polynomial expansion and reduction by `Phi_12`. The Gröbner engine is never trusted — only the replayed identity. Attempted first because its certificate is smallest to replay and needs no positivity modelling |
| Waypoint pair unextendibility, route (b) | rational Positivstellensatz: real and imaginary parts over `Q`, circle constraints `a^2 + b^2 = 1`; certificate is an exact identity `-1 = sigma_0 + sum of lambda_j * q_j` with `sigma_0` a sum of squares given as exact rational PSD Gram matrices with rational `LDL^T`, and exact rational polynomial multipliers `lambda_j` | exact polynomial identity expansion plus exact rational `LDL^T` per Gram matrix. If a floating-point program produced the candidate multipliers, that is exploration and is labelled so; only the exact identity certifies |
| Waypoint pair unextendibility, route (c) | exact interval exclusion: finitely many boxes with **rational** endpoints covering the compact parameter torus, each with an exact rational bound showing a constraint unsatisfiable on it, plus an exact covering proof | exact rational interval replay per box plus an exact covering check. Exclusion only: an incomplete cover yields a recorded exclusion set, never a nonexistence claim |
| Nonexistence of a quadruple over `C` | the same three routes on the full ~75-unknown system | same verifiers. Section 7 states plainly that no route is known to scale here; this row records the contract, not a promise |

**Refused as a certificate, without exception.**

- **Pair unextendibility presented as resolving Problem 10.2.** Since a triple
  exists, the route "no pair extends to a triple" is *already refuted*, so no
  universal-over-pairs argument can work. Unextendibility of one pair excludes
  exactly the quadruples containing that pair. The frozen statement is
  equivalent to "no triple extends to a quadruple", and only an argument
  covering all triples, or an exclusion covering all quadruples, settles it.
  This is the single most important refusal in this dossier and it is a direct
  consequence of the section 9 finding.
- Any floating-point number: residual, tolerance, numerical eigenvalue,
  numerical semidefinite bound, or an interval with floating endpoints. The
  repository owner rejects floating-point solvers outright, and ADR-0035
  records that no interval or residual-reconstruction path exists.
- **Failure of a numerical search.** The planning dossier's own primary risk,
  refused by name.
- **Failure of the `mu_12` or `mu_24` search.** It bounds nothing outside the
  envelope.
- A **star** configuration of four bases. Three bases each unbiased to one
  fixed basis is not a pairwise quadruple and refutes nothing.
- A model's assertion that four bases do or do not exist.
- An unreplayed third-party computer-algebra transcript. A CAS may *produce* a
  candidate cofactor representation or SOS multipliers; only the replayed exact
  identity certifies.
- A numerical invariant (spectrum, Haagerup set, or similar) used in place of
  the exact finite dephasing check when deciding equivalence.

## 9. Useful negative outcomes

The first item is a result the dossier **already holds**, not a hoped-for one.

### 9.1 Retained finding: `{I, F_6}` extends to a triple

This refutes the pair-level target of the earlier version of this dossier and
is retained as content. It is a derivation supplied by the repository owner,
every step exactly checkable, with the replay obligation discharged by stage 0.
Its status until then is `derived, not machine-replayed`.

**Claim.** The pair consisting of the standard basis and the columns of
`(1/sqrt(6)) F_6` extends to a triple of pairwise mutually unbiased bases of
`C^6`. Hence at least three pairwise MUBs exist in `C^6`, and **every** pair
equivalent under the frozen group to `{I, (F_2 tensor F_3)/sqrt(6)}` is
extendible and therefore worthless as an unextendibility target.

**Proof.**

1. *CRT relabelling in idempotent form.* The map `(j_2, j_3) -> j = 3 j_2 + 4
   j_3 mod 6` is a bijection `Z_2 x Z_3 -> Z_6`, since `3` and `4` are the
   idempotents (`3 = 1 mod 2`, `3 = 0 mod 3`; `4 = 0 mod 2`, `4 = 1 mod 3`).
   Expanding,

   ```
   j k = (3 j_2 + 4 j_3)(3 k_2 + 4 k_3)
       = 9 j_2 k_2 + 12 (j_2 k_3 + j_3 k_2) + 16 j_3 k_3   mod 6
       = 3 j_2 k_2 + 4 j_3 k_3                             mod 6
   ```

   because the cross terms carry the factor `12`, which vanishes mod 6, while
   `9 = 3` and `16 = 4` mod 6. Therefore

   ```
   zeta_6^(j k) = (zeta_6^3)^(j_2 k_2) * (zeta_6^4)^(j_3 k_3)
                = (-1)^(j_2 k_2) * (w^2)^(j_3 k_3),   w = zeta_3 = zeta_6^2
   ```

   using `zeta_6^3 = -1` and `zeta_6^4 = zeta_3^2`. The right side is the
   `(j_2,j_3),(k_2,k_3)` entry of `F_2 tensor F_3'`, where `F_3'` is `F_3` with
   its columns permuted by `d -> 2 d mod 3`. So `F_6 = P (F_2 tensor F_3') Q`
   for permutation matrices `P` (row relabelling) and `Q` (column relabelling).
2. *Tensor construction.* `C^2` admits three pairwise MUBs `A_0 = I`,
   `A_1 = F_2/sqrt(2)`, `A_2`; `C^3` admits four, hence at least three,
   `B_0 = I`, `B_1 = F_3/sqrt(3)`, `B_2`. By the tensor lemma,
   `A_0 tensor B_0`, `A_1 tensor B_1`, `A_2 tensor B_2` are three pairwise MUBs
   of `C^6`, and `A_0 tensor B_0 = I`.
3. *Transport.* `A_1 tensor B_1 = (F_2 tensor F_3)/sqrt(6)`. Row relabelling is
   a global permutation unitary, which lies in the frozen group and carries the
   standard basis to itself **as a set**; column relabelling, including the
   `d -> 2 d mod 3` permutation, reorders vectors within a single basis and
   also lies in the group. Neither changes an unordered pair of bases. So the
   triple of step 2 transports to a triple containing exactly
   `{I, F_6/sqrt(6)}`.
4. Hence `{I, F_6/sqrt(6)}` extends to a triple, and the same argument applies
   verbatim to any pair equivalent to `{I, (F_2 tensor F_3)/sqrt(6)}`. `QED`

**What this does and does not give.** It gives a **lower** bound: at least
three pairwise MUBs exist in `C^6`, so the frozen statement is equivalent to
that maximum being exactly 3. It gives an **exclusion criterion** for choosing
waypoints (stage 2). It gives a **refuted route**: since one pair is
extendible, no universal-over-pairs argument can settle Problem 10.2, which is
the refusal at the top of section 8. It says **nothing** about whether four
bases exist. It is a lower bound, not progress on the upper bound.

**Why `Q(zeta_12)`.** `A_2` has entries in `mu_4` and `B_2` in `mu_3`, so the
third basis has entries in `mu_12`. `Q(zeta_6)` cannot represent it. This is a
concrete, derived justification for the frozen coefficient field rather than a
convention.

### 9.2 Other retained artifacts

- **The exact `mu_12` Hadamard matrix list and its equivalence-class
  partition**, with cardinalities and content hashes. Reusable by every later
  dimension-six target, and the input to any waypoint selection.
- **The exact admissible column set** with cardinality and content hash: the
  input to any clique search or widened envelope.
- **The certified exclusion set of pairs.** Each waypoint pair whose
  unextendibility is certified excludes the quadruples containing it. The
  exclusion set is the cumulative artifact of this programme and the only thing
  that accumulates toward the frozen target. Every entry records the pair, the
  certificate, and its verifier replay.
- **The exact stabilizer** of each pair considered, with generators, computed
  rather than assumed.
- **The encoded polynomial systems** (waypoint and full quadruple) with
  generator lists and content hashes, independent of whether any route
  succeeds. Reusable with only constants changed.
- **Per-route refutation records.** A Gröbner route exceeding its bound is
  recorded with the degree and term statistics reached, so the next attempt
  does not repeat it blind; likewise SOS degree bounds attempted and interval
  covers left incomplete, whose partial exclusion sets are retained.
- **The negative branch of stage 2**, if every `mu_12` Hadamard matrix is
  tensor-equivalent: that is a real, exact, reusable fact about the envelope
  and it converts acquisition from a convenience into the gating step.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics:

- `dephased_hadamard_matrices_enumerated`
- `hadamard_equivalence_classes_computed`
- `non_tensor_equivalent_waypoint_pairs_certified`
- `quadruple_families_excluded`
- `exact_certificate_identities_replayed`
- `floating_point_values_admitted_to_trust_path`
- `failed_routes_preserved`
- `model_cost_usd`

`floating_point_values_admitted_to_trust_path` must be `0` in every run. It is
a metric rather than a comment so that a violation is countable.
`quadruple_families_excluded` counts certified waypoint exclusions and is
explicitly **not** progress toward a proof unless the exclusions are shown to
cover all quadruples.

Success criteria:

- `an explicit set of four pairwise mutually unbiased bases of C^6 with exact
  algebraic entries, every one of the six pairs and all 36 conditions per pair
  verified, refuting the frozen conjecture`
- `an exact nonexistence certificate for four pairwise mutually unbiased bases
  of C^6, replayed as a polynomial identity by an independent verifier`
- `or an explicit unresolved outcome recording the replayed triple that fixes
  the lower bound at three, the certified exclusion set of pairs whose
  containing quadruples are ruled out, the exhausted root-of-unity envelope,
  and the smallest remaining obligation`

Stopping rules:

- `stop on an explicit set of four pairwise mutually unbiased bases of C^6
  whose every exact condition is verified`
- `stop on an exact nonexistence certificate replayed as a polynomial identity
  by an independent verifier`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no obligation, certify no
  newly excluded pair, and widen no envelope`
- `never promote unextendibility of one pair, exhaustion of a root-of-unity
  envelope, or failure of any search to the nonexistence of four mutually
  unbiased bases`
- `abandon the clique or equivalence-class search and record the frontier when
  the frozen node budget is reached`
- `discard rather than round any floating-point value that reaches a
  certificate`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Pair unextendibility mistaken for progress on the conjecture | the natural stepping stone excludes only the quadruples containing that pair, yet reads as "almost solved". This is now a **proved** limitation, not a worry: since a triple exists, the universal-over-pairs route is refuted | `pair_unextendibility_does_not_resolve_the_headline` is a recorded refused route; it heads the section 8 refusals; section 3 restates the target as "no triple extends to a quadruple"; a stopping rule forbids the promotion |
| Adopting a tensor-equivalent waypoint pair | such a pair is provably extendible, so the slice is guaranteed wasted; and "I recall this one is isolated" is exactly the unsourced-recollection failure | `tensor_equivalent_waypoint_refused` is a recorded refused route; stage 2 certifies inequivalence by the exact `(6!)^2` finite check before any search runs; a recalled inequivalence claim is never sufficient |
| No waypoint pair specifiable without the review | the `mu_12` envelope may contain only the tensor class, leaving nothing to freeze | stage 2 is a measured branch, not a guess: it reports the fact outright and promotes acquisition to the gating step, with `mu_24` as an optional prior attempt |
| Star configuration mistaken for a quadruple | three bases each unbiased to one fixed basis is much easier to satisfy and would read as a refutation | `four_mub_set_definition` names the rejected reading; section 8 refuses the star configuration as a certificate; the verifier checks all six pairs explicitly |
| The frozen system is simply out of reach | ~75 unknowns with companion conjugate variables is beyond any exact elimination available, and R6 (the `6x6` classification) is unacquired | section 7 says so plainly rather than promising a route; section 8's last row records the contract without promising delivery; the slice's declared deliverable is the exclusion set, not a proof |
| Numerical nonexistence read as a proof | the planning dossier names it, and it is the standard way this problem class produces false results | refused by name; `numerical_nonexistence_is_not_a_proof` is a recorded refused route; `floating_point_values_admitted_to_trust_path` is a counted metric |
| Envelope exhaustion read as nonexistence | a completed `mu_12` sweep is exact but restricted, and reads deceptively like an answer | `root_of_unity_envelope_is_a_restriction` is a definitional assumption; a stopping rule forbids the promotion; section 8 gives the restricted claim its own certificate row |
| Numerical invariant used for equivalence | spectra and similar invariants are the usual shortcut and can merge or split classes wrongly | `hadamard_equivalence_is_a_finite_check` makes the exact finite check a lemma; section 8 refuses numerical invariants as substitutes |
| `sqrt(6)` or `Q(zeta_6)` entering the field | `sqrt(6)` lies in no cyclotomic field; `Q(zeta_6)` cannot represent the section 9 third basis, so the slice could fail to represent its own certified triple | the `1/6` factor rides as a rational scalar; `Q(zeta_12)` is frozen once, with `Phi_12` named, and section 9.1 supplies the derived reason |
| Trusting a CAS transcript | a Gröbner or SOS engine is large, third-party, and unpinned | only the replayed exact identity certifies; admitting any such engine needs an ADR (section 12) |
| Symmetry convention mismatch | if the review quotients differently, reported counts are not comparable | R4 records it; the group is stated in full with conjugation and role permutation excluded wherever a count is reported; and the group is not part of the frozen statement, so the answer is unaffected |
| The retained finding treated as verified before replay | it is a human derivation; repo doctrine requires replay before a certificate counts | its status is labelled `derived, not machine-replayed`; stage 0 discharges it first, before any framing depends on it |

## 12. Capability check

**Covered by existing capabilities.**

- ADR-0039 declarative problem intake: the intake file is exactly that
  artifact, and `problem validate` plus `problem demo` confirm it creates no
  trust (`logical_status unknown`, novelty and significance `not_assessed`,
  zero warrants).
- Exact algebraic arithmetic over a named number field with the standard
  library only. The Phase 5 slice in `src/math_research/phase5/` does this
  shape of work over `Q(sqrt(d))(i)` per ADR-0033 and ADR-0035; the field here
  is `Q(zeta_12)`, a different extension, so that code is a precedent and a
  pattern rather than a reusable component.
- ADR-0035's posture is the right model: the system **verifies certificates and
  never discovers them**, and a case arriving without a certificate yields an
  explicit unresolved outcome rather than an attempt. Stages 0, 1, and 2 are
  complete finite computations needing no certificate supplier; stage 3 does,
  and that is the boundary.
- Exhaustive finite search with exact arithmetic and a replayable node log, as
  in the Graffiti-322 precedent.
- ADR-0055 two-fresh-novelty-rechecks: the gate for R1 to R7.
- Phase 3A memory for machine-readable retention of the matrix list, the class
  partition, the exclusion set, the frontier, and route refutations.
- ADR-0047 bounded central-lead runtime if a model is involved; the target is
  frozen and no warrant is producible there.
- ADR-0036 publication projection for any write-up: a claim computes to
  `Conjecture` absent a kernel-checked attestation, except that an exact
  certificate reaches `Proposition` — the intended ceiling here, including for
  the section 9.1 finding once replayed.

**Would require a new ADR.** Unchanged in substance by the re-freeze — the
escalation makes the gap wider, not narrower.

- **A Gröbner-basis engine.** None exists in this repository; the only exact
  algebraic engine is the Phase 5 certificate checker, which performs no
  elimination. An in-repository Buchberger implementation over `Q(zeta_12)` is
  a new exact-algebra capability, and using it on a trust path needs an ADR;
  admitting a third-party CAS as a candidate producer needs one too, covering
  the pin, the licence, the invocation bound, and the rule that only the
  replayed identity certifies.
- **Rational sum-of-squares machinery.** No SOS or positive-semidefinite
  machinery exists. Separately, ADR-0035 admits certificates only from a human
  deriving principal and rejects any certificate declaring a solver, search,
  interval, or residual-reconstruction origin, so an SOS certificate must enter
  through that human boundary or a new ADR must define machine derivation.
- **Exact interval arithmetic with rational endpoints.** ADR-0035 states
  explicitly that no interval or residual-reconstruction path exists and that
  none was adopted. Route (c) needs its own ADR before it can run at all.
- **Any numerical semidefinite or optimization solver.** Refused outright by
  repository-owner rule, not gated. Nothing to activate, and an ADR is not the
  right instrument.
- **Acquisition of any row in section 5.** ADR-0050, human-planned exact-URL,
  separately authorized. Not performed here. Note that stage 2's negative
  branch makes this the **gating step** rather than a convenience.
- **Any Crossref discovery query** over these terms runs under ADR-0051, is
  inspiration-only, and does not itself perform or satisfy the ADR-0055
  re-check.

Stages 0, 1, and 2 run entirely on existing capability: exact cyclotomic
arithmetic, finite enumeration, and a finite permutation check. Stage 3 does
not — each of its three routes needs a new ADR. That asymmetry is the main
thing the operator should notice: everything decisive and cheap in this target
is available now, and every nonexistence route is not.

## 13. Open questions before intake

1. **Confirm Problem 10.2's exact statement (R1).** The strength relation is
   `unresolved` because the review is unacquired. If the review's Problem 10.2
   differs from the frozen rendering, the target must be re-frozen rather than
   amended.
2. **Authorize stage 0 first.** Replaying the retained triple is cheap and
   discharges the section 9.1 obligation. Every other framing in this dossier
   depends on it, so it should run before anything else is scheduled.
3. **Is stage 3 authorized at all?** All three certificate routes need a new
   ADR (section 12). The operator may reasonably scope the first run to stages
   0 to 2, which need none, and defer the nonexistence machinery entirely.
4. **The stage 2 branch.** If no `mu_12` Hadamard matrix is tensor-inequivalent,
   does the operator authorize the `mu_24` widening, or go straight to
   acquiring the review? The dossier does not choose; it reports the branch.
5. **Which family member, if acquisition happens?** Once the review is
   acquired, a chosen member of `M_6^(1)`, `K_6^(2)`, or `K_6^(3)` becomes a
   waypoint candidate — but it must still pass the exact tensor-inequivalence
   check before adoption, and freezing a member is a **new problem definition**
   for the waypoint, not an edit to this dossier.
6. **Is the exclusion set an acceptable deliverable?** This target cannot
   deliver a proof in one slice. If a certified exclusion set of pairs is not
   an acceptable outcome, the target should not be scheduled at all.
7. **Confirm the `20` USD spend cap**, the clique and classification node
   budgets, and the review-point cadence used by the stagnation rule.

Human approval of the semantic alignment in sections 3 and 4 remains required
and is not granted by this file.
