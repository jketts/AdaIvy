# Phase 3B Entry-Gate Reproducibility Evidence

Status: repository seals verified; checker reproducibility unmeasured

## Commands executed

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -W error::ResourceWarning -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m phase0_harness.cli check
```

The first command passed 156 tests. The second passed all 19 component checks.
A read-only probe recorded OS, architecture, commands on `PATH`, standard Lean
cache locations, free disk, and Git version. It did not install or download
software.

All 51 tracked JSON documents parsed, all 10 JSON schemas parsed and passed the
existing schema tests, and direct Phase 0, Phase 1, and Phase 3A semantic
validators returned no issue. The seal hashes and tag targets are listed in the
entry-gate report and match the accepted reports.

The final credential scan checked 110 persisted report/artifact/database files. The
configured credential was present only at its allowed local source and was
never printed. Persisted exact matches and credential-token pattern matches
were both zero.

## Checker evidence unavailable

The following fields remain null because no toolchain or fixture ran:

- Lean, Lake, elan binary hashes;
- full Lean/mathlib release commits as resolved locally;
- AdaIvy `lake-manifest.json` bytes/hash;
- source and cache archive hashes and sizes;
- checker invocation hashes;
- axiom-dependency outputs;
- fixture stdout/stderr/result hashes;
- repeated-result hashes;
- sandbox environment identity and containment evidence.

## Canonical checker-result design

A future canonical result hash includes only:

- schema/policy versions;
- exact target statement hash and declaration name;
- submitted fragment and generated wrapper hashes;
- toolchain, dependency lock, import allowlist, and sandbox policy hashes;
- deterministic command/argument identity;
- exit status and terminal classification;
- normalized diagnostic records;
- axiom-dependency set;
- stdout/stderr content hashes and lengths; and
- expected output artifact hashes.

It excludes wall/CPU timing, PID, absolute temporary paths, host run-directory
names, and timestamps. Those remain retained operational metadata but cannot
change the semantic result hash. This exclusion policy is designed only; it
must be proven with repeated fixtures and a clean restart.

## Acquisition/checking split

Networked acquisition creates and hashes the pinned local environment. Checking
then runs with networking disabled and can read only that environment. A replay
with a different Lean version, dependency lock, import policy, or sandbox policy
is a distinct result, never the same canonical checker run.
