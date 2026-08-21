"""Closed machine evidence for Phase 4B acceptance thresholds.

This module does not activate acquisition or parsing.  It turns observations
from the existing production boundaries into small, deterministic evidence for
thresholds whose prose otherwise has no machine-readable result.  Source bytes
and deletion markers are never included in returned evidence.
"""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import stat
import sys
import tomllib
from typing import Mapping

from .acquisition import MAX_RUN_MILLISECONDS
from .parsing import PARSER_BOUNDS
from .serialization import canonical_hash, sha256_bytes


EVIDENCE_SCHEMA = "adaivy.phase4b-threshold-evidence.v1"
MAX_SCAN_FILES = 100_000
MIN_MARKER_BYTES = 16
LOCAL_IMPORT_ROOTS = frozenset({"math_research", "phase0_harness"})

EXPECTED_ACQUISITION_FAILURES = {
    "p4b.acquisition.denied-acquisition-right": "acquisition_rights_invalid",
    "p4b.acquisition.denied-changed-terms": "terms_snapshot_invalid_or_stale",
    "p4b.acquisition.denied-missing-run-authority": "run_authority_invalid",
    "p4b.acquisition.denied-peer-mismatch": "connected_peer_mismatch",
    "p4b.acquisition.denied-response-budget": "response_body_too_large",
    "p4b.acquisition.denied-retention-right": "storage_and_retention_rights_invalid",
    "p4b.acquisition.denied-robots-disallow": "robots_snapshot_invalid_or_stale",
    "p4b.acquisition.denied-robots-unavailable": "robots_snapshot_invalid_or_stale",
    "p4b.acquisition.denied-special-use-redirect": "resolved_address_forbidden",
}

EXPECTED_PARSER_QUARANTINES = {
    "p4b.parsing.html.attack": "html_active_content_forbidden",
    "p4b.parsing.html.malformed": "html_unbalanced_structure",
    "p4b.parsing.pdf.attack": "pdf_incremental_or_ambiguous_revision_forbidden",
    "p4b.parsing.pdf.malformed": "pdf_incremental_or_ambiguous_revision_forbidden",
    "p4b.parsing.tex.attack": "tex_active_or_expanding_command_forbidden",
    "p4b.parsing.tex.malformed": "tex_unbalanced_group",
}


def _closed_reason_observations(
    observed: Mapping[str, str], expected: Mapping[str, str], label: str,
) -> dict[str, object]:
    if set(observed) != set(expected):
        raise ValueError(f"{label} reason observation identities differ")
    cases = [
        {
            "case_id": case_id,
            "exact_match": observed[case_id] == expected_reason,
            "expected_reason": expected_reason,
            "observed_reason": observed[case_id],
        }
        for case_id, expected_reason in sorted(expected.items())
    ]
    matches = sum(bool(item["exact_match"]) for item in cases)
    return {
        "cases": cases,
        "exact_matches": matches,
        "required_matches": len(cases),
        "accuracy_numerator": matches,
        "accuracy_denominator": len(cases),
        "status": "passed" if matches == len(cases) else "failed",
    }


def exact_reason_evidence(
    *, acquisition_failures: Mapping[str, str], parser_quarantines: Mapping[str, str],
) -> dict[str, object]:
    """Prove exact AT-013 reason accuracy over every required negative fixture."""

    acquisition = _closed_reason_observations(
        acquisition_failures, EXPECTED_ACQUISITION_FAILURES, "acquisition",
    )
    parser = _closed_reason_observations(
        parser_quarantines, EXPECTED_PARSER_QUARANTINES, "parser",
    )
    total = int(acquisition["required_matches"]) + int(parser["required_matches"])
    matches = int(acquisition["exact_matches"]) + int(parser["exact_matches"])
    evidence: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA,
        "threshold_id": "P4B-AT-013",
        "acquisition": acquisition,
        "parser": parser,
        "exact_matches": matches,
        "required_matches": total,
        "status": "passed" if matches == total else "failed",
    }
    evidence["content_hash"] = canonical_hash(evidence)
    return evidence


def _contains_marker(path: Path, marker: bytes, expected: os.stat_result) -> bool:
    """Search a regular file in bounded chunks without retaining its content."""

    overlap = len(marker) - 1
    tail = b""
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise ValueError("managed-store file changed during scan")
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return False
            value = tail + chunk
            if marker in value:
                return True
            tail = value[-overlap:] if overlap else b""
    finally:
        os.close(descriptor)


def _store_classes(relative: Path) -> tuple[str, ...]:
    text = relative.as_posix().casefold()
    name = relative.name.casefold()
    parts = tuple(item.casefold() for item in relative.parts)
    classes: list[str] = []
    if text.startswith("phase4b-content/"):
        classes.append("managed_content")
    if name == "source.bin" or "/cards/" in f"/{text}":
        classes.append("reconstructive_plaintext")
    if "cache" in parts or "caches" in parts:
        classes.append("cache")
    if "index" in parts or "indexes" in parts or "fts" in name:
        classes.append("index")
    if "export" in parts or "exports" in parts or name.endswith((".json", ".jsonl")):
        classes.append("export")
    if "temporary" in parts or "temp" in parts or "tmp" in parts:
        classes.append("temp")
    if name == "workspace.sqlite3" or name.endswith((".sqlite3-wal", ".sqlite3-shm", ".sqlite3-journal")):
        classes.append("sqlite_and_journal")
    if "log" in parts or "logs" in parts or name.endswith(".log"):
        classes.append("log")
    return tuple(classes) or ("other_managed",)


def deleted_marker_evidence(workspace_root: Path, marker: bytes) -> dict[str, object]:
    """Scan every managed workspace file after deletion (P4B-AT-016).

    Symlinks, special files, a changing root, or a file-count overflow fail
    closed.  Files may be assigned to multiple named store classes, while the
    aggregate match count is over unique files.
    """

    root = Path(workspace_root).resolve(strict=True)
    if not isinstance(marker, bytes) or len(marker) < MIN_MARKER_BYTES:
        raise ValueError("deleted-source marker must be at least 16 bytes")
    if not root.is_dir() or root.is_symlink():
        raise ValueError("managed workspace root must be a real directory")
    counts = {
        name: {"files_scanned": 0, "marker_matches": 0}
        for name in (
            "managed_content", "reconstructive_plaintext", "cache", "index",
            "export", "temp", "sqlite_and_journal", "log", "other_managed",
        )
    }
    matched_paths: list[str] = []
    files_scanned = 0
    bytes_scanned = 0
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        base = Path(directory)
        for child in tuple(directories) + tuple(filenames):
            path = base / child
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("managed-store scan refuses symlinks")
            if child in directories and not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("managed-store directory changed during scan")
        for filename in filenames:
            path = base / filename
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("managed-store scan accepts only regular files")
            files_scanned += 1
            if files_scanned > MAX_SCAN_FILES:
                raise ValueError("managed-store file-count bound exceeded")
            bytes_scanned += metadata.st_size
            relative = path.relative_to(root)
            classes = _store_classes(relative)
            matched = _contains_marker(path, marker, metadata)
            for name in classes:
                counts[name]["files_scanned"] += 1
                counts[name]["marker_matches"] += int(matched)
            if matched:
                matched_paths.append(relative.as_posix())
    evidence: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA,
        "threshold_id": "P4B-AT-016",
        "marker_sha256": sha256_bytes(marker),
        "marker_byte_length": len(marker),
        "files_scanned": files_scanned,
        "bytes_scanned": bytes_scanned,
        "store_classes": counts,
        "unique_matching_files": len(matched_paths),
        "matching_path_hashes": [
            sha256_bytes(item.encode("utf-8")) for item in sorted(matched_paths)
        ],
        "status": "passed" if not matched_paths else "failed",
    }
    evidence["content_hash"] = canonical_hash(evidence)
    return evidence


def resource_and_spend_evidence(*, external_spend_microusd: int) -> dict[str, object]:
    """Record the exact AT-029, AT-032, and AT-033 production bounds."""

    if isinstance(external_spend_microusd, bool) or external_spend_microusd != 0:
        raise ValueError("Phase 4B acceptance external spend must equal zero")
    evidence: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA,
        "threshold_ids": ["P4B-AT-029", "P4B-AT-032", "P4B-AT-033"],
        "decoded_output_bytes": PARSER_BOUNDS.max_decoded_output_bytes,
        "expansion_ratio": PARSER_BOUNDS.max_expansion_ratio,
        "segments": PARSER_BOUNDS.max_segments,
        "formulas": PARSER_BOUNDS.max_formulas,
        "references": PARSER_BOUNDS.max_references,
        "nesting_depth": PARSER_BOUNDS.max_nesting_depth,
        "warnings": PARSER_BOUNDS.max_warnings,
        "acquisition_run_wall_milliseconds": MAX_RUN_MILLISECONDS,
        "external_spend_microusd": external_spend_microusd,
        "status": "passed",
    }
    evidence["content_hash"] = canonical_hash(evidence)
    return evidence


def _root_name(name: str) -> str:
    return name.split(".", 1)[0]


def _third_party(name: str) -> bool:
    root = _root_name(name)
    return root not in sys.stdlib_module_names and root not in LOCAL_IMPORT_ROOTS


def production_dependency_evidence(
    phase4b_source_root: Path, pyproject_path: Path,
) -> dict[str, object]:
    """Prove the current AT-037 empty production-dependency boundary."""

    source_root = Path(phase4b_source_root).resolve(strict=True)
    project = tomllib.loads(Path(pyproject_path).read_text("utf-8"))
    declared = project.get("project", {}).get("dependencies")
    if not isinstance(declared, list) or any(not isinstance(item, str) for item in declared):
        raise ValueError("project runtime dependencies are not a string list")
    imports: list[dict[str, object]] = []
    dynamic: list[dict[str, object]] = []
    files = sorted(source_root.glob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                names = tuple(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = (node.module,)
            for name in names:
                if _third_party(name):
                    imports.append({"file": path.name, "line": node.lineno, "module": _root_name(name)})
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"find_spec", "import_module"}
            ):
                for argument in node.args:
                    if (
                        isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                        and _third_party(argument.value)
                    ):
                        dynamic.append({
                            "file": path.name, "line": node.lineno,
                            "module": _root_name(argument.value),
                        })
    evidence: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA,
        "threshold_id": "P4B-AT-037",
        "declared_runtime_dependencies": sorted(declared),
        "phase4b_python_files_scanned": len(files),
        "third_party_imports": sorted(imports, key=lambda item: (str(item["file"]), int(item["line"]))),
        "dynamic_third_party_loads": sorted(dynamic, key=lambda item: (str(item["file"]), int(item["line"]))),
        "dependency_wheel_hash_license_inventory": [],
        "mismatches": len(declared) + len(imports) + len(dynamic),
        "status": "passed" if not declared and not imports and not dynamic else "failed",
    }
    evidence["content_hash"] = canonical_hash(evidence)
    return evidence


__all__ = [
    "EVIDENCE_SCHEMA", "EXPECTED_ACQUISITION_FAILURES",
    "EXPECTED_PARSER_QUARANTINES", "deleted_marker_evidence",
    "exact_reason_evidence", "production_dependency_evidence",
    "resource_and_spend_evidence",
]
