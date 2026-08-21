"""Phase 5 application service for exact benchmark runs and research steering."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..phase4a.records import (
    ActorKind, ApplicabilityOutcome, ApplicabilityStatus, Authority, RecordType, RightsUse,
)
from ..phase4a.service import Phase4Service
from . import (
    CANONICALIZATION_VERSION, NONCOMMUTING_ADMISSION_VERSION, NONCOMMUTING_FINDING_VERSION,
    NONCOMMUTING_RUN_VERSION, POLICY_ID, POLICY_VERSION,
)
from .noncommuting import (
    BENCHMARK_ID as NONCOMMUTING_BENCHMARK_ID,
    COVERAGE_STATEMENT, COVERAGE_STATUSES, COVERAGE_UNRESOLVED, FORBIDDEN_COVERAGE_STATUS,
    parse_fixture, verify_fixture,
)
from .quantum import DiagonalCase, run_case
from .serialization import canonical_hash, finalize, stable_id
from .workspace import Phase5ValidationError, Phase5Workspace


SEPARATION_OF_DUTY_NOTE = (
    "Sealed Phase 5 accepts an identical originating and creating principal, so this "
    "slice does not require a second principal. Under ADR-0035 that gap is "
    "load-bearing: when one principal derives a certificate and the same principal "
    "approves its admission, nothing independent stands between derivation and the "
    "trust record. What contains it is mathematical, not procedural -- a zero-gap "
    "certificate is self-verifying against the ensemble, so a wrong certificate fails "
    "the exact check rather than passing quietly. Requiring a second principal is a "
    "separate decision and is not taken here."
)

STEERING_ACTIONS = (
    "continue_objective", "investigate_result", "redirect_objective", "acknowledge", "dismiss",
)
MATERIAL_CLASSIFICATIONS = {"refutes", "restricts", "strengthens", "generalizes", "redirects"}


class Phase5Service:
    def __init__(self, workspace: Phase5Workspace) -> None:
        self.workspace = workspace
        self.phase4 = Phase4Service(workspace.phase4)
        self.workspace.verify_integrity()

    def _one(self, record_type: str, subject_id: str) -> dict[str, Any]:
        rows = self.workspace.find(record_type, subject_id)
        if len(rows) != 1:
            raise Phase5ValidationError(f"expected exactly one {record_type} for {subject_id}")
        return rows[0]

    def ensure_objective(
        self, *, objective_id: str, statement: str, semantic_alignment_id: str,
        recorded_at: str,
    ) -> dict[str, Any]:
        if not statement or not semantic_alignment_id:
            raise Phase5ValidationError("objective statement and approved alignment are required")
        return self.workspace.append(
            record_type="objective", subject_id=objective_id, recorded_at=recorded_at,
            payload={
                "objective_id": objective_id, "statement": statement, "status": "active",
                "main_objective_incomplete": True,
                "semantic_alignment_id": semantic_alignment_id,
                "semantic_alignment_status": "researcher_approved",
            },
        )

    def ensure_principal(
        self, *, principal_id: str, actor_kind: ActorKind, authority: Authority,
        recorded_at: str,
    ) -> dict[str, Any]:
        return self.workspace.append(
            record_type="principal", subject_id=principal_id, recorded_at=recorded_at,
            payload={
                "principal_id": principal_id, "actor_kind": actor_kind.value,
                "authority": authority.value,
            },
        )

    def ensure_capability(
        self, *, capability_id: str, principal_id: str, operation: str, recorded_at: str,
    ) -> dict[str, Any]:
        principal = self._one("principal", principal_id)
        if operation not in {"surface_verified_result", "steer_research", "review_result_lifecycle"}:
            raise Phase5ValidationError("unknown Phase 5 capability")
        return self.workspace.append(
            record_type="capability", subject_id=capability_id, recorded_at=recorded_at,
            payload={
                "capability_id": capability_id, "principal_id": principal_id,
                "operation": operation, "principal_hash": principal["content_hash"],
            },
        )

    def _principal_capability(
        self, principal_id: str, capability_id: str, operation: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        principal = self._one("principal", principal_id)
        capability = self._one("capability", capability_id)
        if capability["payload"]["principal_id"] != principal_id or capability["payload"]["operation"] != operation:
            raise PermissionError("capability does not authorize this principal and operation")
        return principal, capability

    def register_evidence(
        self, *, evidence_id: str, objective_id: str, run_id: str, kind: str,
        artifact: Mapping[str, Any], recorded_at: str,
        source_record_id: str | None = None,
        applicability_review_id: str | None = None,
    ) -> dict[str, Any]:
        self._one("objective", objective_id)
        self._one("run", run_id)
        if (source_record_id is None) != (applicability_review_id is None):
            raise Phase5ValidationError("source evidence requires both source and applicability records")
        if source_record_id is not None:
            source = self.workspace.phase4.record(source_record_id)
            review = self.workspace.phase4.record(str(applicability_review_id))
            if source["record_type"] != RecordType.SOURCE_PROVENANCE.value:
                raise Phase5ValidationError("source evidence does not resolve to provenance")
            if (
                review["record_type"] != RecordType.APPLICABILITY_REVIEW.value
                or review["subject_id"] != source["subject_id"]
                or review["payload"]["status"] != ApplicabilityStatus.CHECKED.value
                or review["payload"]["outcome"] != ApplicabilityOutcome.APPLICABLE.value
            ):
                raise Phase5ValidationError("source evidence lacks checked applicable review")
            self.phase4.require_rights(source["subject_id"], RightsUse.EXCERPTING, at=recorded_at)
        artifact_hash = canonical_hash(artifact)
        return self.workspace.append(
            record_type="evidence", subject_id=evidence_id, recorded_at=recorded_at,
            payload={
                "evidence_id": evidence_id, "objective_id": objective_id, "run_id": run_id,
                "kind": kind, "artifact_hash": artifact_hash, "artifact": dict(artifact),
                "source_record_id": source_record_id,
                "applicability_review_id": applicability_review_id,
                "eligible": True, "trust_effect": "evidence_only",
            },
        )

    def _record_finding(
        self, *, run_id: str, objective_id: str, branch_id: str,
        result: Mapping[str, Any], recorded_at: str,
    ) -> dict[str, Any]:
        finding_id = stable_id("finding", {"run_id": run_id, "case_id": result["case_id"]})
        return self.workspace.append(
            record_type="finding", subject_id=finding_id, recorded_at=recorded_at,
            payload={
                "finding_id": finding_id, "run_id": run_id, "objective_id": objective_id,
                "branch_id": branch_id, "result_hash": result["result_hash"],
                "proposal_status": result["proposal_status"],
                "applicability_status": result["applicability_status"],
                "mathematical_warrant": result["mathematical_warrant"],
                "graph_admitted": False,
                "result": dict(result),
            },
        )

    def _verification_and_materiality(
        self, *, objective_id: str, run_id: str, branch_id: str, finding: dict[str, Any],
        evidence: dict[str, Any], statement: str, classification: str, recorded_at: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        evidence_refs = [{
            "reference_id": evidence["subject_id"], "reference_kind": "certificate",
            "content_hash": evidence["content_hash"],
        }]
        evidence_snapshot_hash = canonical_hash(evidence_refs)
        result_digest = canonical_hash({
            "statement": statement, "object_id": finding["subject_id"],
            "domain": "quantum_discrimination.diagonal_commuting",
            "objective_id": objective_id, "run_id": run_id, "branch_id": branch_id,
            "evidence_snapshot_hash": evidence_snapshot_hash,
            "canonicalization_version": CANONICALIZATION_VERSION,
        })
        verification_id = stable_id("verification", {"result_digest": result_digest, "method": "exact_counterexample"})
        verification = self.workspace.append(
            record_type="verification", subject_id=verification_id, recorded_at=recorded_at,
            payload={
                "verification_id": verification_id, "objective_id": objective_id,
                "run_id": run_id, "branch_id": branch_id, "result_digest": result_digest,
                "evidence_ids": [evidence["subject_id"]], "status": "verified",
                "method": "exact_counterexample", "independent_from_proposal": True,
                "policy_id": POLICY_ID, "policy_version": POLICY_VERSION,
                "trust_effect": "checked_result_not_graph_admission",
            },
        )
        materiality_id = stable_id("materiality", {"result_digest": result_digest, "classification": classification})
        materiality = self.workspace.append(
            record_type="materiality_assessment", subject_id=materiality_id, recorded_at=recorded_at,
            payload={
                "materiality_assessment_id": materiality_id, "objective_id": objective_id,
                "run_id": run_id, "result_digest": result_digest,
                "classification": classification, "policy_id": POLICY_ID,
                "policy_version": POLICY_VERSION,
                "explanation": "Exact checked result changes which convergence statement may be investigated.",
            },
        )
        return verification, materiality, evidence_snapshot_hash, result_digest

    def surface_material_result(
        self, *, objective_id: str, run_id: str, branch_id: str, finding_id: str,
        evidence_id: str, classification: str, statement: str,
        originating_principal_id: str, created_by_principal_id: str, capability_id: str,
        recorded_at: str,
    ) -> dict[str, Any]:
        if classification not in MATERIAL_CLASSIFICATIONS or not statement:
            raise Phase5ValidationError("invalid material result classification or statement")
        objective = self._one("objective", objective_id)
        run = self._one("run", run_id)
        branch = self._one("branch", branch_id)
        finding = self._one("finding", finding_id)
        evidence = self._one("evidence", evidence_id)
        if not objective["payload"]["main_objective_incomplete"] or objective["payload"]["status"] != "active":
            raise Phase5ValidationError("material results require an active incomplete objective")
        if run["payload"]["objective_id"] != objective_id or branch["payload"]["run_id"] != run_id:
            raise Phase5ValidationError("objective, run, and branch identities differ")
        if finding["payload"]["branch_id"] != branch_id or evidence["payload"]["run_id"] != run_id:
            raise Phase5ValidationError("finding or evidence belongs to another branch/run")
        if not evidence["payload"]["eligible"] or finding["payload"]["proposal_status"] != "checked_result":
            raise Phase5ValidationError("unverified or ineligible work cannot be surfaced")
        principal, _capability = self._principal_capability(
            created_by_principal_id, capability_id, "surface_verified_result"
        )
        if principal["payload"]["authority"] not in {
            Authority.HUMAN_FINAL.value, Authority.DETERMINISTIC_POLICY.value,
        }:
            raise PermissionError("surfacing requires human-final or deterministic-policy authority")
        self._one("principal", originating_principal_id)
        verification, materiality, evidence_snapshot_hash, result_digest = self._verification_and_materiality(
            objective_id=objective_id, run_id=run_id, branch_id=branch_id, finding=finding,
            evidence=evidence, statement=statement, classification=classification,
            recorded_at=recorded_at,
        )
        event_id = stable_id("material-result", {"run_id": run_id, "result_digest": result_digest})
        idempotency_key = f"surface:{run_id}:{result_digest}"
        envelope = finalize({
            "schema_version": "adaivy.material-partial-result-event.v1",
            "record_type": "material_partial_result_event",
            "event": {
                "event_id": event_id,
                "event_type": "research.material_partial_result_surfaced",
                "semantic_idempotency_key": idempotency_key,
                "objective_id": objective_id, "run_id": run_id, "branch_id": branch_id,
                "classification": classification,
                "result_identity": {
                    "statement": statement, "object_id": finding_id,
                    "domain": "quantum_discrimination.diagonal_commuting",
                    "evidence_snapshot_hash": evidence_snapshot_hash,
                    "canonicalization_version": CANONICALIZATION_VERSION,
                    "result_digest": result_digest,
                },
                "materiality_explanation": materiality["payload"]["explanation"],
                "materiality_assessment_id": materiality["subject_id"],
                "evidence_references": [{
                    "reference_id": evidence_id, "reference_kind": "certificate",
                    "content_hash": evidence["content_hash"],
                }],
                "verification": {
                    "status": "verified", "method": "exact_counterexample",
                    "verification_record_ids": [verification["subject_id"]],
                    "policy_id": POLICY_ID, "policy_version": POLICY_VERSION,
                },
                "originating_principal_id": originating_principal_id,
                "created_by_principal_id": created_by_principal_id,
                "capability_id": capability_id,
                "required_capability": "surface_verified_result",
                "created_at": recorded_at, "causal_parent_ids": [finding_id],
                "policy_id": POLICY_ID, "policy_version": POLICY_VERSION,
                "main_objective_incomplete": True,
                "available_steering_actions": list(STEERING_ACTIONS),
            },
        })
        record = self.workspace.append(
            record_type="material_partial_result_event", subject_id=event_id,
            record_id=event_id, payload=envelope, recorded_at=recorded_at,
            event_type="research.material_partial_result_surfaced",
            event_idempotency_key=idempotency_key, aggregate_id=run_id,
        )
        self.workspace.rebuild_material_projection()
        return record

    def steer(
        self, *, event_id: str, action: str, principal_id: str, capability_id: str,
        idempotency_key: str, recorded_at: str, target_objective_id: str | None = None,
        target_branch_id: str | None = None,
    ) -> dict[str, Any]:
        if action not in STEERING_ACTIONS:
            raise Phase5ValidationError("unknown steering action")
        event_record = self._one("material_partial_result_event", event_id)
        event = event_record["payload"]["event"]
        projections = {item["event_id"]: item for item in self.workspace.material_results()}
        if projections[event_id]["current_validity"] != "valid":
            raise Phase5ValidationError("invalidated material result cannot be steered")
        principal, _capability = self._principal_capability(principal_id, capability_id, "steer_research")
        if (
            principal["payload"]["actor_kind"] != ActorKind.HUMAN.value
            or principal["payload"]["authority"] != Authority.HUMAN_FINAL.value
        ):
            raise PermissionError("steering requires a trusted human-final principal")
        needs_target = action in {"investigate_result", "redirect_objective"}
        if needs_target != bool(target_objective_id or target_branch_id):
            raise Phase5ValidationError("investigation/redirect requires exactly one target; other actions forbid it")
        if target_objective_id and target_branch_id:
            raise Phase5ValidationError("steering target must be an objective or branch, not both")
        if target_objective_id:
            self._one("objective", target_objective_id)
        if target_branch_id:
            self._one("branch", target_branch_id)
        prior = [
            item for item in self.workspace.records("material_partial_result_steering_action")
            if item["payload"]["action"]["material_result_event_id"] == event_id
        ]
        for existing in prior:
            old = existing["payload"]["action"]
            if old["idempotency_key"] == idempotency_key:
                if (
                    old["action"] != action or old["principal_id"] != principal_id
                    or old["capability_id"] != capability_id
                    or old["target_objective_id"] != target_objective_id
                    or old["target_branch_id"] != target_branch_id
                    or old["created_at"] != recorded_at
                ):
                    raise Phase5ValidationError("steering idempotency key reused with different semantics")
                return existing
        sequence = len(prior) + 1
        predecessor = prior[-1]["record_id"] if prior else event_id
        action_id = stable_id("material-action", {"event_id": event_id, "idempotency_key": idempotency_key})
        envelope = finalize({
            "schema_version": "adaivy.material-partial-result-steering-action.v1",
            "record_type": "material_partial_result_steering_action",
            "action": {
                "action_id": action_id,
                "event_type": "research.material_partial_result_steering_recorded",
                "idempotency_key": idempotency_key,
                "material_result_event_id": event_id,
                "objective_id": event["objective_id"], "run_id": event["run_id"],
                "branch_id": event["branch_id"], "action": action,
                "principal_id": principal_id, "effective_actor_kind": ActorKind.HUMAN.value,
                "authority": Authority.HUMAN_FINAL.value, "capability_id": capability_id,
                "required_capability": "steer_research", "created_at": recorded_at,
                "causal_predecessor_id": predecessor,
                "target_objective_id": target_objective_id,
                "target_branch_id": target_branch_id,
                "policy_id": POLICY_ID, "policy_version": POLICY_VERSION,
                "sequence": sequence,
            },
        })
        record = self.workspace.append(
            record_type="material_partial_result_steering_action", subject_id=event_id,
            record_id=action_id, payload=envelope, recorded_at=recorded_at,
            event_type="research.material_partial_result_steering_recorded",
            event_idempotency_key=idempotency_key, aggregate_id=event["run_id"],
        )
        self.workspace.rebuild_material_projection()
        return record

    def run_quantum_fixture(
        self, fixture: Mapping[str, Any], *, recorded_at: str,
        objective_id: str = "objective.qd-fs-01", run_id: str | None = None,
    ) -> dict[str, Any]:
        if set(fixture) != {"schema_version", "benchmark_id", "cases"}:
            raise Phase5ValidationError("Phase 5 fixture has missing or unknown fields")
        if fixture["schema_version"] != "adaivy.quantum-diagonal-fixture.v1" or fixture["benchmark_id"] != "QD-FS-01":
            raise Phase5ValidationError("unsupported Phase 5 fixture")
        cases = [DiagonalCase.from_value(item) for item in fixture["cases"]]
        if not cases or not any(item.expected_classification in {"refutes", "restricts"} for item in cases):
            raise Phase5ValidationError("adaptive workflow requires a falsification branch")
        fixture_hash = canonical_hash(fixture)
        run_id = run_id or stable_id("run.phase5", {"objective_id": objective_id, "fixture_hash": fixture_hash})
        self.ensure_objective(
            objective_id=objective_id,
            statement="Resolve QD-FS-01 while preserving ordinary-inverse, full-support, and YKL boundaries.",
            semantic_alignment_id="alignment.qd-fs-01.v1", recorded_at=recorded_at,
        )
        system_id, human_id = "principal.phase5.deterministic", "principal.phase5.owner"
        self.ensure_principal(
            principal_id=system_id, actor_kind=ActorKind.SYSTEM,
            authority=Authority.DETERMINISTIC_POLICY, recorded_at=recorded_at,
        )
        self.ensure_principal(
            principal_id=human_id, actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, recorded_at=recorded_at,
        )
        self.ensure_capability(
            capability_id="capability.phase5.surface", principal_id=system_id,
            operation="surface_verified_result", recorded_at=recorded_at,
        )
        self.ensure_capability(
            capability_id="capability.phase5.steer", principal_id=human_id,
            operation="steer_research", recorded_at=recorded_at,
        )
        run = self.workspace.append(
            record_type="run", subject_id=run_id, recorded_at=recorded_at,
            payload={
                "run_id": run_id, "objective_id": objective_id, "benchmark_id": "QD-FS-01",
                "fixture_hash": fixture_hash, "protocol_class": "exploratory",
                "status": "awaiting_steering", "external_cost_usd": 0,
                "network_calls": 0, "model_calls": 0,
                "search_tiers": {
                    "tier_0": "enabled_deterministic",
                    "tier_2": "disabled_no_measured_cost_adjusted_gain",
                    "tier_3": "disabled_no_measured_cost_adjusted_gain",
                    "tier_4": "disabled_no_measured_cost_adjusted_gain",
                },
            },
        )
        findings: list[dict[str, Any]] = []
        surfaced: list[str] = []
        seen_result_hashes: set[str] = set()
        for priority, case in enumerate(cases, start=1):
            branch_id = stable_id("branch.phase5", {"run_id": run_id, "case_id": case.case_id})
            branch_kind = "falsification" if case.expected_classification in {"refutes", "restricts"} else "verification"
            self.workspace.append(
                record_type="branch", subject_id=branch_id, recorded_at=recorded_at,
                payload={
                    "branch_id": branch_id, "run_id": run_id, "objective_id": objective_id,
                    "case_id": case.case_id, "kind": branch_kind,
                    "priority": priority, "status": "checked",
                    "falsification_condition": "exact nonoptimal fixed point" if branch_kind == "falsification" else "exact YKL/dual mismatch",
                },
            )
            result = run_case(case)
            dead_end = result["result_hash"] in seen_result_hashes
            seen_result_hashes.add(result["result_hash"])
            if dead_end:
                self.workspace.append(
                    record_type="dead_end", subject_id=branch_id, recorded_at=recorded_at,
                    payload={"run_id": run_id, "branch_id": branch_id, "reason": "duplicate exact semantic result"},
                )
                continue
            finding = self._record_finding(
                run_id=run_id, objective_id=objective_id, branch_id=branch_id,
                result=result, recorded_at=recorded_at,
            )
            findings.append(finding)
            evidence_id = stable_id("evidence.phase5", {"run_id": run_id, "case_id": case.case_id})
            evidence = self.register_evidence(
                evidence_id=evidence_id, objective_id=objective_id, run_id=run_id,
                kind="exact_arithmetic_certificate", artifact=result, recorded_at=recorded_at,
            )
            if result["nonoptimal_fixed_point"]:
                statement = (
                    "The arbitrary-initialization normalization-corrected JRF claim is false: "
                    "the exact boundary POVM is a non-optimal fixed point with gap 1/3."
                )
                event = self.surface_material_result(
                    objective_id=objective_id, run_id=run_id, branch_id=branch_id,
                    finding_id=finding["subject_id"], evidence_id=evidence_id,
                    classification="restricts", statement=statement,
                    originating_principal_id=system_id, created_by_principal_id=system_id,
                    capability_id="capability.phase5.surface", recorded_at=recorded_at,
                )
                surfaced.append(event["record_id"])
        self.workspace.verify_integrity()
        return {
            "schema_version": "adaivy.phase5-run-result.v1",
            "run_id": run_id, "objective_id": objective_id,
            "run_record_hash": run["content_hash"],
            "fixture_hash": fixture_hash,
            "finding_ids": [item["subject_id"] for item in findings],
            "material_result_event_ids": surfaced,
            "branch_count": len(cases), "dead_end_count": len(cases) - len(findings),
            "search_tiers": run["payload"]["search_tiers"],
            "objective_incomplete": True,
        }

    # -- ADR-0035 noncommuting expansion: verification, never discovery -----
    #
    # These methods are additive. `DiagonalCase` and `run_case` above are
    # unchanged in signature and behaviour, because Phase 6 drives them for its
    # GC-02B control.

    def admit_supplied_certificate(
        self, *, run_id: str, case_id: str, certificate_provenance: Mapping[str, Any],
        certificate_hash: str, admitting_principal_id: str, capability_id: str,
        recorded_at: str,
    ) -> dict[str, Any]:
        """Admit a human-derived certificate through the human-steering boundary.

        The deriving principal is mandatory and must be a recorded trusted
        human-final principal. Nonhuman steering fails closed exactly as sealed
        Phase 5 already requires for `steer`.
        """

        deriving_principal_id = certificate_provenance.get("deriving_principal_id")
        if not deriving_principal_id or not isinstance(deriving_principal_id, str):
            raise Phase5ValidationError(
                "a supplied certificate must record the principal that derived it"
            )
        if certificate_provenance.get("system_generated") is not False:
            raise Phase5ValidationError(
                "a certificate is a human input and may not be recorded as "
                "system-generated"
            )
        deriving = self._one("principal", deriving_principal_id)
        if (
            deriving["payload"]["actor_kind"] != ActorKind.HUMAN.value
            or deriving["payload"]["authority"] != Authority.HUMAN_FINAL.value
        ):
            raise PermissionError(
                "certificate derivation requires a trusted human-final principal"
            )
        admitting, _capability = self._principal_capability(
            admitting_principal_id, capability_id, "steer_research"
        )
        if (
            admitting["payload"]["actor_kind"] != ActorKind.HUMAN.value
            or admitting["payload"]["authority"] != Authority.HUMAN_FINAL.value
        ):
            raise PermissionError(
                "certificate admission requires a trusted human-final principal"
            )
        admission_id = stable_id(
            "noncommuting-admission", {"run_id": run_id, "case_id": case_id}
        )
        return self.workspace.append(
            record_type="noncommuting_certificate_admission", subject_id=admission_id,
            recorded_at=recorded_at,
            payload={
                "schema_version": NONCOMMUTING_ADMISSION_VERSION,
                "admission_id": admission_id,
                "run_id": run_id,
                "case_id": case_id,
                "admitted_through": "authorized_human_steering",
                "required_capability": "steer_research",
                "capability_id": capability_id,
                "admitting_principal_id": admitting_principal_id,
                "deriving_principal_id": deriving_principal_id,
                "deriving_principal_hash": deriving["content_hash"],
                "derivation": certificate_provenance.get("derivation"),
                "certificate_hash": certificate_hash,
                "certificate_origin": "human_supplied",
                "system_generated": False,
                "discovery_performed": False,
                "trust_effect": "admits_a_candidate_for_exact_checking_only",
                "separation_of_duty": {
                    "derivation_and_admission_principals_identical": (
                        deriving_principal_id == admitting_principal_id
                    ),
                    "second_principal_required": False,
                    "enforced": False,
                    "containment": "mathematical_zero_gap_certificate_is_self_verifying",
                    "recorded_gap": SEPARATION_OF_DUTY_NOTE,
                },
            },
        )

    def run_noncommuting_fixture(
        self, fixture: Mapping[str, Any], *, recorded_at: str,
        objective_id: str = "objective.qd-nc-01", run_id: str | None = None,
    ) -> dict[str, Any]:
        """Verify every supplied certificate in a frozen noncommuting fixture.

        A case with no certificate produces an explicit unresolved outcome. No
        branch of this method searches for, defaults to, or generates one, and
        no result may report a discovered optimum.
        """

        cases = parse_fixture(fixture)
        raw_certificates = {
            item["case_id"]: item["certificate"] for item in fixture["cases"]
        }
        fixture_hash = canonical_hash(fixture)
        run_id = run_id or stable_id(
            "run.phase5-noncommuting",
            {"objective_id": objective_id, "fixture_hash": fixture_hash},
        )
        self.ensure_objective(
            objective_id=objective_id,
            statement=(
                "Check exact noncommuting discrimination certificates supplied by an "
                "authorized human; discover none."
            ),
            semantic_alignment_id="alignment.qd-nc-01.v1", recorded_at=recorded_at,
        )
        human_id = "principal.phase5.owner"
        self.ensure_principal(
            principal_id=human_id, actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, recorded_at=recorded_at,
        )
        self.ensure_capability(
            capability_id="capability.phase5.steer", principal_id=human_id,
            operation="steer_research", recorded_at=recorded_at,
        )
        run = self.workspace.append(
            record_type="noncommuting_run", subject_id=run_id, recorded_at=recorded_at,
            payload={
                "run_id": run_id, "objective_id": objective_id,
                "benchmark_id": NONCOMMUTING_BENCHMARK_ID,
                "fixture_hash": fixture_hash, "protocol_class": "exact_verification",
                "status": "verification_only", "external_cost_usd": 0,
                "network_calls": 0, "model_calls": 0,
                "arithmetic": "exact_algebraic_quadratic_complex",
                "tolerance": None,
                "verification_mode": "verifies_supplied_certificate_never_discovers",
                "discovery_performed": False,
                "general_noncommuting_convergence_answered": False,
                "coverage_status_vocabulary": list(COVERAGE_STATUSES),
                "unproducible_coverage_status": FORBIDDEN_COVERAGE_STATUS,
                "search_tiers": {
                    "tier_0": "enabled_deterministic",
                    "tier_2": "disabled_no_measured_cost_adjusted_gain",
                    "tier_3": "disabled_no_measured_cost_adjusted_gain",
                    "tier_4": "disabled_no_measured_cost_adjusted_gain",
                },
            },
        )
        admissions: list[str] = []
        for case in cases:
            if case.certificate is None:
                self.workspace.append(
                    record_type="noncommuting_unresolved", subject_id=(
                        stable_id("noncommuting-unresolved", {"run_id": run_id, "case_id": case.case_id})
                    ),
                    recorded_at=recorded_at,
                    payload={
                        "run_id": run_id, "case_id": case.case_id,
                        "coverage_status": COVERAGE_UNRESOLVED,
                        "reason": "no certificate was supplied and none was constructed",
                        "attempted_discovery": False,
                    },
                )
                continue
            provenance = case.certificate.provenance()
            admission = self.admit_supplied_certificate(
                run_id=run_id, case_id=case.case_id,
                certificate_provenance=provenance,
                certificate_hash=canonical_hash(raw_certificates[case.case_id]),
                admitting_principal_id=provenance["deriving_principal_id"],
                capability_id="capability.phase5.steer", recorded_at=recorded_at,
            )
            admissions.append(admission["record_id"])

        report = verify_fixture(fixture)
        findings: list[str] = []
        for result in report["results"]:
            finding_id = stable_id(
                "noncommuting-finding", {"run_id": run_id, "case_id": result["case_id"]}
            )
            record = self.workspace.append(
                record_type="noncommuting_finding", subject_id=finding_id,
                recorded_at=recorded_at,
                payload={
                    "schema_version": NONCOMMUTING_FINDING_VERSION,
                    "finding_id": finding_id, "run_id": run_id,
                    "objective_id": objective_id, "case_id": result["case_id"],
                    "coverage_status": result["coverage_status"],
                    "coverage": dict(result["coverage"]),
                    "certificate_provenance": result["certificate_provenance"],
                    "result_hash": result["result_hash"],
                    "proposal_status": result["proposal_status"],
                    "applicability_status": result["applicability_status"],
                    "mathematical_warrant": result["mathematical_warrant"],
                    "graph_admitted": False,
                    "result": dict(result),
                },
            )
            findings.append(record["record_id"])
        summary = self.workspace.append(
            record_type="noncommuting_run_summary", subject_id=run_id,
            recorded_at=recorded_at,
            payload={
                "run_id": run_id, "objective_id": objective_id,
                "report_hash": report["content_hash"],
                "coverage_status_counts": dict(report["coverage_status_counts"]),
                "coverage_statement": COVERAGE_STATEMENT,
                "coverage_illusion_warning": report["coverage_illusion_warning"],
                "field_boundary_case_ids": list(report["field_boundary_case_ids"]),
                "unresolved_case_ids": list(report["unresolved_case_ids"]),
                "radicands_used": list(report["radicands_used"]),
                "general_noncommuting_convergence_answered": False,
                "discovery_performed": False,
                "separation_of_duty_note": SEPARATION_OF_DUTY_NOTE,
            },
        )
        self.workspace.verify_integrity()
        return {
            "schema_version": NONCOMMUTING_RUN_VERSION,
            "benchmark_id": NONCOMMUTING_BENCHMARK_ID,
            "run_id": run_id, "objective_id": objective_id,
            "run_record_hash": run["content_hash"],
            "summary_record_hash": summary["content_hash"],
            "fixture_hash": fixture_hash,
            "report_hash": report["content_hash"],
            "case_coverage_status": {
                item["case_id"]: item["coverage_status"] for item in report["results"]
            },
            "coverage_status_counts": dict(report["coverage_status_counts"]),
            "coverage_status_vocabulary": list(COVERAGE_STATUSES),
            "unproducible_coverage_status": FORBIDDEN_COVERAGE_STATUS,
            "coverage_statement": COVERAGE_STATEMENT,
            "coverage_illusion_warning": report["coverage_illusion_warning"],
            "certificate_admission_ids": admissions,
            "finding_ids": findings,
            "field_boundary_case_ids": list(report["field_boundary_case_ids"]),
            "unresolved_case_ids": list(report["unresolved_case_ids"]),
            "gap_not_closed_case_ids": list(report["gap_not_closed_case_ids"]),
            "verified_certificate_case_ids": list(report["verified_certificate_case_ids"]),
            "radicands_used": list(report["radicands_used"]),
            "case_count": report["case_count"],
            "discovery_performed": False,
            "general_noncommuting_convergence_answered": False,
            "separation_of_duty_note": SEPARATION_OF_DUTY_NOTE,
            "search_tiers": run["payload"]["search_tiers"],
            "tolerance": None,
            "objective_incomplete": True,
        }
