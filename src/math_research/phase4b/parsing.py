"""Pre-activation Phase 4B parser contract for bounded candidate profiles.

The built-in fixture oracle intentionally recognises only small, explicitly
named stdlib profiles.  It is not a general rich parser and is not approved for
production activation.  Original bytes are supplied ephemerally in a
:class:`ParseRequest`; results retain hashes and exact anchors, never content
authority or a trust promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping, Protocol, runtime_checkable

from . import MAX_SOURCE_BYTES


REQUEST_SCHEMA = "phase4b-parse-request-v1"
RESULT_SCHEMA = "phase4b-parse-result-v2"
COMPARISON_SCHEMA = "phase4b-representation-comparison-v1"
PARSER_VERSION = "1.0.0"
PARSER_ACTIVATION_STATUS = "fixture_oracle_only"
PRODUCTION_PARSER_STATUS = "disabled_pending_pinned_worker_and_os_sandbox"
PRODUCTION_WORKER_DEPENDENCY_ID = "phase4b-isolated-parser-worker"
MAX_WORKER_CAPTURE_BYTES = 8_388_608
OS_SANDBOX_LIMITATIONS = (
    "no repository implementation currently proves portable network namespace isolation",
    "sampled Darwin RSS is not strict transient-memory-spike enforcement",
    "the named Darwin bridges cover closed strict subsets rather than general formats",
    "parser-connected sandbox evidence is not production parser activation",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a canonical sha256 value")


def _require_identifier(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 256
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ValueError(f"{field} is invalid")


def _strict_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{name} fields must equal {sorted(expected)}")


def _validate_anchor_metadata_record(anchor: Mapping[str, Any]) -> None:
    page_index = anchor["page_index"]
    if page_index is not None and (
        isinstance(page_index, bool)
        or not isinstance(page_index, int)
        or not 0 <= page_index <= PARSER_BOUNDS.max_anchor_page_index
    ):
        raise ValueError("anchor page index invalid")
    object_id = anchor["object_id"]
    if object_id is not None and (
        not isinstance(object_id, str)
        or not object_id
        or len(object_id.encode("utf-8")) > PARSER_BOUNDS.max_anchor_object_id_bytes
        or any(ord(character) < 0x20 for character in object_id)
    ):
        raise ValueError("anchor object identity invalid")


@dataclass(frozen=True)
class ParserBounds:
    max_raw_input_bytes: int = MAX_SOURCE_BYTES
    max_decoded_output_bytes: int = 8_388_608
    max_expansion_ratio: int = 20
    max_wall_seconds: int = 30
    max_memory_bytes: int = 536_870_912
    max_temp_bytes: int = 67_108_864
    max_processes: int = 16
    max_open_files: int = 64
    max_segments: int = 4_096
    max_formulas: int = 2_048
    max_references: int = 2_048
    max_nesting_depth: int = 128
    max_warnings: int = 16_384
    max_transformations: int = 64
    max_anchor_page_index: int = 1_000_000
    max_anchor_object_id_bytes: int = 256

    def to_record(self) -> dict[str, int]:
        return {
            "max_decoded_output_bytes": self.max_decoded_output_bytes,
            "max_expansion_ratio": self.max_expansion_ratio,
            "max_formulas": self.max_formulas,
            "max_memory_bytes": self.max_memory_bytes,
            "max_nesting_depth": self.max_nesting_depth,
            "max_open_files": self.max_open_files,
            "max_anchor_object_id_bytes": self.max_anchor_object_id_bytes,
            "max_anchor_page_index": self.max_anchor_page_index,
            "max_processes": self.max_processes,
            "max_raw_input_bytes": self.max_raw_input_bytes,
            "max_references": self.max_references,
            "max_segments": self.max_segments,
            "max_temp_bytes": self.max_temp_bytes,
            "max_transformations": self.max_transformations,
            "max_wall_seconds": self.max_wall_seconds,
            "max_warnings": self.max_warnings,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha256(_canonical_bytes(self.to_record()))


PARSER_BOUNDS = ParserBounds()


@dataclass(frozen=True)
class Profile:
    name: str
    version: str
    media_type: str
    capability: str

    def to_record(self) -> dict[str, str]:
        return {
            "capability": self.capability,
            "media_type": self.media_type,
            "name": self.name,
            "version": self.version,
        }

    @property
    def sha256(self) -> str:
        value = {"bounds": PARSER_BOUNDS.to_record(), "profile": self.to_record()}
        return _sha256(_canonical_bytes(value))


HTML_PROFILE = Profile(
    "adaivy-structured-html-candidate-v1", "1.0.0", "text/html",
    "restricted structured HTML/MathML candidate extraction",
)
TEX_PROFILE = Profile(
    "adaivy-nonexecuting-tex-candidate-v1", "1.0.0", "application/x-tex",
    "non-expanding TeX lexical candidate extraction",
)
PDF_PROFILE = Profile(
    "adaivy-born-digital-pdf-candidate-v1", "1.0.0", "application/pdf",
    "restricted uncompressed born-digital PDF literal extraction",
)
OCR_PROFILE = Profile(
    "adaivy-ocr-deferred-v1", "1.0.0", "application/vnd.adaivy.ocr-request",
    "deferred OCR outcome capture only",
)
PROFILES = {profile.name: profile for profile in (HTML_PROFILE, TEX_PROFILE, PDF_PROFILE, OCR_PROFILE)}


@dataclass(frozen=True)
class ParseRequest:
    request_id: str
    source_id: str
    content_object_id: str
    representation_id: str
    media_type: str
    profile_name: str
    original_bytes: bytes
    original_sha256: str
    original_byte_length: int
    parser_policy_sha256: str
    schema_version: str = REQUEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_SCHEMA:
            raise ValueError("unsupported parse request schema")
        for field in ("request_id", "source_id", "content_object_id", "representation_id"):
            _require_identifier(getattr(self, field), field)
        if not isinstance(self.original_bytes, bytes):
            raise TypeError("original_bytes must be bytes")
        profile = PROFILES.get(self.profile_name)
        if profile is None:
            raise ValueError("unknown parser profile")
        if profile.media_type != self.media_type:
            raise ValueError("media type does not match parser profile")
        if self.original_byte_length != len(self.original_bytes):
            raise ValueError("declared original byte length mismatch")
        if self.original_sha256 != _sha256(self.original_bytes):
            raise ValueError("declared original byte hash mismatch")
        if self.parser_policy_sha256 != PARSER_BOUNDS.policy_sha256:
            raise ValueError("parser policy hash mismatch")
        if len(self.original_bytes) > PARSER_BOUNDS.max_raw_input_bytes:
            raise ValueError("raw_input_byte_bound_exceeded")

    @classmethod
    def create(
        cls, *, request_id: str, source_id: str, content_object_id: str,
        representation_id: str, media_type: str, profile_name: str,
        original_bytes: bytes,
    ) -> "ParseRequest":
        return cls(
            request_id=request_id,
            source_id=source_id,
            content_object_id=content_object_id,
            representation_id=representation_id,
            media_type=media_type,
            profile_name=profile_name,
            original_bytes=original_bytes,
            original_sha256=_sha256(original_bytes),
            original_byte_length=len(original_bytes),
            parser_policy_sha256=PARSER_BOUNDS.policy_sha256,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any], original_bytes: bytes) -> "ParseRequest":
        expected = {
            "content_object_id", "media_type", "original_byte_length", "original_sha256",
            "parser_policy_sha256", "profile_name", "representation_id", "request_id",
            "schema_version", "source_id",
        }
        _strict_keys(record, expected, "parse request")
        return cls(original_bytes=original_bytes, **dict(record))

    def to_record(self) -> dict[str, Any]:
        return {
            "content_object_id": self.content_object_id,
            "media_type": self.media_type,
            "original_byte_length": self.original_byte_length,
            "original_sha256": self.original_sha256,
            "parser_policy_sha256": self.parser_policy_sha256,
            "profile_name": self.profile_name,
            "representation_id": self.representation_id,
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class ByteAnchor:
    original_sha256: str
    start: int
    end: int
    slice_sha256: str
    page_index: int | None = None
    object_id: str | None = None

    @classmethod
    def create(
        cls, original: bytes, start: int, end: int, *, page_index: int | None = None,
        object_id: str | None = None,
    ) -> "ByteAnchor":
        if not 0 <= start < end <= len(original):
            raise ContentRejected("anchor_invalid")
        return cls(
            original_sha256=_sha256(original), start=start, end=end,
            slice_sha256=_sha256(original[start:end]), page_index=page_index,
            object_id=object_id,
        )

    def validate(self, original: bytes) -> None:
        if self.original_sha256 != _sha256(original):
            raise ContentRejected("anchor_original_hash_mismatch")
        if not 0 <= self.start < self.end <= len(original):
            raise ContentRejected("anchor_invalid")
        if self.slice_sha256 != _sha256(original[self.start:self.end]):
            raise ContentRejected("anchor_slice_hash_mismatch")
        if (
            self.page_index is not None
            and (
                isinstance(self.page_index, bool)
                or not isinstance(self.page_index, int)
                or not 0 <= self.page_index <= PARSER_BOUNDS.max_anchor_page_index
            )
        ):
            raise ContentRejected("anchor_page_index_invalid")
        if self.object_id is not None and (
            not isinstance(self.object_id, str)
            or not self.object_id
            or len(self.object_id.encode("utf-8")) > PARSER_BOUNDS.max_anchor_object_id_bytes
            or any(ord(character) < 0x20 for character in self.object_id)
        ):
            raise ContentRejected("anchor_object_id_invalid")

    def to_record(self) -> dict[str, Any]:
        return {
            "end": self.end,
            "object_id": self.object_id,
            "original_sha256": self.original_sha256,
            "page_index": self.page_index,
            "slice_sha256": self.slice_sha256,
            "start": self.start,
        }


@dataclass(frozen=True)
class ParsedSegment:
    segment_id: str
    kind: str
    normalized_text: str
    anchor: ByteAnchor
    load_bearing: bool

    def __post_init__(self) -> None:
        _require_identifier(self.segment_id, "segment_id")
        if self.kind not in {"text", "formula"}:
            raise ValueError("invalid segment kind")
        if not isinstance(self.normalized_text, str) or not self.normalized_text.strip():
            raise ValueError("empty segment forbidden")
        if (
            not isinstance(self.load_bearing, bool)
            or self.load_bearing != (self.kind == "formula")
        ):
            raise ValueError("segment load-bearing semantics invalid")

    def to_record(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_record(), "kind": self.kind,
            "load_bearing": self.load_bearing, "normalized_text": self.normalized_text,
            "segment_id": self.segment_id,
        }


@dataclass(frozen=True)
class ParsedReference:
    reference_id: str
    target: str
    anchor: ByteAnchor

    def __post_init__(self) -> None:
        _require_identifier(self.reference_id, "reference_id")
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("empty reference target")

    def to_record(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_record(), "reference_id": self.reference_id,
            "target": self.target,
        }


@dataclass(frozen=True)
class AdapterOutcome:
    segments: tuple[ParsedSegment, ...]
    references: tuple[ParsedReference, ...] = ()
    warnings: tuple[str, ...] = ()
    transformations: tuple[str, ...] = ("unicode_whitespace_collapse",)


@dataclass(frozen=True)
class OperationContext:
    operation_id: str
    attempt_ordinal: int
    duration_ms: int
    worker_exit_code: int | None
    stdout_sha256: str
    stderr_sha256: str
    stdout_byte_length: int
    stderr_byte_length: int

    @classmethod
    def create(
        cls, operation_id: str, *, attempt_ordinal: int = 1, duration_ms: int = 0,
        worker_exit_code: int | None = None, stdout: bytes = b"", stderr: bytes = b"",
    ) -> "OperationContext":
        return cls(
            operation_id, attempt_ordinal, duration_ms, worker_exit_code,
            _sha256(stdout), _sha256(stderr), len(stdout), len(stderr),
        )

    def __post_init__(self) -> None:
        _require_identifier(self.operation_id, "operation_id")
        if self.attempt_ordinal < 1 or self.duration_ms < 0:
            raise ValueError("invalid operation counters")
        _require_sha256(self.stdout_sha256, "stdout_sha256")
        _require_sha256(self.stderr_sha256, "stderr_sha256")
        if not 0 <= self.stdout_byte_length <= MAX_WORKER_CAPTURE_BYTES:
            raise ValueError("stdout byte count is invalid")
        if not 0 <= self.stderr_byte_length <= MAX_WORKER_CAPTURE_BYTES:
            raise ValueError("stderr byte count is invalid")

    def to_record(self) -> dict[str, Any]:
        return {
            "attempt_ordinal": self.attempt_ordinal, "duration_ms": self.duration_ms,
            "operation_id": self.operation_id, "stderr_sha256": self.stderr_sha256,
            "stdout_sha256": self.stdout_sha256, "worker_exit_code": self.worker_exit_code,
            "stderr_byte_length": self.stderr_byte_length,
            "stdout_byte_length": self.stdout_byte_length,
        }


@dataclass(frozen=True)
class WorkerExecution:
    """Captured result returned by an explicitly supplied isolated-worker port.

    Raw stdout and stderr are hashed and discarded by :meth:`capture`.  This
    record is not proof that an OS sandbox enforced the declared bounds; that
    remains an activation prerequisite for a future pinned worker.
    """

    outcome: AdapterOutcome | None
    operation: OperationContext
    status: str
    failure_code: str | None
    stdout_byte_length: int
    stderr_byte_length: int

    @classmethod
    def capture(
        cls, *, outcome: AdapterOutcome | None, operation_id: str,
        status: str = "completed", failure_code: str | None = None,
        attempt_ordinal: int = 1, duration_ms: int = 0,
        worker_exit_code: int | None = 0, stdout: bytes = b"", stderr: bytes = b"",
    ) -> "WorkerExecution":
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise TypeError("worker stdout and stderr captures must be bytes")
        if len(stdout) > MAX_WORKER_CAPTURE_BYTES or len(stderr) > MAX_WORKER_CAPTURE_BYTES:
            raise ValueError("worker output capture bound exceeded")
        return cls(
            outcome=outcome,
            operation=OperationContext.create(
                operation_id, attempt_ordinal=attempt_ordinal, duration_ms=duration_ms,
                worker_exit_code=worker_exit_code, stdout=stdout, stderr=stderr,
            ),
            status=status,
            failure_code=failure_code,
            stdout_byte_length=len(stdout),
            stderr_byte_length=len(stderr),
        )

    def __post_init__(self) -> None:
        if self.status not in {
            "completed", "content_rejected", "failed", "missing_dependency",
            "sandbox_rejected",
        }:
            raise ValueError("unknown worker execution status")
        if not 0 <= self.stdout_byte_length <= MAX_WORKER_CAPTURE_BYTES:
            raise ValueError("worker stdout byte count is invalid")
        if not 0 <= self.stderr_byte_length <= MAX_WORKER_CAPTURE_BYTES:
            raise ValueError("worker stderr byte count is invalid")
        if self.stdout_byte_length != self.operation.stdout_byte_length:
            raise ValueError("worker stdout byte count differs from operation capture")
        if self.stderr_byte_length != self.operation.stderr_byte_length:
            raise ValueError("worker stderr byte count differs from operation capture")
        if self.status == "completed":
            if self.outcome is None or self.failure_code is not None:
                raise ValueError("completed worker execution requires only an outcome")
            if self.operation.worker_exit_code not in {None, 0}:
                raise ValueError("completed worker execution has a nonzero exit")
        elif self.outcome is not None or not self.failure_code:
            raise ValueError("unsuccessful worker execution requires only a failure code")


class ContentRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


CROSS_FORMAT_AMBIGUITY = "cross_format_envelope_ambiguity"


def _has_structural_pdf_envelope(original: bytes) -> bool:
    """Recognise a classic PDF envelope by linked xref structure, not a token."""
    for header in re.finditer(rb"%PDF-1\.[0-7]\r?\n", original):
        base = header.start()
        tail = original[base:]
        for footer in re.finditer(
            rb"startxref\r?\n([0-9]+)\r?\n%%EOF(?:\r?\n|\Z)", tail,
        ):
            offset = int(footer.group(1))
            if offset <= 0 or offset >= footer.start() or not tail.startswith(b"xref\n", offset):
                continue
            subsection = re.match(rb"xref\n0 ([1-9][0-9]*)\n", tail[offset:])
            if subsection is None:
                continue
            size = int(subsection.group(1))
            if size > 1_025:
                continue
            entries_start = offset + len(subsection.group(0))
            entries_end = entries_start + size * 20
            entries = tail[entries_start:entries_end]
            if len(entries) != size * 20 or any(
                re.fullmatch(rb"[0-9]{10} [0-9]{5} [nf] \n", entries[index:index + 20]) is None
                for index in range(0, len(entries), 20)
            ):
                continue
            trailer = tail[entries_end:footer.start()]
            if re.search(rb"\btrailer\s*<<[^<>]*/Size\s+" + str(size).encode("ascii") + rb"\b[^<>]*/Root\s+[1-9][0-9]*\s+[0-9]+\s+R\b[^<>]*>>\s*\Z", trailer, re.DOTALL):
                return True
    return False


def _has_structural_html_envelope(original: bytes) -> bool:
    """Recognise a complete HTML root/body pair while ignoring ordinary < math."""
    try:
        text = original.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return False
    for root in re.finditer(r"<html(?:\s[^<>]*)?>", text, re.IGNORECASE):
        close = re.search(r"</html\s*>", text[root.end():], re.IGNORECASE)
        if close is None:
            continue
        candidate = text[root.start():root.end() + close.end()]
        body_open = re.search(r"<body(?:\s[^<>]*)?>", candidate, re.IGNORECASE)
        body_close = re.search(r"</body\s*>", candidate, re.IGNORECASE)
        if (
            body_open is not None and body_close is not None
            and body_open.end() <= body_close.start()
            and len(re.findall(r"<html(?:\s[^<>]*)?>", candidate, re.IGNORECASE)) == 1
            and len(re.findall(r"</html\s*>", candidate, re.IGNORECASE)) == 1
        ):
            return True
    return False


def _has_structural_tex_envelope(original: bytes) -> bool:
    """Recognise a section-plus-formula source shape, not isolated math notation."""
    try:
        text = original.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return False
    section = re.search(r"\\(?:sub)?section\{[^{}\r\n]+\}", text)
    if section is None:
        return False
    inline = re.search(r"(?<!\\)\$(?!\$)[^$\r\n]+(?<!\\)\$", text[section.end():])
    display = re.search(r"\\\[[^\]]+\\\]", text[section.end():], re.DOTALL)
    return inline is not None or display is not None


def _reject_cross_format_ambiguity(original: bytes, expected: str) -> None:
    detected = {
        name for name, present in (
            ("html", _has_structural_html_envelope(original)),
            ("tex", _has_structural_tex_envelope(original)),
            ("pdf", _has_structural_pdf_envelope(original)),
        ) if present
    }
    if detected - {expected}:
        raise ContentRejected(CROSS_FORMAT_AMBIGUITY)


class ParserDependencyMissing(RuntimeError):
    def __init__(self, dependency_id: str):
        _require_identifier(dependency_id, "dependency_id")
        super().__init__(dependency_id)
        self.dependency_id = dependency_id


@runtime_checkable
class ParserAdapter(Protocol):
    """Replaceable port for a future separately pinned parser dependency."""

    name: str
    version: str
    implementation_sha256: str
    dependency_environment_sha256: str

    def supports(self, profile: Profile) -> bool: ...

    def parse(self, request: ParseRequest) -> AdapterOutcome: ...


@runtime_checkable
class ParserWorker(Protocol):
    """Explicit production port; implementations must enforce isolation outside Python."""

    name: str
    version: str
    implementation_sha256: str
    dependency_environment_sha256: str
    sandbox_contract: str

    def execute(self, request: ParseRequest) -> WorkerExecution: ...


_BUILTIN_MANIFEST = {
    "activation_status": PARSER_ACTIVATION_STATUS,
    "adapter": "adaivy-restricted-stdlib",
    "profiles": [HTML_PROFILE.to_record(), TEX_PROFILE.to_record(), PDF_PROFILE.to_record()],
    "security": "no network, subprocess, compilation, rendering, entity resolution, or OCR",
    "version": PARSER_VERSION,
}


class RestrictedStdlibAdapter:
    """Fixture oracle only; not approved as production HTML/TeX/PDF support."""

    name = "adaivy-restricted-stdlib"
    version = PARSER_VERSION
    implementation_sha256 = _sha256(_canonical_bytes(_BUILTIN_MANIFEST))
    dependency_environment_sha256 = _sha256(b"python-standard-library-only")

    def supports(self, profile: Profile) -> bool:
        return profile.name in {HTML_PROFILE.name, TEX_PROFILE.name, PDF_PROFILE.name}

    def parse(self, request: ParseRequest) -> AdapterOutcome:
        if request.profile_name == HTML_PROFILE.name:
            return _parse_html(request.original_bytes)
        if request.profile_name == TEX_PROFILE.name:
            return _parse_tex(request.original_bytes)
        if request.profile_name == PDF_PROFILE.name:
            return _parse_pdf(request.original_bytes)
        raise ContentRejected("unsupported_parser_profile")


def _adapter_identity(adapter: ParserAdapter | None, profile: Profile) -> dict[str, str]:
    if adapter is None:
        name, version = "none", "0"
        implementation = _sha256(b"no-parser-adapter")
        environment = _sha256(b"no-dependency-environment")
    else:
        name, version = adapter.name, adapter.version
        implementation = adapter.implementation_sha256
        environment = adapter.dependency_environment_sha256
    for value, field in (
        (implementation, "implementation_sha256"),
        (environment, "dependency_environment_sha256"),
    ):
        _require_sha256(value, field)
    return {
        "adapter_implementation_sha256": implementation,
        "adapter_name": name,
        "adapter_version": version,
        "dependency_environment_sha256": environment,
        "policy_sha256": PARSER_BOUNDS.policy_sha256,
        "profile_name": profile.name,
        "profile_sha256": profile.sha256,
        "profile_version": profile.version,
    }


TRUST_EFFECTS = {
    "applicability": "unchanged",
    "graph_admission": "unchanged",
    "mathematical_warrant": "unchanged",
    "novelty": "not_assessed",
    "publication": "not_authorized",
    "redistribution": "not_authorized",
    "significance": "not_assessed",
}


@dataclass(frozen=True)
class ParseResult:
    request: ParseRequest
    parser_identity: Mapping[str, str]
    disposition: str
    failure_code: str | None
    segments: tuple[ParsedSegment, ...]
    references: tuple[ParsedReference, ...]
    warnings: tuple[str, ...]
    transformations: tuple[str, ...]
    operation: OperationContext
    adapter_status: str

    def semantic_record(self) -> dict[str, Any]:
        formula_ids = [item.segment_id for item in self.segments if item.kind == "formula"]
        return {
            "bounds": PARSER_BOUNDS.to_record(),
            "disposition": self.disposition,
            "failure_code": self.failure_code,
            "formula_segment_ids": formula_ids,
            "original_lineage": {
                "byte_length": self.request.original_byte_length,
                "sha256": self.request.original_sha256,
            },
            "parser_identity": dict(self.parser_identity),
            "references": [item.to_record() for item in self.references],
            "request": self.request.to_record(),
            "schema_version": RESULT_SCHEMA,
            "segments": [item.to_record() for item in self.segments],
            "transformations": list(self.transformations),
            "trust_effects": dict(TRUST_EFFECTS),
            "warnings": list(self.warnings),
        }

    @property
    def semantic_sha256(self) -> str:
        return _sha256(_canonical_bytes(self.semantic_record()))

    def operational_record(self) -> dict[str, Any]:
        return {
            "adapter_status": self.adapter_status,
            "operation": self.operation.to_record(),
            "semantic_sha256": self.semantic_sha256,
        }

    @property
    def operational_sha256(self) -> str:
        return _sha256(_canonical_bytes(self.operational_record()))

    def to_record(self) -> dict[str, Any]:
        return {
            "operational": self.operational_record(),
            "operational_sha256": self.operational_sha256,
            "schema_version": RESULT_SCHEMA,
            "semantic": self.semantic_record(),
            "semantic_sha256": self.semantic_sha256,
        }


def _bounded_outcome(request: ParseRequest, outcome: AdapterOutcome) -> AdapterOutcome:
    if len(outcome.segments) > PARSER_BOUNDS.max_segments:
        raise ContentRejected("segment_count_bound_exceeded")
    formulas = sum(item.kind == "formula" for item in outcome.segments)
    if formulas > PARSER_BOUNDS.max_formulas:
        raise ContentRejected("formula_count_bound_exceeded")
    if len(outcome.references) > PARSER_BOUNDS.max_references:
        raise ContentRejected("reference_count_bound_exceeded")
    if len(outcome.warnings) > PARSER_BOUNDS.max_warnings:
        raise ContentRejected("warning_count_bound_exceeded")
    if len(outcome.transformations) > PARSER_BOUNDS.max_transformations:
        raise ContentRejected("transformation_count_bound_exceeded")
    segment_ids = [item.segment_id for item in outcome.segments]
    if len(segment_ids) != len(set(segment_ids)):
        raise ContentRejected("duplicate_segment_identity")
    reference_ids = [item.reference_id for item in outcome.references]
    if len(reference_ids) != len(set(reference_ids)):
        raise ContentRejected("duplicate_reference_identity")
    for segment in outcome.segments:
        segment.anchor.validate(request.original_bytes)
    for reference in outcome.references:
        reference.anchor.validate(request.original_bytes)
    decoded = sum(len(item.normalized_text.encode("utf-8")) for item in outcome.segments)
    decoded += sum(len(item.target.encode("utf-8")) for item in outcome.references)
    if decoded > PARSER_BOUNDS.max_decoded_output_bytes:
        raise ContentRejected("decoded_output_byte_bound_exceeded")
    if decoded > max(1, request.original_byte_length) * PARSER_BOUNDS.max_expansion_ratio:
        raise ContentRejected("decoded_output_expansion_ratio_exceeded")
    if any(not warning or len(warning.encode("utf-8")) > 256 for warning in outcome.warnings):
        raise ContentRejected("warning_invalid")
    if any(
        not isinstance(item, str)
        or not item
        or len(item.encode("utf-8")) > 256
        for item in outcome.transformations
    ):
        raise ContentRejected("transformation_invalid")
    return outcome


def run_parser(
    request: ParseRequest, *, adapter: ParserAdapter | None = None,
    operation: OperationContext | None = None,
) -> ParseResult:
    """Run one injected parser and retain every outcome without trust promotion."""
    profile = PROFILES[request.profile_name]
    operation = operation or OperationContext.create("operation.parse.default.v1")
    if profile is OCR_PROFILE:
        return ParseResult(
            request, _adapter_identity(None, profile), "failed", "ocr_deferred",
            (), (), (), (), operation, "not_invoked",
        )
    adapter = adapter or RestrictedStdlibAdapter()
    identity = _adapter_identity(adapter, profile)
    try:
        if operation.duration_ms > PARSER_BOUNDS.max_wall_seconds * 1_000:
            raise ContentRejected("parser_wall_time_bound_exceeded")
        if operation.worker_exit_code not in {None, 0}:
            raise ContentRejected("parser_worker_nonzero_exit")
        if not adapter.supports(profile):
            raise ContentRejected("unsupported_parser_profile")
        outcome = _bounded_outcome(request, adapter.parse(request))
        if not outcome.segments:
            raise ContentRejected("empty_parse_proposal")
        return ParseResult(
            request, identity, "candidate_proposal", None, outcome.segments,
            outcome.references, outcome.warnings, outcome.transformations,
            operation, "completed",
        )
    except ParserDependencyMissing as error:
        return ParseResult(
            request, identity, "failed", f"missing_dependency:{error.dependency_id}",
            (), (), (), (), operation, "missing_dependency",
        )
    except ContentRejected as error:
        return ParseResult(
            request, identity, "quarantined", error.reason, (), (), (), (),
            operation, "rejected",
        )
    except Exception as error:  # Adapter messages are untrusted; retain only type hash.
        failure_fingerprint = _sha256(type(error).__qualname__.encode("utf-8"))[7:23]
        return ParseResult(
            request, identity, "failed", f"adapter_failure:{failure_fingerprint}",
            (), (), (), (), operation, "failed",
        )


class _CapturedWorkerAdapter:
    """Expose one already-captured worker outcome to the common validator."""

    def __init__(self, worker: ParserWorker, outcome: AdapterOutcome) -> None:
        if worker.sandbox_contract != "external-os-sandbox-contract-v1":
            raise ValueError("worker sandbox contract is not declared")
        self.name = worker.name
        self.version = worker.version
        self.implementation_sha256 = worker.implementation_sha256
        self.dependency_environment_sha256 = worker.dependency_environment_sha256
        self._outcome = outcome

    def supports(self, profile: Profile) -> bool:
        return True

    def parse(self, request: ParseRequest) -> AdapterOutcome:
        return self._outcome


def run_production_parser(
    request: ParseRequest, *, worker: ParserWorker | None = None,
) -> ParseResult:
    """Run only an explicitly supplied worker port; absence fails closed.

    The repository ships a pre-activation named-Darwin sandbox boundary but no
    approved parser/sandbox pairing. A worker declaration remains integration
    evidence, not approval of a concrete parser dependency or platform.
    """

    profile = PROFILES[request.profile_name]
    if worker is None:
        return ParseResult(
            request, _adapter_identity(None, profile), "failed",
            f"missing_dependency:{PRODUCTION_WORKER_DEPENDENCY_ID}",
            (), (), (), (),
            OperationContext.create("operation.parse.worker-not-configured"),
            "missing_dependency",
        )
    try:
        execution = worker.execute(request)
        if not isinstance(execution, WorkerExecution):
            raise TypeError("worker returned an invalid execution record")
        if execution.status == "completed":
            assert execution.outcome is not None
            adapter = _CapturedWorkerAdapter(worker, execution.outcome)
            return run_parser(request, adapter=adapter, operation=execution.operation)
        identity = _adapter_identity(worker, profile)
        if execution.status == "missing_dependency":
            disposition, adapter_status = "failed", "missing_dependency"
        elif execution.status in {"content_rejected", "sandbox_rejected"}:
            disposition, adapter_status = "quarantined", "rejected"
        else:
            disposition, adapter_status = "failed", "failed"
        return ParseResult(
            request, identity, disposition, execution.failure_code,
            (), (), (), (), execution.operation, adapter_status,
        )
    except ParserDependencyMissing as error:
        return ParseResult(
            request, _adapter_identity(worker, profile), "failed",
            f"missing_dependency:{error.dependency_id}", (), (), (), (),
            OperationContext.create("operation.parse.worker-dependency-missing"),
            "missing_dependency",
        )
    except Exception as error:
        failure_fingerprint = _sha256(type(error).__qualname__.encode("utf-8"))[7:23]
        return ParseResult(
            request, _adapter_identity(worker, profile), "failed",
            f"worker_boundary_failure:{failure_fingerprint}", (), (), (), (),
            OperationContext.create("operation.parse.worker-boundary-failed"),
            "failed",
        )


def quarantine_before_worker(request: ParseRequest, failure_code: str) -> ParseResult:
    """Retain a deterministic pre-worker rejection without invoking a parser.

    This is used for service-level media lineage and content-signature gates.
    It deliberately carries no segments, references, or reconstructive text.
    """
    _require_identifier(failure_code, "failure_code")
    profile = PROFILES[request.profile_name]
    return ParseResult(
        request,
        _adapter_identity(None, profile),
        "quarantined",
        failure_code,
        (),
        (),
        (),
        (),
        OperationContext.create("operation.parse.pre-worker-quarantine"),
        "rejected",
    )


def verify_result_record(record: Mapping[str, Any], original_bytes: bytes | None = None) -> None:
    """Strictly verify a raw result envelope, hashes, anchors, and no extra fields."""
    _strict_keys(
        record,
        {"operational", "operational_sha256", "schema_version", "semantic", "semantic_sha256"},
        "parse result",
    )
    if record["schema_version"] != RESULT_SCHEMA:
        raise ValueError("unsupported parse result schema")
    semantic = record["semantic"]
    semantic_keys = {
        "bounds", "disposition", "failure_code", "formula_segment_ids",
        "original_lineage", "parser_identity", "references", "request",
        "schema_version", "segments", "transformations", "trust_effects", "warnings",
    }
    _strict_keys(semantic, semantic_keys, "semantic result")
    if semantic["schema_version"] != RESULT_SCHEMA:
        raise ValueError("unsupported semantic result schema")
    if semantic["disposition"] not in {"candidate_proposal", "quarantined", "failed"}:
        raise ValueError("invalid parse disposition")
    _strict_keys(record["operational"], {"adapter_status", "operation", "semantic_sha256"}, "operational result")
    _strict_keys(
        record["operational"]["operation"],
        {
            "attempt_ordinal", "duration_ms", "operation_id", "stderr_byte_length",
            "stderr_sha256", "stdout_byte_length", "stdout_sha256", "worker_exit_code",
        },
        "operation",
    )
    operation = record["operational"]["operation"]
    if operation["attempt_ordinal"] < 1 or operation["duration_ms"] < 0:
        raise ValueError("invalid operational counters")
    _require_sha256(operation["stdout_sha256"], "operational stdout sha256")
    _require_sha256(operation["stderr_sha256"], "operational stderr sha256")
    for name in ("stdout_byte_length", "stderr_byte_length"):
        if (
            isinstance(operation[name], bool) or not isinstance(operation[name], int)
            or not 0 <= operation[name] <= MAX_WORKER_CAPTURE_BYTES
        ):
            raise ValueError("operational output byte count is invalid")
    worker_exit_code = operation["worker_exit_code"]
    if worker_exit_code is not None and (
        isinstance(worker_exit_code, bool)
        or not isinstance(worker_exit_code, int)
        or not -255 <= worker_exit_code <= 255
    ):
        raise ValueError("operational worker exit status is invalid")
    if record["operational"]["adapter_status"] not in {
        "completed", "failed", "missing_dependency", "not_invoked", "rejected"
    }:
        raise ValueError("invalid adapter status")
    expected_semantic = _sha256(_canonical_bytes(semantic))
    if record["semantic_sha256"] != expected_semantic:
        raise ValueError("semantic hash mismatch")
    if record["operational"]["semantic_sha256"] != expected_semantic:
        raise ValueError("operational semantic binding mismatch")
    if record["operational_sha256"] != _sha256(_canonical_bytes(record["operational"])):
        raise ValueError("operational hash mismatch")
    if semantic["bounds"] != PARSER_BOUNDS.to_record():
        raise ValueError("parser bounds mismatch")
    if semantic["trust_effects"] != TRUST_EFFECTS:
        raise ValueError("trust effects mismatch")
    request_record = semantic["request"]
    expected_request_keys = set(ParseRequest.create(
        request_id="verification.request", source_id="verification.source",
        content_object_id="verification.content", representation_id="verification.representation",
        media_type=HTML_PROFILE.media_type, profile_name=HTML_PROFILE.name,
        original_bytes=b"",
    ).to_record())
    _strict_keys(request_record, expected_request_keys, "embedded parse request")
    if request_record["schema_version"] != REQUEST_SCHEMA:
        raise ValueError("unsupported embedded request schema")
    identity = semantic["parser_identity"]
    _strict_keys(
        identity,
        {
            "adapter_implementation_sha256", "adapter_name", "adapter_version",
            "dependency_environment_sha256", "policy_sha256", "profile_name",
            "profile_sha256", "profile_version",
        },
        "parser identity",
    )
    for field in (
        "adapter_implementation_sha256", "dependency_environment_sha256",
        "policy_sha256", "profile_sha256",
    ):
        _require_sha256(identity[field], field)
    profile = PROFILES.get(identity["profile_name"])
    if profile is None or identity["profile_sha256"] != profile.sha256:
        raise ValueError("parser profile hash mismatch")
    if identity["profile_version"] != profile.version:
        raise ValueError("parser profile version mismatch")
    if identity["policy_sha256"] != PARSER_BOUNDS.policy_sha256:
        raise ValueError("parser identity policy mismatch")
    _require_identifier(identity["adapter_name"], "adapter_name")
    _require_identifier(identity["adapter_version"], "adapter_version")
    if request_record["profile_name"] != profile.name:
        raise ValueError("request/parser profile mismatch")
    if request_record["media_type"] != profile.media_type:
        raise ValueError("request media/profile mismatch")
    if request_record["parser_policy_sha256"] != PARSER_BOUNDS.policy_sha256:
        raise ValueError("request parser policy mismatch")
    lineage = semantic["original_lineage"]
    _strict_keys(lineage, {"byte_length", "sha256"}, "original lineage")
    if request_record["original_sha256"] != lineage["sha256"]:
        raise ValueError("lineage/request hash mismatch")
    if request_record["original_byte_length"] != lineage["byte_length"]:
        raise ValueError("lineage/request length mismatch")
    _require_sha256(lineage["sha256"], "original lineage sha256")
    if original_bytes is not None:
        if len(original_bytes) != lineage["byte_length"]:
            raise ValueError("original byte length mismatch")
        if _sha256(original_bytes) != lineage["sha256"]:
            raise ValueError("original byte hash mismatch")
    if not isinstance(semantic["segments"], list) or len(semantic["segments"]) > PARSER_BOUNDS.max_segments:
        raise ValueError("segment count bound exceeded")
    if not isinstance(semantic["references"], list) or len(semantic["references"]) > PARSER_BOUNDS.max_references:
        raise ValueError("reference count bound exceeded")
    if not isinstance(semantic["warnings"], list) or len(semantic["warnings"]) > PARSER_BOUNDS.max_warnings:
        raise ValueError("warning count bound exceeded")
    if not isinstance(semantic["formula_segment_ids"], list) or len(semantic["formula_segment_ids"]) > PARSER_BOUNDS.max_formulas or len(set(semantic["formula_segment_ids"])) != len(semantic["formula_segment_ids"]):
        raise ValueError("formula segment identities invalid")
    formula_ids = set(semantic["formula_segment_ids"])
    segment_ids: set[str] = set()
    actual_formula_ids: set[str] = set()
    for segment in semantic["segments"]:
        _strict_keys(segment, {"anchor", "kind", "load_bearing", "normalized_text", "segment_id"}, "segment")
        _strict_keys(
            segment["anchor"],
            {"end", "object_id", "original_sha256", "page_index", "slice_sha256", "start"},
            "byte anchor",
        )
        if not segment["normalized_text"]:
            raise ValueError("empty segment forbidden")
        if (
            segment["kind"] not in {"text", "formula"}
            or not isinstance(segment["load_bearing"], bool)
            or segment["load_bearing"] != (segment["kind"] == "formula")
        ):
            raise ValueError("invalid segment semantics")
        if segment["anchor"]["original_sha256"] != lineage["sha256"]:
            raise ValueError("anchor original hash mismatch")
        _validate_anchor_metadata_record(segment["anchor"])
        if not 0 <= segment["anchor"]["start"] < segment["anchor"]["end"] <= lineage["byte_length"]:
            raise ValueError("anchor range invalid")
        if segment["segment_id"] in segment_ids:
            raise ValueError("duplicate segment identity")
        segment_ids.add(segment["segment_id"])
        if segment["kind"] == "formula":
            actual_formula_ids.add(segment["segment_id"])
        _require_sha256(segment["anchor"]["slice_sha256"], "anchor slice sha256")
        if original_bytes is not None:
            start, end = segment["anchor"]["start"], segment["anchor"]["end"]
            if _sha256(original_bytes[start:end]) != segment["anchor"]["slice_sha256"]:
                raise ValueError("anchor slice hash mismatch")
    if formula_ids != actual_formula_ids:
        raise ValueError("formula segment identity mismatch")
    reference_ids: set[str] = set()
    for reference in semantic["references"]:
        _strict_keys(reference, {"anchor", "reference_id", "target"}, "reference")
        _strict_keys(
            reference["anchor"],
            {"end", "object_id", "original_sha256", "page_index", "slice_sha256", "start"},
            "reference anchor",
        )
        anchor = reference["anchor"]
        _require_identifier(reference["reference_id"], "reference_id")
        if reference["reference_id"] in reference_ids:
            raise ValueError("duplicate reference identity")
        reference_ids.add(reference["reference_id"])
        if not isinstance(reference["target"], str) or not reference["target"]:
            raise ValueError("empty reference target")
        if anchor["original_sha256"] != lineage["sha256"]:
            raise ValueError("reference anchor original hash mismatch")
        _validate_anchor_metadata_record(anchor)
        if not 0 <= anchor["start"] < anchor["end"] <= lineage["byte_length"]:
            raise ValueError("reference anchor range invalid")
        _require_sha256(anchor["slice_sha256"], "reference anchor slice sha256")
        if original_bytes is not None and _sha256(original_bytes[anchor["start"]:anchor["end"]]) != anchor["slice_sha256"]:
            raise ValueError("reference anchor slice hash mismatch")
    if semantic["disposition"] == "candidate_proposal" and not semantic["segments"]:
        raise ValueError("empty proposal forbidden")
    if semantic["disposition"] == "candidate_proposal" and semantic["failure_code"] is not None:
        raise ValueError("candidate proposal cannot retain a failure code")
    if semantic["disposition"] != "candidate_proposal" and (semantic["segments"] or semantic["references"]):
        raise ValueError("failed or quarantined result cannot expose parsed content")
    if any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256 for item in semantic["warnings"]):
        raise ValueError("invalid parser warning")
    if (
        not isinstance(semantic["transformations"], list)
        or len(semantic["transformations"]) > PARSER_BOUNDS.max_transformations
    ):
        raise ValueError("parser transformation count bound exceeded")
    if any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256 for item in semantic["transformations"]):
        raise ValueError("invalid parser transformation")
    decoded = sum(len(item["normalized_text"].encode("utf-8")) for item in semantic["segments"])
    decoded += sum(len(item["target"].encode("utf-8")) for item in semantic["references"])
    if decoded > PARSER_BOUNDS.max_decoded_output_bytes:
        raise ValueError("decoded output byte bound exceeded")
    if decoded > max(1, lineage["byte_length"]) * PARSER_BOUNDS.max_expansion_ratio:
        raise ValueError("decoded output expansion ratio exceeded")
    if semantic["disposition"] == "candidate_proposal":
        if operation["duration_ms"] > PARSER_BOUNDS.max_wall_seconds * 1_000:
            raise ValueError("successful parser wall time bound exceeded")
        if operation["worker_exit_code"] not in {None, 0}:
            raise ValueError("successful parser worker exit invalid")
    disposition = semantic["disposition"]
    adapter_status = record["operational"]["adapter_status"]
    failure_code = semantic["failure_code"]
    if failure_code is not None:
        _require_identifier(failure_code, "failure_code")
    exposed_content = any((
        semantic["segments"], semantic["references"], semantic["warnings"],
        semantic["transformations"], semantic["formula_segment_ids"],
    ))
    if disposition == "candidate_proposal":
        if (
            adapter_status != "completed" or failure_code is not None
            or not semantic["segments"] or profile is OCR_PROFILE
        ):
            raise ValueError("candidate proposal status mapping is contradictory")
        if worker_exit_code not in {None, 0}:
            raise ValueError("candidate proposal exit status is contradictory")
    elif disposition == "quarantined":
        if adapter_status != "rejected" or failure_code is None or exposed_content:
            raise ValueError("quarantined status mapping is contradictory")
    else:
        if adapter_status not in {"failed", "missing_dependency", "not_invoked"}:
            raise ValueError("failed status mapping is contradictory")
        if failure_code is None or exposed_content:
            raise ValueError("failed result mapping is contradictory")
        if adapter_status == "missing_dependency" and (
            not failure_code.startswith("missing_dependency:") or worker_exit_code is not None
        ):
            raise ValueError("missing dependency status mapping is contradictory")
        if adapter_status == "not_invoked" and (
            failure_code != "ocr_deferred" or worker_exit_code is not None
            or profile is not OCR_PROFILE
        ):
            raise ValueError("not-invoked status mapping is contradictory")


def compare_representations(left: ParseResult, right: ParseResult) -> dict[str, Any]:
    """Compare formula candidates; equality never changes either trust axis."""
    if left.request.source_id != right.request.source_id:
        raise ValueError("representations must bind the same source")
    left_formulas = [item.normalized_text for item in left.segments if item.kind == "formula"]
    right_formulas = [item.normalized_text for item in right.segments if item.kind == "formula"]
    reason = None
    if left.disposition != "candidate_proposal" or right.disposition != "candidate_proposal":
        reason = "representation_not_candidate_proposal"
    elif not left_formulas or not right_formulas:
        reason = "formula_missing"
    disagreement = left_formulas != right_formulas
    return {
        "comparison": "not_comparable" if reason else ("disagreement" if disagreement else "candidate_text_equal"),
        "left_formula_sha256": _sha256(_canonical_bytes(left_formulas)),
        "left_representation_id": left.request.representation_id,
        "quarantine_reason": reason or ("formula_disagreement" if disagreement else None),
        "quarantine_required": reason is not None or disagreement,
        "right_formula_sha256": _sha256(_canonical_bytes(right_formulas)),
        "right_representation_id": right.request.representation_id,
        "schema_version": COMPARISON_SCHEMA,
        "source_id": left.request.source_id,
        "trust_effect": "none",
    }


def _segment(
    original: bytes, kind: str, text: str, start: int, end: int, ordinal: int,
    *, page_index: int | None = None, object_id: str | None = None,
) -> ParsedSegment:
    normalized = " ".join(text.split())
    if not normalized:
        raise ContentRejected("empty_segment_forbidden")
    anchor = ByteAnchor.create(
        original, start, end, page_index=page_index, object_id=object_id,
    )
    return ParsedSegment(
        segment_id=f"segment.{ordinal:04d}", kind=kind,
        normalized_text=normalized, anchor=anchor, load_bearing=kind == "formula",
    )


class _RestrictedHTMLCollector(HTMLParser):
    def __init__(self, original: bytes):
        super().__init__(convert_charrefs=False)
        self.original = original
        self.decoded = original.decode("utf-8", errors="strict")
        self.line_starts = [0] + [match.end() for match in re.finditer("\n", self.decoded)]
        self.stack: list[str] = []
        self.segments: list[ParsedSegment] = []
        self.warnings: list[str] = []
        self.max_depth = 0

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() != "doctype html":
            raise ContentRejected("html_declaration_forbidden")

    def unknown_decl(self, data: str) -> None:
        raise ContentRejected("html_declaration_forbidden")

    def handle_pi(self, data: str) -> None:
        raise ContentRejected("html_processing_instruction_forbidden")

    def handle_entityref(self, name: str) -> None:
        raise ContentRejected("html_entity_reference_forbidden")

    def handle_charref(self, name: str) -> None:
        raise ContentRejected("html_entity_reference_forbidden")

    def handle_comment(self, data: str) -> None:
        if "html_comment_ignored" not in self.warnings:
            self.warnings.append("html_comment_ignored")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "iframe", "object", "embed", "applet", "style", "svg", "form"}:
            raise ContentRejected("html_active_content_forbidden")
        allowed = {
            "html", "head", "meta", "title", "body", "article", "section", "div",
            "h1", "h2", "h3", "h4", "p", "span", "strong", "em", "ol", "ul",
            "li", "blockquote", "math", "mrow", "mi", "mn", "mo", "msup", "msub",
            "mfrac", "semantics", "annotation",
        }
        if tag not in allowed:
            raise ContentRejected("html_tag_outside_profile")
        values = {name.lower(): (value or "").strip() for name, value in attrs}
        if tag == "meta" and values.get("http-equiv", "").lower() == "refresh":
            raise ContentRejected("html_meta_refresh_forbidden")
        global_attributes = {"aria-label", "class", "id", "lang", "role"}
        tag_attributes = {
            "meta": {"charset", "content", "http-equiv", "name"},
            "math": {"display", "xmlns"}, "annotation": {"encoding"},
        }
        for name, value in attrs:
            attribute = name.lower()
            lowered = (value or "").strip().lower()
            if attribute.startswith("on") or attribute in {"srcdoc", "formaction"}:
                raise ContentRejected("html_active_attribute_forbidden")
            if attribute in {"href", "src", "action", "poster", "data", "xlink:href"} and lowered.startswith(
                ("http:", "https:", "file:", "data:", "javascript:", "vbscript:", "//")
            ):
                raise ContentRejected("html_external_reference_forbidden")
            if attribute not in global_attributes | tag_attributes.get(tag, set()):
                raise ContentRejected("html_attribute_outside_profile")
        if tag != "meta":
            self.stack.append(tag)
            self.max_depth = max(self.max_depth, len(self.stack))
            if self.max_depth > PARSER_BOUNDS.max_nesting_depth:
                raise ContentRejected("nesting_depth_bound_exceeded")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() != "meta":
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.stack or self.stack[-1] != tag:
            raise ContentRejected("html_unbalanced_structure")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if not normalized or not self.stack or self.stack[-1] in {"head", "title"}:
            return
        line, column = self.getpos()
        char_start = self.line_starts[line - 1] + column
        start = len(self.decoded[:char_start].encode("utf-8"))
        end = start + len(data.encode("utf-8"))
        kind = "formula" if "math" in self.stack else "text"
        self.segments.append(_segment(
            self.original, kind, data, start, end, len(self.segments) + 1,
        ))
        if len(self.segments) > PARSER_BOUNDS.max_segments:
            raise ContentRejected("segment_count_bound_exceeded")


def _parse_html(original: bytes) -> AdapterOutcome:
    _reject_cross_format_ambiguity(original, "html")
    try:
        collector = _RestrictedHTMLCollector(original)
        collector.feed(collector.decoded)
        collector.close()
    except UnicodeDecodeError as error:
        raise ContentRejected("html_invalid_utf8") from error
    if collector.stack:
        raise ContentRejected("html_unbalanced_structure")
    return AdapterOutcome(tuple(collector.segments), warnings=tuple(collector.warnings))


_DANGEROUS_TEX = {
    "catcode", "csname", "def", "documentclass", "endcsname", "everyjob", "include",
    "includegraphics", "immediate", "input", "loop", "newcommand", "openin", "openout",
    "read", "repeat", "special", "usepackage", "write",
}
_KNOWN_TEX = {"begin", "end", "section", "subsection", "textbf", "emph"}


def _tex_max_depth(text: str) -> int:
    depth = maximum = 0
    escaped = False
    for character in text:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "{":
            depth += 1
            maximum = max(maximum, depth)
            if maximum > PARSER_BOUNDS.max_nesting_depth:
                raise ContentRejected("nesting_depth_bound_exceeded")
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise ContentRejected("tex_unbalanced_group")
    if depth:
        raise ContentRejected("tex_unbalanced_group")
    return maximum


def _parse_tex(original: bytes) -> AdapterOutcome:
    _reject_cross_format_ambiguity(original, "tex")
    try:
        text = original.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContentRejected("tex_invalid_utf8") from error
    if "\x00" in text:
        raise ContentRejected("tex_nul_forbidden")
    _tex_max_depth(text)
    commands = list(re.finditer(r"\\([A-Za-z@]+)", text))
    for command in commands:
        if command.group(1).lower() in _DANGEROUS_TEX:
            raise ContentRejected("tex_active_or_expanding_command_forbidden")
    warnings = tuple(sorted({
        "unknown_tex_command:" + command.group(1)
        for command in commands if command.group(1).lower() not in _KNOWN_TEX
    }))
    segments: list[ParsedSegment] = []
    patterns = (
        re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.DOTALL),
        re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
        re.compile(r"\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}", re.DOTALL),
    )
    spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            char_start, char_end = match.span(1)
            if (char_start, char_end) in spans:
                continue
            spans.add((char_start, char_end))
            start = len(text[:char_start].encode("utf-8"))
            end = len(text[:char_end].encode("utf-8"))
            segments.append(_segment(original, "formula", match.group(1), start, end, 1))
    for match in re.finditer(r"\\(?:sub)?section\{([^{}]+)\}", text):
        char_start, char_end = match.span(1)
        start = len(text[:char_start].encode("utf-8"))
        end = len(text[:char_end].encode("utf-8"))
        segments.append(_segment(original, "text", match.group(1), start, end, 1))
    segments.sort(key=lambda item: item.anchor.start)
    segments = [
        ParsedSegment(f"segment.{index:04d}", item.kind, item.normalized_text, item.anchor, item.load_bearing)
        for index, item in enumerate(segments, 1)
    ]
    return AdapterOutcome(tuple(segments), warnings=warnings, transformations=("tex_lexical_whitespace_collapse",))


_FORBIDDEN_PDF = (
    b"/AA", b"/AcroForm", b"/EmbeddedFile", b"/Encrypt", b"/JavaScript", b"/JS",
    b"/Launch", b"/OpenAction", b"/RichMedia", b"/SubmitForm", b"/URI", b"/XFA",
)


def _decode_pdf_literal(raw: bytes) -> str:
    if any(byte > 0x7F for byte in raw):
        raise ContentRejected("pdf_literal_encoding_outside_profile")
    output = bytearray()
    index = 0
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9}
    while index < len(raw):
        byte = raw[index]
        if byte != 92:
            output.append(byte)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            raise ContentRejected("pdf_malformed_literal")
        escaped = raw[index]
        if escaped in escapes:
            output.append(escapes[escaped])
        elif escaped in (40, 41, 92):
            output.append(escaped)
        else:
            raise ContentRejected("pdf_escape_outside_profile")
        index += 1
    return output.decode("ascii")


def _parse_pdf(original: bytes) -> AdapterOutcome:
    _reject_cross_format_ambiguity(original, "pdf")
    if not original.startswith(b"%PDF-1.") or not original.rstrip().endswith(b"%%EOF"):
        raise ContentRejected("pdf_envelope_invalid")
    if any(token in original for token in _FORBIDDEN_PDF):
        raise ContentRejected("pdf_active_or_embedded_content_forbidden")
    if b"/Filter" in original:
        raise ContentRejected("pdf_compressed_stream_outside_profile")
    if b"xref" in original:
        startxref = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", original)
        if startxref is None:
            raise ContentRejected("pdf_cross_reference_invalid")
        offset = int(startxref.group(1))
        if offset >= len(original) or not original[offset:].startswith(b"xref"):
            raise ContentRejected("pdf_cross_reference_invalid")
    object_matches = list(re.finditer(rb"(?m)^(\d+)\s+(\d+)\s+obj\s*$", original))
    object_ranges: list[tuple[int, int, str]] = []
    for index, match in enumerate(object_matches):
        end = object_matches[index + 1].start() if index + 1 < len(object_matches) else len(original)
        object_ranges.append((match.start(), end, f"{match.group(1).decode()} {match.group(2).decode()} obj"))
    segments: list[ParsedSegment] = []
    for match in re.finditer(rb"\(([^()]*)\)\s*Tj", original):
        decoded = _decode_pdf_literal(match.group(1))
        kind = "formula" if decoded.startswith("FORMULA:") else "text"
        text = decoded.removeprefix("FORMULA:").strip()
        object_id = next(
            (identifier for start, end, identifier in object_ranges if start <= match.start() < end),
            None,
        )
        if object_id is None:
            raise ContentRejected("pdf_object_anchor_unmappable")
        segments.append(_segment(
            original, kind, text, match.start(1), match.end(1), len(segments) + 1,
            page_index=0, object_id=object_id,
        ))
    if not segments and b"/Subtype /Image" in original:
        raise ContentRejected("ocr_required_but_deferred")
    return AdapterOutcome(
        tuple(segments), warnings=("restricted_uncompressed_pdf_profile",),
        transformations=("pdf_literal_escape_decode", "unicode_whitespace_collapse"),
    )
