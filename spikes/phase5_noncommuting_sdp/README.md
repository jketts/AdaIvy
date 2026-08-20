# Phase 5 noncommuting SDP design spike

This isolated spike validates project-authored, exact rational-complex primal
and dual candidates for small quantum-state-discrimination SDPs. It is a
certificate-format and adapter-adoption experiment, not a solver.

Run the focused offline suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
  python3 -m unittest tests.test_phase5_noncommuting_sdp_spike -v
```

Nothing here integrates with Phase 5, changes its sealed records, enables
search tiers 2--4, imports a dependency, or grants a mathematical warrant to a
numerical result.
