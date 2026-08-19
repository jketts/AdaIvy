"""Deterministic trusted Lean wrapper generation."""

from __future__ import annotations

from . import FIXED_INPUT_PATH, MAX_STDIN_BYTES, POLICY_VERSION, RUNTIME_DIGEST, RUNTIME_REFERENCE
from .records import FormalCheckRequest, GeneratedWrapper, WrapperManifest
from .serialization import canonical_hash, canonical_bytes, sha256_bytes


DOCKER_CREATE_OPTIONS = (
    "--interactive", "--network", "none", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges", "--pids-limit", "64", "--cpus", "1",
    "--memory", "1536m", "--memory-swap", "1536m", "--ulimit", "nofile=64:64",
    "--stop-timeout", "1", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
)
DOCKER_START_OPTIONS = ("start", "--attach", "--interactive")

INVOCATION = {
    "engine": "docker",
    "image": RUNTIME_REFERENCE,
    "container_entrypoint": "/checker/launcher",
    "input_transport": "stdin",
    "fixed_input_path": FIXED_INPUT_PATH,
    "stdin_max_bytes": MAX_STDIN_BYTES,
    "network": "none",
    "read_only_root": True,
    "cap_drop": "ALL",
    "no_new_privileges": True,
    "pids_limit": 64,
    "cpus": "1",
    "memory": "1536m",
    "memory_swap": "1536m",
    "nofile": "64:64",
    "tmpfs": "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
    "user": "65532:65532",
    "host_mounts": [],
    "container_arguments": [],
    "container_environment": "sealed_image_path_only",
    "docker_create_argv": ["docker", "create", "--name", "<adapter-generated>", *DOCKER_CREATE_OPTIONS, RUNTIME_REFERENCE],
    "docker_start_argv": ["docker", *DOCKER_START_OPTIONS, "<adapter-generated>"],
}
POLICY = {
    "version": POLICY_VERSION,
    "request_kind": "restricted_theorem_and_proof_fragment",
    "user_controlled_imports": False,
    "placeholders": False,
    "unsafe_ffi_native_evaluation": False,
    "side_effect_apis": False,
}


def generate_wrapper(request: FormalCheckRequest) -> GeneratedWrapper:
    lines: list[str] = [*(f"import {item}" for item in request.imports), "set_option autoImplicit false", "namespace AdaIvyPhase3B"]
    for assumption in request.assumptions:
        lines.append(f"axiom {assumption.name} : {assumption.type_expression}")
    target_line = len(lines) + 1
    lines.append(f"theorem {request.declaration_name} {request.target_statement} := {request.proof_fragment}")
    lines.append(f"#print axioms AdaIvyPhase3B.{request.declaration_name}")
    meaning_start = len(lines) + 1 if request.meaning_tests else None
    for index, test in enumerate(request.meaning_tests, start=1):
        lines.append(f"example {test.statement} := {test.proof_fragment}")
        lines.append(f"#check AdaIvyPhase3B.{request.declaration_name} -- meaning-test-{index}:{test.test_id}")
    lines.extend(("end AdaIvyPhase3B", ""))
    source = "\n".join(lines).encode("utf-8")
    if len(source) > MAX_STDIN_BYTES:
        raise ValueError(f"generated wrapper exceeds {MAX_STDIN_BYTES} bytes")
    manifest = WrapperManifest(
        source_hash=canonical_hash(request),
        target_hash=sha256_bytes(request.target_statement.encode("utf-8")),
        proof_fragment_hash=sha256_bytes(request.proof_fragment.encode("utf-8")),
        declaration_hash=sha256_bytes(
            f"theorem {request.declaration_name} {request.target_statement} := {request.proof_fragment}".encode("utf-8")
        ),
        import_manifest_hash=canonical_hash(request.imports),
        wrapper_hash=sha256_bytes(source),
        invocation_hash=canonical_hash(INVOCATION),
        policy_hash=canonical_hash(POLICY),
        runtime_hash=RUNTIME_DIGEST,
        wrapper_byte_length=len(source),
        target_line=target_line,
        meaning_test_start_line=meaning_start,
    )
    # The source bytes are deliberately the only adapter payload.
    assert manifest.wrapper_hash == sha256_bytes(source)
    assert canonical_bytes(INVOCATION)
    return GeneratedWrapper(source, manifest)
