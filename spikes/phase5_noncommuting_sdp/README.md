# Phase 5 noncommuting SDP design spike

This isolated spike validates project-authored, exact rational-complex primal
and dual candidates for small quantum-state-discrimination SDPs. It is a
certificate-format and adapter-adoption experiment, not a solver.

Run the focused offline suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
  python3 -m unittest tests.test_phase5_noncommuting_sdp_spike \
                      tests.test_phase5_noncommuting_sdp_comparison -v
```

Nothing here integrates with Phase 5, changes its sealed records, enables
search tiers 2--4, imports a dependency on the offline path, or grants a
mathematical warrant to a numerical result.

## Engine-comparison experiment (ADR-0045)

`DEPENDENCY_LICENSE_COMPARISON.md` asked for the smallest later experiment:
the same frozen real and complex fixtures through at least two independent SDP
engines, retaining raw solver status/residuals and exact problem encodings, and
attempting rational/algebraic or interval reconstruction. That experiment is now
implemented, under an owner authorization restricted to **permissive licences
only** -- Clarabel (Apache-2.0), SCS (MIT), CVXPY (Apache-2.0). CVXOPT
(GPLv3-or-later) and MOSEK (commercial EULA) are out of scope.

| Module | Role |
|---|---|
| `validator.py` | the original exact rational-complex checker, unchanged; the file-based baseline |
| `algebraic.py` | exact arithmetic in `Q(sqrt(s))`, exact PSD by principal minors, rigorous `isqrt` enclosures |
| `encoding.py` | the exact problem encoding both engines consume, including the real embedding of complex Hermitian data |
| `ports.py` | `SDPEngine`, `ModuleResolver`, and the record types that make an engine result structurally untrusted |
| `engines.py` | the two licence-gated adapters and the excluded-module refusal |
| `reconstruction.py` | the five reconstruction attempts and the exact audit of an engine's floating-point point |
| `comparison.py` | the experiment runner, canonical report, and the semantic/operational hash split |
| `comparison_cli.py` | `run` and `inspect` |

### Running it

The offline default loads no engine and reports the experiment INCOMPLETE. That
exit status of `1` is the correct offline result and is not a pass:

```bash
PYTHONPATH=src:. python3 -m spikes.phase5_noncommuting_sdp.comparison_cli run
make spike-phase5-sdp
```

The engine-present leg needs a disposable environment built from
`requirements-phase5-sdp-comparison-py314-macos-arm64.txt` -- never the ordinary
`.venv`, and never the repository environment. `make check` must keep passing
with zero third-party packages installed.

```bash
python3 -m venv "$ENVDIR"
"$ENVDIR"/bin/python -m pip install --no-index --no-cache-dir \
  --find-links "$WHEELS" --require-hashes --only-binary=:all: \
  -r requirements-phase5-sdp-comparison-py314-macos-arm64.txt
make spike-phase5-sdp PY="$ENVDIR"/bin/python
```

### The trust boundary

A solver reporting `optimal` produces an **untrusted candidate**. Only an exact
check may call anything certified, and a case's disposition is derived only from
an exact check: `NumericSolution` has no field by which an engine can assert
correctness, and its `trust` is a constant.

Two engines agreeing is **not** evidence of correctness. They can share a
formulation error, a conditioning failure, or the same wrong optimum. The
agreement record carries `is_evidence_of_correctness: false` and cannot change a
disposition.

A tolerance-sized gap is not a closed gap. The measured result is that both
engines hit `(2 + sqrt(2))/4` to about `1e-11` and **neither closed the gap**:
under exact arithmetic every returned point failed POVM completeness and
complementarity, with exact gaps of roughly `1e-14` to `1e-11`, one of them
negative. What closed the gap was the solver-free exact reconstruction. Rational
reconstruction **failed**, because the optimum is irrational, and that failure is
recorded rather than dropped.

### Bounded scope of the reconstruction

The exact spectral construction covers exactly two outcomes in dimension two,
inside a quadratic field with a bounded squarefree radicand. Anything else is
recorded as `unsupported_shape` with a reason code and no optimum is claimed.
This is not a general noncommuting SDP solver and does not make Phase 5's
noncommuting expansion available.

### Timing and hashing

Timing and other operational observations -- elapsed milliseconds, iteration
counts, residuals, returned floating-point matrices, and everything derived from
them -- are hashed separately from semantic identity, so scheduling variance
cannot change a result's semantic identity. Any object carrying
`hash_class: operational_only` is replaced by a marker in the semantic preimage.
Verified by execution: two consecutive real two-engine runs produced identical
`content_hash` values and different `operational_hash` values.
