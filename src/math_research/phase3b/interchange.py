"""Canonical export and replay validation for Phase 3B findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .serialization import canonical_bytes, canonical_hash
from .workspace import FormalCheckWorkspace


def validate_finding_dict(value: dict[str, Any]) -> None:
    required_false = (
        "semantic_alignment_approved", "source_applicability_approved", "novelty_approved",
        "significance_approved", "contribution_approved", "epistemic_warrant_created",
    )
    if value.get("schema_version") != SCHEMA_VERSION or value.get("disposition") != "proposal" or value.get("trust_effect") != "none":
        raise ValueError("finding violates Phase 3B proposal-only contract")
    if any(value.get(field) is not False for field in required_false):
        raise ValueError("formal finding attempted to promote an orthogonal trust decision")
    original = value.get("content_hash")
    candidate = dict(value)
    candidate["content_hash"] = ""
    if original != canonical_hash(candidate):
        raise ValueError("formal finding content hash mismatch")


def build_export(workspace: FormalCheckWorkspace) -> dict[str, Any]:
    findings = list(workspace.canonical_findings())
    for finding in findings:
        validate_finding_dict(finding)
    body: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "record_type": "phase3b_formal_check_export", "findings": findings}
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
    original = value.get("content_hash")
    body = dict(value)
    body.pop("content_hash", None)
    if original != canonical_hash(body):
        raise ValueError("Phase 3B export content hash mismatch")
    findings = value.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings must be an array")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("finding must be an object")
        validate_finding_dict(finding)
    if data != canonical_bytes(value) and data != canonical_bytes(value) + b"\n":
        raise ValueError("Phase 3B interchange is not canonical JSON")
    return value
