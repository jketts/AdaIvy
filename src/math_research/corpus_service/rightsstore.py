"""Phase 4A decisions materialized from policy-derived corpus rights.

ADR-0072 §7 replaces the *authorship mechanism*, not the records: every
document still carries its per-document Phase 4A decisions, written through the
unchanged Phase 4A service so the named-processor rule, the closed processor
field set, expiry, revocation, and takedown semantics all apply exactly as
ADR-0064 left them.  The recorded actor is the human who authored the policy;
the derivation provenance (policy content hash, deriving rule id, decision
content hash) travels in the evidence references, and the full derived decision
lives in the corpus rights ledger beside these record ids.

Shard arithmetic: a Phase 4A workspace caps at 256 records.  One admitted
document writes at most five decisions, and takedown appends lifecycle records
later, so a shard admits at most ``RIGHTS_SHARD_MAX_DOCUMENTS`` (40) documents:
1 policy snapshot + 200 decisions, leaving 55 slots for lifecycle history.
Shard assignment is first-admission order, recorded in the rights ledger, so it
never changes when the grow-only corpus later re-sorts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ..phase4a.records import (
    RecordType, RightsReason, RightsUse, RightsValue,
)
from ..phase4a.service import Phase4Service
from ..phase4a.workspace import Phase4Workspace
from .constants import RIGHTS_SHARD_MAX_DOCUMENTS
from .dataroot import rights_dir
from .derivation import STATUS_DERIVED
from .errors import DerivedDecisionInvalidError

_USE_BY_KEY = {
    "acquisition": RightsUse.ACQUISITION,
    "storage_and_retention": RightsUse.STORAGE_AND_RETENTION,
    "parsing": RightsUse.PARSING,
    "embedding": RightsUse.EMBEDDING,
    "model_context": RightsUse.MODEL_CONTEXT,
}

REASON_DETAIL = (
    "Deterministically derived from the operator-approved content-hashed "
    "source-and-rights policy under ADR-0072 Decision 7; the policy content "
    "hash, deriving rule identifier, and exact per-document licence inputs "
    "are recorded in the corpus rights ledger and referenced here."
)


def evidence_refs_for(decision: Mapping[str, Any]) -> tuple[str, ...]:
    """Identifiers binding a Phase 4A record to its derivation provenance."""

    policy_digest = str(decision["policy_content_hash"]).removeprefix("sha256:")[:24]
    decision_digest = str(decision["content_hash"]).removeprefix("sha256:")[:24]
    refs = {
        f"evidence.source-rights-policy.{policy_digest}",
        f"evidence.derived-rights-decision.{decision_digest}",
        f"evidence.deriving-rule.{decision['rule_id']}",
    }
    return tuple(sorted(refs))


class PolicyDerivedRightsWriter:
    """Writes/reads Phase 4A records for derived decisions, shard by shard."""

    def __init__(
        self, root: Path, *, actor_id: str, valid_from: str,
        valid_until: str | None,
    ) -> None:
        self.root = rights_dir(root)
        self.actor_id = actor_id
        self.valid_from = valid_from
        self.valid_until = valid_until

    def shard_root(self, shard_name: str) -> Path:
        return self.root.joinpath(shard_name)

    def existing_shards(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted(
            path.name for path in self.root.iterdir()
            if path.is_dir() and path.name.startswith("shard-")
        ))

    def _shard_document_counts(self) -> dict[str, set[str]]:
        counts: dict[str, set[str]] = {}
        for shard_name in self.existing_shards():
            with Phase4Workspace(self.shard_root(shard_name)) as workspace:
                subjects = {
                    record["subject_id"] for record in workspace.records()
                    if record["record_type"] == RecordType.RIGHTS_DECISION.value
                }
            counts[shard_name] = subjects
        return counts

    def locate(self, source_id: str) -> str | None:
        for shard_name, subjects in self._shard_document_counts().items():
            if source_id in subjects:
                return shard_name
        return None

    def assign_shard(self, source_id: str) -> str:
        located = self.locate(source_id)
        if located is not None:
            return located
        counts = self._shard_document_counts()
        for shard_name in sorted(counts):
            if len(counts[shard_name]) < RIGHTS_SHARD_MAX_DOCUMENTS:
                return shard_name
        return f"shard-{len(counts):03d}"

    def write_derived_decision(
        self, decision: Mapping[str, Any], *, recorded_at: str,
    ) -> tuple[str, tuple[str, ...]]:
        """Append the Phase 4A decisions one derived record implies. Idempotent.

        Returns ``(shard_name, record_ids)``.  A quarantined decision writes
        nothing here — quarantine grants no allowance and needs no record to
        withhold one.
        """

        if decision["status"] != STATUS_DERIVED:
            raise DerivedDecisionInvalidError(
                "only a derived decision materializes Phase 4A records; a "
                "quarantined document carries no allowance"
            )
        source_id = str(decision["source_id"])
        shard_name = self.assign_shard(source_id)
        shard = self.shard_root(shard_name)
        shard.mkdir(parents=True, exist_ok=True)
        refs = evidence_refs_for(decision)
        ids: list[str] = []
        with Phase4Workspace(shard) as workspace:
            service = Phase4Service(workspace)
            if workspace.next_sequence == 0:
                service.initialize_policy(
                    actor_id=self.actor_id, recorded_at=recorded_at,
                )
            existing = {
                (record["subject_id"], record["payload"]["intended_use"]):
                record
                for record in workspace.records()
                if record["record_type"] == RecordType.RIGHTS_DECISION.value
            }
            for key, use in _USE_BY_KEY.items():
                entry = decision["uses"][key]
                disclosing = use in {RightsUse.EMBEDDING, RightsUse.MODEL_CONTEXT}
                if disclosing and entry["value"] != "allowed":
                    # ADR-0064's schema cannot state a prohibited disclosing
                    # use without naming a processor, and naming one would
                    # read as an authorization.  Absence of a decision blocks
                    # the use; the prohibition is recorded in the derived
                    # decision and the corpus rights ledger.
                    continue
                prior = existing.get((source_id, use.value))
                processor = entry["processor"] if disclosing else None
                expected_value = (
                    RightsValue.ALLOWED.value if entry["value"] == "allowed"
                    else RightsValue.PROHIBITED.value
                )
                if (
                    prior is not None
                    and prior["payload"]["value"] == expected_value
                    and prior["payload"]["processor"] == processor
                    and tuple(prior["evidence_refs"]) == refs
                ):
                    ids.append(prior["id"])
                    continue
                record = service.append_rights(
                    source_id=source_id,
                    intended_use=use,
                    value=(
                        RightsValue.ALLOWED if entry["value"] == "allowed"
                        else RightsValue.PROHIBITED
                    ),
                    reason_code=(
                        RightsReason.PERMITTED if entry["value"] == "allowed"
                        else RightsReason.EXPLICITLY_PROHIBITED
                    ),
                    reason_detail=REASON_DETAIL,
                    evidence_refs=refs,
                    actor_id=self.actor_id,
                    valid_from=self.valid_from,
                    valid_until=self.valid_until,
                    recorded_at=recorded_at,
                    lifecycle_id="lifecycle." + source_id,
                    processor=processor,
                    predecessor_id=prior["id"] if prior is not None else None,
                )
                ids.append(record.id)
        return shard_name, tuple(sorted(ids))

    def record_takedown(
        self, source_id: str, *, actor_id: str, reason_detail: str,
        evidence_refs: Iterable[str], recorded_at: str,
    ) -> tuple[str, ...]:
        """Supersede every live decision with PROHIBITED / rights_revoked.

        This is ADR-0064's unchanged revocation semantics: the latest decision
        per ``(source_id, intended_use)`` wins, so every use — including the
        disclosing ones, which keep their named processor on the prohibition —
        evaluates ``EXPLICITLY_PROHIBITED`` from this point on.  Idempotent:
        an already-revoked use is not revoked again.
        """

        shard_name = self.locate(source_id)
        if shard_name is None:
            raise DerivedDecisionInvalidError(
                f"no rights shard holds {source_id}; nothing to take down"
            )
        refs = tuple(sorted(set(evidence_refs)))
        revoked: list[str] = []
        with Phase4Workspace(self.shard_root(shard_name)) as workspace:
            service = Phase4Service(workspace)
            latest: dict[str, dict[str, Any]] = {}
            for record in workspace.records():
                if (
                    record["record_type"] == RecordType.RIGHTS_DECISION.value
                    and record["subject_id"] == source_id
                ):
                    latest[record["payload"]["intended_use"]] = record
            for intended_use, prior in sorted(latest.items()):
                if prior["payload"]["value"] == RightsValue.PROHIBITED.value:
                    continue
                record = service.append_rights(
                    source_id=source_id,
                    intended_use=RightsUse(intended_use),
                    value=RightsValue.PROHIBITED,
                    reason_code=RightsReason.RIGHTS_REVOKED,
                    reason_detail=reason_detail,
                    evidence_refs=refs,
                    actor_id=actor_id,
                    valid_from=recorded_at,
                    valid_until=None,
                    recorded_at=recorded_at,
                    lifecycle_id="lifecycle." + source_id,
                    processor=prior["payload"]["processor"],
                    predecessor_id=prior["id"],
                )
                revoked.append(record.id)
        return tuple(revoked)

    def rights_record_count(self) -> int:
        total = 0
        for shard_name in self.existing_shards():
            with Phase4Workspace(self.shard_root(shard_name)) as workspace:
                total += sum(
                    1 for record in workspace.records()
                    if record["record_type"] == RecordType.RIGHTS_DECISION.value
                )
        return total


__all__ = ["PolicyDerivedRightsWriter", "REASON_DETAIL", "evidence_refs_for"]
