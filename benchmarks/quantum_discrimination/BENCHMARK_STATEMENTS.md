# Quantum Discrimination: Precise Benchmark Statements

Status: specification-only; non-executable

Normative scope: this file freezes the statements to be reviewed or proved. It
does not implement the iteration, invoke a solver, define numerical tolerances,
or contain Lean code. The supporting mathematical and source analysis is in
`THEOREM_DOSSIER.md`.

## 1. Disposition vocabulary

Every statement has exactly one disposition:

- `DEFINITION`: fixes notation or semantics; it is not a theorem.
- `PROVE`: an admissible future proof benchmark.
- `SOURCE-BACKED`: a proof target with a reviewed paper proof plan, but no
  AdaIvy proof warrant.
- `CONDITIONAL`: valid only after every named premise has been established.
- `EXACT-WITNESS`: a finite exact-arithmetic certificate to verify.
- `REJECTED`: known false under its stated quantifiers; it must not be posed as
  a proof target.
- `OPEN`: not established by the reviewed sources or this repository.
- `DEFERRED`: inadmissible until its named source or semantic gate is complete.

`SOURCE-BACKED`, numerical evidence, and successful finite tests never mean
`PROVE` has been discharged.

## 2. Common universe and assumptions

The following IDs are the only assumptions used below. A statement must list
all IDs on which it depends.

| ID | Exact assumption |
|---|---|
| S01 | $I=\{1,\ldots,m\}$ with $1\le m<\infty$. |
| S02 | $H$ is a complex Hilbert space with $1\le d=\dim H<\infty$. |
| S03 | $p_i>0$ for all $i$, and $\sum_i p_i=1$. |
| S04 | $\rho_i\succeq0$ and $\operatorname{Tr}\rho_i=1$ for all $i$. |
| S05 | $W_i:=p_i\rho_i$. |
| S06 | $H=\operatorname{supp}(\sum_iW_i)$; all operators are restricted to this effective space. |
| S07 | $M=(M_i)_i$ is a POVM: $M_i\succeq0$ and $\sum_iM_i=I_H$. |
| S08 | The algorithm variant is exactly `normalization_corrected` from QD-ALG-01. |
| S09 | The initial POVM is exactly $M_i^{(0)}=I_H/m$. |
| S10 | Whenever an ordinary inverse square root is used, $K(M)\succ0$ on $H$. |
| S11 | Algebraic identities and PSD order are interpreted in exact arithmetic. |
| S12 | Limits use the product norm $\lVert M\rVert:=\max_i\lVert M_i\rVert_{\rm op}$, which induces the finite-product operator-norm topology. |
| S13 | No uniqueness of either the optimal POVM or a trajectory limit is assumed. |
| S14 | For a cluster-point-to-fixed-point inference, $T_{\mathcal E}$ is continuous at that cluster point. |
| S15 | For a cluster-point-to-fixed-point inference, $\lVert M^{(n+1)}-M^{(n)}\rVert\to0$. |
| S16 | For a fixed/stationary-point-to-optimum inference, the YKL dual-domination inequalities hold. |

Zero-prior labels must be removed before S01--S06 are instantiated. A theorem
using an ambient space larger than S06, a pseudoinverse, a completed sub-POVM,
or a different initialization is a different benchmark statement.

## 3. Problem and algorithm statements

### QD-OBJ-01 — minimum-error objective

- Disposition: `DEFINITION`.
- Requires: S01--S07.
- Statement:

  \[
    P_{\rm succ}(M):=\sum_i\operatorname{Tr}(W_iM_i),\qquad
    P_{\rm err}(M):=1-P_{\rm succ}(M),
  \]

  and

  \[
    P_*:=\max_{N_i\succeq0,\,\sum_iN_i=I_H}
             \sum_i\operatorname{Tr}(W_iN_i).
  \]

  A POVM is globally optimal exactly when its success probability is $P_*$.

### QD-OBJ-02 — attainment of the optimum

- Disposition: `PROVE`.
- Requires: S01--S07.
- Statement: the POVM feasible set is nonempty and compact, the objective in
  QD-OBJ-01 is continuous, and at least one POVM attains $P_*$.
- Excludes: uniqueness and any algorithmic convergence conclusion.

### QD-ALG-00 — literal printed pair is not the canonical algorithm

- Disposition: `REJECTED` as a POVM self-map; retain as a source-alignment
  fixture only.
- Requires: S01--S07 and exact use of the two displayed formulas

  \[
    M_i^+=p_i^2\Lambda^{-1}\rho_iM_i\rho_i\Lambda^{-1},
    \qquad
    \Lambda^2=\sum_i p_i\rho_iM_i\rho_i.
  \]

- Rejection witness: $H=\mathbb C$, $p=(1/3,2/3)$,
  $\rho_1=\rho_2=1$, and $M=(1/2,1/2)$. The updated effects sum to
  $5/9\ne1$.
- Rule: no proof or implementation may silently replace either displayed
  formula while claiming to check this statement.

### QD-ALG-01 — normalization-corrected partial iteration

- Disposition: `DEFINITION`.
- Requires: S01--S07 and S11. The domain condition for a particular input is
  S10.
- Statement: for a POVM $M$, set

  \[
    D_i(M):=W_iM_iW_i,
    \qquad
    K(M):=\sum_iD_i(M).
  \]

  If $K(M)\succ0$, its unique positive-definite inverse square root exists
  and the next effects are

  \[
    T_{\mathcal E}(M)_i
      :=K(M)^{-1/2}D_i(M)K(M)^{-1/2}.
    \tag{QD-JRF}
  \]

  `QD-JRF` is a partial operation whose domain is

  \[
    \mathcal D_{\mathcal E}
      :=\{M\in\mathsf{POVM}_m(H):K(M)\succ0\}.
  \]

- Excludes: Moore--Penrose inversion and any rule that allocates a missing
  support projection among outcomes.

### QD-ALG-02 — conditional one-step feasibility

- Disposition: `PROVE`.
- Requires: S01--S08, S10--S11.
- Statement: if $M\in\mathcal D_{\mathcal E}$, then

  \[
    T_{\mathcal E}(M)_i\succeq0\quad\text{for all }i,
    \qquad
    \sum_iT_{\mathcal E}(M)_i=I_H.
  \]

  Hence QD-ALG-01 produces one and only one POVM from every point in its
  domain.
- Excludes: the assertion that $T_{\mathcal E}(M)$ remains in
  $\mathcal D_{\mathcal E}$.

### QD-ALG-03 — the uniform first step exists

- Disposition: `PROVE`.
- Requires: S01--S09 and S11.
- Statement: for $M_i^{(0)}=I_H/m$,

  \[
    K(M^{(0)})=\frac1m\sum_iW_i^2\succ0
  \]

  on the effective space S06. Therefore $M^{(1)}$ is defined and is a POVM.
- Excludes: existence of $M^{(n)}$ for every $n\ge2$.

### QD-ALG-04 — forward well-definedness from uniform initialization

- Disposition: `SOURCE-BACKED`.
- Requires: S01--S09 and S11.
- Statement: the trajectory

  \[
    M_i^{(0)}=I_H/m,\qquad
    M^{(n+1)}=T_{\mathcal E}(M^{(n)})
  \]

  exists for every $n\in\mathbb N$; equivalently,
  $K(M^{(n)})\succ0$ for every $n$.
- Required proof obligation: establish forward support invariance. QD-ALG-03
  alone is insufficient.

### QD-ALG-05 — per-step monotonicity

- Disposition: `SOURCE-BACKED`.
- Requires: S01--S08 and S10--S11 for the input $M$.
- Statement:

  \[
    P_{\rm succ}(T_{\mathcal E}(M))\ge P_{\rm succ}(M).
  \]

- Excludes: strict improvement, convergence of the effects, convergence to
  $P_*$, and optimality of fixed points.

## 4. Exact rejection benchmark

### QD-REJ-01 — unrestricted global-limit optimality

- Disposition: `REJECTED`.
- Requires: S01--S08 and S10--S13, but permits any initial POVM in
  $\mathcal D_{\mathcal E}$.
- Rejected statement:

  > For every admissible initial POVM for which every corrected step exists,
  > every limit point of the trajectory is globally optimal for QD-OBJ-01.

- Rejection dependency: QD-CE-01.
- Benchmark result: a proof attempt is an expected failure. Acceptance means
  verifying the counterexample and recording this universal statement as
  false, not weakening its quantifiers silently.

### QD-CE-01 — exact scalar non-optimal fixed point

- Disposition: `EXACT-WITNESS`.
- Requires: exact rational arithmetic and the scalar instance of S01--S08,
  S10--S13.
- Data:

  \[
    H=\mathbb C,\quad m=2,\quad
    \rho_1=\rho_2=1,\quad
    p_1=\frac13,\quad p_2=\frac23,
  \]

  \[
    M_1=1,\qquad M_2=0.
  \]

- Obligations, all of which must be checked:

  1. Ensemble validity: $p_i>0$, $p_1+p_2=1$, both states have trace one,
     and the effective space is all of $\mathbb C$.
  2. POVM validity: $M_1,M_2\ge0$ and $M_1+M_2=1$.
  3. Step domain:

     \[
       D_1=\frac19,\qquad D_2=0,\qquad K=\frac19>0.
     \]

  4. Fixedness: $K^{-1/2}=3$, so

     \[
       T_{\mathcal E}(M)=(1,0)=M.
     \]

     Thus every step exists and the constant sequence has the unique limit
     point $M$.
  5. Objective gap:

     \[
       P_{\rm succ}(M)=\frac13,\qquad
       P_{\rm succ}((0,1))=\frac23,qquad
       P_*=\frac23.
     \]

  6. YKL diagnosis: $\Gamma(M)=1/3$ is Hermitian and the complementary-
     slackness products vanish, but

     \[
       \Gamma(M)-W_2=-\frac13<0.
     \]

     Dual domination fails.

- Exact conclusion: well-definedness, fixedness, zero step residual, zero
  objective increment, and complementary slackness do not imply global
  optimality.

## 5. YKL benchmark statements

### QD-YKL-01 — dual feasibility

- Disposition: `DEFINITION`.
- Requires: S01--S06.
- Statement: $\Gamma$ is dual feasible exactly when

  \[
    \Gamma=\Gamma^\dagger,qquad
    \Gamma-W_i\succeq0\quad\text{for every }i.
  \]

  Its dual objective is $\operatorname{Tr}\Gamma$.

### QD-YKL-02 — weak duality

- Disposition: `PROVE`.
- Requires: S01--S07 and QD-YKL-01.
- Statement: for every POVM $M$ and every dual-feasible $\Gamma$,

  \[
    P_{\rm succ}(M)\le\operatorname{Tr}\Gamma.
  \]

### QD-YKL-03 — complementary slackness

- Disposition: `DEFINITION`.
- Requires: S01--S07 and a Hermitian operator $\Gamma$.
- Statement: $M$ and $\Gamma$ satisfy complementary slackness when, for
  every $i$,

  \[
    (\Gamma-W_i)M_i=0
    \quad\text{and}\quad
    M_i(\Gamma-W_i)=0.
  \]

- Rule: QD-YKL-03 without QD-YKL-01 is not an optimality certificate.

### QD-YKL-04 — YKL sufficiency

- Disposition: `PROVE`.
- Requires: S01--S07, QD-YKL-01, and QD-YKL-03.
- Statement: if $M$ is a POVM and there exists a dual-feasible $\Gamma$
  complementary to $M$, then

  \[
    P_{\rm succ}(M)=\operatorname{Tr}\Gamma=P_*,
  \]

  so $M$ is globally optimal.

### QD-YKL-05 — YKL necessity

- Disposition: `PROVE`.
- Requires: S01--S07, finite-dimensional primal and dual attainment, and strong
  duality.
- Statement: if $M$ is globally optimal, there exists a dual-feasible
  $\Gamma$ satisfying QD-YKL-03.

### QD-YKL-06 — canonical YKL form

- Disposition: `PROVE`.
- Requires: S01--S07 and QD-YKL-02--QD-YKL-05.
- Statement: define

  \[
    \Gamma(M):=\sum_iW_iM_i.
  \]

  Then $M$ is globally optimal if and only if

  \[
    \Gamma(M)=\Gamma(M)^\dagger,qquad
    \Gamma(M)-W_i\succeq0\quad\text{for every }i.
  \]

  At optimum this is equivalent to dual feasibility plus QD-YKL-03, and to
  the pairwise extremal equations

  \[
    M_j(W_j-W_k)M_k=0\quad\text{for every }j,k
  \]

  together with dual domination.
- Rule: pairwise extremality alone is not equivalent to global optimality.

## 6. Theorem ladder

QD-L00--QD-L14 are theorem rungs, and each states its full additional
hypotheses. A later theorem rung may be attempted only after its dependencies
are available or are repeated as explicit premises. QD-L15 is not a theorem
rung: it is a bounded conjecture-family and statement-construction target.

### QD-L00 — a finite optimum exists

- Disposition: `PROVE`.
- Requires: S01--S07.
- Statement: QD-OBJ-02.
- Depends on: no iteration claim.

### QD-L01 — one corrected step is a POVM

- Disposition: `PROVE`.
- Requires: S01--S08, S10--S11 for the input step.
- Statement: QD-ALG-02.
- Depends on: PSD congruence and positive square-root identities.

### QD-L02 — the uniform trajectory starts

- Disposition: `PROVE`.
- Requires: S01--S09 and S11.
- Statement: QD-ALG-03.
- Depends on: QD-L01 and effective-support positivity.

### QD-L03 — every uniform-initialized step exists

- Disposition: `SOURCE-BACKED`.
- Requires: S01--S09 and S11.
- Statement: QD-ALG-04.
- Depends on: QD-L02 plus a forward support-invariance lemma.

### QD-L04 — each defined step is monotone

- Disposition: `SOURCE-BACKED`.
- Requires: S01--S08, S10--S11.
- Statement: QD-ALG-05.
- Depends on: a separately checked directional-iterate or matrix inequality
  proof; POVM normalization alone is insufficient.

### QD-L05 — uniform-initialized objective values converge

- Disposition: `CONDITIONAL`.
- Requires: S01--S09, S11, and established QD-L03--QD-L04.
- Statement: there exists $P_\infty\in[0,1]$ such that

  \[
    P_{\rm succ}(M^{(n)})\uparrow P_\infty.
  \]

- Depends on: monotone bounded convergence for real sequences.
- Excludes: $P_\infty=P_*$.

### QD-L06 — the trajectory has cluster points

- Disposition: `CONDITIONAL`.
- Requires: S01--S09, S11--S12, and established QD-L03.
- Statement: the infinite sequence $M^{(n)}$ has a convergent subsequence
  whose limit is a POVM.
- Depends on: compactness of the finite-dimensional POVM set.
- Excludes: uniqueness, fixedness, stationarity, and optimality of the cluster
  point.

### QD-L07 — a regular cluster point is fixed

- Disposition: `CONDITIONAL`.
- Requires: S01--S09, S11--S15, established QD-L03, S10 for the named limit
  point, and a subsequence
  $M^{(n_k)}\to\bar M$ with $K(\bar M)\succ0$.
- Statement: if S14--S15 hold, then

  \[
    T_{\mathcal E}(\bar M)=\bar M.
  \]

- Excludes: YKL feasibility and optimality.

### QD-L08 — fixed-point equations do not close the proof

- Disposition: `REJECTED` as the implication “fixed point implies global
  optimum.”
- Requires: S01--S08 and S10--S11.
- Rejected statement:

  \[
    T_{\mathcal E}(M)=M\quad\Longrightarrow\quad
    P_{\rm succ}(M)=P_*.
  \]

- Rejection dependency: QD-CE-01.
- Rule: deriving complementary slackness or pairwise extremality at this rung
  does not repair the implication.

### QD-L09 — YKL-certified points are globally optimal

- Disposition: `PROVE`.
- Requires: S01--S07, S16, QD-YKL-01, and QD-YKL-03.
- Statement: QD-YKL-04.
- Depends on: QD-YKL-02.

### QD-L10 — the uniform mixed-state objective reaches the optimum

- Disposition: `OPEN`.
- Requires for the proposed target: S01--S09, S11--S13, and established
  QD-L03--QD-L05.
- Proposed statement: the limit in QD-L05 satisfies

  \[
    P_\infty=P_*.
  \]

- Excludes: convergence of the POVMs and optimality of every cluster point.
- Rule: monotonicity and boundedness establish existence of $P_\infty$, not
  this equality.

### QD-L11 — uniform mixed-state cluster points are globally optimal

- Disposition: `OPEN`.
- Requires for the proposed target: S01--S09, S11--S13, established QD-L03
  and QD-L06, plus a proof that every cluster point satisfies the full
  QD-YKL-06 conditions.
- Proposed statement: every cluster point of the uniform-initialized
  trajectory is a globally optimal POVM.
- Depends on: QD-L09 once the YKL premise is proved.
- Rule: “fixed,” “stationary,” “pairwise extremal,” or “complementary” cannot
  replace YKL dual domination. S16 is an obligation to prove here, not an
  assumption granted by the benchmark.

### QD-L12 — convergence in distance to the optimal set

- Disposition: `CONDITIONAL`.
- Requires: S01--S09, S11--S13, established QD-L00, QD-L03, QD-L06, and
  QD-L11, plus compactness of the POVM set.
- Statement: if $\mathcal M_*$ is the set of optimal POVMs, then

  \[
    \operatorname{dist}(M^{(n)},\mathcal M_*)\to0.
  \]

- Excludes: convergence to one POVM.

### QD-L13 — convergence to one globally optimal POVM

- Disposition: `OPEN` for arbitrary finite mixed-state ensembles under S09.
- Requires for the proposed target: S01--S09, S11--S13, established QD-L03,
  QD-L06, QD-L11, and QD-L12, plus an additional argument that the trajectory
  has a unique cluster point.
- Proposed conclusion: there exists $M_*\in\mathcal M_*$ such that

  \[
    M^{(n)}\to M_*.
  \]

- Rule: neither monotone objective values nor QD-L12 supplies the unique-
  cluster-point argument.

### QD-L14 — arbitrary-initialization global-limit optimality

- Disposition: `REJECTED`.
- Requires: the quantifiers in QD-REJ-01.
- Statement: QD-REJ-01.
- Rejection dependency: QD-CE-01.

### QD-L15 — bounded pure-state statement-construction target

- Disposition: `DEFERRED`; not a theorem statement or proof benchmark.
- Bounded family: pure-state, support-conditioned convergence questions for the
  exact algorithm variant in S08.
- Statement-construction target: after full-text acquisition and
  semantic-alignment review, construct one or more exact candidate statements
  that specify S01--S08, purity, initialization, support, topology, and the
  precise convergence conclusion.
- Statement status: intentionally not frozen. No member of the family is an
  imported premise or an admissible proof target yet.
- Gate: the published abstract is not sufficient to import the theorem, and
  its hypotheses must not be reconstructed from secondary descriptions.

## 7. Dependency summary

```text
QD-OBJ-01 ──> QD-OBJ-02 ──> QD-L00

QD-ALG-01 ──> QD-ALG-02 ──> QD-L01
      │              └────> QD-ALG-03 ──> QD-L02
      │                                  └─ support invariance ──> QD-L03
      └─ directional inequality ──> QD-ALG-05 ──> QD-L04

QD-L03 + QD-L04 ──> QD-L05
QD-L03 + compactness ──> QD-L06
QD-L06 + continuity + asymptotic regularity ──> QD-L07

QD-YKL-01 + QD-YKL-02 + QD-YKL-03 ──> QD-YKL-04 ──> QD-L09
QD-L05 + proof that its limit is optimal ──> QD-L10
QD-L06 + full YKL conditions ──> QD-L11 ──> QD-L12

QD-L07 - - no implication - -> QD-L09
QD-CE-01 ──> reject QD-REJ-01, QD-L08, and QD-L14
```

## 8. Acceptance contract for this specification pass

This pass is complete when review confirms all of the following:

1. QD-REJ-01 preserves the false universal quantifiers and is marked
   `REJECTED` rather than silently weakened.
2. QD-CE-01 verifies ensemble validity, POVM validity, invertibility,
   fixedness, the exact $1/3$ objective gap, and the failed YKL inequality.
3. QD-ALG-01 uses $K=\sum_iW_iM_iW_i$ and ordinary positive-definite inverse
   square roots, with pseudoinverse completion excluded.
4. QD-YKL-01--QD-YKL-06 keep dual feasibility, complementary slackness, and
   global optimality logically distinct.
5. Every theorem rung QD-L00--QD-L14 lists its assumptions, dependencies,
   disposition, and excluded stronger conclusions. QD-L15 remains separately
   labeled as a bounded conjecture-family and statement-construction target,
   with no frozen theorem statement.
6. No numerical stopping rule, finite experiment, source citation, or formal
   checker result is treated as proof.
7. No solver, numerical search, Lean implementation, runtime dependency, core
   import, or Phase 3B production change is introduced.
