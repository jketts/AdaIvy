"""Canonical export and replay validation for Phase 3B findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import HASH_PROFILE, SCHEMA_VERSION
from .serialization import (
    canonical_bytes, canonical_hash, finding_content_hash, operational_export_hash,
    semantic_export_hash,
)
from .workspace import FormalCheckWorkspace


_ANY_PROFILE = object()


def validate_finding_dict(
    value: dict[str, Any], *, expected_profile: str | None | object = _ANY_PROFILE,
) -> None:
    required_false = (
        "semantic_alignment_approved", "source_applicability_approved", "novelty_approved",
        "significance_approved", "contribution_approved", "epistemic_warrant_created",
    )
    if value.get("schema_version") != SCHEMA_VERSION or value.get("disposition") != "proposal" or value.get("trust_effect") != "none":
        raise ValueError("finding violates Phase 3B proposal-only contract")
    if any(value.get(field) is not False for field in required_false):
        raise ValueError("formal finding attempted to promote an orthogonal trust decision")
    has_profile = "hash_profile" in value
    profile = value.get("hash_profile")
    if expected_profile is None and has_profile:
        raise ValueError("formal finding hash profile mismatch")
    if expected_profile is not _ANY_PROFILE and profile != expected_profile:
        raise ValueError("formal finding hash profile mismatch")
    original = value.get("content_hash")
    if has_profile and profile == HASH_PROFILE:
        expected = finding_content_hash(value)
    elif not has_profile:
        candidate = dict(value)
        candidate["content_hash"] = ""
        expected = canonical_hash(candidate)
    else:
        raise ValueError("unsupported formal finding hash profile")
    if original != expected:
        raise ValueError("formal finding content hash mismatch")


def build_export(workspace: FormalCheckWorkspace) -> dict[str, Any]:
    findings = list(workspace.canonical_findings())
    for finding in findings:
        validate_finding_dict(finding)
    profiles = {finding.get("hash_profile") for finding in findings}
    if profiles == {HASH_PROFILE} or not findings:
        body: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "phase3b_formal_check_export",
            "hash_profile": HASH_PROFILE,
            "findings": findings,
        }
        body["content_hash"] = semantic_export_hash(body)
        body["operational_hash"] = operational_export_hash(body)
        return body
    if profiles != {None}:
        raise ValueError("mixed formal finding hash profiles cannot be exported")
    body = {"schema_version": SCHEMA_VERSION, "record_type": "phase3b_formal_check_export", "findings": findings}
    body["content_hash"] = canonical_hash(body)
    return body


def export_workspace(workspace: FormalCheckWorkspace, path: Path) -> str:
    value = build_export(workspace)
    data = canonical_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(value["content_hash"])


def import_trusted_replay(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Phase 3B interchange") from error
    if not isinstance(value, dict) or value.get("record_type") != "phase3b_formal_check_export":
        raise ValueError("wrong Phase 3B interchange type")
    findings = value.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings must be an array")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("finding must be an object")

    if "hash_profile" not in value:
        expected_profile: str | None = None
    elif value.get("hash_profile") == HASH_PROFILE:
        expected_profile = HASH_PROFILE
    else:
        raise ValueError("unsupported Phase 3B export hash profile")

    # Establish a homogeneous profile boundary before hashes or proposal fields
    # can make any imported finding appear eligible for trusted replay.
    for finding in findings:
        if expected_profile is None:
            if "hash_profile" in finding:
                raise ValueError("formal finding hash profile mismatch")
        elif finding.get("hash_profile") != expected_profile:
            raise ValueError("formal finding hash profile mismatch")

    if expected_profile == HASH_PROFILE:
        if value.get("content_hash") != semantic_export_hash(value):
            raise ValueError("Phase 3B export semantic content hash mismatch")
        if value.get("operational_hash") != operational_export_hash(value):
            raise ValueError("Phase 3B export operational hash mismatch")
        for finding in findings:
            validate_finding_dict(finding, expected_profile=HASH_PROFILE)
    elif "operational_hash" not in value:
        original = value.get("content_hash")
        body = dict(value)
        body.pop("content_hash", None)
        if original != canonical_hash(body):
            raise ValueError("Phase 3B export content hash mismatch")
        for finding in findings:
            validate_finding_dict(finding, expected_profile=None)
    else:
        raise ValueError("unsupported Phase 3B export hash profile")
    if data != canonical_bytes(value) and data != canonical_bytes(value) + b"\n":
        raise ValueError("Phase 3B interchange is not canonical JSON")
    return value
