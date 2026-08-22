# ADR-0066: Campaign experiment sandbox for model-generated exact computation

- **Status:** accepted and implemented for the bounded exact-graph campaign
  experiment on 22 August 2026. This is the gate ADR-0057 fail-closes on and
  ADR-0065 names as the critical path: the slice after which AdaIvy can execute
  one admitted Python program it wrote and attribute the resulting computation
  to itself.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 2 C7 (reproducibility: code and dependency
  version, input content hashes, parameters, runtime image identity, stdout,
  stderr, exit status); Section 15 (`:1801` prompt injection, `:1817-1818` treat
  retrieved content as untrusted data); ADR-0057 (campaign provenance);
  ADR-0018 and ADR-0028 (the Phase 4B digest-pinned OCI gate this reuses);
  ADR-0016 (bounded stdin runtime precedent); ADR-0065 (the entrypoint)
- **Decision owners:** repository owner and researcher

## Context

ADR-0065 makes the campaign loop reachable with its experiment runner
fail-closed, so a campaign can propose a program and not run it. That is the
single reason material mathematics cannot cross an AdaIvy boundary: the loop can
derive a route and record a program, then must stop.

The isolation machinery already exists and is demonstrated. Phase 4B's
digest-pinned OCI parser gate reproduces twelve parser fixtures with zero false
admissions and its activation probes demonstrate kernel-enforced memory, CPU,
process, file, network-none, read-only-root, noexec-temp, and ambient-secret
controls. `oci_parser_sandbox.py:497-519` is the invocation: `--network=none`,
`--read-only`, `--memory`/`--memory-swap`, `--pids-limit`, `nofile`/`fsize`/`cpu`
ulimits, `--cpus=1.0`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges=true`, `--user=65534:65534`, a
`rw,noexec,nosuid,nodev` tmpfs, and `--pull=never` against a digest-pinned
image carrying Python 3.14.7 with `production_python_dependencies: []`.

**The threat model is nonetheless different, and this is the whole reason this
needs its own ADR rather than a flag on the parser gate.** The parser gate runs
*our* pinned code on untrusted input. This sandbox runs *untrusted code*. The
program is written by a model that may have read retrieved documents, so a
prompt injection upstream becomes an adversarial program here — the threat
`:1801` names, arriving as executable rather than as text.

One consequence governs the design. A sandbox bounds what a program can *do*; it
cannot make what a program *says* true. A program that prints "I found a
counterexample" has produced a string, and no amount of kernel isolation makes
that string a result.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Keep it fail-closed | ADR-0057 status quo | zero risk | AdaIvy can never compute; every target ends at the same blocker; the system stays a bookkeeping layer | Rejected |
| `subprocess` with `resource` rlimits | stdlib only, no image | cheap; no container runtime needed | no network namespace, so `--network=none` is unavailable and exfiltration is possible; no filesystem isolation; rlimits are per-process and a fork evades several; the host's environment and secrets are inherited | Rejected: not an isolation boundary at all |
| Reuse the Phase 4B parser sandbox directly | it exists and is proven | no new gate | its authorization record is role-scoped `phase4b_parser_sandbox_only`, and silently widening a role is exactly how an authorization stops meaning anything; also its entrypoint runs our worker, not an arbitrary program | Rejected as written; reused with its own role below |
| Own digest-pinned OCI sandbox, same image, distinct role, program on bounded stdin, output treated as an untrusted candidate re-derived by an in-repo exact verifier | ADR-0018/0028 controls; ADR-0016 bounded-stdin precedent; ADR-0035's self-verifying-certificate containment | the loop computes; the result is trustworthy for a *mathematical* reason rather than a procedural one | a container runtime becomes a prerequisite for the research path, so the offline suite must stay meaningful without it | **Selected** |

## Decision

Add a digest-pinned OCI experiment sandbox and wire it as ADR-0065's
`CampaignExperimentRunner`. Reuse the Phase 4B image digest and control set;
authorize it under its **own** role.

### Trust framing, which is the load-bearing part

**A sandboxed program's output is an untrusted candidate, exactly like a
retrieved document.** It gets no warrant, no premise status, and no graph
admission. What makes a campaign result trustworthy is that the candidate is
re-derived by an isolated in-repository exact verifier which reads the candidate
alone — not the program, not its stdout, not the planner's description of it.

This is the ADR-0035 containment argument transplanted: a zero-gap certificate is
self-verifying against its ensemble, so a wrong certificate fails the exact check
rather than passing quietly. Here, a candidate graph is self-verifying against
the frozen target: the verifier rebuilds it from its edge list and recomputes the
property exactly. A malicious or simply buggy program cannot manufacture a false
result, because it does not get to do the checking. **The sandbox contains what
the program can do; the verifier is what makes its output mean anything.**

### Authorization

A new `config/campaign-experiment-oci-image-v1.json` lock, same
`image_reference` digest and `platform_manifest_digest` as Phase 4B, with
`runtime_role: campaign_experiment_sandbox_only` and its own `authorization`
block. Sharing a digest across two roles is a deliberate, recorded reuse; the
Phase 4B lock is not edited and its role is not widened.

Activation reuses the Phase 4B probe suite and adds probes for the risks specific
to untrusted code. Every probe must pass before the runner will execute anything,
and the activation record is content-hashed.

### Invocation

The Phase 4B flag set, plus:

- **The program arrives on bounded stdin**, following ADR-0016 rather than a
  writable mount, so there is no path by which a program can be modified between
  hashing and execution. Its `program_artifact_hash` is computed over the exact
  bytes written to stdin.
- **`--env=PYTHONHASHSEED=0`** and no other host-derived environment. Untrusted
  code that iterates a set must not produce run-dependent output, or the
  campaign export stops being replayable.
- **Input artifacts are read-only** and content-hashed; the program receives
  their hashes and their bytes, and can reach nothing else.
- **stdout, stderr, and the result artifact are each independently bounded.** An
  unbounded print is a resource attack; truncation is recorded as truncation and
  never as a complete result.
- **Resource measurement comes from outside the program, never the program.**
  The current adapter records host-observed wall time and output byte counts.
  It deliberately records CPU and peak-memory observations as unavailable:
  Docker Desktop does not expose trustworthy per-run values to this host-side
  adapter, while an in-container value is program-influenceable. A
  program-asserted measurement is refused rather than recorded.
- **No clock, no network, no randomness on the trust path.** Wall time is
  measured outside the container. A program that needs entropy to produce its
  result is producing a result that cannot be replayed, and the campaign refuses
  it rather than seeding it.

### Named boundaries

- **The verifier never runs in the sandbox.** It runs in-repository, in the host
  process, over exact integers and `Fraction`, and holds no reference to the
  planner or the program. If it ran in the sandbox, an adversarial program could
  influence its own verification.
- **A non-zero exit is a recorded outcome, not a retry.** No model may iterate on
  a sandbox error, for the same reason ADR-0040 forbids feeding a validator
  diagnostic back to a proposer: it teaches evasion rather than correctness.
- **Determinism is a gate, not an aspiration.** The same program and inputs must
  produce a byte-identical result artifact across repeated runs and a fresh
  container. A program whose output varies is rejected as unusable, not averaged.
- **The offline suite stays meaningful without a container runtime.** `make check`
  exercises the scripted runner and the refusal paths; the sandbox itself is a
  separate named target, as `check-sealed` already is. An absent runtime is a
  recorded blocker and never a skip that reads as a pass.
- **No credential ever enters the sandbox.** Not the provider keys, not the
  Phase 4A workspace, not the acquisition store. The ambient-secret probe is a
  release condition.
- **Exact arithmetic still binds inside the sandbox.** The image carries no
  third-party package, so there is no numerical solver to reach for. A program
  that produces a float on the trust path is refused by the verifier, which is
  where the rule was always enforced.

## What this decision does not license

It does not grant warrant: `epistemic_warrant_created` stays `False`
unconditionally, and only the existing Phase 3B kernel-checked path reaches
`Theorem`. It does not enable search tiers 2-4, parallel or evolutionary
specialists, or any autonomous scheduling. It does not let a program acquire,
retrieve, embed, or call a model. It does not assess novelty or significance. It
does not make a campaign's output publishable — that still needs the ADR-0055
announcement re-check and the ADR-0036 projection. And it does not make a
program's claim about its own output true, ever.

## Consequences

- A container runtime becomes a prerequisite for the research path, which is a
  real narrowing of where AdaIvy can do work. Named honestly: `make check` stays
  runtime-free, and the research capability does not.
- The first genuinely AdaIvy-attributed computation becomes possible. So does the
  first genuinely AdaIvy-attributed *wrong* computation, which is why the
  verifier is separate and why the candidate is re-derived rather than trusted.
- Sandbox execution is reviewable in host-observed wall-clock and bytes; every
  run closes into the campaign export with its image digest, program hash,
  input hashes, limits, available host observations, and exit status. CPU and
  peak memory remain null rather than being guessed from program-controlled
  reports.

## Blueprint deviation

None. This implements C7's reproducibility record and keeps `:1817-1818`'s
untrusted-data posture by treating program output as data rather than as
finding. It relaxes no ADR-0057 bound other than the one it exists to open, and
opens that one behind its own activation gate.

## Falsifiability probes

`probes_flipped == probes_total` gates the slice.

- `pr.sandbox-network-refused` — a program opening a socket must fail with the
  network unavailable, not succeed.
- `pr.sandbox-write-outside-tmpfs-refused` — a write to any path outside the
  bounded tmpfs and creation beyond its fixed inode count must both fail.
- `pr.sandbox-noexec-tmpfs` — a binary dropped in the tmpfs must not execute.
- `pr.sandbox-fork-bomb-bounded` — exceeding `--pids-limit` must terminate the
  run, not the host.
- `pr.sandbox-memory-bounded` — an allocation above `--memory` must be killed.
- `pr.sandbox-cpu-bounded` — a spin loop must be terminated by the CPU ulimit.
- `pr.sandbox-no-ambient-secret` — no host environment variable, and specifically
  no provider credential, may be readable inside.
- `pr.sandbox-stdout-truncation-recorded` — an unbounded print must be recorded
  as truncated and must not read as a complete result.
- `pr.sandbox-program-measurement-refused` — a program-asserted CPU or memory
  measurement must be refused, not recorded.
- `pr.sandbox-nondeterministic-program-refused` — a program whose result differs
  across two runs must be refused rather than averaged or retried.
- `pr.sandbox-image-digest-pinned` — a mismatched image digest must refuse, and
  `--pull=never` must hold.
- `pr.sandbox-role-not-widened` — the Phase 4B lock's role must still read
  `phase4b_parser_sandbox_only`, asserted so reuse cannot become widening.
- `pr.sandbox-verifier-not-in-container` — the verifier must be structurally
  unable to run inside the sandbox.
- `pr.sandbox-output-creates-no-warrant` — no sandbox result may set
  `epistemic_warrant_created`, assert applicability, or admit to the graph.
- `pr.sandbox-lying-program-caught` — a program that prints a false claim while
  emitting a candidate that fails the exact check must produce a refutation of
  its own claim. **This is the probe that tests the actual security argument.**
- `pr.sandbox-absent-runtime-is-a-blocker` — with no container runtime, the run
  must record a blocker and must not report success.

## Validation and revisit trigger

The recorded activation is
`reports/campaign-experiment-sandbox/v1/activation.json`, content hash
`sha256:9b5b46afa7a2d0d6bb34507fb588bf9b35e62293c5d613da09dfdd6610d5a32c`.
Two independent executions against the exact locally installed Linux/arm64
image produced byte-identical records with all sixteen probes flipped. The
ordinary offline suite verifies admission, exact verification, replay,
tamper-refusal, deterministic failure records, and the no-runtime path without
launching a process. `make check-campaign-experiment-oci` is the separate live
kernel gate and fails rather than skips when the runtime or pinned image is
absent.

Valid while: the image stays digest-pinned with `--pull=never`; every control
probe passes; the verifier stays outside the container and holds no planner
reference; program output stays an untrusted candidate; no credential enters; and
determinism is enforced rather than assumed.

Reconsider if a legitimate research program ever genuinely needs entropy or wall
time — that is a real tension with replayability and deserves its own decision
rather than a seeded workaround.

Revisit with a new ADR before: allowing network from a sandbox for any reason;
mounting anything writable; running the verifier inside; permitting a
third-party package in the image; letting a model iterate on a sandbox error; or
raising a limit without moving the activation record.

## Explicit deferrals

- Parallel sandbox execution: one run at a time, so a resource-exhaustion
  interaction between concurrent runs cannot exist yet.
- Non-Python programs, and any compiled toolchain.
- Sandboxes on a non-Linux host: the controls are kernel-enforced and this is
  `linux/arm64` only, matching the Phase 4B lock.
