# Phase 5 noncommuting SDP design spike

This isolated spike validates project-authored, exact primal and dual
candidates for small quantum-state-discrimination SDPs. It is a
certificate-format and adapter-adoption experiment, not a solver.

Arithmetic is exact over one real quadratic extension of the rationals per
case, `Q(sqrt(d))(i)` with `d` squarefree (`d = 1` meaning the rationals). See
`algebraic.py` for the field and `docs/adrs/0033-phase5-noncommuting-exact-algebraic-certificates.md`
for the decision, the measured outcome, and what falls outside the field.

Run the focused offline suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
  python3 -m unittest tests.test_phase5_noncommuting_sdp_spike -v
```

Measured on the frozen fixtures in
`fixtures/phase5-noncommuting-sdp/exact-small-cases.json`:

| Case | Field of the certificate | Primal/dual gap |
|---|---|---|
| `commuting-exact-control` | `Q` | exactly `0` |
| `real-noncommuting-rational-candidate` | `Q` | exactly `1/4` |
| `complex-noncommuting-rational-candidate` | `Q` | exactly `1/4` |
| `real-noncommuting-algebraic-certificate` | `Q(sqrt 2)` | exactly `0` |
| `complex-noncommuting-algebraic-certificate` | `Q(sqrt 2)(i)` | exactly `0` |
| `real-noncommuting-algebraic-certificate-radicand-five` | `Q(sqrt 5)` | exactly `0` |
| `real-noncommuting-irreducible-cubic-boundary` | `Q` | exactly `1/2`, unreachable in any quadratic extension |

The two `1/4` rows are retained deliberately: they use ensembles byte-identical
to the two rows above them that reach zero, so the difference is the field the
certificate is written in and nothing else.

Nothing here integrates with Phase 5, changes its sealed records, enables
search tiers 2--4, imports a dependency, or grants a mathematical warrant to
any result. The checker verifies supplied certificates; it does not find them.

## ADR-0045 engine-comparison experiment

The optional comparison keeps its separate exact arithmetic in
`comparison_algebraic.py` and preserves its older file-based baseline as
`comparison_validator.py`, so it cannot replace the ADR-0033 certificate
checker. Clarabel and CVXPY/SCS are gated, spike-only dependencies; absent
engines produce explicit missing-tool records. Numerical agreement creates no
warrant, and only the exact reconstruction can close a gap.

Run the offline fail-closed leg with `make spike-phase5-sdp`. To exercise both
engines, use the hash-pinned
`requirements-phase5-sdp-comparison-py314-macos-arm64.txt` in a disposable
environment and pass its Python as `PY=...`.

The comparison retains its original three-case input separately as
`fixtures/phase5-noncommuting-sdp/comparison-small-cases-v1.json`; it does not
reinterpret or replace the expanded ADR-0033 certificate fixture.
