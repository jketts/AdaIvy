# ADR-0082: Exact scientific workspace sandbox (campaign sandbox v2)

- **Status:** accepted. Machinery, locks, and gates are implemented and
  offline-tested; the v2 image itself is **pending the named operator build
  step** on a linux/arm64 Docker host, and every gate in this ADR refuses
  until that step is complete. Supersedes three specific clauses of ADR-0066
  (named below); everything else in ADR-0066 stands, and the v1 instrument is
  unchanged and remains activated.
- **Date:** 2026-08-22
- **Plan:** `docs/CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md` Slice 15
- **Blueprint requirement:** Section 2 C7 (reproducibility), Section 15
  (`:1801` prompt injection, untrusted retrieved content); ADR-0017/Phase 4A
  (dependency standard: pinned version, artifact hash, licence); ADR-0018 and
  ADR-0028 (digest-pinned OCI controls); ADR-0066 (the v1 sandbox this
  widens); ADR-0073 (verifier router wiring)
- **Decision owners:** repository owner and researcher

## What this supersedes in ADR-0066

1. **The empty-package-set clause.** ADR-0066 reuses the Phase 4B image with
   `production_python_dependencies: []`. The v2 *workspace* image lock
   (`config/campaign-workspace-oci-image-v2.json`) declares an exact,
   allowlisted package set — `gmpy2`, `networkx`, `sympy` — each with a pinned
   version, a wheel SHA-256 field, and a licence field per the Phase 4A
   dependency standard. `numpy` and `scipy` are named forbidden: no
   floating-point solver enters the candidate path. The v1 lock is untouched
   and still authorizes only the empty-package image under its own role.
2. **The single-target clause.** ADR-0066's activation bound execution to one
   fixture target file's hash. The v2 activation binds a target *schema
   class* (`experiment_sandbox/target_schema.py`): the content hash of a
   closed class definition (schema version, exact engine, complete field
   inventory) enters the activation record, and any target validating exactly
   against the bound class is runnable. The exact-graph 12-field schema is
   the first registered class; new classes follow the four-step registration
   path documented at `campaign/verifier_router.py::TARGET_CLASS_ROUTES`.
3. **The one-shot clause, at the sandbox layer.** The v2 sandbox supports
   repeated `run` calls over one persistent campaign workspace and reports
   program failures as structured, content-hashed data
   (`adaivy.campaign-workspace-failure-diagnostics.v1`: exit status, bounded
   stderr, workspace manifest delta) rather than as terminal refusals. The
   corresponding change to campaign-loop RUNNER semantics (retry/iterate
   policy in `campaign/runner.py`) is owned by Slice 11 and is **not** made
   here.

## Decision

Add a v2 **workspace** sandbox capability alongside — never replacing — the
v1 instrument:

### Image lock v2, fail closed until built

`config/campaign-workspace-oci-image-v2.json` ships with all-zero placeholder
digests, placeholder wheel hashes, and `build_status:
pending_operator_build`. `WorkspaceImageLock.pending` is computed from the
digests themselves, never from the flag alone, and three layers refuse a
pending lock: the loader (a `built_and_probed` claim with any placeholder is a
hard reject), the `WorkspaceSandbox` constructor, and
`require_activatable_workspace_lock`, which additionally demands the stored
probe evidence at the lock's `probe_evidence_path`, parses it through the
closed canonical activation-record gate, and checks that it names the current
lock hash. Mere file presence is not activation evidence. Nothing in this
repository can execute against the v2 image until the operator completes the
build step below.

### Bootstrap v2

The v2 image's site-packages must be importable, so the interpreter runs
`python3 -I -c` — **without `-S`** — for this image only. The v2 bootstrap
text differs from v1 (v2 protocol identifiers; the program additionally
receives `ADAIVY_WORKSPACE`) and carries its own recorded hash
(`BOOTSTRAP_V2_SHA256`), bound into the v2 activation. `--network=none`,
`--pull=never`, `--read-only`, `--cap-drop=ALL`, no credentials, and the full
v1 kernel-control flag set are unchanged.

### Persistent campaign workspace

One campaign-scoped writable directory is bind-mounted at `/workspace` and
persists across `run` calls within a campaign. At **every** run boundary the
workspace file inventory (relative paths, sizes, SHA-256) is hashed into a
manifest (`adaivy.campaign-workspace-manifest.v1`) and recorded in the
run record — before-hash, after-hash, and delta. Workspace byte and inode
ceilings are structural (1 GiB / 65 536 hard; per-run requests below).
Symlinks and non-regular files in the workspace are refusals, not entries.
Determinism replicas each run over a fresh copy of the pre-run state; the
persistent workspace is promoted to the replica post-state only when the
execution was not refused (a `program_failed` run *is* promoted: its partial
writes are data the next iteration may build on; a nondeterministic or
sandbox-refused run is not, so it cannot corrupt campaign state). **The
workspace is provenance, never trust**: nothing in it is believed, and every
claim is still re-derived by the host-side exact verifier, which is unchanged
and still refuses floats.

### Operator-budgeted long computation

Hard structural ceilings rise to 3 600 s CPU / 4 500 s wall / 8 GiB memory /
1 GiB tmpfs and workspace. Per-run requests remain configurable strictly
below the ceilings and are never rounded up (`limits_from_request_v2`).

### Configurable determinism replicas, 1–4

The replica count is recorded in every run record. Two to four replicas run
the byte-identical gate over result, stdout, stderr, exit, **and** the
post-run workspace manifest. One replica means the gate did not run: the
execution carries `determinism_unverified: true` in its semantic record,
adapter configuration, explicit `ExperimentResult`, planner/report context,
verification request, and verifier result. Verifiers and reports **must
surface** that flag.
A determinism-unverified result is never silently equal to a verified one.

### Trust framing, unchanged

A sandboxed program's output — including everything it writes into the
workspace — is an untrusted candidate. No warrant, no premise, no graph
admission, no novelty or significance. The verifiers run host-side, outside
every container, over `int` and `fractions.Fraction` only.

## Named operator step to activate v2 (linux/arm64 Docker host)

1. Download the three pinned wheels named in the lock, verify each SHA-256,
   and replace the placeholder `wheel_sha256` values (set `digest_status:
   pinned`).
2. Build the image FROM the digest-pinned v1 base with
   `pip install --no-index --no-deps` of the verified wheels only; record
   `image_reference`, `oci_index_digest`, `platform_manifest_digest` from the
   built artifact into the lock.
3. Run the sixteen-probe v2 gate (`WORKSPACE_PROBE_IDS`) against fresh
   containers, including the exact-package probe (allowlist importable,
   numpy/scipy refused) and the cross-run workspace-manifest probe; store the
   content-hashed report at `reports/campaign-workspace-sandbox/v2/activation.json`.
4. Set `build_status: built_and_probed`. Only then does
   `require_activatable_workspace_lock` pass and
   `verify_workspace_activation` yield the attestation the v2 runner demands.

## Consequences

- The offline suite (`make check`) stays green with no container runtime: all
  v2 tests inject fake executors and fake locks, and the checked-in pending
  lock is itself the fixture for the refusal tests.
- Two sandboxes, two locks, two bootstraps, two activation schemas. Sharing
  code between them was deliberately limited to the response-outcome types;
  the v1 hashes and records are byte-identical to before this ADR.
- A future problem family costs: one host-side exact verifier, one registered
  schema class, one router route, one re-run of the activation gate.
