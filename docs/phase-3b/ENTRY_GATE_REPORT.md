# Phase 3B Lean Entry-Gate Report

Date: 2026-08-19

Status: **blocked before acquisition and checker execution**

## Outcome

Lean 4 plus mathlib remains the preferred first formal-checker candidate, but
the entry gate does not pass on this machine. `elan`, `lean`, and `lake` are not
installed, there is no Lean/mathlib cache, and no Docker, Podman, Colima, Lima,
or equivalent container runtime is available. macOS provides
`/usr/bin/sandbox-exec`, but its presence alone does not demonstrate the memory,
process, filesystem, network, and cleanup controls required for hostile Lean
metaprogramming.

Per the requested stop condition, no toolchain was installed, no Lean fixture
was executed, no formal result was classified, and no production Phase 3B code
was written. Unexecuted candidates are recorded as not evaluated, never as
low-performing.

## Architecture consistency

The gate is consistent with architecture baseline 0.3:

- ADR-0012 schedules formal-tool and proof-assistant grounding in Phase 3B.
- Blueprint sections 9.3 and 19 require a sandboxed, pinned proof-assistant
  adapter that rejects placeholders and records axioms and warnings.
- Phase 1 semantic custody remains separate from formal validity.
- Phase 2 proposal-only imports and orthogonal independence labels remain
  authoritative.
- Phase 3A source/provenance records remain immutable and unchanged.

No architecture contradiction or material design deviation was found. ADR-0015
records the proposed first backend and its acceptance conditions.

## Sealed-entry results

| Check | Result |
|---|---|
| Existing tests | 156/156 passed with `ResourceWarning` promoted to error |
| Phase 0 harness | 19/19 passed |
| Tracked JSON | 51/51 parsed |
| JSON schemas | 10/10 parsed; existing schema tests passed |
| Phase 0 semantic validation | zero issues |
| Phase 1 semantic validation | zero issues |
| Phase 3A export/provenance validation | passed |
| Persisted credential scan | 110 files, zero exact or token-pattern matches |
| Working tree before deliverables | clean |
| AdaIvy runtime model/provider/API calls | zero |

The protected hashes matched their sealed values:

- Phase 0 raw observations:
  `e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533`
- Phase 2 live status:
  `c29c13d80164890d0b5d1d1fdca3eeac66c56300c9683a1c4087d7bc03c1ac05`
- failed v2 database:
  `4c1c402d142a33d6529fb3991cb18bab2513bcb13dd2eddd3b30af0ab76ad064`
- accepted v3 database:
  `30e0db8d1bf9b601ce9d262fdce9459dea573c742aaca27f7af97d7895f81e94`
- accepted v3 report:
  `ff706139a8f0415e1f1f6efc0ac714f0e588f187e94e82c7dff0af92d5da8cb9`
- Phase 2 release manifest:
  `90b188e134e0489318319919e09dedf52fb817f658f07b173ff4ab3d75188664`
- Phase 3A acceptance JSON:
  `c0ea908f3b6f1c9fd19d83180f3e55f865238dfc4f96727048531d51bfe8c241`
- Phase 3A canonical export:
  `f1b57c2cae96638a7545476722685f17eb7470c5b4d0a790ca788de8e8756272`
- Phase 3A traceable report:
  `881b2d0a85da1c9c57181c0aeb28ae6efccbc88e4a6521f6d29bd60856544ac9`

The annotated `phase-2` tag object remains
`730595f22b72888f7b73ed92ef874b8694637558` and peels to
`f8531aefc39792ecf02c61f0019cea087ebf87f2`. The annotated `phase-3a` tag
object remains `1b61ea26a5f9dc6b3b1a81a4f78ceced6cb25fb3` and peels to
`c21374a1f2239c24b305a58c15d149db4de5fdbf`. `origin/main` also resolved to
the Phase 3A commit during the gate.

## Local prerequisite probe

| Item | Measured result |
|---|---|
| OS | macOS 26.5.2, build 25F84 |
| Kernel/architecture | Darwin 25.5.0, arm64 |
| `elan` | unavailable |
| `lean` | unavailable |
| `lake` | unavailable |
| Git | Apple Git 2.50.1 |
| Container runtime | none found on `PATH` or in `/Applications` |
| macOS sandbox | `/usr/bin/sandbox-exec` present; capability not accepted |
| Lean/mathlib caches | none in the probed standard locations or repository |
| Disk | 623 GiB available on the repository volume |

The probe did not modify the machine or shell startup files. Official upstream
web documentation was consulted to prepare the pin and license proposal; no
toolchain archive, installer, source tree, cache, or runtime dependency was
downloaded into AdaIvy or executed.

## Proposed pin

The proposed acquisition target is:

- elan `v4.2.1`;
- toolchain file content `leanprover/lean4:v4.32.1`;
- mathlib release tag `v4.32.1` (official release commit prefix `520045a`);
- mathlib's release `lake-manifest.json` format `1.2.0` and exact transitive
  revisions recorded in `PROPOSED_TOOLCHAIN_MANIFEST.json`.

This is a proposal, not an acquired lock. Acceptance requires resolving the
full mathlib and Lean commit IDs, generating AdaIvy's own `lake-manifest.json`,
and recording archive/binary/content hashes during an explicitly authorized
networked bootstrap. A floating branch is prohibited.

Plan for at least 8 GiB free for the toolchain, sources, and precompiled cache;
the actual compressed download and expanded disk use must be measured during
acquisition. The current 623 GiB free is sufficient for that planning reserve.

## Trust and security decision

The ten formal result classifications are specified in
`TRUST_CLASSIFICATION_POLICY.md`. A zero exit code is never sufficient:
placeholder scans, warning retention, exact target hash, import policy,
`#print axioms` output, and sandbox evidence all participate in classification.
Only an empty axiom set may be called `kernel_checked`; the approved standard
set is disclosed separately, and any new declaration or unknown dependency is
`kernel_checked_with_unapproved_assumptions` at best.

The initial checker must embed a restricted theorem/proof fragment in a trusted
wrapper. Arbitrary complete Lean files are outside the trusted profile. Static
source rules reject placeholders, custom imports, unsafe/FFI/native/evaluation
constructs, and direct side-effect APIs, but those rules are only defense in
depth. Production checking still requires an OS/container sandbox.

## Fixture and reproducibility status

All twelve required synthetic fixtures are specified. Every result is
`not_evaluated` with blocker `lean_toolchain_unavailable`; side-effect fixtures
also carry `safe_sandbox_not_demonstrated`. No expected outcome is presented as
an observation. Consequently, placeholder/axiom detection reliability,
containment, repeated canonical result hashes, and exclusion of timing/temp
paths from hashes remain unmeasured.

## Recommendation

**Defer acceptance; retain Lean as the proposed first backend.** Authorize a
separate acquisition-only step and install or identify a sandbox runtime. Then
rerun this gate from the pinned local environment with network disabled. Do not
build the production adapter until every fixture passes, axiom detection is
reliable, and containment is demonstrated.

Why3, SMT solvers, OMDoc/MMT, additional proof assistants, autonomous proof
generation, and the quantum convergence problem remain deferred.
