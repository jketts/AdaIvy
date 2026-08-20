"""End-to-end checks for the offline Phase 4B integration service."""

from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from math_research.phase4a.records import RightsReason, RightsUse, RightsValue
from math_research.phase4a.service import Phase4Service, RightsBlocked
from math_research.phase4b.acquisition import (
    AcquisitionPolicy, AcquisitionRequest, AuthorizedResource, Resolution,
    RobotsSnapshot, RunAuthorization, TermsSnapshot, TransportRequest,
    TransportResponse,
)
from math_research.phase4b.parsing import (
    HTML_PROFILE, PDF_PROFILE, TEX_PROFILE, RestrictedStdlibAdapter, WorkerExecution,
)
from math_research.phase4b.records import CandidateState, RecordType
from math_research.phase4b.serialization import (
    canonical_bytes, canonical_hash, operational_export_hash, semantic_export_hash,
    sha256_bytes, stable_id,
)
from math_research.phase4b.service import Phase4BService
from math_research.phase4b.workspace import Phase4BWorkspace


T0 = "2026-08-20T00:00:00Z"
T1 = "2026-08-20T00:00:01Z"
T2 = "2026-08-20T00:00:02Z"
T3 = "2026-08-20T00:00:03Z"
NOW = 200_000
URL = "https://papers.example/theorem"
ORIGIN = "https://papers.example"
ADDRESS = "93.184.216.34"
BODY = b"<p>Theorem <math>x + y</math></p>"


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, hostname: str) -> Resolution:
        self.calls += 1
        return Resolution(hostname, (ADDRESS,))


class Transport:
    def __init__(self, body: bytes = BODY, media_type: str = "text/html") -> None:
        self.body = body
        self.media_type = media_type
        self.calls = 0

    def fetch(self, request: TransportRequest) -> TransportResponse:
        self.calls += 1
        return TransportResponse(
            200, (("content-type", self.media_type),),
            self.body, ADDRESS, 3,
        )


class CallbackTransport(Transport):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def fetch(self, request: TransportRequest) -> TransportResponse:
        response = super().fetch(request)
        self.callback()
        return response


class StartClock:
    def __init__(self) -> None:
        self.value = -1_000

    def now_milliseconds(self) -> int:
        self.value += 1_000
        return self.value


class FixtureWorker:
    """Explicit test worker; the stdlib adapter remains only a fixture oracle."""

    adapter = RestrictedStdlibAdapter()
    name = "fixture-worker"
    version = "1.0.0"
    implementation_sha256 = adapter.implementation_sha256
    dependency_environment_sha256 = adapter.dependency_environment_sha256
    sandbox_contract = "external-os-sandbox-contract-v1"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return WorkerExecution.capture(
            outcome=self.adapter.parse(request),
            operation_id="operation.fixture-worker",
        )


class CallbackWorker(FixtureWorker):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def execute(self, request):
        result = super().execute(request)
        self.callback()
        return result


class Phase4BServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = Phase4BWorkspace(self.root)
        phase4a = Phase4Service(self.workspace.phase4a)
        phase4a.initialize_policy(actor_id="actor.policy", recorded_at=T0)
        self.source_id = "source.phase4b.service"
        self.initial_rights = {}
        for use in (
            RightsUse.ACQUISITION,
            RightsUse.STORAGE_AND_RETENTION,
            RightsUse.PARSING,
        ):
            self.initial_rights[use] = phase4a.append_rights(
                source_id=self.source_id,
                intended_use=use,
                value=RightsValue.ALLOWED,
                reason_code=RightsReason.PERMITTED,
                reason_detail="fixture owner permits bounded candidate processing",
                evidence_refs=(f"evidence.rights-{use.value.replace('_', '-')}",),
                actor_id="actor.owner",
                valid_from=T0,
                valid_until=None,
                recorded_at=T0,
                lifecycle_id=f"rights-lifecycle.{use.value}",
            )
        self.phase4a = phase4a
        self.service = Phase4BService(self.workspace)

    def tearDown(self) -> None:
        self.service.close()
        self.workspace.close()
        self.temporary.cleanup()

    def authorization(self) -> tuple[AcquisitionPolicy, RunAuthorization, AcquisitionRequest]:
        policy = AcquisitionPolicy()
        authorization = RunAuthorization(
            run_id="run.phase4b.service",
            actor_id="actor.owner",
            actor_kind="human",
            authority="human_final",
            capability_id="capability.phase4b.acquire",
            operation="acquire_https",
            network_enabled=True,
            policy_hash=policy.content_hash,
            approved_origins=(ORIGIN,),
            resources=(AuthorizedResource("request.phase4b.service", URL),),
        )
        request = AcquisitionRequest(
            authorization.run_id,
            "request.phase4b.service",
            authorization.actor_id,
            URL,
        )
        return policy, authorization, request

    def acquire(self, *, resolver: Resolver | None = None, transport: Transport | None = None):
        policy, authorization, request = self.authorization()
        return self.service.acquire(
            self.source_id,
            (request,),
            authorization=authorization,
            policy=policy,
            terms=(TermsSnapshot("terms.service", ORIGIN, "a" * 64, NOW, True, True),),
            robots=(RobotsSnapshot("robots.service", URL, "b" * 64, NOW, True, True),),
            resolver=resolver or Resolver(),
            transport=transport or Transport(),
            start_clock=StartClock(),
            now_epoch=NOW,
            recorded_at_epoch=NOW,
            recorded_at=T1,
        )

    def test_acquire_parse_persists_only_candidate_metadata(self) -> None:
        acquired = self.acquire()
        self.assertEqual(1, len(acquired.records))
        acquisition_record = acquired.records[0]
        self.assertEqual(RecordType.ACQUISITION_CANDIDATE.value, acquisition_record["record_type"])
        self.assertEqual(BODY, self.service.content.read(
            self.source_id, expected_hash=acquisition_record["payload"]["artifact_hash"]
        ))

        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.service",
            representation_id="representation.html.service",
            media_type="text/html",
            profile_name=HTML_PROFILE.name,
            recorded_at=T1,
            worker=FixtureWorker(),
        )
        self.assertEqual("candidate_proposal", parsed.result.disposition)
        self.assertEqual(RecordType.PARSE_CANDIDATE.value, parsed.record["record_type"])
        self.assertGreater(parsed.record["payload"]["segment_count"], 0)
        self.assertTrue(parsed.record["payload"]["anchors"])
        durable = self.workspace.export_bytes()
        self.assertNotIn(BODY, durable)
        self.assertNotIn(b"Theorem", durable)
        self.assertNotIn(b"x + y", durable)
        artifacts = self.workspace.replay_artifacts()
        self.assertEqual(
            ["acquisition_attempt_trace", "parse_proposal"],
            [item["artifact_type"] for item in artifacts],
        )
        trace = artifacts[0]["payload"]
        self.assertEqual("candidate_acquired", trace["semantic"]["results"][0]["outcome"])
        self.assertEqual(URL, trace["operational"]["operations"][0]["url"])
        proposal = artifacts[1]["payload"]
        self.assertEqual(parsed.result.semantic_sha256, proposal["result_semantic_sha256"])
        self.assertEqual("candidate_proposal", proposal["disposition"])
        self.assertTrue(proposal["segments"])
        self.assertTrue(proposal["formula_segment_id_hashes"])
        self.assertNotIn("normalized_text", proposal["segments"][0])
        with self.assertRaises(sqlite3.IntegrityError):
            self.workspace.connection.execute(
                "UPDATE phase4b_replay_artifacts SET artifact_type='parse_proposal'"
            )
        self.service.content.verify_inventory({self.source_id})

    def test_missing_phase4a_right_blocks_before_injected_io(self) -> None:
        source_id = "source.phase4b.blocked"
        resolver, transport = Resolver(), Transport()
        policy, authorization, request = self.authorization()
        with self.assertRaises(RightsBlocked):
            self.service.acquire(
                source_id,
                (request,),
                authorization=authorization,
                policy=policy,
                terms=(TermsSnapshot("terms.service", ORIGIN, "a" * 64, NOW, True, True),),
                robots=(RobotsSnapshot("robots.service", URL, "b" * 64, NOW, True, True),),
                resolver=resolver,
                transport=transport,
                start_clock=StartClock(),
                now_epoch=NOW,
                recorded_at_epoch=NOW,
                recorded_at=T1,
            )
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)
        self.assertEqual((), self.workspace.records())

    def test_one_source_rejects_multiple_requests_before_injected_io(self) -> None:
        policy, authorization, request = self.authorization()
        resolver, transport = Resolver(), Transport()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.service.acquire(
                self.source_id,
                (request, request),
                authorization=authorization,
                policy=policy,
                terms=(TermsSnapshot("terms.service", ORIGIN, "a" * 64, NOW, True, True),),
                robots=(RobotsSnapshot("robots.service", URL, "b" * 64, NOW, True, True),),
                resolver=resolver,
                transport=transport,
                start_clock=StartClock(),
                now_epoch=NOW,
                recorded_at_epoch=NOW,
                recorded_at=T1,
            )
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)

    def test_acquisition_failure_records_specific_closed_reason(self) -> None:
        policy, authorization, request = self.authorization()
        resolver, transport = Resolver(), Transport()
        stored = self.service.acquire(
            self.source_id,
            (request,),
            authorization=authorization,
            policy=policy,
            terms=(TermsSnapshot("terms.service", ORIGIN, "a" * 64, NOW, True, True),),
            robots=(RobotsSnapshot("robots.service", URL, "b" * 64, NOW, True, False),),
            resolver=resolver,
            transport=transport,
            start_clock=StartClock(),
            now_epoch=NOW,
            recorded_at_epoch=NOW,
            recorded_at=T1,
        )
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)
        self.assertEqual(RecordType.FAILURE.value, stored.records[0]["record_type"])
        self.assertEqual("robots_blocked", stored.records[0]["payload"]["failure_code"])

    def test_rights_change_invalidates_all_candidates_and_deletes_bytes(self) -> None:
        acquired = self.acquire()
        acquisition_record = acquired.records[0]
        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.service",
            representation_id="representation.html.service",
            media_type="text/html",
            profile_name=HTML_PROFILE.name,
            recorded_at=T1,
            worker=FixtureWorker(),
        )
        prohibited = self.phase4a.append_rights(
            source_id=self.source_id,
            intended_use=RightsUse.STORAGE_AND_RETENTION,
            value=RightsValue.PROHIBITED,
            reason_code=RightsReason.EXPLICITLY_PROHIBITED,
            reason_detail="fixture owner withdraws retention permission",
            evidence_refs=("evidence.rights-withdrawal",),
            actor_id="actor.owner",
            valid_from=T2,
            valid_until=None,
            recorded_at=T2,
            lifecycle_id="rights-lifecycle.storage_and_retention",
        )
        invalidation = self.service.synchronize_rights(self.source_id, at=T2)
        self.assertIsNotNone(invalidation)
        assert invalidation is not None
        self.assertEqual(prohibited.id, invalidation["payload"]["trigger_record_id"])
        self.assertEqual(
            sorted((acquisition_record["record_id"], parsed.record["record_id"])),
            invalidation["payload"]["affected_record_ids"],
        )
        projection = {
            item["record_id"]: item for item in self.workspace.projection()
        }
        self.assertEqual(CandidateState.INVALIDATED.value, projection[acquisition_record["record_id"]]["current_state"])
        self.assertEqual(CandidateState.INVALIDATED.value, projection[parsed.record["record_id"]]["current_state"])
        self.service.content.verify_absent(self.source_id)
        with self.assertRaisesRegex(ValueError, "invalidated acquisition"):
            self.service.parse(
                self.source_id,
                acquisition_record["record_id"],
                request_id="request.parse.after-invalidation",
                representation_id="representation.invalidated.service",
                media_type="text/html",
                profile_name=HTML_PROFILE.name,
                recorded_at=T2,
            )

        # Restart reconciliation preserves the tombstone outcome.
        self.service.close()
        restarted = Phase4BService(self.workspace)
        self.service = restarted
        restarted.content.verify_absent(self.source_id)

    def test_source_level_invalidation_cannot_skip_content_erasure(self) -> None:
        acquisition = self.acquire().records[0]
        with self.assertRaisesRegex(ValueError, "must erase content"):
            self.service.invalidate_candidates(
                self.source_id,
                (acquisition["record_id"],),
                trigger_record_id="deletion.unsafe-request",
                reason_code="source_deletion",
                at=T2,
                erase_content=False,
            )
        projection = {item["record_id"]: item for item in self.workspace.projection()}
        self.assertEqual(
            CandidateState.ACTIVE.value,
            projection[acquisition["record_id"]]["current_state"],
        )
        self.assertEqual(
            BODY,
            self.service.content.read(
                self.source_id,
                expected_hash=acquisition["payload"]["artifact_hash"],
            ),
        )

    def test_default_production_parser_fails_closed_and_keeps_original(self) -> None:
        acquired = self.acquire()
        acquisition_record = acquired.records[0]
        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.no-worker",
            representation_id="representation.html.no-worker",
            media_type="text/html",
            profile_name=HTML_PROFILE.name,
            recorded_at=T1,
        )
        self.assertEqual(RecordType.FAILURE.value, parsed.record["record_type"])
        self.assertEqual("missing_dependency", parsed.record["payload"]["failure_code"])
        self.assertEqual(BODY, self.service.content.read(
            self.source_id, expected_hash=acquisition_record["payload"]["artifact_hash"]
        ))

    def test_acquired_media_type_mismatch_quarantines_before_worker(self) -> None:
        acquired = self.acquire()
        acquisition_record = acquired.records[0]
        worker = FixtureWorker()
        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.media-mismatch",
            representation_id="representation.pdf.mismatch",
            media_type="application/pdf",
            profile_name=PDF_PROFILE.name,
            recorded_at=T1,
            worker=worker,
        )
        self.assertEqual(0, worker.calls)
        self.assertEqual("quarantined", parsed.result.disposition)
        self.assertEqual("acquisition_media_type_mismatch", parsed.result.failure_code)
        self.assertEqual(RecordType.FAILURE.value, parsed.record["record_type"])
        self.assertEqual("unsupported_media", parsed.record["payload"]["failure_code"])
        self.assertEqual(BODY, self.service.content.read(
            self.source_id, expected_hash=acquisition_record["payload"]["artifact_hash"]
        ))

    def test_media_profile_mismatch_quarantines_before_worker(self) -> None:
        acquired = self.acquire()
        acquisition_record = acquired.records[0]
        worker = FixtureWorker()
        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.profile-mismatch",
            representation_id="representation.profile.mismatch",
            media_type="text/html",
            profile_name=PDF_PROFILE.name,
            recorded_at=T1,
            worker=worker,
        )
        self.assertEqual(0, worker.calls)
        self.assertEqual("media_profile_mismatch", parsed.result.failure_code)
        self.assertEqual("unsupported_media", parsed.record["payload"]["failure_code"])

    def _assert_signature_quarantine(
        self, *, body: bytes, media_type: str, profile_name: str
    ) -> None:
        acquired = self.acquire(transport=Transport(body, media_type))
        acquisition_record = acquired.records[0]
        worker = FixtureWorker()
        parsed = self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.bad-signature",
            representation_id="representation.bad-signature",
            media_type=media_type,
            profile_name=profile_name,
            recorded_at=T1,
            worker=worker,
        )
        self.assertEqual(0, worker.calls)
        self.assertEqual("quarantined", parsed.result.disposition)
        self.assertEqual("content_signature_mismatch", parsed.result.failure_code)
        self.assertEqual("malformed_input", parsed.record["payload"]["failure_code"])
        self.assertEqual(body, self.service.content.read(
            self.source_id, expected_hash=acquisition_record["payload"]["artifact_hash"]
        ))
        self.assertNotIn(body, self.workspace.export_bytes())
        artifacts = [
            item for item in self.workspace.replay_artifacts()
            if item["owner_record_id"] == parsed.record["record_id"]
        ]
        self.assertEqual(1, len(artifacts))
        self.assertEqual("parse_proposal", artifacts[0]["artifact_type"])
        self.assertEqual("quarantined", artifacts[0]["payload"]["disposition"])
        self.assertEqual(
            "content_signature_mismatch", artifacts[0]["payload"]["failure_code"]
        )
        self.assertEqual([], artifacts[0]["payload"]["segments"])

    def test_html_signature_mismatch_quarantines_before_worker(self) -> None:
        self._assert_signature_quarantine(
            body=b"plain prose masquerading as HTML",
            media_type="text/html",
            profile_name=HTML_PROFILE.name,
        )

    def test_tex_signature_mismatch_quarantines_before_worker(self) -> None:
        self._assert_signature_quarantine(
            body=b"plain prose masquerading as TeX",
            media_type="application/x-tex",
            profile_name=TEX_PROFILE.name,
        )

    def test_pdf_signature_mismatch_quarantines_before_worker(self) -> None:
        self._assert_signature_quarantine(
            body=b"plain prose masquerading as PDF",
            media_type="application/pdf",
            profile_name=PDF_PROFILE.name,
        )

    def test_self_rehashed_parse_replay_forgery_is_rejected_on_import(self) -> None:
        acquired = self.acquire()
        acquisition_record = acquired.records[0]
        self.service.parse(
            self.source_id,
            acquisition_record["record_id"],
            request_id="request.parse.forgery-base",
            representation_id="representation.forgery-base",
            media_type="text/html",
            profile_name=HTML_PROFILE.name,
            recorded_at=T1,
            worker=FixtureWorker(),
        )
        base = self.workspace.export_value()
        with tempfile.TemporaryDirectory() as valid_target_root:
            with Phase4BWorkspace(Path(valid_target_root)) as valid_target:
                valid_target.import_bytes(canonical_bytes(base))
                self.assertEqual(2, len(valid_target.replay_artifacts()))

        def forged(mutator):
            value = copy.deepcopy(base)
            artifact = next(
                item for item in value["replay_artifacts"]
                if item["artifact_type"] == "parse_proposal"
            )
            mutator(artifact["payload"])
            core = {
                "artifact_type": artifact["artifact_type"],
                "owner_record_id": artifact["owner_record_id"],
                "payload": artifact["payload"],
                "schema_version": artifact["schema_version"],
            }
            artifact["artifact_id"] = stable_id("phase4b-replay-artifact", core)
            artifact["content_hash"] = canonical_hash(core)
            value["content_hash"] = semantic_export_hash(value)
            value["operational_hash"] = operational_export_hash(value)
            return canonical_bytes(value)

        def detach_semantic(payload):
            payload["result_semantic_sha256"] = "sha256:" + "9" * 64
            payload["result_operational_sha256"] = sha256_bytes(canonical_bytes({
                "adapter_status": payload["adapter_status"],
                "operation": payload["operation"],
                "semantic_sha256": payload["result_semantic_sha256"],
            }))

        def detach_operation(payload):
            payload["operation"]["duration_ms"] += 1
            payload["result_operational_sha256"] = sha256_bytes(canonical_bytes({
                "adapter_status": payload["adapter_status"],
                "operation": payload["operation"],
                "semantic_sha256": payload["result_semantic_sha256"],
            }))

        mutations = {
            "trust promotion": lambda payload: payload["trust_effects"].__setitem__("mathematical_warrant", "proved"),
            "parser identity swap": lambda payload: payload["parser_identity"].__setitem__("adapter_name", "forged-worker"),
            "impossible bounds": lambda payload: payload["bounds"].__setitem__("max_raw_input_bytes", 1),
            "semantic detachment": detach_semantic,
            "operational detachment": lambda payload: payload.__setitem__("result_operational_sha256", "sha256:" + "8" * 64),
            "owner operational detachment": detach_operation,
            "disposition promotion": lambda payload: payload.__setitem__("adapter_status", "missing_dependency"),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as target_root:
                with Phase4BWorkspace(Path(target_root)) as target:
                    with self.assertRaises(ValueError):
                        target.import_bytes(forged(mutation))
                    self.assertEqual((), target.records())
                    self.assertEqual((), target.replay_artifacts())

    def test_parser_result_is_not_appended_when_right_is_revoked_during_worker(self) -> None:
        acquisition = self.acquire().records[0]

        def revoke() -> None:
            self.phase4a.append_rights(
                source_id=self.source_id, intended_use=RightsUse.PARSING,
                value=RightsValue.PROHIBITED,
                reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                reason_detail="owner withdraws permission while worker runs",
                evidence_refs=("evidence.concurrent-revocation",), actor_id="actor.owner",
                valid_from=T1, valid_until=None, recorded_at=T2,
                lifecycle_id="rights-lifecycle.parsing",
            )

        with self.assertRaises(RightsBlocked):
            self.service.parse(
                self.source_id, acquisition["record_id"],
                request_id="request.parse.concurrent-revocation",
                representation_id="representation.concurrent-revocation",
                media_type="text/html", profile_name=HTML_PROFILE.name,
                recorded_at=T1, worker=CallbackWorker(revoke),
            )
        records = self.workspace.records()
        self.assertEqual(
            [RecordType.ACQUISITION_CANDIDATE.value, RecordType.INVALIDATION.value],
            [item["record_type"] for item in records],
        )
        self.assertEqual("rights_changed", records[-1]["payload"]["reason_code"])
        self.service.content.verify_absent(self.source_id)

    def test_acquisition_is_not_published_when_right_is_revoked_during_transport(self) -> None:
        def revoke() -> None:
            self.phase4a.append_rights(
                source_id=self.source_id, intended_use=RightsUse.ACQUISITION,
                value=RightsValue.PROHIBITED,
                reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                reason_detail="owner withdraws acquisition while transport runs",
                evidence_refs=("evidence.concurrent-acquisition-revocation",),
                actor_id="actor.owner", valid_from=T1, valid_until=None,
                recorded_at=T2, lifecycle_id="rights-lifecycle.acquisition",
            )

        with self.assertRaises(RightsBlocked):
            self.acquire(transport=CallbackTransport(revoke))
        self.assertEqual(RecordType.FAILURE.value, self.workspace.records()[-1]["record_type"])
        self.assertEqual("rights_blocked", self.workspace.records()[-1]["payload"]["failure_code"])
        self.assertEqual((), self.workspace.pending_publications())
        self.service.content.verify_absent(self.source_id)

    def test_parser_result_is_not_appended_when_retention_is_revoked_during_worker(self) -> None:
        acquisition = self.acquire().records[0]

        def revoke() -> None:
            self.phase4a.append_rights(
                source_id=self.source_id,
                intended_use=RightsUse.STORAGE_AND_RETENTION,
                value=RightsValue.PROHIBITED,
                reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                reason_detail="owner withdraws retention while worker runs",
                evidence_refs=("evidence.concurrent-retention-revocation",),
                actor_id="actor.owner", valid_from=T1, valid_until=None,
                recorded_at=T2,
                lifecycle_id="rights-lifecycle.storage_and_retention",
            )

        with self.assertRaises(RightsBlocked):
            self.service.parse(
                self.source_id, acquisition["record_id"],
                request_id="request.parse.concurrent-retention-revocation",
                representation_id="representation.concurrent-retention-revocation",
                media_type="text/html", profile_name=HTML_PROFILE.name,
                recorded_at=T1, worker=CallbackWorker(revoke),
            )
        self.assertFalse(any(
            item["record_type"] == RecordType.PARSE_CANDIDATE.value
            for item in self.workspace.records()
        ))
        self.assertEqual(
            RecordType.INVALIDATION.value, self.workspace.records()[-1]["record_type"]
        )
        self.service.content.verify_absent(self.source_id)

    def test_parser_result_is_not_appended_when_predecessor_invalidates_during_worker(self) -> None:
        acquisition = self.acquire().records[0]

        def invalidate() -> None:
            self.workspace.append(
                record_type=RecordType.INVALIDATION, subject_id=self.source_id,
                recorded_at=T2,
                payload={
                    "invalidation_id": "invalidation.concurrent-worker",
                    "trigger_record_id": "trigger.concurrent-worker",
                    "affected_record_ids": [acquisition["record_id"]],
                    "reason_code": "source_correction",
                    "policy_snapshot_id": acquisition["payload"]["policy_snapshot_id"],
                },
            )

        with self.assertRaisesRegex(ValueError, "invalidated acquisition"):
            self.service.parse(
                self.source_id, acquisition["record_id"],
                request_id="request.parse.concurrent-invalidation",
                representation_id="representation.concurrent-invalidation",
                media_type="text/html", profile_name=HTML_PROFILE.name,
                recorded_at=T1, worker=CallbackWorker(invalidate),
            )
        self.assertFalse(any(
            item["record_type"] == RecordType.PARSE_CANDIDATE.value
            for item in self.workspace.records()
        ))
        self.service.content.verify_absent(self.source_id)

    def test_restart_removes_orphaned_pending_publication(self) -> None:
        artifact_hash = "sha256:" + __import__("hashlib").sha256(BODY).hexdigest()
        object_id = self.service.content.object_id(self.source_id)
        self.workspace.begin_publication(
            source_id=self.source_id, artifact_hash=artifact_hash,
            content_object_id=object_id, recorded_at=T1,
        )
        self.service.content.publish(self.source_id, BODY, expected_hash=artifact_hash)
        self.service.close()
        self.service = Phase4BService(self.workspace)
        self.assertEqual((), self.workspace.pending_publications())
        self.service.content.verify_absent(self.source_id)

    def test_restart_preserves_committed_content_and_clears_stale_journal(self) -> None:
        acquisition = self.acquire().records[0]
        self.workspace.begin_publication(
            source_id=self.source_id,
            artifact_hash=acquisition["payload"]["artifact_hash"],
            content_object_id=acquisition["payload"]["content_object_id"],
            recorded_at=acquisition["recorded_at"],
        )
        self.service.close()
        self.service = Phase4BService(self.workspace)
        self.assertEqual((), self.workspace.pending_publications())
        self.assertEqual(
            BODY,
            self.service.content.read(
                self.source_id,
                expected_hash=acquisition["payload"]["artifact_hash"],
            ),
        )

    def test_restart_invalidates_active_candidate_when_content_is_missing(self) -> None:
        acquisition = self.acquire().records[0]
        self.service.content.remove(self.source_id)
        self.service.close()
        self.service = Phase4BService(self.workspace)
        projected = {
            item["record_id"]: item for item in self.workspace.projection()
        }
        self.assertEqual(
            CandidateState.INVALIDATED.value,
            projected[acquisition["record_id"]]["current_state"],
        )
        invalidations = [
            item for item in self.workspace.records()
            if item["record_type"] == RecordType.INVALIDATION.value
        ]
        self.assertEqual("integrity_failure", invalidations[-1]["payload"]["reason_code"])

    def test_metadata_import_without_content_is_durably_invalidated(self) -> None:
        acquisition = self.acquire().records[0]
        exported = self.workspace.export_bytes()
        imported_workspace = Phase4BWorkspace(self.root / "imported")
        imported_service = None
        try:
            imported_workspace.import_bytes(exported)
            imported_service = Phase4BService(imported_workspace)
            projection = {
                item["record_id"]: item for item in imported_workspace.projection()
            }
            self.assertEqual(
                CandidateState.INVALIDATED.value,
                projection[acquisition["record_id"]]["current_state"],
            )
            self.assertEqual(
                "integrity_failure", imported_workspace.records()[-1]["payload"]["reason_code"]
            )
            imported_service.content.verify_absent(self.source_id)
        finally:
            if imported_service is not None:
                imported_service.close()
            imported_workspace.close()

    def test_invalidated_source_identity_cannot_resurrect_content(self) -> None:
        acquisition = self.acquire().records[0]
        self.workspace.append(
            record_type=RecordType.INVALIDATION, subject_id=self.source_id,
            recorded_at=T2,
            payload={
                "invalidation_id": "invalidation.permanent-tombstone",
                "trigger_record_id": "trigger.permanent-tombstone",
                "affected_record_ids": [acquisition["record_id"]],
                "reason_code": "source_takedown",
                "policy_snapshot_id": acquisition["payload"]["policy_snapshot_id"],
            },
        )
        self.service.content.remove(self.source_id)
        resolver, transport = Resolver(), Transport()
        with self.assertRaisesRegex(ValueError, "cannot be republished"):
            self.acquire(resolver=resolver, transport=transport)
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)
        self.service.content.verify_absent(self.source_id)


if __name__ == "__main__":
    unittest.main()
