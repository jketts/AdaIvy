"""Inward-facing ports for the review surface.

The review slice READS Phase 2 and Phase 3B; it never writes to either. These
protocols are the narrowest read views that satisfy the decision preconditions,
so the concrete `SQLiteWorkspace` and `FileArtifactStore` satisfy them
structurally without any change on their side.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..domain.entities import OpaqueId, ResearchDossier
from ..phase2.records import ProposalRecord, RunRecord
from .records import DecisionProposal, Refusal


class RunReader(Protocol):
    """Read-only view of the Phase 2 durable workspace."""

    def get_run(self, run_id: OpaqueId) -> RunRecord: ...
    def load_dossier(self, dossier_id: OpaqueId) -> ResearchDossier: ...
    def list_proposals(self, run_id: OpaqueId) -> tuple[ProposalRecord, ...]: ...


class ArtifactReader(Protocol):
    """Read-only view of the Phase 2 content-addressed artifact store."""

    def get(self, content_hash: str) -> bytes: ...
    def exists(self, content_hash: str) -> bool: ...


class DecisionJournal(Protocol):
    """Append-only journal of review decisions and refusals."""

    def append_once(
        self, proposal: DecisionProposal, *, recorded_at: str
    ) -> tuple[dict[str, Any], bool]: ...
    def decisions(self, *, decision_kind: str | None = None) -> tuple[dict[str, Any], ...]: ...
    def record_refusal(self, refusal: Refusal, *, recorded_at: str) -> dict[str, Any]: ...
    def refusals(self) -> tuple[dict[str, Any], ...]: ...
    def export(self) -> Mapping[str, Any]: ...
