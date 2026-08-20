# Phase 4B acquisition adoption spike

This is a nonproduction, offline-only contract spike. It demonstrates a narrow
candidate-acquisition boundary with injected transport, explicit network
capability, pre-fetch acquisition authorization, operator-supplied robots
decisions, fixed bounds, immutable failure records, and deterministic replay.

It does not implement live HTTP or DNS, terms handling, connected-peer checks,
retention/parsing rights, Phase 4A persistence, deletable content objects,
streaming storage, rate scheduling, or the complete ADR-0028 gate. Captured
fixture bytes in its replay manifest are permitted only because every input is
project-authored synthetic data. A production audit/export must never retain
revocable source plaintext outside its per-source deletable object.

Run the focused suite offline:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_phase4b_acquisition_spike
```
