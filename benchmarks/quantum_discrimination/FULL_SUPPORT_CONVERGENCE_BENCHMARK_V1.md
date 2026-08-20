# QD-FS-01: Full-Support Quantum-Discrimination Convergence

Status: **preregistered / specification-only / execution deferred until AdaIvy completion**

Benchmark identifier: `QD-FS-01`

Document version: `1.0.0`

Registration basis: successor to the audited quantum-discrimination dossier at
commit `6010b117d9a7a5494c60ceb3d810b7f790e5b27a`

This document freezes a two-sided research question. It does not assert a
theorem, select an expected answer, execute a benchmark, report a search, or
introduce solver, numerical, Lean, or production code.

## 1. Frozen research question

> For every finite-dimensional weighted ensemble in the stated domain and
> every initial POVM $M^{(0)}$ whose components satisfy
> $M_i^{(0)}\succ0$ for every outcome $i$, resolve whether every
> accumulation point of the normalization-corrected JRF iteration satisfies
> the Yuen--Kennedy--Lax optimality conditions.

The question is deliberately two-sided. An admissible resolution may be:

- a proof of the universally quantified statement;
- an exact counterexample satisfying every frozen hypothesis;
- an exact demonstration that the proposed domain does not ensure an
  iteration-closed, well-defined orbit, in which case the primary question is
  classified as ill-posed under this domain rather than silently repaired; or
- an `OPEN-AFTER-BOUNDED-WORK` disposition, but only after every bounded search,
  proof attempt, failed reconstruction, missing certificate, and unresolved
  obligation has been reported.

No disposition beyond preregistration is assigned in this version.

## 2. Quantified domain

The universal quantifiers range over the following data.

1. **Outcomes and space.** Let $I=\{1,\ldots,m\}$, where
   $1\le m<\infty$, and let $H$ be a complex Hilbert space with
   $1\le d=\dim H<\infty$.
2. **Weighted ensemble.** For every $i\in I$, let
   $W_i\in\operatorname{Pos}(H)$ satisfy

   \[
     p_i:=\operatorname{Tr}(W_i)>0,
     \qquad
     \sum_i p_i=1.
   \]

   Equivalently, $W_i=p_i\rho_i$, where
   \(\rho_i\succeq0\) and \(\operatorname{Tr}\rho_i=1\). Individual
   $W_i$ may be rank deficient. Zero-weight outcomes are excluded rather
   than retained as degenerate labels.
3. **Effective space.** All operators are restricted to

   \[
     H=H_{\mathcal E}:=
       \operatorname{supp}\!\left(\sum_iW_i\right).
   \]

   Thus the ensemble has no invisible ambient orthogonal summand, but no
   individual $W_i$ is assumed positive definite.
4. **Feasible measurements.** The feasible set is

   \[
     \mathsf{POVM}_m(H)
       :=\left\{M=(M_i)_i:
          M_i\succeq0\ \text{for every }i,
          \sum_iM_i=I_H\right\}.
   \]
5. **Initial full support.** The initial measurement must satisfy

   \[
     M^{(0)}\in\mathsf{POVM}_m(H),
     \qquad
     M_i^{(0)}\succ0\quad\text{for every }i.
     \tag{FS-INIT}
   \]

   In `QD-FS-01`, **full support means componentwise positive definiteness**.
   The equation \(\sum_iM_i^{(0)}=I_H\) is POVM normalization and does not by
   itself imply full support.
6. **Exact semantics.** Algebraic equalities, positive-semidefinite order,
   support, rank, and zero tests have exact mathematical meaning. A later
   numerical protocol must use rigorous enclosures before any approximate
   quantity can discharge one of these predicates.

No commutativity, full rank of the $W_i$, binary-outcome restriction,
uniqueness of an optimum, or uniqueness of an accumulation point is assumed.

## 3. Objective and optimum

For $M\in\mathsf{POVM}_m(H)$, define

\[
  P_{\rm succ}(M):=\sum_i\operatorname{Tr}(W_iM_i),
  \qquad
  P_*:=\max_{N\in\mathsf{POVM}_m(H)}P_{\rm succ}(N).
\]

Finite dimension makes the feasible set compact and the objective continuous,
so $P_*$ is attained. This fact does not imply that any JRF orbit converges
or that any of its accumulation points is optimal.

## 4. Frozen normalization-corrected iteration

For a POVM $M$, set

\[
  D_i(M):=W_iM_iW_i,
  \qquad
  K(M):=\sum_iD_i(M).
\]

The canonical benchmark map is exactly the ordinary-inverse
`normalization_corrected` map already frozen in `THEOREM_DOSSIER.md` and
`BENCHMARK_STATEMENTS.md`:

\[
  M_i^+:=T_{\mathcal E}(M)_i
    :=K(M)^{-1/2}D_i(M)K(M)^{-1/2},
  \qquad K(M)\succ0.
  \tag{FS-JRF}
\]

Here $M^+$ means the next iterate; it does not denote a Moore--Penrose
completion. The ordinary inverse square root is defined only when $K(M)$ is
positive definite on the effective space. The intended orbit, if it exists,
is

\[
  M^{(n+1)}=T_{\mathcal E}(M^{(n)}),
  \qquad n\in\mathbb N.
  \tag{FS-ORBIT}
\]

The dossier separately records the Moore--Penrose negative power

\[
  K(M)^{-1/2+}
    =\sum_{\lambda_j>0}\lambda_j^{-1/2}\Pi_j
\]

and the corresponding algebraic formula denoted there by $T^+$. If $K(M)$
is singular, that formula satisfies

\[
  \sum_iT^+(M)_i=P_{\operatorname{supp}K(M)},
\]

which need not equal $I_H$. It is therefore not a silent extension of
(FS-JRF) as a full-POVM iteration. `QD-FS-01` introduces no allocation rule for
the missing support projection and no second corrected iteration. Any future
use of a Moore--Penrose convention or a named completion is a distinct
benchmark variant. Under the frozen ordinary-inverse convention, failure of
$K(M^{(n)})\succ0$ is a domain diagnosis under Obligation A.

The inconsistent literal JRF Eq. (4)--(5) pair recorded in the dossier is not
the map in this benchmark.

## 5. Accumulation points and topology

On tuples of operators use the finite-product operator norm

\[
  \lVert M\rVert:=\max_i\lVert M_i\rVert_{\rm op}.
\]

A POVM \(\bar M\) is an accumulation point of an infinite orbit
\((M^{(n)})_{n\ge0}\) when there is a strictly increasing sequence
\((n_k)_{k\ge0}\) such that

\[
  \lVert M^{(n_k)}-\bar M\rVert\longrightarrow0.
\]

All finite-dimensional matrix norms induce the same topology, but this norm is
the frozen benchmark topology. Existence of accumulation points follows from
compactness only after Obligation A has supplied an infinite POVM orbit.

## 6. Complete YKL target

For a POVM $M$, define the canonical operator

\[
  \Gamma(M):=\sum_iW_iM_i.
\]

The complete canonical Yuen--Kennedy--Lax condition required by `QD-FS-01` is

\[
  \Gamma(M)=\Gamma(M)^\dagger,
  \qquad
  \Gamma(M)-W_i\succeq0\quad\text{for every }i.
  \tag{FS-YKL}
\]

In the finite-dimensional discrimination problem, (FS-YKL) is necessary and
sufficient for global optimality. Equivalently, a separately supplied
Hermitian dual operator $\Gamma$ must satisfy dual domination
\(\Gamma\succeq W_i\) and complementary slackness

\[
  (\Gamma-W_i)M_i=M_i(\Gamma-W_i)=0
  \quad\text{for every }i.
\]

Complementarity, pairwise extremality, fixedness, a small step residual, or
monotone objective values do not replace Hermiticity and dual domination. A
positive resolution must derive every required YKL condition rather than
assume the missing domination inequalities.

## 7. Obligation A -- well-defined orbit

Determine whether the quantified assumptions in Section 2 ensure all of the
following:

1. $K(M^{(n)})\succ0$ for every $n\in\mathbb N$, so every ordinary-inverse
   update in (FS-ORBIT) exists;
2. every updated component is positive semidefinite and
   \(\sum_iM_i^{(n)}=I_H\), so every iterate is a valid POVM; and
3. every iterate lies in the domain required by its successor.

A positive solution must prove all three properties from the frozen
hypotheses. One-step feasibility does not establish forward domain invariance.

If any property fails, the result must supply an exact admissible ensemble and
an exact componentwise-positive-definite initial POVM exhibiting the failure.
The primary convergence question must then be classified as ill-posed under
the proposed domain. The response must not switch to a pseudoinverse,
completion rule, regularization, or narrowed initialization without assigning a
new benchmark identifier.

## 8. Obligation B -- optimality of accumulation points

Conditional only on an infinite orbit satisfying Obligation A, determine the
truth of the following universal statement:

> For every data set quantified in Section 2, for every initial POVM satisfying
> (FS-INIT), and for every accumulation point \(\bar M\) of the orbit
> (FS-ORBIT), \(\bar M\) satisfies (FS-YKL), and therefore
> \(P_{\rm succ}(\bar M)=P_*\).

A positive resolution must prove this statement with the displayed
quantifiers and without importing YKL domination as an assumption. A negative
resolution must provide an exact counterexample satisfying every frozen
hypothesis and acceptance requirement in Section 9.

## 9. Counterexample acceptance contract

A disproof of Obligation B must include:

- a valid finite-dimensional weighted ensemble on its effective space;
- a valid initial POVM with $M_i^{(0)}\succ0$ for every outcome;
- exact entries, preferably rational or algebraic;
- a proof that every orbit step used by the conclusion exists and remains a
  POVM, under the frozen convention;
- an exact or rigorously certified orbit and accumulation-point argument;
- the objective value at the accumulation point;
- the true optimum, an exact optimum certificate, or an exact strictly better
  feasible POVM;
- an explicit YKL violation or an equivalent exact nonoptimality certificate;
  and
- a reproducible derivation independent of unbounded or uncertified
  floating-point evidence.

The following are insufficient:

- an initialization containing any zero or singular measurement component;
- the existing scalar boundary trap $M=(1,0)$;
- Tyson's inadmissible printed tuple $M_i=I_H$ when $m>1$;
- the inconsistent literal JRF formula in place of (FS-JRF);
- numerical convergence alone; or
- approximate eigenvalue, objective, or residual evidence without rigorous
  bounds.

A commuting or scalar counterexample can logically disprove the universal
statement if it satisfies every hypothesis. It must be classified as a
classical/commuting resolution, separately from a genuinely noncommuting
quantum counterexample.

## 10. Positive-result acceptance contract

A claimed positive theorem must include:

- one exact statement containing every ensemble, initialization, rank,
  support, domain, topology, and conclusion hypothesis;
- a proof of Obligation A for the claimed domain;
- a proof of the universally quantified accumulation-point property;
- a derivation of Hermiticity, dual domination, and any complementary
  relations used to reach (FS-YKL);
- explicit treatment of rank-deficient $W_i$ and possible support changes;
- comparison with the pinned literature and an exact semantic mapping of any
  imported theorem; and
- a clear classification as universal or restricted to a commuting,
  full-rank, binary, pure-state, or other proper subclass.

A theorem for a proper subclass earns only the corresponding restricted tier.
It must not be reported as resolving `QD-FS-01` universally.

## 11. Outcome and difficulty tiers

These tiers classify correct outcomes; they do not assume the answer is
positive.

1. **Domain diagnosis.** An exact proof that the orbit remains well-defined, or
   an exact admissible counterexample showing failure of well-definedness or
   iteration closure.
2. **Classical/commuting resolution.** A rigorous theorem or exact
   counterexample for the commuting reduction, explicitly restricted to that
   class.
3. **Noncommuting quantum resolution.** A rigorous theorem covering a
   noncommuting class, or an exact noncommuting counterexample in dimension at
   least two.
4. **Universal resolution.** A proof of the full frozen statement, or one
   counterexample satisfying every universal-domain hypothesis.
5. **Formal verification.** A machine-checked proof or counterexample
   certificate. This tier is recorded separately from ordinary mathematical
   proof and does not upgrade a restricted result to a universal one.

Correct falsification, exact domain diagnosis, and correct qualification of
assumptions are valid research outcomes. Failure to find a counterexample is
not evidence of truth.

## 12. Relationship to the committed boundary result

The audited counterexample in `THEOREM_DOSSIER.md` uses the scalar POVM
$M=(1,0)$. It proves that the arbitrary-initialization formulation is false:
the corrected orbit is constant at a nonoptimal boundary point with
$K=1/9$, optimum $2/3$, objective gap $1/3$, and YKL domination failure
$-1/3$.

`QD-FS-01` preserves that result unchanged and uses it only as motivation and
benchmark-history evidence. It does not satisfy (FS-INIT), because its second
measurement component is zero. The new benchmark removes that elementary
loophole by requiring $M_i^{(0)}\succ0$ for every outcome. This observation
does not prove, disprove, or otherwise resolve `QD-FS-01`.

## 13. Preregistration and contamination controls

- This specification is registered before any AdaIvy execution of
  `QD-FS-01`.
- Production implementation must not be tailored to a presumed positive or
  negative answer.
- The benchmark branch remains separate from `main`.
- Execution is deferred until AdaIvy's research, evidence, steering, replay,
  and formal-verification paths reach the selected readiness gate.
- Execution must begin from a recorded clean commit with pinned benchmark
  bytes, inputs, sources, budgets, tool permissions, and environment identity.
- The eventual record must distinguish discovery, ordinary mathematical proof,
  independent audit, and formal verification.
- Failed attempts, bounded negative searches, missing tools, unresolved source
  applicability, and unverified candidates must remain explicit artifacts.
- Repository tests, retrieval results, model agreement, and numerical evidence
  do not confer proof status.

## 14. Pinned source identities and future source gate

`QD-FS-01` reuses the approved dossier's source ledger:

- Ježek--Řeháček--Fiurášek: arXiv `quant-ph/0201109v1`,
  `https://arxiv.org/html/quant-ph/0201109v1`;
- Tyson: arXiv `0907.3386v4`,
  `https://arxiv.org/html/0907.3386v4`;
- Nakahira--Usuda--Kato: arXiv `1510.05202v1`,
  `https://arxiv.org/pdf/1510.05202v1`;
- Barnett--Croke: arXiv `0810.1919v1`,
  `https://arxiv.org/pdf/0810.1919v1`;
- Lü--Dong: *Physical Review A* **113**, 022451 (2026), DOI
  `10.1103/q7wq-ygm9`; only the official abstract is admitted in the current
  source record; and
- John Watrous, *The Theory of Quantum Information*, ©2018, visibly labeled
  “draft, pre-publication copy,” exact URL
  `https://jhwatrous.github.io/TQI.double.pdf`, byte length `2908202`, SHA-256
  `d947c05c29295357689cc798fe80dc0e4509e1706b2ed117a6cc913fd52debbc`.

The Watrous identity fixes reviewed bytes; it does not claim that the URL is an
immutable publication identifier or substitute the later published book.
Source links are provenance pointers, not proof warrants.

No literature theorem is recorded as resolving `QD-FS-01`. A future,
separately authorized literature audit may change that assessment only by
identifying a precise theorem whose ensemble, initialization, update, support,
topology, and conclusion hypotheses match the frozen question. Abstract-only
claims and secondary descriptions are insufficient.

## 15. Deferred execution record requirements

Before any future run, freeze at least:

- the clean source commit and SHA-256 of this specification;
- the exact obligation and outcome tier being attempted;
- all ensemble and initialization parameterizations;
- arithmetic, precision, interval, and reconstruction policies;
- search spaces, seeds, budgets, stop conditions, and time limits;
- source versions and permitted tool/network capabilities;
- proof-assistant version, imports, axioms, and checker policy when applicable;
  and
- the separation between discovery artifacts, candidate arguments,
  independent review, and accepted formal warrants.

Execution remains deferred. This file contains no executable benchmark,
algorithm implementation, proof search, numerical experiment, or formal
artifact.
