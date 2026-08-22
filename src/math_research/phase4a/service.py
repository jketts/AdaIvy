"""Production application service for local intake, rights, lifecycle, and review."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from . import MAX_SOURCE_BYTES
from .content_store import ContentStoreError, read_local_text
from .records import (
    DISCLOSING_RIGHTS_USES, PROCESSOR_FORBIDDEN_REFUSAL, PROCESSOR_REQUIRED_REFUSAL,
    ActorKind, ApplicabilityOutcome, ApplicabilityReason, ApplicabilityStatus, AuditRecord,
    Authority, LifecycleType, Processor, RecordType, RightsEvaluation, RightsOutcome,
    RightsReason, RightsUse, RightsValue,
)
from .serialization import (
    ZERO_HASH, canonical_hash, expected_record_id, finalize_record, sha256_bytes,
    stable_id,
)
from .validation import PRODUCTION_SCHEMA_SHA256, Phase4ValidationError
from .workspace import Phase4Workspace


class RightsBlocked(PermissionError):
    def __init__(self, evaluation: RightsEvaluation) -> None:
        self.evaluation = evaluation
        super().__init__(evaluation.reason)


class DeletionInterrupted(RuntimeError):
    """Testable crash boundary; metadata is intentionally left for restart reconciliation."""


class Phase4Service:
    def __init__(self, workspace: Phase4Workspace) -> None:
        self.workspace = workspace
        self.reconcile_deletions()
        self.workspace.verify_durable_integrity()

    def _record(
        self, *, record_type: RecordType, subject_id: str, actor_id: str,
        actor_kind: ActorKind, authority: Authority, reason_code: str,
        reason_detail: str, evidence_refs: Iterable[str], recorded_at: str,
        policy_snapshot_id: str, payload: dict[str, Any], predecessor_id: str | None = None,
        supersedes: str | None = None,
    ) -> AuditRecord:
        evidence = tuple(sorted(set(evidence_refs)))
        record = AuditRecord(
            id="record.provisional", record_type=record_type, subject_id=subject_id,
            sequence=self.workspace.next_sequence, actor_id=actor_id, actor_kind=actor_kind,
            authority=authority, reason_code=reason_code, reason_detail=reason_detail,
            evidence_refs=evidence, recorded_at=recorded_at,
            policy_snapshot_id=policy_snapshot_id, predecessor_id=predecessor_id,
            supersedes=supersedes, payload=payload, content_hash=ZERO_HASH,
        )
        from dataclasses import replace

        record = replace(record, id=expected_record_id(record))
        return finalize_record(record)

    def initialize_policy(self, *, actor_id: str, recorded_at: str) -> AuditRecord:
        if self.workspace.next_sequence != 0:
            raise ValueError("Phase 4A policy snapshot must be the first record")
        payload = {
            "schema_sha256": PRODUCTION_SCHEMA_SHA256,
            "rights_policy_version": "phase4a-rights-v1",
            "applicability_policy_version": "phase4a-applicability-v1",
            "lifecycle_policy_version": "phase4a-lifecycle-v1",
            "canonical_identity_policy_version": "phase4a-canonical-identity-v1",
        }
        provisional_id = stable_id("phase4-policy", payload)
        record = AuditRecord(
            id=provisional_id, record_type=RecordType.POLICY_SNAPSHOT, subject_id=provisional_id,
            sequence=0, actor_id=actor_id, actor_kind=ActorKind.SYSTEM,
            authority=Authority.DETERMINISTIC_POLICY, reason_code="policy_snapshot",
            reason_detail="closed Phase 4A v1 production policy", evidence_refs=(),
            recorded_at=recorded_at, policy_snapshot_id=provisional_id, predecessor_id=None,
            supersedes=None, payload=payload, content_hash=ZERO_HASH,
        )
        record = finalize_record(record)
        self.workspace.append(record)
        return record

    def policy_id(self) -> str:
        rows = [record for record in self.workspace.records() if record["record_type"] == RecordType.POLICY_SNAPSHOT.value]
        if len(rows) != 1:
            raise ValueError("Phase 4A workspace lacks exactly one policy snapshot")
        return str(rows[0]["id"])

    def append_rights(
        self, *, source_id: str, intended_use: RightsUse, value: RightsValue,
        reason_code: RightsReason, reason_detail: str, evidence_refs: Iterable[str],
        actor_id: str, valid_from: str, valid_until: str | None, recorded_at: str,
        lifecycle_id: str, processor: Processor | Mapping[str, Any] | None = None,
        predecessor_id: str | None = None,
    ) -> AuditRecord:
        """Append one human-final rights decision.

        ADR-0064: `processor` names the recipient of disclosed source text.  It
        is required for the two disclosing uses and must be `None` for every
        other use.  The closed-envelope validator is the gate: an omitted or
        misplaced processor is refused there and nothing is appended.
        """

        processor_payload = processor.as_payload() if isinstance(processor, Processor) else (
            None if processor is None else dict(processor)
        )
        prior = [
            item for item in self.workspace.records()
            if item["record_type"] == RecordType.RIGHTS_DECISION.value
            and item["subject_id"] == source_id
            and item["payload"]["intended_use"] == intended_use.value
        ]
        expected_predecessor = prior[-1]["id"] if prior else None
        if predecessor_id is None:
            predecessor_id = expected_predecessor
        elif predecessor_id != expected_predecessor:
            raise ValueError("rights predecessor must be the latest decision for the intended use")
        if prior and recorded_at < prior[-1]["recorded_at"]:
            raise ValueError("rights decision time cannot precede its predecessor")
        record = self._record(
            record_type=RecordType.RIGHTS_DECISION, subject_id=source_id, actor_id=actor_id,
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code=reason_code.value, reason_detail=reason_detail,
            evidence_refs=evidence_refs, recorded_at=recorded_at,
            policy_snapshot_id=self.policy_id(), predecessor_id=predecessor_id,
            supersedes=predecessor_id,
            payload={
                "source_id": source_id, "intended_use": intended_use.value, "value": value.value,
                "valid_from": valid_from, "valid_until": valid_until, "lifecycle_id": lifecycle_id,
                "processor": processor_payload,
            },
        )
        self.workspace.append(record)
        return record

    @staticmethod
    def _require_processor_argument(intended_use: RightsUse, processor_id: str | None) -> None:
        """ADR-0064: naming the processor is the caller's obligation, not a default.

        Omitting it for a disclosing use is a programming error and raises; it
        never falls back to a decision that authorized some other processor.
        """

        if intended_use in DISCLOSING_RIGHTS_USES:
            if processor_id is None:
                raise ValueError(
                    f"{PROCESSOR_REQUIRED_REFUSAL}: {intended_use.value} requires a named processor_id"
                )
        elif processor_id is not None:
            raise ValueError(
                f"{PROCESSOR_FORBIDDEN_REFUSAL}: {intended_use.value} must not name a processor_id"
            )

    def evaluate_rights(
        self, source_id: str, intended_use: RightsUse, *, at: str,
        processor_id: str | None = None,
    ) -> RightsEvaluation:
        self._require_processor_argument(intended_use, processor_id)
        records = list(self.workspace.records())
        lifecycles = [
            record for record in records
            if record["record_type"] == RecordType.LIFECYCLE_ACTION.value and record["subject_id"] == source_id
        ]
        deletion_block = any(
            record["payload"]["action"] in {
                LifecycleType.DELETION_REQUEST.value, LifecycleType.DELETION_COMPLETION.value,
            }
            for record in lifecycles
        )
        if deletion_block or (any(
            record["payload"]["action"] in {
                LifecycleType.REVOCATION.value, LifecycleType.TAKEDOWN.value,
                LifecycleType.SUPPRESSION.value,
            }
            for record in lifecycles
        ) and not (
            lifecycles and lifecycles[-1]["payload"]["action"] == LifecycleType.RESTORE.value
        )):
            return RightsEvaluation(source_id, intended_use, RightsOutcome.REVOKED, False, None, "source lifecycle blocks use")
        decisions = [
            record for record in records
            if record["record_type"] == RecordType.RIGHTS_DECISION.value
            and record["subject_id"] == source_id and record["payload"]["intended_use"] == intended_use.value
        ]
        if not decisions:
            other_allowed = any(
                record["record_type"] == RecordType.RIGHTS_DECISION.value
                and record["subject_id"] == source_id and record["payload"]["value"] == RightsValue.ALLOWED.value
                for record in records
            )
            outcome = RightsOutcome.REQUESTED_USE_INCOMPATIBLE if other_allowed else RightsOutcome.MISSING_OR_UNKNOWN
            return RightsEvaluation(source_id, intended_use, outcome, False, None, "no allowed decision exists for requested use")
        decision = decisions[-1]
        payload = decision["payload"]
        if payload["valid_from"] > at or (payload["valid_until"] is not None and at > payload["valid_until"]):
            return RightsEvaluation(source_id, intended_use, RightsOutcome.EXPIRED, False, decision["id"], "rights decision is outside its validity interval")
        value = RightsValue(payload["value"])
        if value is RightsValue.ALLOWED:
            if intended_use in DISCLOSING_RIGHTS_USES:
                authorized = payload["processor"]
                if authorized is None or authorized["processor_id"] != processor_id:
                    named = "none" if authorized is None else authorized["processor_id"]
                    return RightsEvaluation(
                        source_id, intended_use, RightsOutcome.PROCESSOR_NOT_AUTHORIZED, False,
                        decision["id"],
                        f"rights decision authorizes processor {named} and not {processor_id}",
                    )
            return RightsEvaluation(source_id, intended_use, RightsOutcome.PERMITTED, True, decision["id"], "explicit human decision permits requested use")
        if value is RightsValue.PROHIBITED:
            return RightsEvaluation(source_id, intended_use, RightsOutcome.EXPLICITLY_PROHIBITED, False, decision["id"], "explicit human decision prohibits requested use")
        return RightsEvaluation(source_id, intended_use, RightsOutcome.MISSING_OR_UNKNOWN, False, decision["id"], "rights remain unresolved")

    def require_rights(
        self, source_id: str, intended_use: RightsUse, *, at: str,
        processor_id: str | None = None,
    ) -> RightsEvaluation:
        """Raise `RightsBlocked` on any non-permitted outcome.

        The returned evaluation is retained for callers that need the decision
        identity; a caller coding to ADR-0064's `-> None` contract may ignore it.
        """

        evaluation = self.evaluate_rights(source_id, intended_use, at=at, processor_id=processor_id)
        if not evaluation.allowed:
            raise RightsBlocked(evaluation)
        try:
            projection = self.workspace.projection(source_id)
        except KeyError:
            projection = None
        if projection is not None and (projection["suppressed"] or not projection["content_retained"]):
            raise RightsBlocked(RightsEvaluation(source_id, intended_use, RightsOutcome.REVOKED, False, evaluation.decision_id, "source is suppressed"))
        return evaluation

    def intake_local(
        self, path: Path, *, source_id: str, actor_id: str, recorded_at: str,
        title: str | None = None,
    ) -> AuditRecord:
        # Rights checks happen before opening the caller-supplied path.
        for intended_use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.require_rights(source_id, intended_use, at=recorded_at)
        data = read_local_text(path, max_bytes=MAX_SOURCE_BYTES)
        try:
            data.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise ValueError("Phase 4A local source must be valid UTF-8") from error
        if b"\x00" in data or path.suffix.casefold() != ".txt":
            raise ValueError("Phase 4A local source must be eligible UTF-8 .txt content")
        artifact_hash = sha256_bytes(data)
        content_object_id = self.workspace.content.object_id(source_id)
        content_created = False
        try:
            published_object_id = self.workspace.content.put_source(source_id, data)
            content_created = True
            if published_object_id != content_object_id:
                raise ContentStoreError("verified content publication identity differs")
            record = self._record(
                record_type=RecordType.SOURCE_PROVENANCE, subject_id=source_id, actor_id=actor_id,
                actor_kind=ActorKind.HUMAN, authority=Authority.SOURCE_PROVENANCE,
                reason_code="local_user_supplied", reason_detail="explicit local source supplied by named user",
                evidence_refs=(f"evidence.{artifact_hash[7:31]}",), recorded_at=recorded_at,
                policy_snapshot_id=self.policy_id(),
                payload={
                    "source_identity": source_id, "source_name": title or path.name,
                    "content_object_id": content_object_id, "artifact_hash": artifact_hash,
                    "byte_length": len(data), "media_type": "text/plain", "encoding": "utf-8",
                    "quarantined": False, "quarantine_reasons": [],
                    "content_retained": True, "tombstone": False,
                },
            )
            self.workspace.append(record)
        except BaseException:
            if content_created:
                self.workspace.content.remove_source(source_id)
            raise
        self.workspace.record_source_path(source_id, sha256_bytes(str(path.resolve()).encode("utf-8")))
        self.workspace.rebuild_projections()
        return record

    def append_lifecycle(
        self, *, source_id: str, action: LifecycleType, target_record_id: str,
        actor_id: str, actor_kind: ActorKind, authority: Authority,
        reason_code: str, reason_detail: str, evidence_refs: Iterable[str],
        recorded_at: str, legal_hold: bool = False,
    ) -> AuditRecord:
        target = self.workspace.record(target_record_id)
        if target["subject_id"] != source_id:
            raise ValueError("lifecycle target belongs to another source")
        prior = [
            record for record in self.workspace.records()
            if record["record_type"] == RecordType.LIFECYCLE_ACTION.value and record["subject_id"] == source_id
        ]
        if prior and recorded_at < prior[-1]["recorded_at"]:
            raise ValueError("lifecycle event time cannot precede its predecessor")
        projection = self.workspace.projection(source_id)
        if action is LifecycleType.DELETION_COMPLETION:
            raise ValueError("deletion completion is emitted only by verified complete_deletion")
        content_retained = action is not LifecycleType.DELETION_COMPLETION and projection["content_retained"]
        record = self._record(
            record_type=RecordType.LIFECYCLE_ACTION, subject_id=source_id, actor_id=actor_id,
            actor_kind=actor_kind, authority=authority, reason_code=reason_code,
            reason_detail=reason_detail, evidence_refs=evidence_refs, recorded_at=recorded_at,
            policy_snapshot_id=self.policy_id(), predecessor_id=prior[-1]["id"] if prior else None,
            payload={
                "source_id": source_id, "action": action.value, "target_record_id": target_record_id,
                "previous_event_id": prior[-1]["id"] if prior else None,
                "original_semantic_hash": target["content_hash"], "content_retained": content_retained,
                "legal_hold": legal_hold,
            },
        )
        self.workspace.append(record)
        return record

    def complete_deletion(self, source_id: str, *, fail_after: str | None = None) -> dict[str, Any]:
        info = self.workspace.deletion_info(source_id)
        if info["deletion_state"] == "completed":
            self.workspace.verify_source_absent(source_id)
            with self.workspace.verified_read_snapshot() as (records, _paths):
                completions = [
                    record for record in records
                    if record["record_type"] == RecordType.LIFECYCLE_ACTION.value
                    and record["subject_id"] == source_id
                    and record["payload"]["action"] == LifecycleType.DELETION_COMPLETION.value
                ]
                if len(completions) != 1:
                    raise Phase4ValidationError(
                        "completed Phase 4A source lacks exactly one completion event"
                    )
                return completions[0]
        if info["deletion_state"] not in {"requested", "removing"}:
            raise ValueError("deletion completion requires a pending deletion request")
        projection = self.workspace.projection(source_id)
        if projection["legal_hold"]:
            raise ValueError("legal hold blocks deletion completion")
        request = self.workspace.record(str(info["deletion_request_id"]))
        try:
            self.workspace._begin_deletion_removal(source_id)
            if fail_after == "before_removal":
                raise DeletionInterrupted("interrupted before Phase 4 content removal")
            self.workspace.content.remove_source(source_id)
            if fail_after == "after_removal":
                raise DeletionInterrupted("interrupted after Phase 4 content removal")
            self.workspace.verify_source_absent(source_id)
            provenance_id = str(info["provenance_record_id"])
            prior = [
                record for record in self.workspace.records()
                if record["record_type"] == RecordType.LIFECYCLE_ACTION.value and record["subject_id"] == source_id
            ]
            target = self.workspace.record(provenance_id)
            completion = self._record(
                record_type=RecordType.LIFECYCLE_ACTION, subject_id=source_id,
                actor_id="actor.phase4-deletion", actor_kind=ActorKind.SYSTEM,
                authority=Authority.DETERMINISTIC_POLICY, reason_code="content_deleted",
                reason_detail="verified Phase 4A content-boundary deletion completed",
                evidence_refs=tuple(request["evidence_refs"]),
                recorded_at=str(info["completion_recorded_at"]), policy_snapshot_id=self.policy_id(),
                predecessor_id=prior[-1]["id"] if prior else None,
                payload={
                    "source_id": source_id, "action": LifecycleType.DELETION_COMPLETION.value,
                    "target_record_id": provenance_id,
                    "previous_event_id": prior[-1]["id"] if prior else None,
                    "original_semantic_hash": target["content_hash"],
                    "content_retained": False, "legal_hold": False,
                },
            )
            self.workspace.append_deletion_completion(completion)
            return self.workspace.record(completion.id)
        except DeletionInterrupted:
            raise
        except BaseException as error:
            self.workspace._record_deletion_failure(source_id, error)
            raise

    def reconcile_deletions(self) -> None:
        for source_id in self.workspace.pending_deletions():
            try:
                self.complete_deletion(source_id)
            except (Phase4ValidationError, OSError, ValueError):
                # complete_deletion records the durable fail-closed incomplete state.
                continue

    def create_evidence_card(
        self, *, source_id: str, span_byte_ranges: Iterable[tuple[int, int]],
        bibliographic_identity: str, imported_statement: str,
        hypotheses: Iterable[str], definitions: Iterable[str], scope: Iterable[str],
        exceptions: Iterable[str], actor_id: str, actor_kind: ActorKind,
        reason_detail: str, recorded_at: str,
    ) -> AuditRecord:
        self.require_rights(source_id, RightsUse.EXCERPTING, at=recorded_at)
        content_lists = {
            "hypotheses": sorted(set(hypotheses)), "definitions": sorted(set(definitions)),
            "scope": sorted(set(scope)), "exceptions": sorted(set(exceptions)),
        }
        if not imported_statement or len(bibliographic_identity.encode("utf-8")) > 8192 or len(imported_statement.encode("utf-8")) > 8192:
            raise ValueError("evidence-card identity/statement is empty or exceeds 8192 UTF-8 bytes")
        if any(len(items) > 32 or any(len(item.encode("utf-8")) > 8192 for item in items) for items in content_lists.values()):
            raise ValueError("evidence-card lists exceed the closed production bounds")
        source = self.workspace.content.read_source(source_id)
        ranges = tuple(span_byte_ranges)
        if not ranges or len(ranges) > 16:
            raise ValueError("evidence card requires 1..16 exact source byte ranges")
        if any(
            isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int)
            or start < 0 or end <= start or end > len(source)
            for start, end in ranges
        ):
            raise ValueError("evidence card source byte range is invalid")
        if list(ranges) != sorted(ranges) or any(ranges[index - 1][1] > ranges[index][0] for index in range(1, len(ranges))):
            raise ValueError("evidence card source byte ranges must be ordered and non-overlapping")
        selected = b"".join(source[start:end] for start, end in ranges)
        if selected != imported_statement.encode("utf-8"):
            raise ValueError("imported statement must exactly match the selected source bytes")
        info = self.workspace.deletion_info(source_id)
        artifact_id = str(info["content_object_id"])
        span_values = [
            {
                "start": start, "end": end,
                "span_hash": sha256_bytes(source[start:end]),
            }
            for start, end in ranges
        ]
        span_ids = [stable_id("phase4-span", {"source_id": source_id, **value}) for value in span_values]
        evidence_unit_id = stable_id(
            "phase4-evidence-unit", {"source_id": source_id, "artifact_hash": info["artifact_hash"], "spans": span_values}
        )
        record = self._record(
            record_type=RecordType.EVIDENCE_CARD, subject_id=source_id, actor_id=actor_id,
            actor_kind=actor_kind, authority=Authority.PROPOSAL, reason_code="source_derived_evidence",
            reason_detail=reason_detail, evidence_refs=tuple(span_ids),
            recorded_at=recorded_at, policy_snapshot_id=self.policy_id(),
            payload={
                "source_id": source_id, "artifact_id": artifact_id, "evidence_unit_id": evidence_unit_id,
                "span_ids": span_ids, "span_byte_ranges": span_values,
                "bibliographic_identity_hash": sha256_bytes(bibliographic_identity.encode("utf-8")),
                "bibliographic_identity_bytes": len(bibliographic_identity.encode("utf-8")),
                "imported_statement_hash": sha256_bytes(imported_statement.encode("utf-8")),
                "imported_statement_bytes": len(imported_statement.encode("utf-8")),
                "hypotheses_hash": canonical_hash(content_lists["hypotheses"]), "hypotheses_count": len(content_lists["hypotheses"]),
                "definitions_hash": canonical_hash(content_lists["definitions"]), "definitions_count": len(content_lists["definitions"]),
                "scope_hash": canonical_hash(content_lists["scope"]), "scope_count": len(content_lists["scope"]),
                "exceptions_hash": canonical_hash(content_lists["exceptions"]), "exceptions_count": len(content_lists["exceptions"]),
                "content_exported": False,
            },
        )
        self.workspace.content.put_card(
            source_id, record.id,
            {
                "bibliographic_identity": bibliographic_identity, "imported_statement": imported_statement,
                **content_lists,
            },
        )
        try:
            self.workspace.append(record)
        except BaseException:
            self.workspace.content.remove_card(source_id, record.id)
            raise
        return record

    def inspect_evidence_card(self, card_id: str, *, at: str) -> dict[str, Any]:
        record = self.workspace.record(card_id)
        if record["record_type"] != RecordType.EVIDENCE_CARD.value:
            raise ValueError("record is not an evidence card")
        self.require_rights(record["subject_id"], RightsUse.EXCERPTING, at=at)
        return self.workspace.content.read_card(record["subject_id"], card_id)

    def review_applicability(
        self, *, source_id: str, evidence_card_id: str, status: ApplicabilityStatus,
        outcome: ApplicabilityOutcome, reason_code: ApplicabilityReason, reason_detail: str,
        evidence_refs: Iterable[str], actor_id: str, actor_kind: ActorKind,
        recorded_at: str, checks: Mapping[str, bool], predecessor_id: str | None = None,
    ) -> AuditRecord:
        if actor_kind is ActorKind.HUMAN and status is not ApplicabilityStatus.PROPOSED:
            authority = Authority.HUMAN_FINAL
        else:
            authority = Authority.PROPOSAL
        required_checks = {
            "bibliographic_identity_checked", "hypotheses_checked", "definitions_checked",
            "scope_exceptions_checked", "implication_checked",
        }
        if set(checks) != required_checks:
            raise ValueError("applicability review check fields differ")
        if outcome is ApplicabilityOutcome.APPLICABLE and status is ApplicabilityStatus.CHECKED:
            self.require_rights(source_id, RightsUse.EXCERPTING, at=recorded_at)
        record = self._record(
            record_type=RecordType.APPLICABILITY_REVIEW, subject_id=source_id, actor_id=actor_id,
            actor_kind=actor_kind, authority=authority, reason_code=reason_code.value,
            reason_detail=reason_detail, evidence_refs=evidence_refs, recorded_at=recorded_at,
            policy_snapshot_id=self.policy_id(), predecessor_id=predecessor_id,
            supersedes=predecessor_id,
            payload={
                "source_id": source_id, "evidence_card_id": evidence_card_id,
                "status": status.value, "outcome": outcome.value, **dict(checks),
            },
        )
        # Validate the complete actor matrix before persistence.
        if actor_kind is not ActorKind.HUMAN and status is not ApplicabilityStatus.PROPOSED:
            raise Phase4ValidationError("nonhuman applicability observations must remain proposed")
        if actor_kind is ActorKind.HUMAN and status is ApplicabilityStatus.CHECKED and outcome is ApplicabilityOutcome.APPLICABLE and not all(checks.values()):
            raise Phase4ValidationError("checked/applicable requires every human review dimension")
        self.workspace.append(record)
        return record
