"""The ADR-0080 snapshot fetcher, behind the ADR-0072 activation gate.

Acquisition of a snapshot archive sends traffic to a third party under its
terms, so nothing here runs without an ACTIVE
``corpus-service-snapshot-acquisition`` record, the exact acknowledgement
string, and the human operator identity — the same gate the pending shipped
record has always named.  Given that gate:

* **Allowlisted origins only.** The fetch config names one origin from the
  closed allowlist pinned in :mod:`.constants`; anything else refuses before
  any request is made, and the refusal itself is ledgered.
* **Pinned pacing.** At most one connection, at least
  ``FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS`` between requests.  The pacer's
  clock and sleep are injected so the offline suite observes pacing without
  waiting; elapsed time is operational and never enters a content hash.
* **Bytes land exactly like the local-archive path.** Fetched document bytes
  are verified against the archive manifest hash and stored write-once in the
  grow-only object store; ingestion then reads them through
  :class:`ObjectStoreArchiveSource` with zero further network access.
* **Resumable and delta-only.** A document whose exact bytes are already in
  the store is skipped without a request, so an interrupted tranche resumes
  where it stopped and a second run fetches nothing.
* **Everything is recorded.** Every request appends origin, URL, byte count,
  and outcome to the append-only ``fetches`` ledger; failures are retained,
  never discarded.

The live transport (:class:`UrllibSnapshotTransport`) uses stdlib urllib with
redirects disabled and a bounded read.  Offline tests inject a fake transport;
no test touches the network.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from . import FETCH_REPORT_SCHEMA_VERSION
from .activation import require_active
from .constants import (
    ALLOWLISTED_SNAPSHOT_ORIGINS,
    FETCH_MAX_CONCURRENT_CONNECTIONS,
    FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS,
    FETCH_TIMEOUT_MILLISECONDS,
    IDENTIFIER_PATTERN,
    MAX_DOCUMENT_BYTES,
    TIMESTAMP_PATTERN,
)
from .dataroot import object_exists, open_data_root, read_object, write_object
from .errors import (
    ArchiveDocumentMismatchError,
    ArchiveManifestInvalidError,
    CorpusServiceError,
    SnapshotFetchBoundExceededError,
    SnapshotFetchFailedError,
    SnapshotOriginNotAllowlistedError,
)
from .ledger import append_ledger
from .serialization import canonical_bytes, sealed, sha256_bytes
from .snapshot import validate_archive_manifest


class SnapshotTransport(Protocol):
    """One bounded HTTP GET. No redirects, no credentials, no retries."""

    def get(self, url: str) -> bytes:
        """The exact response body bytes, or an exception."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise SnapshotFetchFailedError(
            f"redirect refused: {req.full_url} -> {newurl}; a snapshot fetch "
            "follows nothing"
        )


@dataclass(frozen=True, slots=True)
class UrllibSnapshotTransport:
    """The live stdlib transport. Construct only behind the activation gate."""

    timeout_milliseconds: int = FETCH_TIMEOUT_MILLISECONDS

    def get(self, url: str) -> bytes:
        if not url.startswith("https://"):
            raise SnapshotFetchFailedError(f"only https is fetched: {url!r}")
        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(url, method="GET")
        try:
            with opener.open(request, timeout=self.timeout_milliseconds / 1000) as response:
                body = response.read(MAX_DOCUMENT_BYTES + 1)
        except SnapshotFetchFailedError:
            raise
        except Exception as error:  # noqa: BLE001 -- coded, recorded upstream
            raise SnapshotFetchFailedError(f"transport failure for {url}: {error}") from error
        if len(body) > MAX_DOCUMENT_BYTES:
            raise SnapshotFetchFailedError(
                f"response for {url} exceeds the pinned document byte bound"
            )
        return body


class RatePacer:
    """Pins the request interval. Clock and sleep are injected, never global."""

    def __init__(
        self, *,
        min_interval_milliseconds: int = FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_milliseconds < FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS:
            raise CorpusServiceError(
                "the fetch pacing interval is pinned; a caller may slow it, "
                "never speed it",
                code="snapshot_fetch_pacing_widened",
            )
        self.min_interval_seconds = min_interval_milliseconds / 1000
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.waits_requested: int = 0

    def before_request(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self.min_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.waits_requested += 1
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now


@dataclass(frozen=True, slots=True)
class ObjectStoreArchiveSource:
    """The fetched snapshot, served from the grow-only object store.

    Shape-identical to :class:`~.ports.DirectoryArchiveSource`: ingestion
    cannot tell fetched bytes from locally supplied bytes, which is the point —
    the network never reaches ingestion.
    """

    root: Path
    manifest: Mapping[str, Any]

    def manifest_bytes(self) -> bytes:
        return canonical_bytes(validate_archive_manifest(self.manifest)) + b"\n"

    def document_bytes(self, relative_path: str) -> bytes:
        for document in self.manifest["documents"]:
            if document["relative_path"] == relative_path:
                return read_object(self.root, document["sha256"])
        raise ArchiveDocumentMismatchError(
            f"archive document {relative_path!r} is absent from the manifest"
        )


def _document_url(origin: str, relative_path: str) -> str:
    return origin + "/" + relative_path


def fetch_snapshot(
    root: Path, *,
    manifest: Mapping[str, Any],
    origin: str,
    activation: Mapping[str, Any],
    acknowledgement: str | None,
    transport: SnapshotTransport,
    run_id: str,
    recorded_at: str,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch one archive manifest's documents into the data root. Resumable.

    Returns the sealed fetch report.  Interrupting a run loses nothing: the
    stored bytes and ledger records stand, and the next run requests only the
    documents still absent.
    """

    open_data_root(root)
    if not isinstance(run_id, str) or IDENTIFIER_PATTERN.fullmatch(run_id) is None:
        raise CorpusServiceError(f"run_id must be an identifier: {run_id!r}")
    if not isinstance(recorded_at, str) or TIMESTAMP_PATTERN.fullmatch(recorded_at) is None:
        raise CorpusServiceError(
            "recorded_at must be a canonical UTC timestamp argument, not a "
            "clock read"
        )
    record = require_active(activation, acknowledgement=acknowledgement)
    validated = validate_archive_manifest(manifest)
    if not isinstance(origin, str) or origin not in ALLOWLISTED_SNAPSHOT_ORIGINS:
        # The refusal is itself evidence: record it before failing closed.
        append_ledger(root, "fetches", kind="snapshot_request", recorded_at=recorded_at, payload={
            "run_id": run_id,
            "origin": origin if isinstance(origin, str) else repr(origin),
            "url": None,
            "document_id": None,
            "byte_count": 0,
            "outcome": "refused_off_allowlist",
            "archive_manifest_hash": validated["content_hash"],
        })
        raise SnapshotOriginNotAllowlistedError(
            f"origin {origin!r} is not on the pinned allowlist "
            f"{list(ALLOWLISTED_SNAPSHOT_ORIGINS)}; refused before any request"
        )
    if validated["document_count"] > record["max_tranche_documents"]:
        raise SnapshotFetchBoundExceededError(
            f"the archive lists {validated['document_count']} documents; the "
            f"activation record pins {record['max_tranche_documents']} for "
            "live acquisition"
        )
    if validated["total_bytes"] > record["max_tranche_total_bytes"]:
        raise SnapshotFetchBoundExceededError(
            f"the archive totals {validated['total_bytes']} bytes; the "
            f"activation record pins {record['max_tranche_total_bytes']}"
        )

    pacer = RatePacer(monotonic=monotonic, sleep=sleep)
    documents_fetched = 0
    documents_already_stored = 0
    bytes_fetched = 0
    for document in validated["documents"]:
        if object_exists(root, document["sha256"]):
            documents_already_stored += 1
            continue
        url = _document_url(origin, document["relative_path"])
        pacer.before_request()
        try:
            body = transport.get(url)
        except Exception as error:  # noqa: BLE001 -- recorded, then re-raised
            append_ledger(root, "fetches", kind="snapshot_request", recorded_at=recorded_at, payload={
                "run_id": run_id,
                "origin": origin,
                "url": url,
                "document_id": document["document_id"],
                "byte_count": 0,
                "outcome": "transport_error",
                "detail": str(error)[:512],
                "archive_manifest_hash": validated["content_hash"],
            })
            raise SnapshotFetchFailedError(
                f"fetch of {document['document_id']} failed and was recorded; "
                "re-running the same tranche resumes here"
            ) from error
        if (
            sha256_bytes(body) != document["sha256"]
            or len(body) != document["byte_count"]
        ):
            append_ledger(root, "fetches", kind="snapshot_request", recorded_at=recorded_at, payload={
                "run_id": run_id,
                "origin": origin,
                "url": url,
                "document_id": document["document_id"],
                "byte_count": len(body),
                "outcome": "hash_mismatch",
                "archive_manifest_hash": validated["content_hash"],
            })
            raise ArchiveDocumentMismatchError(
                f"fetched bytes for {document['document_id']} do not match the "
                "manifest; a corrupt response is refused, not repaired"
            )
        write_object(root, body)
        append_ledger(root, "fetches", kind="snapshot_request", recorded_at=recorded_at, payload={
            "run_id": run_id,
            "origin": origin,
            "url": url,
            "document_id": document["document_id"],
            "byte_count": len(body),
            "outcome": "fetched",
            "sha256": document["sha256"],
            "archive_manifest_hash": validated["content_hash"],
        })
        documents_fetched += 1
        bytes_fetched += len(body)

    report = sealed({
        "schema_version": FETCH_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "origin": origin,
        "archive_id": validated["archive_id"],
        "archive_version": validated["archive_version"],
        "archive_manifest_hash": validated["content_hash"],
        "documents_total": validated["document_count"],
        "documents_fetched": documents_fetched,
        "documents_already_stored": documents_already_stored,
        "bytes_fetched": bytes_fetched,
        "network_requests": documents_fetched,
        "max_concurrent_connections": FETCH_MAX_CONCURRENT_CONNECTIONS,
        "min_request_interval_milliseconds": FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS,
        "content_hash": None,
    })
    append_ledger(root, "fetches", kind="snapshot_fetch_run", recorded_at=recorded_at, payload={
        "run_id": run_id,
        "origin": origin,
        "archive_manifest_hash": validated["content_hash"],
        "documents_fetched": documents_fetched,
        "documents_already_stored": documents_already_stored,
        "bytes_fetched": bytes_fetched,
        "report_content_hash": report["content_hash"],
    })
    return report


__all__ = [
    "ObjectStoreArchiveSource",
    "RatePacer",
    "SnapshotTransport",
    "UrllibSnapshotTransport",
    "fetch_snapshot",
]
