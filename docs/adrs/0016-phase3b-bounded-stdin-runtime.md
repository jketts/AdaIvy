# ADR-0016: Admit bounded stdin wrappers into the sealed Lean runtime

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** sections 9.3 and 19 Phase 3B; ADR-0015 production-input gate
- **Decision owners:** researcher and repository maintainer

## Context

ADR-0015 accepted the Lean 4 plus mathlib backend after entry-gate repair v4,
but the sealed v4 launcher accepted only twelve image-embedded fixture paths.
The bounded production prompt correctly stopped because using those fixture
paths as a production interface, adding a host mount, or mutating the container
would have changed the accepted runtime or policy.

Dynamic-input entry gate v5 tested the smallest policy change needed for a
production wrapper: bounded source bytes enter on standard input and are staged
by the trusted launcher at one fixed container-only path. The v5 image inherits
the exact v4 root filesystem and replaces only `/checker/launcher`. No
toolchain, dependency closure, Landlock hardener, executable allowlist, seccomp
rule, privilege control, resource control, network control, or v4 artifact was
changed.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Reuse a v4 fixture path | v4 launcher allowlist | No new image | Treats tests as production and requires container mutation | Prohibited |
| Add a read-only host bind mount | Docker supports it | Simple input delivery | Changes the accepted no-host-mount control and exposes a host path | Rejected |
| Copy source into a created container | Docker copy path | Avoids a mount | Mutates the sealed container root filesystem | Rejected |
| Stage bounded stdin on container-only noexec tmpfs | v5 repeated/restart gate | No host path, fixed invocation, bounded bytes | Launcher becomes a new sealed artifact | Selected |

## Decision

Accept image `adaivy-phase3b-gate-v5:lean-v4.32.1` at digest
`sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f`
as the production-candidate runtime for the first bounded Lean adapter.

The launcher accepts no source path or user argument. It reads at most 262,144
bytes from standard input, rejects empty and oversized streams, and creates
exactly `/tmp/adaivy-input.lean` with `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`
before setting its mode to `0400`. `/tmp` remains the accepted container-only
`rw,noexec,nosuid,nodev,size=64m` tmpfs. The launcher then makes the same fixed
Lean invocation under the inherited Landlock, seccomp, no-network, read-only
root, no-capability, no-new-privileges, user, CPU, memory, process, file, and
descriptor controls.

The v5 image contains no production or dynamic fixture source. Gate fixtures
are stdin-fed tests only and are not an interface. Production validation and
trusted-wrapper generation remain outside this ADR and must fail closed before
invoking the launcher.

## Consequences

- A deterministic trusted wrapper can now reach the checker without a host
  mount, fixture-path reuse, or root-filesystem mutation.
- The launcher source and binary join the sealed runtime identity; changing the
  stdin limit, fixed path, creation flags, invocation, hardener, toolchain, or
  any sandbox control requires a fresh entry gate.
- Standard input is untrusted data. Passing the runtime gate does not authorize
  arbitrary Lean files or weaken the production fragment policy.
- Checker output remains proposal-only. This decision cannot approve semantic
  alignment, applicability, novelty, significance, contribution, or an
  `EpistemicWarrant`.
- The first v5 fixture attempt is retained: its `simp` proof disclosed
  `propext`, correctly contradicting the fixture's empty-axiom expectation. The
  corrected axiom-free `rfl` fixture then passed three rounds.

## Blueprint deviation

None. This supplies the previously missing sandboxed production-input path for
the Lean adapter selected by ADR-0015. It does not implement a production
adapter or broaden Phase 3B.

## Validation and revisit trigger

Keep this decision only while the decisive
`reports/phase-3b-entry-gate/v5/entry-gate-v5.json` remains reproducible:

- the v5 root filesystem begins with the exact v4 diff IDs and only the
  launcher path differs;
- the executable inventory remains exactly the launcher, ELF loader, and Lean;
- all v4 controls and the three-round executable-policy probe pass;
- empty, oversized, path-argument, exact-limit, and dynamic-source stdin probes
  pass over two repeats and one clean restart;
- all formal-classification fixtures and canonical hashes remain stable;
- all Phase 0-3A checks, protected seals, v4 artifacts, credential scans, and
  zero-model/API checks pass.

Revisit before any new import closure, larger input, alternate path/transport,
host mount, writable dependency, runtime executable, policy change, or broader
Phase 3B tool.
