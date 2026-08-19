# Phase 3B Formal-Checker Threat Model

Status: proposed controls; sandbox acceptance blocked

## Assets and trust boundary

Protected assets are the repository, sealed Phase 2/3A evidence, credentials,
user files, host processes, network identity, pinned toolchain, result records,
and trust projections. Submitted Lean text, imports, syntax, macros, tactics,
elaborator code, diagnostics, and generated output are hostile.

Lean elaboration supports metaprogramming. Static text scanning cannot be the
security boundary. A fragment that passes scanning must still execute in an OS
or container sandbox.

## Initial accepted input shape

The first backend may accept only:

- one exact theorem statement supplied separately from its proof fragment;
- a proof term or `by` block embedded into an AdaIvy-generated wrapper;
- an adapter-selected import set from a frozen allowlist;
- adapter-selected declaration names and namespace; and
- fixed `#print axioms` queries appended by the trusted wrapper.

An arbitrary complete Lean file, arbitrary imports, commands outside the
restricted fragment, package configuration, plugins, shared libraries, and
build scripts are rejected.

## Threats and required controls

| Threat | Control | Acceptance evidence |
|---|---|---|
| `sorry`, `admit`, or `sorryAx` hides a gap | token/syntax scan plus warning and axiom checks | placeholder fixtures rejected |
| custom axiom proves false target | parse declarations and `#print axioms`; unknown axiom is unapproved | custom-axiom fixture disclosed |
| macro/elaborator side effect | restricted wrapper plus OS sandbox | filesystem/network/process fixtures contained |
| malicious import | wrapper-owned exact import allowlist; no user imports | unknown import rejected before execution |
| unsafe/FFI/native execution | reject `unsafe`, extern/FFI, `#eval`, `run_io`, native execution and equivalents | policy fixtures rejected |
| repository or secret read/write | no repository mount; dependency/toolchain read-only; no secret environment | attempted access cannot observe or change asset |
| network exfiltration | sandbox network disabled; no proxy/DNS variables | attempted network action denied |
| child-process escape | process allowlist and process-count limit | attempted process action denied |
| resource exhaustion | wall/CPU/memory/process/file/output limits and kill group | timeout fixture classified once |
| diagnostic flood | stdout/stderr byte caps; full streams stored only as bounded artifacts plus hashes | oversized-output fixture classified once |
| stale or swapped toolchain | content hashes and read-only mount bound to invocation | manifest and invocation hashes match |
| temp-path nondeterminism | temp paths and timings retained only as noncanonical operational metadata | repeated canonical result hash matches |
| warning loss | retain exit code, structured warnings, stdout/stderr hashes and bounded bytes | warning count and hashes replay |
| automatic trust promotion | checker returns a proposal/finding; domain policy alone creates warrants | no claim/obligation mutation |

## Required execution profile

- fresh disposable run directory outside the repository;
- generated wrapper and submitted fragment are the only writable inputs;
- pinned Lean/mathlib/toolchain mounted read-only;
- no repository, home-directory, SSH, cloud, model, or package-manager secrets;
- environment allowlist limited to locale, deterministic temp/work paths, and
  explicitly pinned Lean/Lake paths;
- exact command allowlist, initially one `lake env lean <wrapper>` invocation;
- no network namespace/access;
- wall timeout and CPU limit;
- memory limit and process-count limit where enforceable;
- stdout/stderr and produced-file count/size limits;
- terminate the whole process group on timeout/cancellation;
- verify expected output file set, hashes, and symlink absence;
- remove the disposable run directory after artifacts are content-addressed.

## Local gap

`/usr/bin/sandbox-exec` exists, but this gate did not establish a complete
profile or demonstrate all limits. No container runtime is available. The
production sandbox requirement therefore fails closed. Installing a toolchain
without first resolving this boundary would not make the checker acceptable.

## Residual risks

The trusted computing base includes the Lean kernel, elaborator/toolchain
packaging, operating system/container runtime, AdaIvy wrapper generator,
diagnostic/axiom parser, and policy implementation. A kernel-checked theorem
still says nothing by itself about semantic fidelity, source applicability,
novelty, significance, or contribution.
