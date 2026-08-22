"""The ADR-0064 processor-bound rights seam, and a filesystem text reader.

`TECHNICAL_BLUEPRINT.md:1672-1675`: "Rights bind the processor, not only the use.
A current Phase 4A `embedding` rights decision authorizes a named processor.
Sending the same source text to a second provider requires its own decision,
because it is a distinct disclosure."

ADR-0064 (slice A) adds ``processor_id`` to
``Phase4Service.require_rights(source_id, intended_use, *, at, processor_id=None)``
and a ``RightsOutcome.PROCESSOR_NOT_AUTHORIZED``. Neither exists at the time this
module was written, so `Phase4ProcessorRightsGate` is a THIN SEAM: it forwards
when the parameter is present and REFUSES when it is not. It never falls back to
the unbound two-argument call, because a rights check that cannot name the
processor is not the check the blueprint requires.

Integration is one line: once slice A lands, `Phase4ProcessorRightsGate(service)`
starts forwarding and `test_embedding_rights_seam` flips from "seam refuses" to
"seam forwards" with no change to the ingestion path.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from ..phase4a.records import RightsUse
from .errors import EmbeddingError, ProcessorNotNamedError, RightsSeamUnavailableError

#: The single Phase 4A use this slice ever requests. Already in the closed
#: vocabulary at `phase4a/records.py:30`; this slice extends nothing.
EMBEDDING_RIGHTS_USE = RightsUse.EMBEDDING

#: Maximum bytes a single source may contribute to one embedding call.
MAX_SOURCE_TEXT_BYTES = 1_048_576


def processor_bound_rights_supported(service: Any) -> bool:
    """Does the service explicitly bind the complete processor identity?"""

    method = getattr(service, "require_rights", None)
    if method is None:
        return False
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtin or C callable
        return False
    # ``**kwargs`` is not evidence of support: it can silently swallow the
    # identity and recreate the exact fail-open seam this adapter closes.
    return {"processor_id", "provider", "model_identifier"}.issubset(parameters)


class Phase4ProcessorRightsGate:
    """Adapter from this slice's `RightsGate` port onto Phase 4A.

    Fails closed twice: once when the caller does not name a processor, and once
    when the underlying service cannot bind one.
    """

    def __init__(self, service: Any) -> None:
        self.service = service

    def require_rights(
        self, source_id: str, intended_use: Any, *, at: str,
        processor_id: str | None = None, provider: str | None = None,
        model_identifier: str | None = None,
    ) -> Any:
        if not processor_id or not provider or not model_identifier:
            raise ProcessorNotNamedError(
                "an embedding rights check must name the processor that will "
                "receive the text"
            )
        if not processor_bound_rights_supported(self.service):
            raise RightsSeamUnavailableError(
                "Phase 4A require_rights does not accept processor_id yet "
                "(ADR-0064 slice A); refusing rather than checking an "
                "unbound decision"
            )
        return self.service.require_rights(
            source_id, intended_use, at=at, processor_id=processor_id,
            provider=provider, model_identifier=model_identifier,
        )


class DirectorySourceTextReader:
    """Reads ``<root>/<source_id>.txt``. Bounded, UTF-8 strict, no traversal."""

    def __init__(self, root: Path, *, max_bytes: int = MAX_SOURCE_TEXT_BYTES) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.reads: list[str] = []

    def read(self, source_id: str) -> bytes:
        if "/" in source_id or "\\" in source_id or source_id in {".", ".."}:
            raise EmbeddingError(f"source_id is not a bare name: {source_id!r}",
                                 code="source_id_invalid")
        path = self.root / f"{source_id}.txt"
        resolved = path.resolve()
        if self.root.resolve() not in resolved.parents:
            raise EmbeddingError("source path escapes the corpus root",
                                 code="source_path_escape")
        try:
            data = resolved.read_bytes()
        except OSError as error:
            raise EmbeddingError(f"cannot read source {source_id}",
                                 code="source_unreadable") from error
        if len(data) > self.max_bytes:
            raise EmbeddingError(
                f"source {source_id} exceeds {self.max_bytes} bytes",
                code="source_too_large",
            )
        try:
            data.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise EmbeddingError(f"source {source_id} is not valid UTF-8",
                                 code="source_not_utf8") from error
        self.reads.append(source_id)
        return data


__all__ = [
    "EMBEDDING_RIGHTS_USE",
    "MAX_SOURCE_TEXT_BYTES",
    "DirectorySourceTextReader",
    "Phase4ProcessorRightsGate",
    "processor_bound_rights_supported",
]
