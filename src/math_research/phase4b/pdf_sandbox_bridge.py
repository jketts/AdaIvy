"""Source-bound Darwin sandbox bridge for the strict PDF candidate.

This module is pre-activation integration evidence.  It extracts the measured
PDF candidate semantics into a self-contained ``-I -S -c`` child program.  The
child receives neither a repository path nor an AdaIvy import path, and the
existing Darwin resource-sandbox profile is used without modification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib

from .parser_sandbox import (
    DarwinResourceSandboxWorker,
    SandboxLimits,
    measured_runtime_identity,
)
from .pdf_exact_candidate import (
    IMPLEMENTATION_SHA256 as PDF_IMPLEMENTATION_SHA256,
    IMPLEMENTATION_SOURCE_PATH,
    StrictBornDigitalPdfAdapter,
)


ARTIFACT_SCHEMA = "adaivy.phase4b-strict-pdf-sandbox-artifact.v2"
PROTOCOL_SCHEMA = "phase4b-parser-worker-response-v2"

_REQUIRED_ASSIGNMENTS = {
    "CROSS_FORMAT_AMBIGUITY",
    "_PDF_WS", "_DELIMITERS", "_FORBIDDEN_NAMES", "_MAX_OBJECTS",
    "_MAX_PAGES", "_MAX_CONTENT_STREAM_BYTES", "_MAX_TOKENS",
}
_REQUIRED_CLASSES = {"_Name", "_Ref", "_String", "_Keyword", "_Object", "_Syntax"}
_REQUIRED_FUNCTIONS = {
    "_has_structural_pdf_envelope", "_has_structural_html_envelope",
    "_has_structural_tex_envelope", "_reject_cross_format_ambiguity",
    "_dictionary", "_name", "_ref", "_read_xref", "_read_object",
    "_extract_text", "parse_strict_pdf",
}


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _pdf_semantics_source() -> str:
    """Copy the measured parser semantics into the isolated child source."""

    source = IMPLEMENTATION_SOURCE_PATH.read_text("utf-8")
    if _sha256(source.encode("utf-8")) != PDF_IMPLEMENTATION_SHA256:
        raise RuntimeError("PDF parser source identity changed during bridge construction")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    selected: list[str] = []
    found_assignments: set[str] = set()
    found_classes: set[str] = set()
    found_functions: set[str] = set()
    for node in tree.body:
        include = False
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            matched = names & _REQUIRED_ASSIGNMENTS
            if matched:
                found_assignments.update(matched)
                include = True
        elif isinstance(node, ast.ClassDef) and node.name in _REQUIRED_CLASSES:
            found_classes.add(node.name)
            include = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _REQUIRED_FUNCTIONS:
            found_functions.add(node.name)
            include = True
        if include:
            assert node.end_lineno is not None
            start_line = node.lineno
            if isinstance(node, ast.ClassDef) and node.decorator_list:
                start_line = min(start_line, *(decorator.lineno for decorator in node.decorator_list))
            selected.append("".join(lines[start_line - 1:node.end_lineno]))
    if (
        found_assignments != _REQUIRED_ASSIGNMENTS
        or found_classes != _REQUIRED_CLASSES
        or found_functions != _REQUIRED_FUNCTIONS
    ):
        raise RuntimeError("PDF parser semantics inventory is incomplete")
    return "\n".join(selected)


_BOOTSTRAP = r'''
import base64, hashlib, json, re, sys
from dataclasses import dataclass
from typing import Any

class ContentRejected(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason

class Bounds:
    max_nesting_depth = __MAX_NESTING_DEPTH__
    max_segments = __MAX_SEGMENTS__
    max_formulas = __MAX_FORMULAS__
    max_decoded_output_bytes = __MAX_DECODED_OUTPUT_BYTES__
    max_expansion_ratio = __MAX_EXPANSION_RATIO__
PARSER_BOUNDS = Bounds()

def _sha256(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()

class ByteAnchor:
    @classmethod
    def create(cls, original, start, end, *, page_index=None, object_id=None):
        if not 0 <= start < end <= len(original):
            raise ContentRejected("anchor_invalid")
        value = cls()
        value.original_sha256 = _sha256(original)
        value.start, value.end = start, end
        value.slice_sha256 = _sha256(original[start:end])
        value.page_index, value.object_id = page_index, object_id
        return value
    def to_record(self):
        return {"end": self.end, "object_id": self.object_id,
                "original_sha256": self.original_sha256,
                "page_index": self.page_index, "slice_sha256": self.slice_sha256,
                "start": self.start}

class ParsedSegment:
    def __init__(self, segment_id, kind, normalized_text, anchor, load_bearing):
        self.segment_id, self.kind = segment_id, kind
        self.normalized_text, self.anchor = normalized_text, anchor
        self.load_bearing = load_bearing
    def to_record(self):
        return {"anchor": self.anchor.to_record(), "kind": self.kind,
                "load_bearing": self.load_bearing,
                "normalized_text": self.normalized_text,
                "segment_id": self.segment_id}

class AdapterOutcome:
    def __init__(self, segments, references=(), warnings=(), transformations=()):
        self.segments, self.references = tuple(segments), tuple(references)
        self.warnings, self.transformations = tuple(warnings), tuple(transformations)
'''

_DRIVER = r'''
def _main():
    envelope = json.loads(sys.stdin.buffer.read())
    if set(envelope) != {"original_bytes_base64", "request", "schema_version"}:
        raise ContentRejected("worker_request_envelope_invalid")
    if envelope["schema_version"] != "phase4b-parser-worker-request-v1":
        raise ContentRejected("worker_request_schema_invalid")
    request = envelope["request"]
    original = base64.b64decode(envelope["original_bytes_base64"], validate=True)
    if request.get("original_sha256") != _sha256(original):
        raise ContentRejected("worker_request_hash_mismatch")
    if request.get("original_byte_length") != len(original):
        raise ContentRejected("worker_request_length_mismatch")
    if request.get("profile_name") != PDF_PROFILE_NAME:
        raise ContentRejected("unsupported_parser_profile")
    outcome = parse_strict_pdf(original)
    response = {"outcome": {
        "references": [], "segments": [item.to_record() for item in outcome.segments],
        "transformations": list(outcome.transformations),
        "warnings": list(outcome.warnings)},
        "schema_version": "phase4b-parser-worker-response-v2", "status": "completed"}
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")))

try:
    _main()
except ContentRejected as error:
    sys.stdout.write(json.dumps({"failure_code": error.reason,
                                 "schema_version": "phase4b-parser-worker-response-v2",
                                 "status": "rejected"},
                                sort_keys=True, separators=(",", ":")))
'''


def _worker_source() -> str:
    from .parsing import PARSER_BOUNDS, PDF_PROFILE

    bootstrap = _BOOTSTRAP
    for marker, value in {
        "__MAX_NESTING_DEPTH__": PARSER_BOUNDS.max_nesting_depth,
        "__MAX_SEGMENTS__": PARSER_BOUNDS.max_segments,
        "__MAX_FORMULAS__": PARSER_BOUNDS.max_formulas,
        "__MAX_DECODED_OUTPUT_BYTES__": PARSER_BOUNDS.max_decoded_output_bytes,
        "__MAX_EXPANSION_RATIO__": PARSER_BOUNDS.max_expansion_ratio,
    }.items():
        bootstrap = bootstrap.replace(marker, str(value))
    identities = (
        f"PDF_PROFILE_NAME = {PDF_PROFILE.name!r}\n"
        f"PDF_PARSER_SOURCE_SHA256 = {PDF_IMPLEMENTATION_SHA256!r}\n"
    )
    return bootstrap + "\n" + identities + _pdf_semantics_source() + "\n" + _DRIVER


@dataclass(frozen=True, slots=True)
class PdfSandboxArtifact:
    schema_version: str
    pdf_parser_source_sha256: str
    worker_source_sha256: str
    dependency_environment_sha256: str
    protocol_schema: str


def build_pdf_darwin_sandbox_worker(
    *, limits: SandboxLimits | None = None,
) -> tuple[DarwinResourceSandboxWorker, PdfSandboxArtifact]:
    """Create the unactivated PDF worker and its measured identity artifact."""

    source = _worker_source()
    runtime = measured_runtime_identity()
    worker = DarwinResourceSandboxWorker(
        name=StrictBornDigitalPdfAdapter.name + "-darwin-sandbox",
        version=StrictBornDigitalPdfAdapter.version,
        worker_source=source,
        expected_dependency_environment_sha256=runtime,
        limits=limits,
    )
    artifact = PdfSandboxArtifact(
        ARTIFACT_SCHEMA,
        PDF_IMPLEMENTATION_SHA256,
        _sha256(source.encode("utf-8")),
        runtime,
        PROTOCOL_SCHEMA,
    )
    if artifact.worker_source_sha256 != worker.implementation_sha256:
        raise RuntimeError("PDF sandbox worker source identity mismatch")
    return worker, artifact


__all__ = [
    "ARTIFACT_SCHEMA", "PdfSandboxArtifact", "build_pdf_darwin_sandbox_worker",
]
