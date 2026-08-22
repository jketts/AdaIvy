# ADR-0066: A distinct digest-pinned sandbox for model-authored experiment code

- **Status:** accepted for the fail-closed request-admission and refusal slice;
  live generated-code execution remains DISABLED pending the owner's image
  digest pin and the container-runtime probe run
- **Date:** 2026-08-22
- **Blueprint requirement:** ADR-0057 section 2 ("Model-authored research code
  runs only through a separate sandbox port"); ADR-0028 Phase 4B OCI precedent;
  ADR-0026 acceptance-suite and falsifiability rules; Sections 8, 11, 15.3, 23
- **Decision owners:** repository owner and researcher

## Context

ADR-0057 activated a campaign control plane with a `run_program` action, but
left it unable to execute. Its status line reads "live generated-code execution
pending its OCI gate" and its Consequences say the capability "remains
fail-closed until the separate OCI sandbox gate named above passes." No
production implementation of the `CampaignExperimentRunner` protocol declared in
`src/math_research/campaign/runner.py` existed; the only implementations were
scripted test doubles.

The consequence is measured, not hypothetical. `work/erdos-128-20260822/core.py`
is a 318-line exact search program written directly into a scratch directory by
the driving session: no campaign action, no program artifact hash, no tool-run
record, no sandbox. Because `run_program` cannot execute, the mathematics
happens outside the ledger, and ADR-0057's whole provenance argument -- that
"every material AI invocation, declared rationale, program, tool execution,
candidate selection, and verifier result used to claim AdaIvy authorship must
cross an AdaIvy boundary" -- is unenforceable in exactly the step where the
mathematics is.

This ADR is the gate ADR-0057 section 2 defers to.

Three facts constrain what can be delivered now.

1. Pulling or building an image requires network access and repository-owner
   authorization that has not been given. No image has been pulled, built, or
   run for this role.
2. Therefore no kernel-enforcement claim can be measured yet. The Phase 4B
   parser gate reproduces twelve fixtures with zero false admissions and
   demonstrates kernel memory, CPU, process, file, network-none,
   read-only-root, noexec-temp and ambient-secret controls; that evidence is
   about the parser image and the parser profile, and does not transfer.
3. ADR-0057 section 2 warns explicitly: "The Phase 4B parser image is a
   precedent, not authorization to reuse a parser-specific sandbox for
   generated code." A parser worker is a fixed, project-authored program that
   reads one document. Generated code is arbitrary, model-authored, and
   adversarial-by-construction with respect to its own bounds. Reusing the
   parser image would silently reuse a threat model derived for the wrong
   input.

So the deliverable is the refusal semantics, proven; not the execution.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt: reuse the Phase 4B parser image and profile | ADR-0028 gate is green on twelve parser fixtures | zero new pin, immediate execution | forbidden by ADR-0057 section 2; parser bounds were derived for a fixed project-authored worker, not for adversarial generated code; a shared image makes one role's widening the other's | rejected |
| Wrap: host `subprocess` with `rlimit`/`sandbox-exec` | Phase 4B's Darwin probe records `parent_sampled_rss_tripwire_not_strict` | no container needed | memory is a sampled tripwire rather than a kernel ceiling; no network namespace; no read-only root; ADR-0057 section 2 names hard limits | rejected |
| Interoperate: run generated code in the ADR-0016 Lean image | image already pinned and reviewed | reuse | same category error as the parser image; a formal-checking profile is not an experiment profile | rejected |
| **Build/defer (chosen): a distinct digest-pinned experiment image and profile, with the digest left unresolved and every call refusing until the owner pins it** | this ADR's probe suite runs offline today | the request-admission surface -- the only part the model can influence -- is enforced and falsifiable now; the digest is one line the owner adds later | the kernel claims stay unproven until the owner pins and the runtime probe runs; a reader could mistake a green `make check` for a proven sandbox | the pin, then `make check-campaign-experiment-oci` |

## Decision

Add `src/math_research/campaign/experiment_sandbox.py`: the single production
`CampaignExperimentRunner`. It is fail-closed and its refusals are a closed,
machine-readable vocabulary.

### 1. This is a distinct image and a distinct profile

The pin lives in `config/campaign-experiment-oci-image-linux-arm64-v1.json`
under its own schema `adaivy.campaign-experiment-oci-image-lock.v1`, with
`runtime_role: campaign_experiment_generated_code_only`. A lock whose
`runtime_role` differs is refused with `image_role_not_generated_code`.

The lock additionally carries `forbidden_reuse_digests`, which must list the
Phase 4B parser image digest. Pinning that digest as the experiment image is
itself a refusal, `parser_image_reuse_forbidden`, at both lock-parse time and
runtime-identity construction. `PHASE4B_PARSER_IMAGE_DIGEST` in the module is
cross-checked against `config/phase4b-oci-image-linux-arm64-v1.json` by the
acceptance suite, so the exclusion cannot drift away from the image it excludes.

### 2. The digest is unresolved and that is a refusal, not a fallback

The shipped lock carries `digest_status: unresolved`, `image_digest: null`,
`image_reference: null`, and `authorization_status:
unresolved_pending_owner_pin`. Every `CampaignExperimentSandbox` call refuses
with `image_digest_unresolved`. There is no default image, no `:latest`, no
pull, and no host-Python fallback path anywhere in the module. A `pinned` lock
whose `image_reference` is not exactly `<image_repository>@<image_digest>`
refuses with `image_digest_mismatch`; so does a local image whose measured
descriptor digest differs from the pin. `pull_policy` must be `never` and
`network_default` must be `none` in the lock itself.

### 3. Request admission is pure, first, and complete

`validate_experiment_request` is a pure function that opens nothing. It is
evaluated FIRST -- before the digest gate, before activation -- so a
model-chosen violation is always named precisely, and so the entire
model-influenced surface is provable offline. The gate order is:

1. request admission;
2. the bounded JSON stdin envelope;
3. the image digest pin;
4. the owner activation record;
5. an injected container-engine launcher;
6. the measured runtime identity; and only then
7. one bounded container launch.

Admission enforces, each with its own named refusal reason:

- **adapter**: `tool_id` must match a closed grammar and be a member of
  `ADMITTED_TOOL_IDS` (`exact_python_search`). An identifier whose tokens
  intersect a closed shell/process/network vocabulary is refused separately as
  `shell_adapter_forbidden`, so a shell adapter is distinguishable from an
  unknown one.
- **network**: `network` must be exactly `none`.
- **host path and command**: every argument must match
  `^[a-z][a-z0-9_]{0,31}=[A-Za-z0-9_.:+,-]{1,64}$`. A `/`, `\`, `~`, `..` or NUL
  is `host_path_forbidden`; anything else off-grammar, including a leading `-`
  that would inject a client flag, is `argument_forbidden`.
- **environment variable**: `ExperimentRequest` has no environment field, the
  planner action schema in `runner.py` is a closed field set, and the stdin
  envelope refuses `env`/`environ`/`environment`/`environment_variables` under
  `environment_field_forbidden` and any other unknown key under
  `envelope_unknown_field`. The container environment is the fixed eight-entry
  `CONTAINER_ENVIRONMENT`; nothing model-supplied reaches it.
- **content addressing**: the program bytes must hash to
  `program_artifact_hash` and every input artifact's bytes to its declared
  hash, or `program_hash_mismatch` / `input_hash_mismatch`. Duplicate input
  hashes are refused.
- **resource limits**: the model may *declare* the five `ResourceLimits`
  fields, and a declaration may only tighten. A declared value above the
  profile ceiling is `resource_limit_exceeds_profile`; below the profile floor
  it is `resource_limit_below_profile_floor`; a non-integer or `bool` is
  `resource_limit_malformed`. Every other bound -- open files, tmpfs inodes,
  file size, tmpfs size, stdin envelope bytes, program bytes, input counts and
  sizes, argument count -- is profile-fixed and is not expressible in a request
  at all.

### 4. The language and package set is bounded and narrow

A generated program is parsed with `ast` and admitted only if every import is
in `ALLOWED_IMPORT_MODULES`, an eighteen-entry standard-library set with no
filesystem, process, or network surface: `array`, `bisect`, `collections`,
`collections.abc`, `dataclasses`, `enum`, `fractions`, `functools`, `heapq`,
`itertools`, `json`, `math`, `numbers`, `operator`, `string`, `sys`, `textwrap`,
`typing`. Importing a network module is refused separately as
`program_network_import_forbidden`; any other import as
`program_import_forbidden`. Relative and star imports are refused.
`eval`, `exec`, `compile`, `__import__` are `program_dynamic_execution_forbidden`;
`open` is `program_filesystem_access_forbidden`; a closed set of escape
attributes (`__class__`, `__globals__`, `__subclasses__`, `__builtins__`, ...)
and the remaining introspection builtins are `program_reflection_forbidden`.

**This static check is defence in depth and is not a security boundary.**
Python reflection cannot be statically excluded in general; a determined
generated program can reach the interpreter's internals. The container is the
containment. The check exists to make the ordinary case obvious, to keep the
declared surface honest, and to make widening it a visible edit.

ADR-0057's revisit trigger fires before this set widens, before network or
credentials are allowed in the sandbox, and before parallel workers are
admitted. `max_process_count` has an ADR ceiling of 4 tasks precisely so a
generated program cannot build a useful worker pool inside a single container.

### 5. Every ADR-0057 section 2 control, its mechanism, and its proof

`CONTAINER_CONTROLS` is a machine-readable table of fifteen controls. Each
carries the ADR-0057 clause it implements, its enforcement mechanism, the
command-line evidence that must be present, and a `proof` string that says
honestly whether it is proven offline or is pending the container gate.

| Control | Mechanism | Proof today |
|---|---|---|
| digest-pinned image | `repository@sha256` only, `--pull=never`, measured descriptor digest compared to the pin | offline: lock probes + command construction |
| no network | `--network=none` (OCI network namespace) | command construction only; kernel claim PENDING |
| read-only root | `--read-only`, no `--mount`/`--volume`/`-v` anywhere in the argv | command construction only; kernel claim PENDING |
| empty noexec temporary filesystem | fresh `--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=...,nr_inodes=...,mode=0700,uid=65534,gid=65534` | command construction only; kernel claim PENDING |
| no inherited credentials | closed four-entry engine-client environment, closed eight-entry container environment, `--cap-drop=ALL`, `--security-opt=no-new-privileges=true`, `--user=65534:65534` | offline: the argv carries no credential-bearing name and the client environment is a closed mapping; kernel claim PENDING |
| fresh work directory | per-container `--tmpfs=/work:...` plus `--workdir=/work` | command construction only; kernel claim PENDING |
| bounded JSON stdin/stdout/stderr | closed stdin envelope under `max_stdin_envelope_bytes`; non-blocking reads truncated and the client killed at the output bound | offline: envelope closure and byte bound; stream truncation PENDING |
| hard wall limit | monotonic parent deadline then kill | PENDING |
| hard CPU limit | `--ulimit=cpu` (RLIMIT_CPU) plus `--cpus=1.0` | command construction only; kernel claim PENDING |
| hard memory limit | `--memory` and `--memory-swap` cgroup ceiling, `OOMKilled` read from container state | command construction only; kernel claim PENDING |
| hard process limit | `--pids-limit` cgroup | command construction only; kernel claim PENDING |
| hard file-count limit | `--ulimit=nofile` plus tmpfs `nr_inodes` | command construction only; kernel claim PENDING |
| hard file-size limit | `--ulimit=fsize` plus bounded tmpfs `size` | command construction only; kernel claim PENDING |
| content-addressed inputs and outputs | sha256 of program and every input checked before launch; the response's `result_sha256` recomputed after | offline |
| no model-chosen host path, command, image, environment variable, network target, or resource limit | closed adapter allowlist, closed argument grammar, fixed image and argv, fixed environment, `network=none` only, declared limits validated against a fixed profile | offline |

The evidence record `ExperimentSandboxEvidence` carries one boolean per control
plus `epistemic_warrant_created: False` and
`trust_effect: "untrusted_observation"`. On every refusal path all ten kernel
booleans are `False`, and the acceptance suite asserts that. They are set `True`
only in the post-launch branch, which no offline test reaches.

### 6. Bounds, derived before the fixtures

Every number below was fixed in this ADR before any fixture was written, and
`ExperimentSandboxProfile.__post_init__` refuses any profile outside them with
`profile_outside_adr_envelope`.

Ceilings: wall 120,000 ms and CPU 120,000 ms (two minutes -- an interactive
research step, not a batch job); memory 1 GiB; each of stdout/stderr/result
1 MiB; processes 4 tasks (interpreter plus its own service threads, no useful
fork); open files 64; tmpfs inodes 64; file size 8 MiB; tmpfs size 8 MiB for
each of `/tmp` and `/work`; stdin envelope 4 MiB; program 262,144 bytes (the
same bound `runner.py` already applies to a `write_program` action); at most 8
input artifacts, 1 MiB each and 4 MiB in total; at most 16 arguments.

Floors, because a container cannot honour an arbitrarily small declaration:
wall 1,000 ms and CPU 1,000 ms (a container start alone costs hundreds of
milliseconds); memory 67,108,864 bytes (the engine's own documented 6 MiB
minimum plus a CPython baseline, rounded to 64 MiB); output 1,024 bytes (one
response envelope); processes 1.

### 7. The engine boundary is injected and lives outside the campaign package

`src/math_research/campaign/` contains no process, socket, or engine code at
all -- an invariant `tests/test_campaign_provenance.py` already asserts
textually for the whole package. The sandbox therefore declares an
`ExperimentLauncher` port and the production implementation lives in
`src/math_research/experiment_oci_launcher.py`, named for what it needs.

The split is not cosmetic. The launcher is mechanism only: the sandbox builds
the complete argv and the bounds, and the launcher runs exactly what it is
given, so a substituted launcher cannot relax a control. The digest comparison
in `ExperimentRuntimeIdentity.measure` stays in the campaign package for the
same reason. `selectors` is network-capable in the repository's structural scan
and loads lazily inside the launcher's execution call, per
`tests/test_repository_invariants.py`.

A sandbox constructed without a launcher refuses with `launcher_unavailable`.
The default construction from the shipped pin has no activation, no runtime and
no launcher, so it refuses three times over.

### 8. Failures are retained, not raised away

A refusal returns a `FAILED` `ExperimentResult` whose `result` bytes are the
canonical refusal record, rather than raising out of
`SequentialCampaignRunner.run` and discarding the campaign. The refusal is
therefore recorded as a `ToolRunRecord` inside the campaign export and survives
replay. Refusal bytes are deterministic: the record contains no timestamp and
no elapsed measurement, so two identical calls produce byte-identical results.
A refusal reports `measurement_source: unavailable` with every observation
`null`, because it measured nothing and `ToolRunRecord` correctly refuses an
`unavailable` measurement that still carries an observation.

### 9. Tool output is an untrusted observation

Nothing in this slice creates an `EpistemicWarrant`, discharges a proof
obligation, approves semantic alignment, asserts source applicability, sets
novelty or significance, or admits anything to the trusted graph. A completed
sandbox run produces bytes with a content hash and a `trust_effect` of
`untrusted_observation`; only the existing exact, formal, and human-review paths
can create their respective warrants. The `cpu_milliseconds` and
`peak_memory_kib` values in the response envelope are reported by the sandboxed
process's own `getrusage` and are untrusted observations like everything else it
emits.

### 10. `make check` stays free of a container runtime

The offline probes live in `tests/test_campaign_experiment_sandbox.py` and run
under `make check` with no runtime, no image, no network, no subprocess and no
socket. The container-dependent assertions live in a single `ContainerGateTests`
class that SKIPS unless three `ADAIVY_CAMPAIGN_EXPERIMENT_OCI_*` variables are
set. `make check-campaign-experiment-oci` is a separate target named for what
it needs and is NOT in the `check` aggregate. With the shipped unresolved pin
that target FAILS loudly rather than skipping, because an unpinned digest is a
refusal.

## Consequences

Operationally, `run_program` still cannot execute, and that is now a named,
recorded, machine-readable refusal instead of a missing implementation. A
campaign that attempts an experiment gets `image_digest_unresolved` in its
ledger, which is a truthful artifact: it says the work was requested, admitted,
and then refused for want of an owner decision. ADR-0065's campaign entrypoint
depends on exactly this: it makes `run_program` fail closed with a named reason
citing this ADR.

Security: the model-influenced surface is enforced today. The kernel surface is
not. Anyone reading a green `make check` must read it as "no model-chosen host
path, command, image, environment variable, network target, or resource limit
can reach a launch", NOT as "generated code is contained". Containment is
unproven until the owner pins the digest and the probe run executes.

Reproducibility: the pin, profile, policy, envelope, bootstrap and refusal
records are canonically serialized with sorted keys and explicit schema
versions, and the profile and the admitted import set are declared in the config
and cross-checked against the module, so a drift between the documented surface
and the enforced surface fails the suite.

Licensing: nothing new is vendored. The image will be an upstream
digest-pinned distribution image; its licence inventory is recorded when the
owner pins it, following the Phase 4B `inventory` precedent. The lock schema
does not yet carry an `inventory` block; adding one at pin time is expected and
is a schema-version bump, not a silent addition, because the parser fails closed
on unknown fields.

Negative consequences, stated plainly:

- The static language check could give false comfort. It is labelled as defence
  in depth here, in the module docstring, and in the test docstrings, and it is
  not counted as a containment control in `CONTAINER_CONTROLS`.
- The offline suite proves the argv carries every control flag. It cannot prove
  the kernel honoured any of them. A flag present in a string is not a cgroup.
- `ContainerGateTests` has never executed. A skip is not a pass, and the class
  docstring says so.
- The floors mean a campaign that declares a 100 ms wall gets a refusal rather
  than a fast failure. That is deliberate: a bound the runtime cannot honour is
  not a bound.
- `--cidfile` puts one host path on the command line. It is written by the
  engine client on the host, not mounted into the container, and the acceptance
  suite asserts that it and the client binary are the only absolute paths in the
  argv.

## Blueprint deviation

Two, both stated rather than hidden.

1. The production container-engine adapter is `src/math_research/experiment_oci_launcher.py`,
   outside `src/math_research/campaign/`, whereas Phase 4B keeps its engine
   adapter inside its phase package. **Necessity:** the campaign package carries
   a stronger invariant than Phase 4B -- `tests/test_campaign_provenance.py`
   forbids the *text* `import subprocess` anywhere under
   `src/math_research/campaign/`, which makes ADR-0057's "the ordinary offline
   suite ... opens no subprocess or socket" a structural property of the package
   rather than a property of a test's mocking. Preserving that is worth one
   extra module. **Revisit trigger:** if the campaign package ever legitimately
   needs a host process for another reason, reconcile that invariant explicitly
   in an ADR rather than by deleting the check.
2. The image digest is shipped unresolved, so this ADR is accepted for the
   refusal slice only and its execution half is deferred. **Necessity:** pulling
   an image needs network access and owner authorization. **Revisit trigger:**
   the owner pins the digest, records the image inventory, and
   `make check-campaign-experiment-oci` passes; only then may the status line
   claim live execution.

## Validation and revisit trigger

This decision remains valid while all of the following hold.

- `make check` passes with no container runtime, no image, no network, no
  subprocess and no socket, and `tests/test_campaign_experiment_sandbox.py`'s
  audit-hook observer records zero `subprocess.Popen`/`socket.*` events on every
  offline path.
- Every named control in `CONTAINER_CONTROLS` carries at least one single-field
  falsifiability probe, and every probe table asserts `flipped == total` so an
  emptied table fails. The probes are:

  - 48 request-admission probes, each a one-field mutation of one
    `ExperimentRequest` fixture that must produce one named refusal reason and
    field;
  - 8 stdin-envelope probes plus separate duplicate-key, malformed-JSON,
    non-object, non-UTF-8, missing-field and byte-bound refusals;
  - 17 image-lock probes covering digest mismatch, unresolved digest, parser
    reuse, role, unknown field, duplicate key, schema version, digest-status
    vocabulary, network default, pull policy, platform, profile declaration,
    language-surface declaration, forbidden-reuse declaration, authorization
    status, unresolved-with-digest, and a missing field;
  - 7 bootstrap tamper probes, one per named in-container exit code 91-97;
  - 11 command-evidence probes, each deleting exactly one control's flag from
    the argv and requiring the coverage check to reject it, plus 4 declared-bound
    and 3 profile-bound probes that move exactly one flag; and
  - 10 profile-ceiling probes and 1 profile-floor probe.

  Two mechanisms have NO offline probe and are labelled accordingly:
  `wall_limit` and the stream-truncation half of `bounded_json_streams` are
  parent-side, are not argv-visible, and are measurable only on the container
  gate. `tests/test_campaign_experiment_sandbox.py` asserts that fact rather
  than implying coverage.
- The shipped pin stays unresolved until the owner resolves it, and
  `image_digest_unresolved`, `image_digest_mismatch`,
  `parser_image_reuse_forbidden`, `activation_not_authorized`,
  `launcher_unavailable` and `runtime_unavailable` remain refusals with no
  fallback.
- `PHASE4B_PARSER_IMAGE_DIGEST` still equals the digest in
  `config/phase4b-oci-image-linux-arm64-v1.json`, and the two runtime roles
  still differ.
- The declared `resource_profile` and `allowed_import_modules` in the config
  still equal the module's frozen profile and import set.
- No sandbox result creates a warrant, discharges an obligation, approves
  applicability, or sets novelty or significance.

Revisit this decision before: widening `ALLOWED_IMPORT_MODULES` or admitting a
third-party package into the image; allowing network or any credential in the
sandbox; admitting a second concurrent experiment worker or raising
`max_process_count`; loosening any ADR ceiling in
`ExperimentSandboxProfile`; adding a second admitted tool adapter; permitting a
host bind mount for inputs instead of the content-addressed stdin envelope;
treating a sandbox observation as anything but an untrusted proposal; or
claiming this gate has passed on the strength of a skipped
`ContainerGateTests`.
