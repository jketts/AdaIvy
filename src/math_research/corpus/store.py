"""Content-addressed storage of the exact response bytes, and its manifest.

ADR-0065's vector replay is the precedent: the stored bytes are the artifact of
record and a rebuild replays them rather than calling the provider again.  Here
the stored bytes are the arXiv Atom responses.  Everything downstream --
records, rights subjects, reports, projections -- is derived from them, so a
replay is a pure function of this directory.

Two refusals carry the guarantee.  Absent bytes are
``stored_response_missing`` and never a re-fetch, because a replay that can fall
back to the network is not a replay.  Altered bytes are
``stored_response_hash_mismatch``, because a content hash is tamper evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from . import STORE_MANIFEST_SCHEMA_VERSION
from .constants import (
    HASH_PATTERN, IDENTIFIER_PATTERN, MAX_MANIFEST_BYTES, MAX_RESPONSE_BYTES,
    PROVIDER,
)
from .errors import (
    ManifestHashMismatchError, ManifestInvalidError, StoreOverwriteRefusedError,
    StoredResponseHashMismatchError, StoredResponseMissingError,
    UnplannedRequestUrlError,
)
from .serialization import (
    canonical_bytes, sealed, sha256_bytes, strict_canonical_object, verify_sealed,
)
from .tranche import assert_metadata_target, planned_request_urls

RESPONSES_DIRNAME = "responses"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_FIELDS = frozenset({
    "schema_version", "provider", "tranche_id", "plan_hash", "page_count",
    "pages", "content_hash",
})
_PAGE_FIELDS = frozenset({
    "page_index", "request_url", "response_sha256", "response_bytes",
})


def responses_dir(root: Path) -> Path:
    return Path(root).joinpath(RESPONSES_DIRNAME)


def manifest_path(root: Path) -> Path:
    return Path(root).joinpath(MANIFEST_FILENAME)


def response_path(root: Path, response_sha256: str) -> Path:
    if not isinstance(response_sha256, str) or HASH_PATTERN.fullmatch(response_sha256) is None:
        raise StoredResponseMissingError(f"not a sha256 value: {response_sha256!r}")
    return responses_dir(root).joinpath(response_sha256.removeprefix("sha256:") + ".xml")


def write_response(root: Path, body: bytes) -> str:
    """Store one response by content hash. Returns the hash."""

    if not isinstance(body, bytes) or not body or len(body) > MAX_RESPONSE_BYTES:
        raise ManifestInvalidError(
            f"a stored response must be 1..{MAX_RESPONSE_BYTES} bytes"
        )
    digest = sha256_bytes(body)
    path = response_path(root, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise StoreOverwriteRefusedError(
                f"a different response already occupies {digest}"
            )
        return digest
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(body)
    temporary.replace(path)
    return digest


def read_response(root: Path, response_sha256: str) -> bytes:
    """Read stored bytes, verifying the hash. Absence is a refusal."""

    path = response_path(root, response_sha256)
    try:
        body = path.read_bytes()
    except OSError as error:
        raise StoredResponseMissingError(
            f"stored response {response_sha256} is absent; a replay never "
            "re-fetches"
        ) from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise StoredResponseHashMismatchError("stored response exceeds its byte bound")
    if sha256_bytes(body) != response_sha256:
        raise StoredResponseHashMismatchError(
            f"stored response bytes do not hash to {response_sha256}"
        )
    return body


def build_manifest(
    *, tranche_id: str, plan_hash: str, pages: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = [
        {
            "page_index": int(page["page_index"]),
            "request_url": str(page["request_url"]),
            "response_sha256": str(page["response_sha256"]),
            "response_bytes": int(page["response_bytes"]),
        }
        for page in pages
    ]
    ordered.sort(key=lambda page: page["page_index"])
    return sealed({
        "schema_version": STORE_MANIFEST_SCHEMA_VERSION,
        "provider": PROVIDER,
        "tranche_id": tranche_id,
        "plan_hash": plan_hash,
        "page_count": len(ordered),
        "pages": ordered,
        "content_hash": None,
    })


def write_manifest(root: Path, manifest: Mapping[str, Any]) -> str:
    validated = verify_manifest(manifest)
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(validated) + b"\n")
    return str(validated["content_hash"])


def verify_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = verify_sealed(
        value, label="corpus response manifest", code=ManifestInvalidError.code,
    )
    if set(manifest) != MANIFEST_FIELDS:
        raise ManifestInvalidError(
            "corpus response manifest fields differ: "
            f"missing={sorted(MANIFEST_FIELDS - set(manifest))}, "
            f"extra={sorted(set(manifest) - MANIFEST_FIELDS)}"
        )
    if manifest["schema_version"] != STORE_MANIFEST_SCHEMA_VERSION:
        raise ManifestInvalidError("corpus response manifest schema differs")
    if manifest["provider"] != PROVIDER:
        raise ManifestInvalidError("corpus response manifest provider differs")
    if not isinstance(manifest["tranche_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        manifest["tranche_id"]
    ) is None:
        raise ManifestInvalidError("corpus response manifest tranche id differs")
    if not isinstance(manifest["plan_hash"], str) or HASH_PATTERN.fullmatch(
        manifest["plan_hash"]
    ) is None:
        raise ManifestInvalidError("corpus response manifest plan hash differs")
    pages = manifest["pages"]
    if not isinstance(pages, list) or not pages or manifest["page_count"] != len(pages):
        raise ManifestInvalidError("corpus response manifest page count differs")
    seen: set[str] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping) or set(page) != _PAGE_FIELDS:
            raise ManifestInvalidError(f"page {index} fields differ")
        if page["page_index"] != index:
            raise ManifestInvalidError(
                f"pages must be contiguous and ordered from zero; page {index} "
                f"declares {page['page_index']!r}"
            )
        digest = page["response_sha256"]
        if not isinstance(digest, str) or HASH_PATTERN.fullmatch(digest) is None:
            raise ManifestInvalidError(f"page {index} response hash differs")
        if digest in seen:
            raise ManifestInvalidError(f"page {index} repeats a stored response")
        seen.add(digest)
        size = page["response_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_RESPONSE_BYTES:
            raise ManifestInvalidError(f"page {index} byte count differs")
        assert_metadata_target(page["request_url"])
    return manifest


def load_manifest(root: Path, *, expected_manifest_hash: str | None = None) -> dict[str, Any]:
    path = manifest_path(root)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise StoredResponseMissingError(
            f"no corpus response manifest at {path}"
        ) from error
    manifest = verify_manifest(strict_canonical_object(
        data, maximum=MAX_MANIFEST_BYTES, label="corpus response manifest",
        code=ManifestInvalidError.code,
    ))
    if expected_manifest_hash is not None and manifest["content_hash"] != expected_manifest_hash:
        raise ManifestHashMismatchError(
            f"stored manifest {manifest['content_hash']} differs from expected "
            f"{expected_manifest_hash}"
        )
    return manifest


def verify_manifest_against_plan(
    manifest: Mapping[str, Any], plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Every stored request URL must be one the plan itself derives.

    This is where "no crawling, no result following, no citation traversal"
    becomes checkable after the fact: a stored request the plan does not derive
    means something chose a URL, and a corpus run is not allowed to choose.
    """

    validated = verify_manifest(manifest)
    planned = planned_request_urls(plan)
    if validated["plan_hash"] != plan["content_hash"]:
        raise ManifestInvalidError(
            "the stored manifest was built from a different tranche plan"
        )
    if validated["tranche_id"] != plan["tranche_id"]:
        raise ManifestInvalidError("the stored manifest names a different tranche")
    if validated["page_count"] > len(planned):
        raise UnplannedRequestUrlError(
            f"the manifest stores {validated['page_count']} pages; the plan "
            f"derives {len(planned)}"
        )
    for page in validated["pages"]:
        expected = planned[page["page_index"]]
        if page["request_url"] != expected:
            raise UnplannedRequestUrlError(
                f"page {page['page_index']} stores a request URL the plan does "
                "not derive; a corpus run never selects a URL"
            )
    return validated


__all__ = [
    "MANIFEST_FIELDS",
    "MANIFEST_FILENAME",
    "RESPONSES_DIRNAME",
    "build_manifest",
    "load_manifest",
    "manifest_path",
    "read_response",
    "response_path",
    "responses_dir",
    "verify_manifest",
    "verify_manifest_against_plan",
    "write_manifest",
    "write_response",
]
