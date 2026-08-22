"""Digest-pinned OCI image locks for the ADR-0066 campaign experiment sandbox.

Two locks describe the *same image bytes* under *different roles*.
``config/phase4b-oci-image-linux-arm64-v1.json`` authorizes the Phase 4B parser
gate and stays at ``phase4b_parser_sandbox_only``;
``config/campaign-experiment-oci-image-v1.json`` authorizes this sandbox at
``campaign_experiment_sandbox_only``.  Sharing a digest across two roles is a
recorded reuse, so this module refuses to load either lock unless the digests
agree *and* the roles differ: a lock whose role drifted, and a Phase 4B lock
that was widened to cover untrusted code, are both hard failures.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

CAMPAIGN_LOCK_SCHEMA = "adaivy.campaign-experiment-oci-image-lock.v1"
PHASE4B_LOCK_SCHEMA = "adaivy.phase4b-oci-image-lock.v1"
CAMPAIGN_RUNTIME_ROLE = "campaign_experiment_sandbox_only"
PHASE4B_RUNTIME_ROLE = "phase4b_parser_sandbox_only"
CAMPAIGN_LOCK_PATH = "config/campaign-experiment-oci-image-v1.json"
PHASE4B_LOCK_PATH = "config/phase4b-oci-image-linux-arm64-v1.json"
MAX_LOCK_BYTES = 65_536

_IMAGE_REFERENCE = re.compile(
    r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[0-9a-f]{64}$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLATFORM = re.compile(r"^linux/arm64$")
_TOP_FIELDS = {
    CAMPAIGN_LOCK_SCHEMA: frozenset({
        "schema_version", "image_reference", "oci_index_digest", "platform",
        "platform_manifest_digest", "upstream", "offline_archive", "inventory",
        "digest_reuse", "authorization",
    }),
    PHASE4B_LOCK_SCHEMA: frozenset({
        "schema_version", "image_reference", "oci_index_digest", "platform",
        "platform_manifest_digest", "upstream", "offline_archive", "inventory",
        "authorization",
    }),
}
_AUTHORIZATION_FIELDS = {
    CAMPAIGN_LOCK_SCHEMA: frozenset({
        "network_default", "pull_policy", "runtime_role", "status",
        "executes_untrusted_program", "credentials_admitted",
    }),
    PHASE4B_LOCK_SCHEMA: frozenset({
        "network_default", "pull_policy", "runtime_role", "status",
    }),
}
_EXPECTED_ROLE = {
    CAMPAIGN_LOCK_SCHEMA: CAMPAIGN_RUNTIME_ROLE,
    PHASE4B_LOCK_SCHEMA: PHASE4B_RUNTIME_ROLE,
}


class ImageLockError(ValueError):
    """A digest-pinned image lock is absent, malformed, or role-inconsistent."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ImageLockError(f"image lock contains a duplicate key: {key}")
        value[key] = item
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class OciImageLock:
    """One reviewed, digest-pinned image authorization under exactly one role."""

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
    production_python_dependencies: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "image_reference": self.image_reference,
            "lock_path": self.lock_path,
            "lock_sha256": self.lock_sha256,
            "network_default": self.network_default,
            "oci_index_digest": self.oci_index_digest,
            "platform": self.platform,
            "platform_manifest_digest": self.platform_manifest_digest,
            "production_python_dependencies": list(self.production_python_dependencies),
            "pull_policy": self.pull_policy,
            "runtime_role": self.runtime_role,
            "schema_version": self.schema_version,
            "status": self.status,
        }


def _load(path: Path, relative: str, schema: str) -> OciImageLock:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImageLockError(f"image lock is unreadable: {relative}") from error
    if not data or len(data) > MAX_LOCK_BYTES:
        raise ImageLockError(f"image lock byte bound differs: {relative}")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImageLockError(f"image lock is not valid UTF-8 JSON: {relative}") from error
    if not isinstance(value, dict) or frozenset(value) != _TOP_FIELDS[schema]:
        raise ImageLockError(f"image lock fields differ from the closed schema: {relative}")
    if value["schema_version"] != schema:
        raise ImageLockError(f"image lock schema differs: {relative}")
    reference = value["image_reference"]
    if not isinstance(reference, str) or _IMAGE_REFERENCE.fullmatch(reference) is None:
        raise ImageLockError(f"image reference is not an exact sha256 digest: {relative}")
    for field in ("oci_index_digest", "platform_manifest_digest"):
        if _SHA256.fullmatch(value[field]) is None:
            raise ImageLockError(f"{field} is not canonical sha256: {relative}")
    if reference.rsplit("@", 1)[1] != value["oci_index_digest"]:
        raise ImageLockError(f"image reference and index digest disagree: {relative}")
    if not isinstance(value["platform"], str) or _PLATFORM.fullmatch(value["platform"]) is None:
        raise ImageLockError(f"platform is outside the linux/arm64 scope: {relative}")
    authorization = value["authorization"]
    if not isinstance(authorization, dict) or frozenset(authorization) != _AUTHORIZATION_FIELDS[schema]:
        raise ImageLockError(f"image lock authorization fields differ: {relative}")
    if authorization["runtime_role"] != _EXPECTED_ROLE[schema]:
        raise ImageLockError(
            f"image lock runtime_role is not {_EXPECTED_ROLE[schema]}: {relative}"
        )
    if authorization["pull_policy"] != "never" or authorization["network_default"] != "none":
        raise ImageLockError(f"image lock relaxed pull or network policy: {relative}")
    if schema == CAMPAIGN_LOCK_SCHEMA:
        if authorization["executes_untrusted_program"] is not True:
            raise ImageLockError("the campaign lock must declare untrusted program execution")
        if authorization["credentials_admitted"] is not False:
            raise ImageLockError("the campaign lock must admit no credential")
        reuse = value["digest_reuse"]
        if (
            not isinstance(reuse, dict)
            or frozenset(reuse) != frozenset({
                "recorded_reuse", "reused_from_lock", "reused_from_role", "rationale",
            })
            or reuse["recorded_reuse"] is not True
            or reuse["reused_from_lock"] != PHASE4B_LOCK_PATH
            or reuse["reused_from_role"] != PHASE4B_RUNTIME_ROLE
            or not isinstance(reuse["rationale"], str)
            or not reuse["rationale"]
        ):
            raise ImageLockError("the campaign lock does not record its digest reuse")
    inventory = value["inventory"]
    if not isinstance(inventory, dict) or not isinstance(
        inventory.get("production_python_dependencies"), list
    ):
        raise ImageLockError(f"image lock inventory differs: {relative}")
    dependencies = inventory["production_python_dependencies"]
    if dependencies:
        raise ImageLockError(
            f"the image must carry no third-party production dependency: {relative}"
        )
    return OciImageLock(
        schema_version=schema,
        lock_path=relative,
        lock_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        image_reference=reference,
        oci_index_digest=value["oci_index_digest"],
        platform=value["platform"],
        platform_manifest_digest=value["platform_manifest_digest"],
        runtime_role=authorization["runtime_role"],
        pull_policy=authorization["pull_policy"],
        network_default=authorization["network_default"],
        status=authorization["status"],
        production_python_dependencies=tuple(dependencies),
    )


def load_phase4b_image_lock(repository_root: Path) -> OciImageLock:
    """Load the Phase 4B lock read-only, asserting its role was not widened."""

    return _load(
        repository_root / PHASE4B_LOCK_PATH, PHASE4B_LOCK_PATH, PHASE4B_LOCK_SCHEMA,
    )


def load_campaign_image_lock(repository_root: Path) -> OciImageLock:
    """Load the campaign experiment lock and cross-check the shared digest."""

    campaign = _load(
        repository_root / CAMPAIGN_LOCK_PATH, CAMPAIGN_LOCK_PATH, CAMPAIGN_LOCK_SCHEMA,
    )
    phase4b = load_phase4b_image_lock(repository_root)
    if (
        campaign.image_reference != phase4b.image_reference
        or campaign.platform_manifest_digest != phase4b.platform_manifest_digest
        or campaign.platform != phase4b.platform
    ):
        raise ImageLockError("the campaign lock does not reuse the reviewed Phase 4B image")
    if campaign.runtime_role == phase4b.runtime_role:
        raise ImageLockError("the two locks share a runtime role, which is role widening")
    return campaign


def shared_digest_distinct_roles(repository_root: Path) -> dict[str, Any]:
    """Evidence for ``pr.sandbox-role-not-widened``: same bytes, distinct roles."""

    campaign = load_campaign_image_lock(repository_root)
    phase4b = load_phase4b_image_lock(repository_root)
    return {
        "campaign_lock": campaign.to_record(),
        "image_reference_identical": campaign.image_reference == phase4b.image_reference,
        "phase4b_lock": phase4b.to_record(),
        "phase4b_role_unchanged": phase4b.runtime_role == PHASE4B_RUNTIME_ROLE,
        "platform_manifest_digest_identical": (
            campaign.platform_manifest_digest == phase4b.platform_manifest_digest
        ),
        "roles_distinct": campaign.runtime_role != phase4b.runtime_role,
    }


__all__ = [
    "CAMPAIGN_LOCK_PATH", "CAMPAIGN_LOCK_SCHEMA", "CAMPAIGN_RUNTIME_ROLE",
    "ImageLockError", "MAX_LOCK_BYTES", "OciImageLock", "PHASE4B_LOCK_PATH",
    "PHASE4B_LOCK_SCHEMA", "PHASE4B_RUNTIME_ROLE", "load_campaign_image_lock",
    "load_phase4b_image_lock", "shared_digest_distinct_roles",
]
