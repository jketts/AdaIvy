"""Executable and replayable activation gate for the ADR-0082 v2 sandbox.

The gate is fail-closed in two independent layers:

1. **The lock gate.**  :func:`require_activatable_workspace_lock` refuses the
   checked-in v2 lock while any digest is an all-zero placeholder or
   ``build_status`` is not ``built_and_probed``.  This repository ships in
   that pending state on purpose: no probe can run, no activation record can
   exist, and no runner can be built until the operator performs the named
   build step on a linux/arm64 Docker host.
2. **The record gate.**  :func:`verify_workspace_activation` strictly verifies
   a stored, content-hashed activation record -- closed fields, per-probe
   hashes, every probe passed, the exact non-placeholder lock hash, and the
   content hash of the bound target *schema class* definition -- before
   returning the small :class:`WorkspaceActivation` attestation the v2 runner
   requires.

Unlike ADR-0066's v1 gate, the activation binds a target schema CLASS, not one
fixture file's hash: any target admitted by
:meth:`~.target_schema.TargetSchemaClass.admit_target` is runnable under one
activation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from ..records import canonical_bytes, canonical_hash
from .target_schema import TargetSchemaClass, resolve_target_class
from .workspace_image_lock import WorkspaceImageLock, load_workspace_image_lock
from .workspace_sandbox import BOOTSTRAP_V2_SHA256

WORKSPACE_REPORT_SCHEMA = "adaivy.campaign-workspace-sandbox-gate.v2"
WORKSPACE_ACTIVATION_SCHEMA = "adaivy.campaign-workspace-sandbox-activation.v2"
MAX_WORKSPACE_ACTIVATION_BYTES = 2_097_152
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

#: The sixteen v2 probes.  The operator runs them on the built image; each one
#: must flip against a fresh container before the gate records ``activated``.
WORKSPACE_PROBE_IDS = (
    "pr.workspace-network-refused",
    "pr.workspace-write-outside-mounts-refused",
    "pr.workspace-noexec-tmpfs",
    "pr.workspace-fork-bomb-bounded",
    "pr.workspace-memory-bounded",
    "pr.workspace-cpu-bounded",
    "pr.workspace-no-ambient-secret",
    "pr.workspace-stdout-truncation-recorded",
    "pr.workspace-program-measurement-refused",
    "pr.workspace-nondeterministic-program-refused",
    "pr.workspace-image-digest-pinned",
    "pr.workspace-package-set-exact",
    "pr.workspace-manifest-ledgered",
    "pr.workspace-verifier-not-in-container",
    "pr.workspace-output-creates-no-warrant",
    "pr.workspace-absent-runtime-is-a-blocker",
)

_REPORT_FIELDS = frozenset({
    "bootstrap_hash", "content_hash", "determinism_replica_policy",
    "environment_hash", "policy_hash", "probes", "probes_blocked",
    "probes_flipped", "probes_total", "schema_version", "status",
    "target_class_definition_hash", "target_schema_class_id",
    "workspace_lock_sha256",
})


class WorkspaceActivationError(ValueError):
    """The v2 workspace sandbox cannot be activated as requested."""


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceActivation:
    """The release condition the v2 workspace runner refuses to run without."""

    schema_version: str
    status: str
    environment_hash: str
    policy_hash: str
    bootstrap_hash: str
    workspace_lock_sha256: str
    target_schema_class_id: str
    target_class_definition_hash: str
    probes_total: int
    probes_flipped: int
    probes_blocked: int
    content_hash: str
    epistemic_warrant_created: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_ACTIVATION_SCHEMA:
            raise ValueError("workspace activation schema differs")
        if self.status not in ("activated", "blocked"):
            raise ValueError("workspace activation status is outside the vocabulary")
        if self.epistemic_warrant_created is not False:
            raise ValueError("a workspace activation may never create warrant")
        if any(
            not isinstance(item, int) or isinstance(item, bool)
            for item in (self.probes_total, self.probes_flipped, self.probes_blocked)
        ):
            raise ValueError("workspace probe counts must be integers")
        if self.probes_total < 1 or self.probes_flipped < 0 or self.probes_blocked < 0:
            raise ValueError("workspace probe counts are invalid")
        if self.probes_flipped + self.probes_blocked > self.probes_total:
            raise ValueError("workspace probe counts do not close")
        if self.status == "activated" and (
            self.probes_flipped != self.probes_total or self.probes_blocked != 0
        ):
            raise ValueError("activation requires every probe flipped")
        for name in (
            "environment_hash", "policy_hash", "bootstrap_hash",
            "workspace_lock_sha256", "target_class_definition_hash",
            "content_hash",
        ):
            if not isinstance(getattr(self, name), str) or _SHA256.fullmatch(
                getattr(self, name)
            ) is None:
                raise ValueError(f"workspace activation {name} is malformed")

    @property
    def activated(self) -> bool:
        return self.status == "activated" and self.probes_flipped == self.probes_total

    def to_record(self) -> dict[str, Any]:
        return {
            name: getattr(self, name) for name in sorted(self.__dataclass_fields__)
        }


def require_activatable_workspace_lock(repository_root: Path) -> WorkspaceImageLock:
    """The first gate: refuse any pending v2 lock before anything executes.

    A placeholder digest, a placeholder wheel hash, or a build_status other
    than ``built_and_probed`` all keep the lock pending, and pending means
    nothing runs.  This is the named refusal the offline suite demonstrates.
    """

    lock = load_workspace_image_lock(repository_root)
    if lock.pending:
        raise WorkspaceActivationError(
            "workspace_image_lock_pending_operator_build: the v2 lock carries "
            "placeholder digests or an unbuilt status; build and probe the "
            "image on a linux/arm64 Docker host, record the real digests, "
            "then re-run the gate"
        )
    try:
        root = repository_root.resolve(strict=True)
        evidence = repository_root / lock.probe_evidence_path
        resolved_evidence = evidence.resolve(strict=True)
        if not resolved_evidence.is_relative_to(root) or evidence.is_symlink():
            raise WorkspaceActivationError(
                "workspace_probe_evidence_path_invalid: activation evidence "
                "must be a regular file inside the repository"
            )
        data = evidence.read_bytes()
    except WorkspaceActivationError:
        raise
    except OSError as error:
        raise WorkspaceActivationError(
            "workspace_probe_evidence_absent: the lock claims built_and_probed "
            f"but {lock.probe_evidence_path} does not exist"
        ) from error
    try:
        _report, activation = load_workspace_activation(data)
    except (TypeError, ValueError) as error:
        raise WorkspaceActivationError(
            "workspace_probe_evidence_invalid: the named activation evidence "
            "does not pass the closed record gate"
        ) from error
    if activation.workspace_lock_sha256 != lock.lock_sha256:
        raise WorkspaceActivationError(
            "workspace_probe_evidence_lock_mismatch: activation evidence was "
            "produced for a different workspace image lock"
        )
    return lock


def build_workspace_activation_report(
    *, lock: WorkspaceImageLock, environment_hash: str, policy_hash: str,
    target_class: TargetSchemaClass, determinism_replica_policy: dict[str, Any],
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble and content-hash the gate report from executed probe summaries.

    The probe execution itself is the operator step on the Docker host; this
    function only closes the record shape so the report the operator stores is
    the exact shape :func:`verify_workspace_activation` demands.
    """

    _reject_floats((environment_hash, policy_hash, determinism_replica_policy, probes))
    if lock.pending:
        raise WorkspaceActivationError(
            "workspace_image_lock_pending_operator_build"
        )
    if tuple(item.get("probe_id") for item in probes) != WORKSPACE_PROBE_IDS:
        raise WorkspaceActivationError("workspace probe inventory differs")
    passed = sum(item.get("passed") is True for item in probes)
    report: dict[str, Any] = {
        "bootstrap_hash": BOOTSTRAP_V2_SHA256,
        "determinism_replica_policy": dict(determinism_replica_policy),
        "environment_hash": environment_hash,
        "policy_hash": policy_hash,
        "probes": probes,
        "probes_blocked": len(probes) - passed,
        "probes_flipped": passed,
        "probes_total": len(probes),
        "schema_version": WORKSPACE_REPORT_SCHEMA,
        "status": "activated" if passed == len(probes) else "blocked",
        "target_class_definition_hash": target_class.definition_hash,
        "target_schema_class_id": target_class.class_id,
        "workspace_lock_sha256": lock.lock_sha256,
    }
    report["content_hash"] = canonical_hash(report)
    return report


def verify_workspace_activation(value: object) -> WorkspaceActivation:
    """Strictly verify a raw v2 gate record and return its small attestation."""

    _reject_floats(value)
    if not isinstance(value, dict) or set(value) != _REPORT_FIELDS:
        raise ValueError("workspace activation fields differ")
    if value["schema_version"] != WORKSPACE_REPORT_SCHEMA:
        raise ValueError("workspace activation report schema differs")
    if value["content_hash"] != canonical_hash({
        key: item for key, item in value.items() if key != "content_hash"
    }):
        raise ValueError("workspace activation content hash differs")
    if value["bootstrap_hash"] != BOOTSTRAP_V2_SHA256:
        raise ValueError("workspace activation bootstrap differs from the pinned v2 text")
    # The bound schema class must be registered and its recorded definition
    # hash must be the hash of the definition as it exists in this repository.
    if not isinstance(value["target_schema_class_id"], str):
        raise ValueError("workspace activation target class id is malformed")
    target_class = resolve_target_class(value["target_schema_class_id"])
    if value["target_class_definition_hash"] != target_class.definition_hash:
        raise ValueError("workspace activation target class definition differs")
    policy = value["determinism_replica_policy"]
    if (
        not isinstance(policy, dict)
        or set(policy) != {"minimum", "maximum", "single_replica_meaning"}
        or policy["minimum"] != 1
        or policy["maximum"] != 4
        or policy["single_replica_meaning"] != "determinism_unverified_recorded"
    ):
        raise ValueError("workspace activation determinism policy differs")
    probes = value["probes"]
    if (
        not isinstance(probes, list)
        or tuple(
            item.get("probe_id") for item in probes if isinstance(item, dict)
        ) != WORKSPACE_PROBE_IDS
    ):
        raise ValueError("workspace activation probe inventory differs")
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) != {
            "content_hash", "observation", "passed", "probe_id",
        }:
            raise ValueError("workspace activation probe fields differ")
        if probe["content_hash"] != canonical_hash({
            key: item for key, item in probe.items() if key != "content_hash"
        }):
            raise ValueError("workspace activation probe hash differs")
        if probe["passed"] is not True:
            raise ValueError("workspace activation contains an unflipped probe")
    by_id = {item["probe_id"]: item["observation"] for item in probes}
    nondeterminism = by_id["pr.workspace-nondeterministic-program-refused"]
    if (
        not isinstance(nondeterminism, dict)
        or nondeterminism.get("replica_count", 0) < 2
        or nondeterminism.get("refusal_code") != "nondeterministic_result"
    ):
        raise ValueError("nondeterminism probe lacks a multi-replica divergence")
    manifest = by_id["pr.workspace-manifest-ledgered"]
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("first_manifest_hash"), str)
        or not isinstance(manifest.get("second_manifest_hash"), str)
        or manifest.get("second_run_read_first_output") is not True
        or manifest["first_manifest_hash"] == manifest["second_manifest_hash"]
    ):
        raise ValueError("workspace manifest probe lacks its cross-run evidence")
    packages = by_id["pr.workspace-package-set-exact"]
    if (
        not isinstance(packages, dict)
        or packages.get("allowlist_importable") is not True
        or packages.get("numpy_refused") is not True
        or packages.get("scipy_refused") is not True
    ):
        raise ValueError("package probe lacks exact allowlist evidence")
    for name in (
        "environment_hash", "policy_hash", "workspace_lock_sha256",
        "target_class_definition_hash",
    ):
        if not isinstance(value[name], str) or _SHA256.fullmatch(value[name]) is None:
            raise ValueError(f"workspace activation {name} is malformed")
    passed = sum(item["passed"] is True for item in probes)
    blocked = len(probes) - passed
    if (
        value["probes_total"] != len(WORKSPACE_PROBE_IDS)
        or value["probes_flipped"] != passed
        or value["probes_blocked"] != blocked
        or value["status"] != ("activated" if blocked == 0 else "blocked")
    ):
        raise ValueError("workspace activation summary differs")
    return WorkspaceActivation(
        schema_version=WORKSPACE_ACTIVATION_SCHEMA,
        status=value["status"],
        environment_hash=value["environment_hash"],
        policy_hash=value["policy_hash"],
        bootstrap_hash=value["bootstrap_hash"],
        workspace_lock_sha256=value["workspace_lock_sha256"],
        target_schema_class_id=value["target_schema_class_id"],
        target_class_definition_hash=value["target_class_definition_hash"],
        probes_total=value["probes_total"],
        probes_flipped=value["probes_flipped"],
        probes_blocked=value["probes_blocked"],
        content_hash=value["content_hash"],
    )


def _reject_floats(value: object) -> None:
    """Reject JSON floats recursively before any activation claim is checked."""

    if isinstance(value, float):
        raise ValueError("workspace activation contains a float")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(key)
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def load_workspace_activation(data: bytes) -> tuple[dict[str, Any], WorkspaceActivation]:
    if not isinstance(data, bytes) or not data or len(data) > MAX_WORKSPACE_ACTIVATION_BYTES:
        raise ValueError("workspace activation byte bound differs")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError("workspace activation contains a duplicate key")
            result[key] = item
        return result

    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("workspace activation JSON is invalid") from error
    if canonical_bytes(value) != data:
        raise ValueError("workspace activation is not canonical")
    return value, verify_workspace_activation(value)


__all__ = [
    "MAX_WORKSPACE_ACTIVATION_BYTES", "WORKSPACE_ACTIVATION_SCHEMA",
    "WORKSPACE_PROBE_IDS", "WORKSPACE_REPORT_SCHEMA", "WorkspaceActivation",
    "WorkspaceActivationError", "build_workspace_activation_report",
    "load_workspace_activation", "require_activatable_workspace_lock",
    "verify_workspace_activation",
]
