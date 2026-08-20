"""Offline integration service for bounded Phase 4B candidate processing.

The service deliberately has no ambient network or parser dependency.  Callers
must inject the acquisition resolver/transport and (optionally) a parser
adapter.  Original bytes live only in the deletable Phase 4B content boundary;
the append-only database receives hashes, counts, and exact byte anchors.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Sequence

from ..phase4a.records import RightsUse
from ..phase4a.service import Phase4Service, RightsBlocked
from .acquisition import (
    AcquisitionPolicy, AcquisitionRequest, AcquisitionResult, Resolver, StartClock,
    RightsDecision, RobotsSnapshot, RunAuthorization, TermsSnapshot, Transport,
    acquire, origin_for,
)
from .content_store import Phase4BContentStore
from .content_store import ContentStoreError
from .parsing import (
    HTML_PROFILE, PDF_PROFILE, PROFILES, TEX_PROFILE, ParseRequest, ParseResult,
    ParserWorker, quarantine_before_worker, run_production_parser,
)
from .records import CandidateState, RecordType
from .replay_artifacts import (
    ACQUISITION_TRACE, PARSE_PROPOSAL, acquisition_trace_payload,
    durable_parse_failure_code, parse_proposal_binding_hash, parse_proposal_payload,
)
from .serialization import canonical_hash, sha256_bytes, stable_id
from .workspace import Phase4BWorkspace


@dataclass(frozen=True, slots=True)
class StoredAcquisition:
    result: AcquisitionResult
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class StoredParse:
    result: ParseResult
    record: dict[str, Any]


class Phase4BService:
    """Coordinate sealed Phase 4A rights with Phase 4B candidate boundaries."""

    def __init__(self, workspace: Phase4BWorkspace) -> None:
        self.workspace = workspace
        self.rights = Phase4Service(workspace.phase4a)
        self.content = Phase4BContentStore(workspace.root / "phase4b-content")
        self._reconcile_content_state()

    def close(self) -> None:
        self.content.close()

    def __enter__(self) -> "Phase4BService":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _prefixed(value: str) -> str:
        return value if value.startswith("sha256:") else "sha256:" + value

    @staticmethod
    def _content_signature_matches(profile_name: str, data: bytes) -> bool:
        """Conservative, non-parsing recognition before the worker boundary."""
        if profile_name == PDF_PROFILE.name:
            return data.startswith(b"%PDF-1.") and data.rstrip().endswith(b"%%EOF")
        if profile_name == HTML_PROFILE.name:
            prefix = data.lstrip()[:256].lower()
            return re.match(
                rb"<(?:!doctype\s+html\b|html\b|head\b|body\b|main\b|article\b|"
                rb"section\b|div\b|p\b|h[1-6]\b|math\b)",
                prefix,
            ) is not None
        if profile_name == TEX_PROFILE.name:
            try:
                text = data.decode("utf-8", "strict")
            except UnicodeDecodeError:
                return False
            return (
                re.search(r"\\[A-Za-z@]+", text) is not None
                or re.search(r"\$[^$\r\n]+\$", text) is not None
                or re.search(r"\\\([^\r\n]+\\\)", text) is not None
            )
        return True

    @staticmethod
    def _acquisition_failure_code(result: AcquisitionResult) -> str:
        semantic = json.loads(result.semantic_bytes)
        reasons = {
            str(item.get("reason", "")) for item in semantic.get("results", [])
            if item.get("outcome") == "failed"
        }
        if any("rights" in reason for reason in reasons):
            return "rights_blocked"
        if any("robots" in reason for reason in reasons):
            return "robots_blocked"
        if any("terms" in reason for reason in reasons):
            return "terms_blocked"
        if any(
            token in reason
            for reason in reasons
            for token in ("authorized", "authority", "authorization")
        ):
            return "authorization_denied"
        if any(
            token in reason
            for reason in reasons
            for token in ("too_large", "exhausted", "exceeded", "limit", "bound")
        ):
            return "resource_limit"
        return "network_policy_blocked"

    def _allowed_decisions(
        self, source_id: str, uses: Sequence[RightsUse], *, at: str
    ) -> tuple[dict[RightsUse, str], str]:
        decisions: dict[RightsUse, str] = {}
        for use in uses:
            evaluation = self.rights.require_rights(source_id, use, at=at)
            if evaluation.decision_id is None:
                raise RuntimeError("allowed Phase 4A rights lack a decision identity")
            decisions[use] = evaluation.decision_id
        return decisions, self.rights.policy_id()

    def _acquisition_projection(self, source_id: str) -> list[dict[str, Any]]:
        return [
            item for item in self.workspace.projection()
            if item["subject_id"] == source_id
            and item["record_type"] == RecordType.ACQUISITION_CANDIDATE.value
        ]

    def _assert_source_not_tombstoned(self, source_id: str) -> None:
        acquisitions = self._acquisition_projection(source_id)
        if any(
            item["current_state"] == CandidateState.INVALIDATED.value
            for item in acquisitions
        ):
            raise ValueError(
                "an invalidated source identity cannot be republished; use a new source identity"
            )
        if acquisitions:
            raise ValueError("a source identity can have only one acquisition candidate")

    def _assert_active_acquisition(self, source_id: str, record_id: str) -> None:
        projected = {item["record_id"]: item for item in self.workspace.projection()}
        item = projected.get(record_id)
        if (
            item is not None
            and item["subject_id"] == source_id
            and item["record_type"] == RecordType.ACQUISITION_CANDIDATE.value
            and item["current_state"] == CandidateState.INVALIDATED.value
        ):
            self.content.remove(source_id)
            self.content.verify_absent(source_id)
        if (
            item is None
            or item["subject_id"] != source_id
            or item["record_type"]
            != RecordType.ACQUISITION_CANDIDATE.value
            or item["current_state"] != CandidateState.ACTIVE.value
        ):
            raise ValueError("invalidated acquisition candidates cannot be parsed")

    def acquire(
        self,
        source_id: str,
        requests: Sequence[AcquisitionRequest],
        *,
        authorization: RunAuthorization,
        policy: AcquisitionPolicy,
        terms: Sequence[TermsSnapshot],
        robots: Sequence[RobotsSnapshot],
        resolver: Resolver,
        transport: Transport,
        start_clock: StartClock,
        now_epoch: int,
        recorded_at_epoch: int,
        recorded_at: str,
    ) -> StoredAcquisition:
        """Acquire through injected ports after authoritative Phase 4A checks."""
        if len(requests) != 1 or len(authorization.resources) != 1:
            raise ValueError(
                "one Phase 4B source must map to exactly one authorized acquisition request"
            )
        self._assert_source_not_tombstoned(source_id)
        decision_ids, policy_snapshot_id = self._allowed_decisions(
            source_id,
            (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION),
            at=recorded_at,
        )
        urls = sorted(
            {resource.url for resource in authorization.resources}
            | {snapshot.url for snapshot in robots}
        )
        derived_rights = tuple(
            RightsDecision(
                decision_ids[use], authorization.run_id, url, use.value,
                "allowed", "human", "human_final", now_epoch, now_epoch,
            )
            for url in urls
            for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION)
        )
        result = acquire(
            requests,
            authorization=authorization,
            policy=policy,
            rights=derived_rights,
            terms=terms,
            robots=robots,
            resolver=resolver,
            transport=transport,
            start_clock=start_clock,
            now_epoch=now_epoch,
            recorded_at_epoch=recorded_at_epoch,
        )
        attempt_trace = acquisition_trace_payload(result)
        stored: list[dict[str, Any]] = []
        terms_by_origin = {item.origin: item for item in terms}
        robots_by_url = {item.url: item for item in robots}
        for candidate in result.candidates:
            artifact_hash = self._prefixed(candidate.content_sha256)
            # The acquisition adapter rechecks its immutable decision envelope;
            # the service separately rechecks the authoritative Phase 4A state
            # immediately before complete bytes become visible.
            try:
                for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION):
                    self.rights.require_rights(source_id, use, at=recorded_at)
            except RightsBlocked:
                self.workspace.append(
                    record_type=RecordType.FAILURE,
                    subject_id=source_id,
                    recorded_at=recorded_at,
                    payload={
                        "candidate_id": stable_id(
                            "candidate.acquisition-rights-revoked", result.semantic_hash
                        ),
                        "operation": "acquisition",
                        "source_id": source_id,
                        "input_hash": self._prefixed(result.semantic_hash),
                        "failure_code": "rights_blocked",
                        "boundary_id": "boundary.phase4b.acquisition",
                        "observed_byte_count": len(candidate.body),
                        "policy_snapshot_id": policy_snapshot_id,
                        "predecessor_record_ids": [],
                    },
                    replay_artifacts=((ACQUISITION_TRACE, attempt_trace),),
                )
                raise
            self._assert_source_not_tombstoned(source_id)
            object_id = self.content.object_id(source_id)
            self.workspace.begin_publication(
                source_id=source_id, artifact_hash=artifact_hash,
                content_object_id=object_id, recorded_at=recorded_at,
            )
            try:
                object_id = self.content.publish(
                    source_id, candidate.body, expected_hash=artifact_hash
                )
                # Close both revocation windows: injected work and filesystem
                # publication may each take time.  A tombstone is permanent for
                # this source identity even if rights are later re-allowed.
                for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION):
                    self.rights.require_rights(source_id, use, at=recorded_at)
                self._assert_source_not_tombstoned(source_id)
                terms_snapshot = terms_by_origin[origin_for(candidate.source_url)]
                robots_snapshot = robots_by_url[candidate.source_url]
                record = self.workspace.append(
                    record_type=RecordType.ACQUISITION_CANDIDATE,
                    subject_id=source_id,
                    recorded_at=recorded_at,
                    payload={
                        "candidate_id": candidate.candidate_id,
                        "source_id": source_id,
                        "request_id": candidate.request_id,
                        "normalized_url_hash": sha256_bytes(candidate.source_url.encode("utf-8")),
                        "content_object_id": object_id,
                        "artifact_hash": artifact_hash,
                        "byte_length": len(candidate.body),
                        "media_type_hash": sha256_bytes(candidate.media_type.encode("utf-8")),
                        "acquisition_adapter_id": "adaivy.injected-https-v1",
                        "acquisition_adapter_version": "1.0.0",
                        "policy_snapshot_id": policy_snapshot_id,
                        "rights_decision_ids": sorted(
                            (decision_ids[RightsUse.ACQUISITION],
                             decision_ids[RightsUse.STORAGE_AND_RETENTION])
                        ),
                        "terms_snapshot_hash": self._prefixed(terms_snapshot.content_hash),
                        "robots_snapshot_hash": self._prefixed(robots_snapshot.content_hash),
                        "predecessor_record_ids": [],
                    },
                    replay_artifacts=((ACQUISITION_TRACE, attempt_trace),),
                )
            except BaseException as error:
                self.content.remove(source_id)
                self.workspace.finish_publication(source_id)
                if isinstance(error, RightsBlocked):
                    self.workspace.append(
                        record_type=RecordType.FAILURE,
                        subject_id=source_id,
                        recorded_at=recorded_at,
                        payload={
                            "candidate_id": stable_id(
                                "candidate.acquisition-rights-revoked", result.semantic_hash
                            ),
                            "operation": "acquisition",
                            "source_id": source_id,
                            "input_hash": self._prefixed(result.semantic_hash),
                            "failure_code": "rights_blocked",
                            "boundary_id": "boundary.phase4b.acquisition",
                            "observed_byte_count": len(candidate.body),
                            "policy_snapshot_id": policy_snapshot_id,
                            "predecessor_record_ids": [],
                        },
                        replay_artifacts=((ACQUISITION_TRACE, attempt_trace),),
                    )
                raise
            self.workspace.finish_publication(source_id)
            stored.append(record)
        if not result.candidates:
            stored.append(
                self.workspace.append(
                    record_type=RecordType.FAILURE,
                    subject_id=source_id,
                    recorded_at=recorded_at,
                    payload={
                        "candidate_id": stable_id(
                            "candidate.acquisition-failure", result.semantic_hash
                        ),
                        "operation": "acquisition",
                        "source_id": source_id,
                        "input_hash": self._prefixed(result.semantic_hash),
                        "failure_code": self._acquisition_failure_code(result),
                        "boundary_id": "boundary.phase4b.acquisition",
                        "observed_byte_count": 0,
                        "policy_snapshot_id": policy_snapshot_id,
                        "predecessor_record_ids": [],
                    },
                    replay_artifacts=((ACQUISITION_TRACE, attempt_trace),),
                )
            )
        return StoredAcquisition(result, tuple(stored))

    def parse(
        self,
        source_id: str,
        acquisition_record_id: str,
        *,
        request_id: str,
        representation_id: str,
        media_type: str,
        profile_name: str,
        recorded_at: str,
        worker: ParserWorker | None = None,
    ) -> StoredParse:
        evaluation = self.rights.require_rights(
            source_id, RightsUse.PARSING, at=recorded_at
        )
        if evaluation.decision_id is None:
            raise RuntimeError("allowed Phase 4A parsing rights lack an identity")
        acquired = self.workspace.record(acquisition_record_id)
        if (
            acquired["record_type"] != RecordType.ACQUISITION_CANDIDATE.value
            or acquired["subject_id"] != source_id
        ):
            raise ValueError("parse predecessor must be this source's acquisition candidate")
        self._assert_active_acquisition(source_id, acquisition_record_id)
        artifact_hash = acquired["payload"]["artifact_hash"]
        original = self.content.read(source_id, expected_hash=artifact_hash)
        profile = PROFILES.get(profile_name)
        if profile is None:
            raise ValueError("unknown parser profile")
        media_profile_mismatch = media_type != profile.media_type
        request = ParseRequest.create(
            request_id=request_id,
            source_id=source_id,
            content_object_id=acquired["payload"]["content_object_id"],
            representation_id=representation_id,
            # A rejected envelope still needs a valid strict request identity.
            # The durable failure and result code record that the caller supplied
            # a mismatched media/profile pair.
            media_type=profile.media_type if media_profile_mismatch else media_type,
            profile_name=profile_name,
            original_bytes=original,
        )
        if media_profile_mismatch:
            result = quarantine_before_worker(request, "media_profile_mismatch")
        elif sha256_bytes(media_type.encode("utf-8")) != acquired["payload"]["media_type_hash"]:
            result = quarantine_before_worker(request, "acquisition_media_type_mismatch")
        elif not self._content_signature_matches(profile_name, original):
            result = quarantine_before_worker(request, "content_signature_mismatch")
        else:
            result = run_production_parser(request, worker=worker)
        # Parser execution is an untrusted, potentially long-running boundary.
        # Re-evaluate every right needed to retain or derive the result and the
        # predecessor state before appending either success or failure metadata.
        try:
            self.rights.require_rights(source_id, RightsUse.PARSING, at=recorded_at)
            self.rights.require_rights(
                source_id, RightsUse.STORAGE_AND_RETENTION, at=recorded_at
            )
        except RightsBlocked:
            self.synchronize_rights(source_id, at=recorded_at)
            raise
        self._assert_active_acquisition(source_id, acquisition_record_id)
        policy_snapshot_id = self.rights.policy_id()
        replay_payload = parse_proposal_payload(result)
        candidate_identity = {
            "result_semantic_sha256": result.semantic_sha256,
            "proposal_binding_sha256": parse_proposal_binding_hash(replay_payload),
        }
        if result.disposition != "candidate_proposal":
            code = durable_parse_failure_code(result.disposition, result.failure_code)
            record = self.workspace.append(
                record_type=RecordType.FAILURE,
                subject_id=source_id,
                recorded_at=recorded_at,
                payload={
                    "candidate_id": stable_id("candidate.parse-failure", candidate_identity),
                    "operation": "parse",
                    "source_id": source_id,
                    "input_hash": artifact_hash,
                    "failure_code": code,
                    "boundary_id": "boundary.phase4b.parser",
                    "observed_byte_count": len(original),
                    "policy_snapshot_id": policy_snapshot_id,
                    "predecessor_record_ids": [acquisition_record_id],
                },
                operational={
                    "attempt_number": result.operation.attempt_ordinal,
                    "elapsed_milliseconds": result.operation.duration_ms,
                    "exit_status": result.operation.worker_exit_code,
                    "stdout_hash": result.operation.stdout_sha256,
                    "stderr_hash": result.operation.stderr_sha256,
                    "stdout_bytes": result.operation.stdout_byte_length,
                    "stderr_bytes": result.operation.stderr_byte_length,
                },
                replay_artifacts=((PARSE_PROPOSAL, replay_payload),),
            )
            return StoredParse(result, record)

        anchors_by_key: dict[tuple[int, int], dict[str, Any]] = {}
        for item in tuple(result.segments) + tuple(result.references):
            anchor = item.anchor
            object_hash = (
                sha256_bytes(anchor.object_id.encode("utf-8"))
                if anchor.object_id is not None else None
            )
            key = (anchor.start, anchor.end)
            anchors_by_key[key] = {
                "start_offset": anchor.start,
                "end_offset": anchor.end,
                "exact_text_hash": anchor.slice_sha256,
                "page_number": anchor.page_index + 1 if anchor.page_index is not None else None,
                "object_id_hash": object_hash,
            }
        anchors = [anchors_by_key[key] for key in sorted(anchors_by_key)]
        decoded_bytes = sum(
            len(item.normalized_text.encode("utf-8")) for item in result.segments
        ) + sum(len(item.target.encode("utf-8")) for item in result.references)
        identity = result.parser_identity
        record = self.workspace.append(
            record_type=RecordType.PARSE_CANDIDATE,
            subject_id=source_id,
            recorded_at=recorded_at,
            payload={
                "candidate_id": stable_id("candidate.parse", candidate_identity),
                "source_id": source_id,
                "artifact_hash": artifact_hash,
                "parser_id": identity["adapter_name"],
                "parser_version": identity["adapter_version"],
                "parser_configuration_hash": canonical_hash(identity),
                "policy_snapshot_id": policy_snapshot_id,
                "input_byte_length": len(original),
                "output_byte_length": decoded_bytes,
                "segment_count": len(result.segments),
                "formula_count": sum(item.kind == "formula" for item in result.segments),
                "reference_count": len(result.references),
                "anchors": anchors,
                "predecessor_record_ids": [acquisition_record_id],
            },
            operational={
                "attempt_number": result.operation.attempt_ordinal,
                "elapsed_milliseconds": result.operation.duration_ms,
                "exit_status": result.operation.worker_exit_code,
                "stdout_hash": result.operation.stdout_sha256,
                "stderr_hash": result.operation.stderr_sha256,
                "stdout_bytes": result.operation.stdout_byte_length,
                "stderr_bytes": result.operation.stderr_byte_length,
            },
            replay_artifacts=((PARSE_PROPOSAL, replay_payload),),
        )
        return StoredParse(result, record)

    def synchronize_rights(self, source_id: str, *, at: str) -> dict[str, Any] | None:
        """Invalidate candidates and erase bytes when any required use is blocked."""
        trigger_id: str | None = None
        for use in (
            RightsUse.ACQUISITION,
            RightsUse.STORAGE_AND_RETENTION,
            RightsUse.PARSING,
        ):
            evaluation = self.rights.evaluate_rights(source_id, use, at=at)
            if not evaluation.allowed:
                trigger_id = evaluation.decision_id or stable_id(
                    "phase4b-rights-evaluation", {"source_id": source_id, "use": use.value, "at": at}
                )
                break
        if trigger_id is None:
            return None
        active = sorted(
            item["record_id"] for item in self.workspace.projection()
            if item["subject_id"] == source_id
            and item["current_state"] == CandidateState.ACTIVE.value
        )
        if not active:
            self.content.remove(source_id)
            self.content.verify_absent(source_id)
            return None
        return self.invalidate_candidates(
            source_id,
            active,
            trigger_record_id=trigger_id,
            reason_code="rights_changed",
            at=at,
            erase_content=True,
        )

    def invalidate_candidates(
        self,
        source_id: str,
        affected_record_ids: Sequence[str],
        *,
        trigger_record_id: str,
        reason_code: str,
        at: str,
        erase_content: bool,
    ) -> dict[str, Any]:
        """Apply one trusted external lifecycle decision to active candidates.

        The caller supplies the append-only identity of the authoritative
        correction, takedown, deletion, or supersession decision.  This method
        never manufactures authority from parser or acquisition output: it
        only validates and projects an already-made external decision.
        """
        allowed_reasons = {
            "source_correction", "source_revocation", "source_takedown",
            "source_deletion", "applicability_superseded", "parser_superseded",
            "policy_superseded", "rights_changed", "integrity_failure",
        }
        if reason_code not in allowed_reasons:
            raise ValueError("lifecycle invalidation reason is not closed")
        deletion_reasons = {
            "source_correction", "source_revocation", "source_takedown",
            "source_deletion", "rights_changed", "integrity_failure",
        }
        if reason_code in deletion_reasons and not erase_content:
            raise ValueError("source-level lifecycle invalidation must erase content")
        requested = tuple(sorted(affected_record_ids))
        if not requested or len(requested) != len(set(requested)):
            raise ValueError("lifecycle invalidation targets must be nonempty and unique")
        projection = {item["record_id"]: item for item in self.workspace.projection()}
        if any(
            target not in projection
            or projection[target]["subject_id"] != source_id
            or projection[target]["current_state"] != CandidateState.ACTIVE.value
            for target in requested
        ):
            raise ValueError("lifecycle invalidation may target only active candidates for this source")
        record = self.workspace.append(
            record_type=RecordType.INVALIDATION,
            subject_id=source_id,
            recorded_at=at,
            payload={
                "invalidation_id": stable_id(
                    "invalidation.phase4b",
                    {"trigger": trigger_record_id, "affected": requested},
                ),
                "trigger_record_id": trigger_record_id,
                "affected_record_ids": list(requested),
                "reason_code": reason_code,
                "policy_snapshot_id": self.rights.policy_id(),
            },
        )
        if erase_content:
            self.content.remove(source_id)
            self.content.verify_absent(source_id)
        return record

    def _append_integrity_invalidation(
        self, source_id: str, active: list[str], acquisition: dict[str, Any]
    ) -> None:
        if not active:
            return
        trigger_id = stable_id(
            "phase4b-content-integrity",
            {"source_id": source_id, "artifact_hash": acquisition["payload"]["artifact_hash"]},
        )
        self.workspace.append(
            record_type=RecordType.INVALIDATION,
            subject_id=source_id,
            recorded_at=acquisition["recorded_at"],
            payload={
                "invalidation_id": stable_id(
                    "invalidation.phase4b", {"trigger": trigger_id, "affected": active}
                ),
                "trigger_record_id": trigger_id,
                "affected_record_ids": active,
                "reason_code": "integrity_failure",
                "policy_snapshot_id": acquisition["payload"]["policy_snapshot_id"],
            },
        )

    def _reconcile_content_state(self) -> None:
        # A journal row means publication did not reach its final durable step.
        # Preserve content only when an active acquisition record proves commit.
        for pending in self.workspace.pending_publications():
            source_id = pending["source_id"]
            matching = [
                item for item in self.workspace.records()
                if item["subject_id"] == source_id
                and item["record_type"] == RecordType.ACQUISITION_CANDIDATE.value
                and item["payload"]["artifact_hash"] == pending["artifact_hash"]
                and item["payload"]["content_object_id"] == pending["content_object_id"]
            ]
            active_ids = {
                item["record_id"] for item in self._acquisition_projection(source_id)
                if item["current_state"] == CandidateState.ACTIVE.value
            }
            if not any(item["record_id"] in active_ids for item in matching):
                self.content.remove(source_id)
            self.workspace.finish_publication(source_id)

        projection = self.workspace.projection()
        subjects = {item["subject_id"] for item in projection}
        for source_id in subjects:
            acquisitions = [
                item for item in projection
                if item["subject_id"] == source_id
                and item["record_type"] == RecordType.ACQUISITION_CANDIDATE.value
            ]
            if acquisitions and all(
                item["current_state"] == CandidateState.INVALIDATED.value
                for item in acquisitions
            ):
                self.content.remove(source_id)
                self.content.verify_absent(source_id)
                continue
            active_acquisitions = [
                item for item in acquisitions
                if item["current_state"] == CandidateState.ACTIVE.value
            ]
            if not active_acquisitions:
                continue
            records = {item["record_id"]: item for item in self.workspace.records()}
            acquisition_records = [
                records[item["record_id"]] for item in active_acquisitions
            ]
            acquisition = acquisition_records[0]
            try:
                # A source-specific object must satisfy every still-active
                # acquisition lineage. Conflicting imported lineages therefore
                # fail closed instead of selecting one by projection order.
                for item in acquisition_records:
                    if item["payload"]["content_object_id"] != self.content.object_id(source_id):
                        raise ContentStoreError("active content object identity differs")
                    self.content.read(
                        source_id, expected_hash=item["payload"]["artifact_hash"]
                    )
            except (ContentStoreError, FileNotFoundError, OSError, ValueError):
                active = sorted(
                    item["record_id"] for item in projection
                    if item["subject_id"] == source_id
                    and item["current_state"] == CandidateState.ACTIVE.value
                )
                self._append_integrity_invalidation(source_id, active, acquisition)
                self.content.remove(source_id)
                self.content.verify_absent(source_id)


__all__ = ["Phase4BService", "StoredAcquisition", "StoredParse"]
