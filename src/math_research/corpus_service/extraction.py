"""The ADR-0080 document-extraction toolchain port.

Every full-text document passes through exactly one :class:`DocumentExtractor`
before span parsing.  The extractor turns acquired source bytes into extracted
UTF-8 text; spans stay ``utf8_exact_char_spans_v1`` — exact character offsets —
but over the EXTRACTED text, and the extractor identity (tool, version, binary
hash) is recorded in the document's provenance chain so a later reader knows
exactly which transformation produced the text the spans index.

Adapters:

* :class:`IdentityTextExtractor` — text/plain and text/markdown; the extracted
  text IS the strict UTF-8 decode of the source bytes (the pre-ADR-0080
  behavior, now stated as an identity transformation).
* :class:`LatexSourceExtractor` — a deterministic, stdlib-only LaTeX-source
  reduction.  It is versioned in-repo; no external binary.
* :class:`PinnedBinaryExtractor` — an explicit opt-in wrapper around one
  external tool (e.g. ``pdftotext``) pinned by binary sha256 and version
  string, following the pinned-typesetter pattern: the exact pinned tool or a
  refusal, never "whatever is on PATH".  Never part of the default registry.
* :class:`FixtureExtractor` — a deterministic mapping for offline tests.

Fail-closed: a media type without a registered extractor quarantines the
document as ``unsupported_media_type``; an extraction that cannot produce
strict UTF-8 text within bounds quarantines as ``parse_failure``.  Neither is
ever silently admitted or approximated.
"""

from __future__ import annotations

import hashlib
import resource
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from .constants import (
    HASH_PATTERN,
    LATEX_MEDIA_TYPES,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_CHARS,
    PARSABLE_MEDIA_TYPES,
    PDF_MEDIA_TYPE,
)
from .errors import ExtractorNotPinnedError, ExtractorRegistryInvalidError

_IDENTITY_FIELDS = frozenset({"tool", "version", "binary_sha256"})

#: Bounded external-tool execution: never unbounded subprocesses.
PINNED_TOOL_TIMEOUT_SECONDS = 120
PINNED_TOOL_DIAGNOSTIC_BYTES = 65_536


def _bounded_subprocess(
    argv: list[str], *, input_bytes: bytes | None, timeout: int,
    output_limit: int,
) -> tuple[int, bytes, bytes]:
    """Run a pinned extractor without unbounded capture_output buffers."""

    def limit_files() -> None:
        # Applied in the child only. Each redirected regular file is bounded
        # by the kernel before a hostile/broken extractor can fill host disk.
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit + 1, output_limit + 1))

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        completed = subprocess.run(
            argv, input=input_bytes, stdout=stdout, stderr=stderr,
            timeout=timeout, check=False, preexec_fn=limit_files,
        )
        stdout.seek(0)
        stderr.seek(0)
        return (
            completed.returncode,
            stdout.read(output_limit + 1),
            stderr.read(PINNED_TOOL_DIAGNOSTIC_BYTES + 1),
        )


class ExtractionFailure(Exception):
    """Raised for quarantine (``parse_failure``), never surfaced as a record."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def verify_extractor_identity(value: Any) -> dict[str, Any]:
    """The closed identity shape recorded into provenance. Fail-closed."""

    if not isinstance(value, Mapping) or set(value) != _IDENTITY_FIELDS:
        raise ExtractorRegistryInvalidError(
            "extractor identity must carry exactly tool, version, and "
            f"binary_sha256: {value!r}"
        )
    if not isinstance(value["tool"], str) or not value["tool"].strip():
        raise ExtractorRegistryInvalidError("extractor tool differs")
    if not isinstance(value["version"], str) or not value["version"].strip():
        raise ExtractorRegistryInvalidError("extractor version differs")
    binary = value["binary_sha256"]
    if binary is not None and (
        not isinstance(binary, str) or HASH_PATTERN.fullmatch(binary) is None
    ):
        raise ExtractorRegistryInvalidError("extractor binary hash differs")
    return {
        "tool": value["tool"],
        "version": value["version"],
        "binary_sha256": binary,
    }


@runtime_checkable
class DocumentExtractor(Protocol):
    """One deterministic source-bytes-to-extracted-text transformation."""

    def identity(self) -> dict[str, Any]:
        """``{"tool", "version", "binary_sha256"}`` recorded into provenance."""

    def media_types(self) -> frozenset[str]:
        """The exact media types this extractor accepts."""

    def extract(self, body: bytes, *, media_type: str) -> str:
        """Extracted text, or :class:`ExtractionFailure` for quarantine."""


def _bounded_text(text: str) -> str:
    if len(text) > MAX_DOCUMENT_CHARS:
        raise ExtractionFailure(
            f"extraction yields {len(text)} characters; the pinned bound is "
            f"{MAX_DOCUMENT_CHARS}"
        )
    if not text.strip():
        raise ExtractionFailure("extraction yields no text")
    return text


@dataclass(frozen=True, slots=True)
class IdentityTextExtractor:
    """text/plain and text/markdown: extracted text is the exact decode."""

    def identity(self) -> dict[str, Any]:
        return {
            "tool": "adaivy.identity-text-extractor",
            "version": "v1",
            "binary_sha256": None,
        }

    def media_types(self) -> frozenset[str]:
        return PARSABLE_MEDIA_TYPES

    def extract(self, body: bytes, *, media_type: str) -> str:
        if media_type not in self.media_types():
            raise ExtractionFailure(f"identity extractor refuses {media_type!r}")
        try:
            return _bounded_text(body.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise ExtractionFailure(f"not strict UTF-8: {error}") from error


def _strip_latex_comment(line: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\" and index + 1 < len(line):
            out.append(line[index: index + 2])
            index += 2
            continue
        if character == "%":
            break
        out.append(character)
        index += 1
    return "".join(out)


@dataclass(frozen=True, slots=True)
class LatexSourceExtractor:
    """Deterministic, stdlib-only LaTeX-source reduction to plain text.

    Deliberately conservative: comments are removed (respecting ``\\%``),
    everything before ``\\begin{document}`` is dropped when the marker exists,
    ``\\begin{...}``/``\\end{...}`` lines vanish, and remaining ``\\word``
    commands are replaced by a single space with their brace arguments kept as
    text.  Math material is kept verbatim.  The transformation is versioned;
    changing it is a new version, never a silent drift.
    """

    def identity(self) -> dict[str, Any]:
        return {
            "tool": "adaivy.latex-source-extractor",
            "version": "v1",
            "binary_sha256": None,
        }

    def media_types(self) -> frozenset[str]:
        return LATEX_MEDIA_TYPES

    def extract(self, body: bytes, *, media_type: str) -> str:
        if media_type not in self.media_types():
            raise ExtractionFailure(f"latex extractor refuses {media_type!r}")
        try:
            source = body.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise ExtractionFailure(f"not strict UTF-8: {error}") from error
        marker = "\\begin{document}"
        position = source.find(marker)
        if position >= 0:
            source = source[position + len(marker):]
        end_marker = "\\end{document}"
        position = source.find(end_marker)
        if position >= 0:
            source = source[:position]
        lines: list[str] = []
        for raw_line in source.split("\n"):
            line = _strip_latex_comment(raw_line)
            stripped = line.strip()
            if stripped.startswith("\\begin{") or stripped.startswith("\\end{"):
                lines.append("")
                continue
            out: list[str] = []
            index = 0
            while index < len(line):
                character = line[index]
                if character == "\\":
                    index += 1
                    start = index
                    while index < len(line) and line[index].isalpha():
                        index += 1
                    if index == start and index < len(line):
                        # An escaped symbol like \% or \&: keep the symbol.
                        out.append(line[index])
                        index += 1
                    else:
                        out.append(" ")
                    continue
                if character in "{}~":
                    out.append(" ")
                    index += 1
                    continue
                out.append(character)
                index += 1
            lines.append(" ".join("".join(out).split()))
        collapsed: list[str] = []
        for line in lines:
            if line or (collapsed and collapsed[-1]):
                collapsed.append(line)
        return _bounded_text("\n".join(collapsed).strip() + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class PinnedBinaryExtractor:
    """One external tool, pinned by binary hash and version string. Opt-in.

    The default registry never contains this adapter: an operator supplies the
    binary path, its expected sha256, and its expected version explicitly, and
    the adapter refuses — coded, before any document is touched — when the
    binary is absent, hashes differently, or reports a different version.
    Execution is bounded (timeout, output cap) and offline: the tool receives
    the document on stdin and returns UTF-8 text on stdout.
    """

    binary_path: Path
    expected_sha256: str
    expected_version: str
    tool_name: str = "pdftotext"
    accepted_media_types: frozenset[str] = frozenset({PDF_MEDIA_TYPE})
    arguments: tuple[str, ...] = ("-q", "-enc", "UTF-8", "-", "-")
    version_arguments: tuple[str, ...] = ("-v",)
    timeout_seconds: int = PINNED_TOOL_TIMEOUT_SECONDS

    def _pinned_binary(self) -> Path:
        path = Path(self.binary_path)
        if not isinstance(self.expected_sha256, str) or HASH_PATTERN.fullmatch(
            self.expected_sha256
        ) is None:
            raise ExtractorNotPinnedError(
                "a pinned extractor needs an exact expected binary sha256"
            )
        if not isinstance(self.expected_version, str) or not self.expected_version.strip():
            raise ExtractorNotPinnedError(
                "a pinned extractor needs an exact expected version string"
            )
        if not path.is_file():
            raise ExtractorNotPinnedError(
                f"pinned extraction tool is absent: {path}; the exact pinned "
                "tool or a refusal, never a substitute"
            )
        actual = sha256_file(path)
        if actual != self.expected_sha256:
            raise ExtractorNotPinnedError(
                f"pinned extraction tool at {path} hashes to {actual}, not the "
                f"pinned {self.expected_sha256}"
            )
        return path

    def identity(self) -> dict[str, Any]:
        self._pinned_binary()
        return {
            "tool": self.tool_name,
            "version": self.expected_version,
            "binary_sha256": self.expected_sha256,
        }

    def media_types(self) -> frozenset[str]:
        return self.accepted_media_types

    def _check_version(self, path: Path) -> None:
        try:
            returncode, stdout, stderr = _bounded_subprocess(
                [str(path), *self.version_arguments], input_bytes=None,
                timeout=self.timeout_seconds,
                output_limit=PINNED_TOOL_DIAGNOSTIC_BYTES,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExtractorNotPinnedError(
                f"pinned extractor version probe failed: {error}"
            ) from error
        if returncode != 0 or len(stdout) > PINNED_TOOL_DIAGNOSTIC_BYTES \
                or len(stderr) > PINNED_TOOL_DIAGNOSTIC_BYTES:
            raise ExtractorNotPinnedError(
                "pinned extractor version probe failed or exceeded its output bound"
            )
        reported = (stdout + stderr).decode("utf-8", "replace")
        if self.expected_version not in reported:
            raise ExtractorNotPinnedError(
                f"pinned extraction tool reports {reported.strip()!r}; the pin "
                f"requires version {self.expected_version!r}"
            )

    def extract(self, body: bytes, *, media_type: str) -> str:
        if media_type not in self.media_types():
            raise ExtractionFailure(
                f"pinned extractor {self.tool_name} refuses {media_type!r}"
            )
        path = self._pinned_binary()
        self._check_version(path)
        try:
            returncode, stdout, stderr = _bounded_subprocess(
                [str(path), *self.arguments], input_bytes=body,
                timeout=self.timeout_seconds, output_limit=MAX_DOCUMENT_BYTES,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExtractionFailure(f"pinned tool execution failed: {error}") from error
        if returncode != 0:
            raise ExtractionFailure(
                f"pinned tool exited {returncode}: "
                f"{stderr[:512].decode('utf-8', 'replace')}"
            )
        if len(stdout) > MAX_DOCUMENT_BYTES:
            raise ExtractionFailure("pinned tool output exceeds the byte bound")
        try:
            return _bounded_text(stdout.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise ExtractionFailure(f"pinned tool output is not UTF-8: {error}") from error


@dataclass(frozen=True, slots=True)
class FixtureExtractor:
    """Deterministic offline adapter: source sha256 -> extracted text."""

    tool: str
    version: str
    binary_sha256: str
    accepted_media_types: frozenset[str]
    texts_by_source_sha256: Mapping[str, str] = field(default_factory=dict)

    def identity(self) -> dict[str, Any]:
        return verify_extractor_identity({
            "tool": self.tool,
            "version": self.version,
            "binary_sha256": self.binary_sha256,
        })

    def media_types(self) -> frozenset[str]:
        return self.accepted_media_types

    def extract(self, body: bytes, *, media_type: str) -> str:
        if media_type not in self.media_types():
            raise ExtractionFailure(f"fixture extractor refuses {media_type!r}")
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        text = self.texts_by_source_sha256.get(digest)
        if text is None:
            raise ExtractionFailure(f"fixture extractor has no text for {digest}")
        return _bounded_text(text)


class ExtractorRegistry:
    """A closed media-type -> extractor map. Unknown media types quarantine."""

    def __init__(self, extractors: tuple[DocumentExtractor, ...]) -> None:
        mapping: dict[str, DocumentExtractor] = {}
        for extractor in extractors:
            verify_extractor_identity(extractor.identity())
            for media_type in sorted(extractor.media_types()):
                if media_type in mapping:
                    raise ExtractorRegistryInvalidError(
                        f"two extractors claim media type {media_type!r}; the "
                        "registry is a function, not a preference order"
                    )
                mapping[media_type] = extractor
        if not mapping:
            raise ExtractorRegistryInvalidError("an extractor registry cannot be empty")
        self._by_media_type = dict(sorted(mapping.items()))

    def media_types(self) -> frozenset[str]:
        return frozenset(self._by_media_type)

    def extractor_for(self, media_type: str) -> DocumentExtractor | None:
        return self._by_media_type.get(media_type)


def default_registry() -> ExtractorRegistry:
    """Identity text plus the in-repo LaTeX reducer. No external binaries."""

    return ExtractorRegistry((IdentityTextExtractor(), LatexSourceExtractor()))


__all__ = [
    "DocumentExtractor",
    "ExtractionFailure",
    "ExtractorRegistry",
    "FixtureExtractor",
    "IdentityTextExtractor",
    "LatexSourceExtractor",
    "PINNED_TOOL_TIMEOUT_SECONDS",
    "PinnedBinaryExtractor",
    "default_registry",
    "sha256_file",
    "verify_extractor_identity",
]
