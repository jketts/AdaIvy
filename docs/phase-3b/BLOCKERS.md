# Phase 3B Entry-Gate Blockers

Status: gate blocked

## Blocking conditions

1. `elan`, `lean`, and `lake` are unavailable.
2. No pinned Lean/mathlib sources, binaries, or precompiled cache exist locally.
3. AdaIvy's full mathlib commit, generated Lake lock, archive hashes, binary
   hashes, and expanded dependency licenses are not yet measured.
4. No production-accepted OS/container sandbox is available. The presence of
   `sandbox-exec` is not sufficient evidence of memory/process/network and
   filesystem containment for hostile elaborator metaprogramming.
5. None of the twelve fixtures has executed, so placeholder/axiom detection,
   warning parsing, containment, resource classification, and canonical replay
   are unverified.

## Unblock criteria

- explicitly authorize a networked acquisition step;
- acquire only the proposed pinned versions without modifying shell startup
  files or installing global Homebrew packages;
- record full commits, download hashes, binary hashes, versions, licenses,
  expanded size, and an AdaIvy `lake-manifest.json` hash;
- provide a sandbox that enforces no network, read-only dependencies, no
  repository/secrets access, bounded CPU/memory/processes/output, and cleanup;
- run all twelve fixtures twice plus a clean restart with canonical hashes;
- prove placeholder detection and axiom parsing fail closed;
- rerun all Phase 0–3A checks and protected hashes.

Until then, ADR-0015 remains proposed and no formal-checking backend may produce
a formal warrant.
