"""Actual-corpus evidence for the strict Phase 4B parser candidates.

This module is deliberately an authorization *measurement*, not an activation
switch.  It runs every parser fixture named by the acceptance manifest through
the source-bound Darwin worker for its exact media/profile pair.  Any missing
sandbox, content mismatch, parser failure, or disposition mismatch is retained
as a closed machine-readable outcome and prevents authorization.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .exact_sandbox_bridge import build_exact_darwin_sandbox_worker
from .pdf_sandbox_bridge import build_pdf_darwin_sandbox_worker
from .parsing import (
    HTML_PROFILE, PDF_PROFILE, TEX_PROFILE, ParseRequest, Profile,
    run_production_parser, verify_result_record,
)
from .serialization import canonical_hash, sha256_bytes
from .service import Phase4BService


EVIDENCE_SCHEMA = "adaivy.phase4b-parser-corpus-authorization.v2"
MANIFEST_SCHEMA = "adaivy.phase4b-acceptance-manifest.v1"
_PROFILES: dict[str, Profile] = {
    "html": HTML_PROFILE,
    "pdf": PDF_PROFILE,
    "tex": TEX_PROFILE,
}


def _manifest(repository_root: Path) -> tuple[Path, dict[str, Any]]:
    base = repository_root / "fixtures/phase4b/acceptance"
    value = json.loads((base / "manifest.json").read_text("utf-8"))
    if value.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("Phase 4B acceptance manifest schema differs")
    fixtures = value.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("Phase 4B acceptance fixture inventory is invalid")
    return base, value


def _fixture_path(base: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ValueError("parser fixture path is invalid")
    path = (base / relative).resolve()
    managed = base.parent.resolve()
    if managed not in path.parents:
        raise ValueError("parser fixture escapes the Phase 4B fixture root")
    return path


def run_parser_corpus_authorization(repository_root: Path) -> dict[str, Any]:
    """Run all 12 declared parser fixtures through the strict sandbox workers."""

    repository_root = repository_root.resolve()
    base, manifest = _manifest(repository_root)
    fixtures = [item for item in manifest["fixtures"] if item.get("class") == "parsing"]
    if len(fixtures) != 12:
        raise ValueError("parser acceptance corpus must contain exactly 12 fixtures")
    if {name: sum(item.get("format") == name for item in fixtures) for name in _PROFILES} != {
        "html": 4, "pdf": 4, "tex": 4,
    }:
        raise ValueError("parser acceptance format counts differ")

    text_worker, text_artifact = build_exact_darwin_sandbox_worker()
    pdf_worker, pdf_artifact = build_pdf_darwin_sandbox_worker()
    cases: list[dict[str, Any]] = []
    for item in fixtures:
        case_id = item.get("case_id")
        format_name = item.get("format")
        expected = item.get("expected_outcome")
        if (
            not isinstance(case_id, str)
            or format_name not in _PROFILES
            or expected not in {"candidate_proposal", "quarantined"}
        ):
            raise ValueError("parser acceptance case declaration is invalid")
        profile = _PROFILES[format_name]
        path = _fixture_path(base, item.get("path"))
        original = path.read_bytes()
        fixture_sha256 = sha256_bytes(original)
        if item.get("byte_length") != len(original) or item.get("sha256") != fixture_sha256:
            raise ValueError(f"parser acceptance fixture bytes differ: {case_id}")

        # Bind the same conservative content check used by the service before
        # an untrusted worker is allowed to see acquired bytes.
        signature_match = Phase4BService._content_signature_matches(profile.name, original)
        media_type_hash = sha256_bytes(profile.media_type.encode("utf-8"))
        request = ParseRequest.create(
            request_id=f"request.authorization.{case_id}",
            source_id=f"source.authorization.{case_id}",
            content_object_id=f"content.authorization.{case_id}",
            representation_id=f"representation.authorization.{case_id}",
            media_type=profile.media_type,
            profile_name=profile.name,
            original_bytes=original,
        )
        worker = pdf_worker if format_name == "pdf" else text_worker
        if signature_match:
            result = run_production_parser(request, worker=worker)
        else:
            # The service would quarantine before worker invocation.  The
            # corpus harness retains that boundary outcome without weakening
            # it to a best-effort parse.
            from .parsing import quarantine_before_worker

            result = quarantine_before_worker(request, "content_signature_mismatch")
        if result.disposition == "candidate_proposal":
            verify_result_record(result.to_record(), original)

        exact_match = result.disposition == expected
        false_admission = expected == "quarantined" and result.disposition == "candidate_proposal"
        cases.append({
            "case_id": case_id,
            "content_signature_match": signature_match,
            "exact_disposition_match": exact_match,
            "expected_outcome": expected,
            "failure_code": result.failure_code,
            "false_admission": false_admission,
            "fixture_byte_length": len(original),
            "fixture_sha256": fixture_sha256,
            "format": format_name,
            "media_type": profile.media_type,
            "media_type_hash": media_type_hash,
            "observed_disposition": result.disposition,
            "parser_semantic_sha256": result.semantic_sha256,
            "profile_name": profile.name,
            "profile_sha256": profile.sha256,
            "request_original_sha256": request.original_sha256,
            "safe_fail_closed": (
                result.disposition == "candidate_proposal"
                if expected == "candidate_proposal"
                else result.disposition != "candidate_proposal"
            ),
            "segment_count": len(result.segments),
        })

    exact_matches = sum(item["exact_disposition_match"] for item in cases)
    false_admissions = sum(item["false_admission"] for item in cases)
    signature_matches = sum(item["content_signature_match"] for item in cases)
    authorization_passed = (
        exact_matches == len(cases)
        and false_admissions == 0
        and signature_matches == len(cases)
    )
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "status": "authorized" if authorization_passed else "blocked",
        "activation_effect": "none",
        "artifacts": {
            "html_tex": asdict(text_artifact),
            "pdf": asdict(pdf_artifact),
        },
        "cases": cases,
        "counts": {
            "cases_exactly_matched": exact_matches,
            "content_signature_matches": signature_matches,
            "exact_disposition_matches": exact_matches,
            "false_admissions": false_admissions,
            "total": len(cases),
        },
        "manifest_content_hash": manifest.get("content_hash"),
        "media_profile_binding": "exact_format_to_single_profile_v1",
        "production_activated": False,
    }
    evidence["content_hash"] = canonical_hash(evidence)
    return evidence


__all__ = ["EVIDENCE_SCHEMA", "run_parser_corpus_authorization"]
