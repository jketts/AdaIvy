"""Pinned, source-inlined bridge from the exact parser to the Darwin sandbox.

This is integration evidence only.  It does not configure the Phase 4B
service or activate a production parser.  The child receives no project path:
the parser functions are copied byte-for-byte from the measured candidate
source into a self-contained ``-I -S -c`` worker program before launch.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path

from .exact_parser_worker import (
    IMPLEMENTATION_SHA256 as EXACT_IMPLEMENTATION_SHA256,
    IMPLEMENTATION_SOURCE_PATH,
    WORKER_NAME,
    WORKER_VERSION,
)
from .parser_sandbox import (
    DarwinResourceSandboxWorker,
    SandboxLimits,
    measured_runtime_identity,
)


ARTIFACT_SCHEMA = "adaivy.phase4b-exact-parser-sandbox-artifact.v2"
PROTOCOL_SCHEMA = "phase4b-parser-worker-response-v2"

_REQUIRED_ASSIGNMENTS = {
    "CROSS_FORMAT_AMBIGUITY",
    "_HTML_ALLOWED_TAGS", "_HTML_VOID_TAGS", "_HTML_GLOBAL_ATTRIBUTES",
    "_HTML_TAG_ATTRIBUTES", "_HTML_FORBIDDEN_TAGS", "_HTML_ATTRIBUTE",
    "_DANGEROUS_TEX_COMMANDS", "_KNOWN_TEX_COMMANDS", "_TEX_COMMAND",
}
_REQUIRED_FUNCTIONS = {
    "_has_structural_pdf_envelope", "_has_structural_html_envelope",
    "_has_structural_tex_envelope", "_reject_cross_format_ambiguity",
    "_decode_utf8", "_segment", "_end_of_html_tag", "_parse_html_tag",
    "parse_exact_html", "_unescaped", "_validate_tex_groups", "parse_exact_tex",
}


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _exact_semantics_source() -> str:
    """Extract the authoritative parser semantics without importing them in-child."""
    source = IMPLEMENTATION_SOURCE_PATH.read_text("utf-8")
    if _sha256(source.encode("utf-8")) != EXACT_IMPLEMENTATION_SHA256:
        raise RuntimeError("exact parser source identity changed during bridge construction")
    tree = ast.parse(source)
    selected: list[str] = []
    found_assignments: set[str] = set()
    found_functions: set[str] = set()
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        include = False
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            matched = names & _REQUIRED_ASSIGNMENTS
            if matched:
                found_assignments.update(matched)
                include = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _REQUIRED_FUNCTIONS:
                found_functions.add(node.name)
                include = True
        if include:
            assert node.end_lineno is not None
            selected.append("".join(lines[node.lineno - 1:node.end_lineno]))
    if found_assignments != _REQUIRED_ASSIGNMENTS or found_functions != _REQUIRED_FUNCTIONS:
        raise RuntimeError("exact parser semantics inventory is incomplete")
    return "\n".join(selected)


_BOOTSTRAP = r'''
import base64, hashlib, json, re, sys

class ContentRejected(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason

class Bounds:
    max_nesting_depth = __MAX_NESTING_DEPTH__
    max_segments = __MAX_SEGMENTS__
    max_formulas = __MAX_FORMULAS__
    max_warnings = __MAX_WARNINGS__
PARSER_BOUNDS = Bounds()

def _sha256(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()

class ByteAnchor:
    @classmethod
    def create(cls, original, start, end):
        if not 0 <= start < end <= len(original):
            raise ContentRejected("anchor_invalid")
        value = cls()
        value.original_sha256 = _sha256(original)
        value.start, value.end = start, end
        value.slice_sha256 = _sha256(original[start:end])
        value.page_index = value.object_id = None
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
    profile = request.get("profile_name")
    if profile == HTML_PROFILE_NAME:
        outcome = parse_exact_html(original)
    elif profile == TEX_PROFILE_NAME:
        outcome = parse_exact_tex(original)
    elif profile == PDF_PROFILE_NAME:
        raise ContentRejected("pdf_exact_source_mapping_unsupported")
    else:
        raise ContentRejected("unsupported_parser_profile")
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
    from .parsing import HTML_PROFILE, PARSER_BOUNDS, PDF_PROFILE, TEX_PROFILE

    bootstrap = _BOOTSTRAP
    for marker, value in {
        "__MAX_NESTING_DEPTH__": PARSER_BOUNDS.max_nesting_depth,
        "__MAX_SEGMENTS__": PARSER_BOUNDS.max_segments,
        "__MAX_FORMULAS__": PARSER_BOUNDS.max_formulas,
        "__MAX_WARNINGS__": PARSER_BOUNDS.max_warnings,
    }.items():
        bootstrap = bootstrap.replace(marker, str(value))
    identities = (
        f"HTML_PROFILE_NAME = {HTML_PROFILE.name!r}\n"
        f"TEX_PROFILE_NAME = {TEX_PROFILE.name!r}\n"
        f"PDF_PROFILE_NAME = {PDF_PROFILE.name!r}\n"
        f"EXACT_PARSER_SOURCE_SHA256 = {EXACT_IMPLEMENTATION_SHA256!r}\n"
    )
    return bootstrap + "\n" + identities + _exact_semantics_source() + "\n" + _DRIVER


@dataclass(frozen=True, slots=True)
class ExactSandboxArtifact:
    schema_version: str
    exact_parser_source_sha256: str
    worker_source_sha256: str
    dependency_environment_sha256: str
    protocol_schema: str


def build_exact_darwin_sandbox_worker(
    *, limits: SandboxLimits | None = None,
) -> tuple[DarwinResourceSandboxWorker, ExactSandboxArtifact]:
    """Create an unactivated worker and its complete measured identity record."""
    source = _worker_source()
    runtime = measured_runtime_identity()
    worker = DarwinResourceSandboxWorker(
        name=WORKER_NAME + "-darwin-sandbox",
        version=WORKER_VERSION,
        worker_source=source,
        expected_dependency_environment_sha256=runtime,
        limits=limits,
    )
    artifact = ExactSandboxArtifact(
        ARTIFACT_SCHEMA, EXACT_IMPLEMENTATION_SHA256,
        _sha256(source.encode("utf-8")), runtime, PROTOCOL_SCHEMA,
    )
    if artifact.worker_source_sha256 != worker.implementation_sha256:
        raise RuntimeError("sandbox worker source identity mismatch")
    return worker, artifact


__all__ = [
    "ARTIFACT_SCHEMA", "ExactSandboxArtifact",
    "build_exact_darwin_sandbox_worker",
]
