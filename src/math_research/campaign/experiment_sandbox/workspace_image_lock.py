"""Digest-pinned OCI image lock for the ADR-0082 workspace sandbox (v2).

Unlike the v1 experiment lock, which reuses the empty-package-set Phase 4B
image, this lock declares an EXACT allowlisted package set -- ``gmpy2``,
``networkx`` and ``sympy``, each with a pinned version, a wheel SHA-256, and a
licence field per the Phase 4A dependency standard -- and explicitly forbids
``numpy`` and ``scipy`` on the candidate path.

The checked-in lock ships with all-zero placeholder digests and
``build_status: pending_operator_build``.  That is a deliberate fail-closed
state: this repository cannot build a linux/arm64 image, so the lock names
exactly what the operator must produce, and :attr:`WorkspaceImageLock.pending`
stays ``True`` until every placeholder is replaced with a real measured digest
AND the sixteen-probe v2 activation gate has produced its content-hashed
evidence.  The sandbox constructor and the activation gate both refuse a
pending lock.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .image_lock import ImageLockError, load_campaign_image_lock

WORKSPACE_LOCK_SCHEMA = "adaivy.campaign-workspace-oci-image-lock.v2"
WORKSPACE_LOCK_PATH = "config/campaign-workspace-oci-image-v2.json"
WORKSPACE_RUNTIME_ROLE = "campaign_workspace_sandbox_only"
PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
MAX_WORKSPACE_LOCK_BYTES = 65_536

#: The exact, closed package allowlist.  Anything else in the lock is a reject,
#: and these two are named forbidden because they are the obvious drift path.
ALLOWED_PACKAGE_NAMES = ("gmpy2", "networkx", "sympy")
FORBIDDEN_PACKAGE_NAMES = ("numpy", "scipy")
BUILD_STATUSES = ("pending_operator_build", "built_and_probed")
PACKAGE_DIGEST_STATUSES = ("pinned", "placeholder_pending_operator_build")

_IMAGE_REFERENCE = re.compile(
    r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[0-9a-f]{64}$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLATFORM = re.compile(r"^linux/arm64$")
_VERSION = re.compile(r"^[0-9]+(\.[0-9]+){1,3}$")

_TOP_FIELDS = frozenset({
    "schema_version", "image_reference", "oci_index_digest", "platform",
    "platform_manifest_digest", "build_status", "build", "inventory",
    "authorization",
})
_BUILD_FIELDS = frozenset({
    "base_lock", "base_image_reference", "build_instructions",
    "probe_evidence_path",
})
_PACKAGE_FIELDS = frozenset({
    "name", "version", "wheel_sha256", "license", "source_url", "digest_status",
})
_AUTHORIZATION_FIELDS = frozenset({
    "network_default", "pull_policy", "runtime_role", "status",
    "executes_untrusted_program", "credentials_admitted",
})


class WorkspaceImageLockError(ImageLockError):
    """The v2 workspace lock is absent, malformed, or inconsistent."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WorkspaceImageLockError(f"workspace lock contains a duplicate key: {key}")
        value[key] = item
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspacePackagePin:
    """One allowlisted exact package: pinned version, wheel hash, licence."""

    name: str
    version: str
    wheel_sha256: str
    license: str
    source_url: str
    digest_status: str

    @property
    def placeholder(self) -> bool:
        return (
            self.wheel_sha256 == PLACEHOLDER_DIGEST
            or self.digest_status != "pinned"
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "digest_status": self.digest_status,
            "license": self.license,
            "name": self.name,
            "source_url": self.source_url,
            "version": self.version,
            "wheel_sha256": self.wheel_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceImageLock:
    """The reviewed v2 workspace image authorization under exactly one role."""

    schema_version: str
    lock_path: str
    lock_sha256: str
    image_reference: str
    oci_index_digest: str
    platform: str
    platform_manifest_digest: str
    runtime_role: str
    pull_policy: str
    network_default: str
    status: str
    build_status: str
    base_lock: str
    base_image_reference: str
    probe_evidence_path: str
    packages: tuple[WorkspacePackagePin, ...]
    forbidden_packages: tuple[str, ...]

    @property
    def pending(self) -> bool:
        """True until the operator built the image and every digest is real."""

        return (
            self.build_status != "built_and_probed"
            or self.oci_index_digest == PLACEHOLDER_DIGEST
            or self.platform_manifest_digest == PLACEHOLDER_DIGEST
            or self.image_reference.endswith(PLACEHOLDER_DIGEST.split(":", 1)[1])
            or any(item.placeholder for item in self.packages)
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "base_image_reference": self.base_image_reference,
            "base_lock": self.base_lock,
            "build_status": self.build_status,
            "forbidden_packages": list(self.forbidden_packages),
            "image_reference": self.image_reference,
            "lock_path": self.lock_path,
            "lock_sha256": self.lock_sha256,
            "network_default": self.network_default,
            "oci_index_digest": self.oci_index_digest,
            "packages": [item.to_record() for item in self.packages],
            "pending": self.pending,
            "platform": self.platform,
            "platform_manifest_digest": self.platform_manifest_digest,
            "probe_evidence_path": self.probe_evidence_path,
            "pull_policy": self.pull_policy,
            "runtime_role": self.runtime_role,
            "schema_version": self.schema_version,
            "status": self.status,
        }


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise WorkspaceImageLockError(f"workspace lock {field} is not bounded text")
    return value


def _package(value: Any) -> WorkspacePackagePin:
    if not isinstance(value, dict) or frozenset(value) != _PACKAGE_FIELDS:
        raise WorkspaceImageLockError("workspace lock package fields differ")
    name = _bounded_text(value["name"], "package name", 64)
    if name not in ALLOWED_PACKAGE_NAMES:
        raise WorkspaceImageLockError(f"package is outside the exact allowlist: {name}")
    if name in FORBIDDEN_PACKAGE_NAMES:
        raise WorkspaceImageLockError(f"package is explicitly forbidden: {name}")
    version = _bounded_text(value["version"], "package version", 32)
    if _VERSION.fullmatch(version) is None:
        raise WorkspaceImageLockError(f"package version is not an exact pin: {name}")
    wheel = value["wheel_sha256"]
    if not isinstance(wheel, str) or _SHA256.fullmatch(wheel) is None:
        raise WorkspaceImageLockError(f"package wheel_sha256 is not canonical sha256: {name}")
    digest_status = value["digest_status"]
    if digest_status not in PACKAGE_DIGEST_STATUSES:
        raise WorkspaceImageLockError(f"package digest_status is outside the vocabulary: {name}")
    if (digest_status == "pinned") == (wheel == PLACEHOLDER_DIGEST):
        raise WorkspaceImageLockError(
            f"package digest_status disagrees with its wheel digest: {name}"
        )
    return WorkspacePackagePin(
        name=name,
        version=version,
        wheel_sha256=wheel,
        license=_bounded_text(value["license"], "package license", 128),
        source_url=_bounded_text(value["source_url"], "package source_url", 256),
        digest_status=digest_status,
    )


def load_workspace_image_lock(repository_root: Path) -> WorkspaceImageLock:
    """Load the v2 workspace lock, fail-closed on any deviation.

    Loading a pending lock succeeds -- the pending state is data the gate must
    be able to see and refuse on -- but :attr:`WorkspaceImageLock.pending` is
    computed here, from the digests themselves, never from a flag alone.
    """

    path = repository_root / WORKSPACE_LOCK_PATH
    try:
        data = path.read_bytes()
    except OSError as error:
        raise WorkspaceImageLockError(
            f"workspace lock is unreadable: {WORKSPACE_LOCK_PATH}"
        ) from error
    if not data or len(data) > MAX_WORKSPACE_LOCK_BYTES:
        raise WorkspaceImageLockError("workspace lock byte bound differs")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkspaceImageLockError("workspace lock is not valid UTF-8 JSON") from error
    if not isinstance(value, dict) or frozenset(value) != _TOP_FIELDS:
        raise WorkspaceImageLockError("workspace lock fields differ from the closed schema")
    if value["schema_version"] != WORKSPACE_LOCK_SCHEMA:
        raise WorkspaceImageLockError("workspace lock schema differs")
    reference = value["image_reference"]
    if not isinstance(reference, str) or _IMAGE_REFERENCE.fullmatch(reference) is None:
        raise WorkspaceImageLockError("workspace image reference is not an exact sha256 digest")
    for field in ("oci_index_digest", "platform_manifest_digest"):
        if not isinstance(value[field], str) or _SHA256.fullmatch(value[field]) is None:
            raise WorkspaceImageLockError(f"workspace {field} is not canonical sha256")
    if reference.rsplit("@", 1)[1] != value["oci_index_digest"]:
        raise WorkspaceImageLockError("workspace image reference and index digest disagree")
    if not isinstance(value["platform"], str) or _PLATFORM.fullmatch(value["platform"]) is None:
        raise WorkspaceImageLockError("workspace platform is outside the linux/arm64 scope")
    if value["build_status"] not in BUILD_STATUSES:
        raise WorkspaceImageLockError("workspace build_status is outside the vocabulary")

    build = value["build"]
    if not isinstance(build, dict) or frozenset(build) != _BUILD_FIELDS:
        raise WorkspaceImageLockError("workspace lock build fields differ")
    base_lock = _bounded_text(build["base_lock"], "base_lock", 256)
    base_reference = _bounded_text(build["base_image_reference"], "base_image_reference", 512)
    _bounded_text(build["build_instructions"], "build_instructions", 4_096)
    probe_evidence = _bounded_text(build["probe_evidence_path"], "probe_evidence_path", 256)
    # The declared base must be the reviewed v1 experiment lock, byte-checked.
    base = load_campaign_image_lock(repository_root)
    if base_lock != "config/campaign-experiment-oci-image-v1.json":
        raise WorkspaceImageLockError("workspace lock base_lock is not the v1 experiment lock")
    if base_reference != base.image_reference:
        raise WorkspaceImageLockError(
            "workspace lock base image differs from the reviewed v1 lock"
        )

    inventory = value["inventory"]
    if not isinstance(inventory, dict) or frozenset(inventory) != frozenset({
        "production_python_dependencies", "forbidden_packages",
    }):
        raise WorkspaceImageLockError("workspace lock inventory fields differ")
    raw_packages = inventory["production_python_dependencies"]
    if not isinstance(raw_packages, list):
        raise WorkspaceImageLockError("workspace lock package list is malformed")
    packages = tuple(_package(item) for item in raw_packages)
    if tuple(item.name for item in packages) != ALLOWED_PACKAGE_NAMES:
        raise WorkspaceImageLockError(
            "workspace lock package set differs from the exact sorted allowlist"
        )
    forbidden = inventory["forbidden_packages"]
    if forbidden != list(FORBIDDEN_PACKAGE_NAMES):
        raise WorkspaceImageLockError("workspace lock forbidden package list differs")

    authorization = value["authorization"]
    if not isinstance(authorization, dict) or frozenset(authorization) != _AUTHORIZATION_FIELDS:
        raise WorkspaceImageLockError("workspace lock authorization fields differ")
    if authorization["runtime_role"] != WORKSPACE_RUNTIME_ROLE:
        raise WorkspaceImageLockError(
            f"workspace lock runtime_role is not {WORKSPACE_RUNTIME_ROLE}"
        )
    if authorization["pull_policy"] != "never" or authorization["network_default"] != "none":
        raise WorkspaceImageLockError("workspace lock relaxed pull or network policy")
    if authorization["executes_untrusted_program"] is not True:
        raise WorkspaceImageLockError(
            "the workspace lock must declare untrusted program execution"
        )
    if authorization["credentials_admitted"] is not False:
        raise WorkspaceImageLockError("the workspace lock must admit no credential")

    lock = WorkspaceImageLock(
        schema_version=WORKSPACE_LOCK_SCHEMA,
        lock_path=WORKSPACE_LOCK_PATH,
        lock_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        image_reference=reference,
        oci_index_digest=value["oci_index_digest"],
        platform=value["platform"],
        platform_manifest_digest=value["platform_manifest_digest"],
        runtime_role=authorization["runtime_role"],
        pull_policy=authorization["pull_policy"],
        network_default=authorization["network_default"],
        status=_bounded_text(authorization["status"], "authorization status", 128),
        build_status=value["build_status"],
        base_lock=base_lock,
        base_image_reference=base_reference,
        probe_evidence_path=probe_evidence,
        packages=packages,
        forbidden_packages=tuple(FORBIDDEN_PACKAGE_NAMES),
    )
    if value["build_status"] == "built_and_probed" and lock.pending:
        raise WorkspaceImageLockError(
            "workspace lock claims built_and_probed but carries a placeholder digest"
        )
    return lock


__all__ = [
    "ALLOWED_PACKAGE_NAMES", "BUILD_STATUSES", "FORBIDDEN_PACKAGE_NAMES",
    "MAX_WORKSPACE_LOCK_BYTES", "PACKAGE_DIGEST_STATUSES", "PLACEHOLDER_DIGEST",
    "WORKSPACE_LOCK_PATH", "WORKSPACE_LOCK_SCHEMA", "WORKSPACE_RUNTIME_ROLE",
    "WorkspaceImageLock", "WorkspaceImageLockError", "WorkspacePackagePin",
    "load_workspace_image_lock",
]
