"""Executed Section 18.4 generality control suite with falsifiability probes.

Every control in this module *executes*. It builds a project-authored fixture
variant, drives real Phase 1 trust policy (`domain/policies.py`), the exact
Phase 5 diagonal engine (`phase5/quantum.py`), or the Phase 6 held-out capability
boundary (`phase6/heldout.py`), and compares the resulting verdict against a
frozen expectation. Nothing here declares an outcome.

Two rules make the forbidden outcomes demonstrable rather than merely untested.

*Falsifiability probe.* Each control carries a named single-field mutation of its
own parameters. The probe must (a) satisfy its own stated forbidden verdict and
(b) break the control's expectation. A control whose probe does not flip is a
suite failure: a control that cannot be made to fail proves nothing.

*Polarity.* At least one control is positive. An all-negative suite is scored
5/5 by a system that rejects everything, which is exactly the defect this module
replaces.

The controls read no clock, no environment, no randomness, and no unordered set
iteration, so `run_suite` is byte-reproducible across runs, restarts, and
processes.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..application.manual_slice import ACTOR, STAMP, build_known_valid_theorem_dossier
from ..domain.entities import (
    ALL_ENTITY_TYPES,
    AlignmentStatus,
    ApplicabilityStatus,
    ApprovalStatus,
    AuditEvent,
    Claim,
    ClaimOrigin,
    ClaimScope,
    Compatibility,
    Disposition,
    ENTITY_SCHEMA_VERSION,
    EpistemicWarrant,
    EvaluationProtocol,
    Evidence,
    EvidenceKind,
    Formalization,
    ObligationStatus,
    ProblemType,
    ProofObligation,
    ProtocolPhase,
    RecordStatus,
    RepresentationStatus,
    ResearchDossier,
    ResearchProblem,
    SemanticAlignmentRecord,
    SourceApplicabilityRecord,
    StrengthRelation,
    VerificationOutcome,
    VerificationRecord,
    WarrantKind,
    oid,
)
from ..domain.policies import TrustPolicy, TrustProjection
from ..interchange import content_hash, export_dossier_dict, validate_dossier_payload
from ..phase5.quantum import DiagonalCase, run_case
from ..phase5.serialization import canonical_hash
from ..phase5.workspace import decode_json
from .errors import GeneralitySuiteError
from .heldout import HeldOutView

SUITE_SCHEMA_VERSION = "adaivy.generality-control-suite.v1"
SUITE_RESULT_SCHEMA_VERSION = "adaivy.generality-control-suite-result.v1"
MAX_SUITE_BYTES = 262_144

SUITE_FIELDS = frozenset({
    "schema_version", "suite_id", "version", "control_corpus_provenance",
    "limitations", "controls",
})
CONTROL_FIELDS = frozenset({
    "control_id", "category", "blueprint_reference", "polarity", "engine",
    "parameters", "expected", "probe", "limitations",
})
PROBE_FIELDS = frozenset({"probe_id", "field", "value", "forbidden_outcome", "expected"})

# Closed set. The first six are the Section 18.4 categories; the rest are the
# Section 20 scenarios and the Section 18.2 plugin contract that 18.4 references.
GC_CATEGORIES = frozenset({
    "known_theorems",
    "false_conjectures",
    "missing_assumption_traps",
    "semantic_mistranslations",
    "inapplicable_citations",
    "cross_representation_problems",
    "unsupported_consensus",
    "finite_experiment_overreach",
    "premise_smuggling",
    "plugin_core_contract",
    "evaluation_leakage",
})
POLARITIES = frozenset({"positive", "negative"})
CONTROL_CORPUS_PROVENANCE = frozenset({"project_authored"})

PROJECTION_AXES = tuple(item.name for item in fields(TrustProjection))
CORE_ENTITY_TYPE_NAMES = frozenset(item.__name__ for item in ALL_ENTITY_TYPES)


# --- fixture variant construction ----------------------------------------
#
# These transforms were previously reachable only from
# `tests/test_phase1_adversarial.py`. They live in `src/` so the controls run at
# release time rather than only under `unittest`. They construct entities; they
# never edit `domain/entities.py` or `domain/policies.py`.


def _enum(cls: type, value: Any, field: str) -> Any:
    try:
        return cls(value)
    except ValueError as error:
        raise GeneralitySuiteError(f"unknown {field} value: {value!r}") from error


def _accepted_warrant(
    claim: Claim, kind: WarrantKind, evidence_kind: EvidenceKind, suffix: str,
    *, statement_hash: str | None = None, warrant_status: RecordStatus = RecordStatus.ACTIVE,
) -> tuple[Evidence, VerificationRecord, EpistemicWarrant]:
    evidence = Evidence(
        id=oid(f"evidence.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, kind=evidence_kind, content=suffix,
        artifact_hash=content_hash(suffix), source_ref=None, disposition=Disposition.ACCEPTED,
    )
    verification = VerificationRecord(
        id=oid(f"verification.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, verifier_kind=kind.value, outcome=VerificationOutcome.PASS,
        evidence_ids=(evidence.id,),
        target_statement_hash=statement_hash or content_hash(claim.statement),
        independent_from_proposer=True, disposition=Disposition.ACCEPTED,
    )
    warrant = EpistemicWarrant(
        id=oid(f"warrant.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, kind=kind, scope="generality control variant",
        evidence_ids=(evidence.id,), verification_record_ids=(verification.id,),
        status=warrant_status,
    )
    return evidence, verification, warrant


def _target_claim(dossier: ResearchDossier) -> Claim:
    target_id = dossier.formalization.target_claim_id
    return next(item for item in dossier.claims if item.id == target_id)


def _replace_target_warrant(
    kind: WarrantKind, evidence_kind: EvidenceKind, suffix: str, *,
    target_statement: str | None = None, statement_hash: str | None = None,
    warrant_status: RecordStatus = RecordStatus.ACTIVE,
) -> ResearchDossier:
    dossier = build_known_valid_theorem_dossier()
    target_id = dossier.formalization.target_claim_id
    target = _target_claim(dossier)
    if target_statement is not None:
        target = replace(target, statement=target_statement)
        claims = tuple(target if item.id == target_id else item for item in dossier.claims)
    else:
        claims = dossier.claims
    evidence, verification, warrant = _accepted_warrant(
        target, kind, evidence_kind, suffix,
        statement_hash=statement_hash, warrant_status=warrant_status,
    )
    obligations = tuple(
        replace(item, status=ObligationStatus.DISCHARGED, discharged_by_warrant_id=warrant.id)
        if item.claim_id == target_id else item
        for item in dossier.obligations
    )
    return replace(
        dossier, claims=claims,
        warrants=tuple(item for item in dossier.warrants if item.claim_id != target_id) + (warrant,),
        evidence=tuple(item for item in dossier.evidence if item.claim_id != target_id) + (evidence,),
        verification_records=tuple(
            item for item in dossier.verification_records if item.claim_id != target_id
        ) + (verification,),
        obligations=obligations,
    )


# --- observations ---------------------------------------------------------


def _blocker_prefixes(blockers: Iterable[str]) -> list[str]:
    return sorted({item.split(":", 1)[0] for item in blockers})


def _dossier_valid(dossier: ResearchDossier) -> bool:
    return not validate_dossier_payload(export_dossier_dict(dossier))


def _projection_observations(dossier: ResearchDossier) -> dict[str, Any]:
    policy = TrustPolicy(dossier)
    target_id = dossier.formalization.target_claim_id
    resolution = policy.target_resolution()
    projected = policy.project_claim(target_id)
    return {
        "target_logical_status": resolution.logical_status,
        "target_semantic_alignment_status": resolution.semantic_alignment_status,
        "target_blockers": list(resolution.blockers),
        "target_blocker_prefixes": _blocker_prefixes(resolution.blockers),
        "target_warrant_kinds": list(resolution.warrant_kinds),
        "target_claim_scope": _target_claim(dossier).scope.value,
        "target_projection_logical_status": projected.logical_status,
        "target_projection_semantic_alignment_status": projected.semantic_alignment_status,
        "target_novelty_status": resolution.novelty_status,
        "target_significance_status": resolution.significance_status,
        "dossier_valid": _dossier_valid(dossier),
        "entity_schema_version": ENTITY_SCHEMA_VERSION,
    }


_PROJECTION_KEYS = frozenset({
    "target_logical_status", "target_semantic_alignment_status", "target_blockers",
    "target_blocker_prefixes", "target_warrant_kinds", "target_claim_scope",
    "target_projection_logical_status", "target_projection_semantic_alignment_status",
    "target_novelty_status", "target_significance_status", "dossier_valid",
    "entity_schema_version",
})


# --- engines --------------------------------------------------------------


def _engine_target_warrant_status(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-01. A known-valid theorem dossier must actually reach `proved`."""

    status = _enum(RecordStatus, parameters["warrant_status"], "warrant_status")
    dossier = build_known_valid_theorem_dossier()
    target_id = dossier.formalization.target_claim_id
    warrants = tuple(
        replace(item, status=status) if item.claim_id == target_id else item
        for item in dossier.warrants
    )
    observations = _projection_observations(replace(dossier, warrants=warrants))
    observations["target_warrant_status"] = status.value
    return observations


def _engine_target_warrant_kind(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-02A, GC-07, GC-08A. Which warrant kind carries the target."""

    kind = _enum(WarrantKind, parameters["warrant_kind"], "warrant_kind")
    evidence_kind = _enum(EvidenceKind, parameters["evidence_kind"], "evidence_kind")
    dossier = _replace_target_warrant(
        kind, evidence_kind, "generality_target_warrant",
        target_statement=parameters["target_statement"],
    )
    observations = _projection_observations(dossier)
    observations["target_warrant_kind"] = kind.value
    return observations


def _engine_alignment_assumption_delta(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-03. A named omitted hypothesis must not resolve the target."""

    delta = parameters["assumption_delta"]
    if not isinstance(delta, list) or any(not isinstance(item, str) or not item for item in delta):
        raise GeneralitySuiteError("assumption_delta must be a list of non-empty strings")
    dossier = build_known_valid_theorem_dossier()
    alignment = replace(dossier.semantic_alignment, assumption_delta=tuple(delta))
    observations = _projection_observations(replace(dossier, semantic_alignment=alignment))
    observations["assumption_delta"] = list(delta)
    return observations


def _engine_formal_target_binding(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-04. Offline substitute for Section 20 scenario H.

    A `FORMAL_ARTIFACT` evidence and its verification record are bound to the
    statement the artifact actually proves. When that statement is the weakened
    one, the formal warrant is retained for the weakened claim and the original
    target stays unresolved. See ADR-0034 for the substitution: no Lean kernel
    runs here, because that is the sealed Phase 3B runtime.
    """

    formal_statement = parameters["formal_statement"]
    if not isinstance(formal_statement, str) or not formal_statement:
        raise GeneralitySuiteError("formal_statement must be a non-empty string")
    base = build_known_valid_theorem_dossier()
    target_statement = _target_claim(base).statement
    dossier = _replace_target_warrant(
        WarrantKind.FORMAL_PROOF, EvidenceKind.FORMAL_ARTIFACT, "generality_formal_target",
        statement_hash=content_hash(formal_statement),
    )
    formal_claim = Claim(
        id=oid("claim.generality_formal_statement.v1"), created_at=STAMP, created_by=ACTOR,
        kind="theorem", statement=formal_statement, assumption_claim_ids=(),
        origin=ClaimOrigin.FORMAL_SYSTEM, scope=ClaimScope.PARTICULAR,
    )
    evidence, verification, warrant = _accepted_warrant(
        formal_claim, WarrantKind.FORMAL_PROOF, EvidenceKind.FORMAL_ARTIFACT,
        "generality_formal_statement",
    )
    candidate = replace(
        dossier, claims=dossier.claims + (formal_claim,),
        evidence=dossier.evidence + (evidence,),
        verification_records=dossier.verification_records + (verification,),
        warrants=dossier.warrants + (warrant,),
    )
    observations = _projection_observations(candidate)
    observations["formal_claim_logical_status"] = (
        TrustPolicy(candidate).project_claim(formal_claim.id).logical_status
    )
    observations["formal_statement_hash"] = content_hash(formal_statement)
    observations["target_statement_hash"] = content_hash(target_statement)
    observations["formal_artifact_binds_target"] = formal_statement == target_statement
    return observations


def _engine_source_applicability(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-05. A real-but-inapplicable source must not close an obligation.

    The imported statement, hypotheses, and span are synthetic: the benchmark
    paper is metadata-only with no licensed local content. ADR-0034 records the
    substitution.
    """

    compatibility = _enum(
        Compatibility, parameters["hypothesis_compatibility"], "hypothesis_compatibility"
    )
    dossier = build_known_valid_theorem_dossier()
    target = _target_claim(dossier)
    imported = Claim(
        id=oid("claim.generality_imported_lemma.v1"), created_at=STAMP, created_by=ACTOR,
        kind="lemma",
        statement="For all positive reals x and y, if x divides y then x is at most y.",
        assumption_claim_ids=(), origin=ClaimOrigin.SOURCE, scope=ClaimScope.UNRESTRICTED_UNIVERSAL,
    )
    evidence, verification, warrant = _accepted_warrant(
        imported, WarrantKind.RIGOROUS_DERIVATION, EvidenceKind.DERIVATION,
        "generality_imported_lemma",
    )
    span = Evidence(
        id=oid("evidence.generality_imported_span.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=imported.id, kind=EvidenceKind.SOURCE_SPAN,
        content="Synthetic span: hypotheses are stated over the positive reals.",
        artifact_hash=content_hash("Synthetic span: hypotheses are stated over the positive reals."),
        source_ref="local:synthetic-source#span-1", disposition=Disposition.ACCEPTED,
    )
    obligation = ProofObligation(
        id=oid("obligation.generality_imported_applicability.v1"), created_at=STAMP,
        created_by=ACTOR, claim_id=target.id,
        description="Check the hypotheses and definition mapping of the imported lemma.",
        category="literature_applicability", status=ObligationStatus.OPEN,
    )
    record = SourceApplicabilityRecord(
        id=oid("applicability.generality_imported_lemma.v1"), created_at=STAMP, created_by=ACTOR,
        local_claim_id=target.id, evidence_id=span.id,
        imported_statement=imported.statement,
        imported_hypotheses=("x and y are positive reals",),
        definition_mapping=(("divides", "integer divisibility"),),
        scope_and_exceptions=("positive reals only; the local target ranges over all integers",),
        implication_obligation_id=obligation.id, bibliographic_status="confirmed",
        hypothesis_compatibility=compatibility, implication_verified=True,
        status=ApplicabilityStatus.CHECKED,
    )
    candidate = replace(
        dossier, claims=dossier.claims + (imported,),
        evidence=dossier.evidence + (evidence, span),
        verification_records=dossier.verification_records + (verification,),
        warrants=dossier.warrants + (warrant,),
        obligations=dossier.obligations + (obligation,),
        source_applicability=dossier.source_applicability + (record,),
    )
    policy = TrustPolicy(candidate)
    allowed, reason = policy.can_discharge_obligation(obligation.id, imported.id)
    after = next(item for item in candidate.obligations if item.id == obligation.id)
    observations = _projection_observations(candidate)
    observations.update({
        "discharge_allowed": allowed,
        "discharge_reason": reason,
        "obligation_status_after_call": after.status.value,
        "supporting_claim_logical_status": policy.project_claim(imported.id).logical_status,
        "hypothesis_compatibility": compatibility.value,
    })
    return observations


def _engine_representation_status(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-06A and GC-06B. A transformed result may not cross an unverified bridge."""

    map_status = _enum(RepresentationStatus, parameters["map_status"], "map_status")
    bridge_status = _enum(
        ObligationStatus, parameters["bridge_obligation_status"], "bridge_obligation_status"
    )
    dossier = build_known_valid_theorem_dossier()
    mapping = dossier.representation_maps[0]
    bridge_id = mapping.bridge_obligation_ids[0]
    obligations = tuple(
        replace(
            item, status=bridge_status,
            discharged_by_warrant_id=(
                item.discharged_by_warrant_id
                if bridge_status is ObligationStatus.DISCHARGED else None
            ),
        )
        if item.id == bridge_id else item
        for item in dossier.obligations
    )
    candidate = replace(
        dossier, representation_maps=(replace(mapping, status=map_status),),
        obligations=obligations,
    )
    observations = _projection_observations(candidate)
    observations.update({
        "map_status": map_status.value,
        "bridge_obligation_status": bridge_status.value,
    })
    return observations


def _engine_helper_lemma(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-08B. Section 20 scenario J: a helper that restates the target."""

    statement = parameters["helper_statement"]
    if statement is not None and (not isinstance(statement, str) or not statement):
        raise GeneralitySuiteError("helper_statement must be null or a non-empty string")
    dossier = build_known_valid_theorem_dossier()
    target = _target_claim(dossier)
    helper = replace(
        target, id=oid("claim.generality_helper.v1"), origin=ClaimOrigin.MODEL,
        statement=target.statement if statement is None else statement,
    )
    evidence, verification, warrant = _accepted_warrant(
        helper, WarrantKind.RIGOROUS_DERIVATION, EvidenceKind.DERIVATION, "generality_helper",
    )
    obligation = ProofObligation(
        id=oid("obligation.generality_helper.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id,
        description="Prove the target via a helper lemma described as standard.",
        category="helper_lemma", status=ObligationStatus.OPEN,
        normalized_statement=target.statement,
    )
    candidate = replace(
        dossier, claims=dossier.claims + (helper,), evidence=dossier.evidence + (evidence,),
        verification_records=dossier.verification_records + (verification,),
        warrants=dossier.warrants + (warrant,),
        obligations=dossier.obligations + (obligation,),
    )
    policy = TrustPolicy(candidate)
    allowed, reason = policy.can_discharge_obligation(obligation.id, helper.id)
    after = next(item for item in candidate.obligations if item.id == obligation.id)
    observations = _projection_observations(candidate)
    observations.update({
        "discharge_allowed": allowed,
        "discharge_reason": reason,
        "obligation_status_after_call": after.status.value,
        "helper_restates_target": helper.statement.strip() == target.statement.strip(),
    })
    return observations


def _engine_exact_diagonal_case(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-02B. The false conjecture is on the benchmark itself.

    "The JRF iteration converges to the optimum from any initialization" is
    false. The boundary initialization is an exact fixed point strictly below the
    independent optimum, and the exact engine must report it as such rather than
    as convergence. The case is carried inline here rather than appended to
    `fixtures/phase5/quantum-diagonal-v1.json`, whose canonical hash is pinned by
    the confirmatory protocol.
    """

    case = DiagonalCase.from_value(dict(parameters))
    result = run_case(case)
    return {
        "case_id": result["case_id"],
        "fixed_point": result["fixed_point"],
        "nonoptimal_fixed_point": result["nonoptimal_fixed_point"],
        "primal_dual_gap": result["primal_dual_gap"],
        "final_objective": result["final_objective"],
        "independent_primal_optimum": result["independent_primal_optimum"],
        "independent_dual_optimum": result["independent_dual_optimum"],
        "independent_primal_dual_agreement": (
            result["independent_primal_optimum"] == result["independent_dual_optimum"]
        ),
        "closed_form_accumulation_point_optimal": result["closed_form_accumulation_point_optimal"],
        "initial_full_support": result["initial_full_support"],
        "graph_admitted": result["graph_admitted"],
        "mathematical_warrant": result["mathematical_warrant"],
        "applicability_status": result["applicability_status"],
    }


def _plugin_dossier(kind: WarrantKind) -> ResearchDossier:
    """A minimal second-domain dossier built from unchanged core entities."""

    definition = Claim(
        id=oid("claim.two_colouring_definition.v1"), created_at=STAMP, created_by=ACTOR,
        kind="definition",
        statement="A graph is 2-colourable iff its vertices admit labels in {0,1} with no edge joining equal labels.",
        assumption_claim_ids=(), origin=ClaimOrigin.SOURCE, scope=ClaimScope.DEFINITIONAL,
    )
    target = Claim(
        id=oid("claim.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        kind="theorem",
        statement="Every cycle graph on an even number of vertices is 2-colourable.",
        assumption_claim_ids=(definition.id,), origin=ClaimOrigin.USER,
        scope=ClaimScope.UNRESTRICTED_UNIVERSAL,
    )
    evidence, verification, warrant = _accepted_warrant(
        target, kind, EvidenceKind.DERIVATION, "plugin_even_cycle",
    )
    obligation = ProofObligation(
        id=oid("obligation.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id, description="Provide a complete proof of the exact target.",
        category="logical_gap", status=ObligationStatus.DISCHARGED,
        discharged_by_warrant_id=warrant.id,
    )
    problem = ResearchProblem(
        id=oid("problem.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        title="Two-colourability of even cycles", informal_statement=target.statement,
        problem_type=ProblemType.PROVE, tags=("graph-theory", "plugin-contract"),
        active_formalization_id=oid("formalization.even_cycle_two_colourable.v1"),
    )
    formalization = Formalization(
        id=oid("formalization.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        problem_id=problem.id, version=1,
        statement="forall n : N, Even(n) and n >= 4 implies TwoColourable(C_n)",
        formal_language="typed_informal_math", quantifiers=("forall n in N",),
        assumption_claim_ids=(definition.id,), target_claim_id=target.id,
        approval_status=ApprovalStatus.APPROVED,
    )
    alignment = SemanticAlignmentRecord(
        id=oid("alignment.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        problem_id=problem.id, formalization_id=formalization.id, compared_claim_id=target.id,
        quantifier_mapping=(("n", "vertex count"),),
        definition_mapping=(("TwoColourable(G)", "labels in {0,1} with no monochromatic edge"),),
        assumption_delta=(), edge_case_delta=(), strength_relation=StrengthRelation.EQUIVALENT,
        status=AlignmentStatus.RESEARCHER_APPROVED, approved_by=ACTOR,
    )
    protocol = EvaluationProtocol(
        id=oid("protocol.plugin_contract.v1"), created_at=STAMP, created_by=ACTOR,
        version=1, phase=ProtocolPhase.CONFIRMATORY,
        metrics=("target_fidelity",), success_criteria=("core projection axes unchanged",),
        stopping_rules=("one deterministic construction",), frozen_at=STAMP, frozen_by=ACTOR,
    )
    event = AuditEvent(
        id=oid("event.plugin_dossier_created.v1"), created_at=STAMP, created_by=ACTOR,
        aggregate_id=problem.id, event_type="plugin_dossier_created",
        payload=(("target_claim_id", target.id.value),),
        idempotency_key="plugin-dossier-created-v1",
    )
    return ResearchDossier(
        id=oid("dossier.even_cycle_two_colourable.v1"), created_at=STAMP, created_by=ACTOR,
        problem=problem, formalization=formalization, semantic_alignment=alignment,
        claims=(definition, target), warrants=(warrant,), evidence=(evidence,),
        source_applicability=(), obligations=(obligation,), representation_maps=(),
        verification_records=(verification,), evaluation_protocol=protocol,
        audit_events=(event,),
        capabilities=("canonical_json", "policy_projection", "append_only_events"),
    )


def _engine_plugin_core_contract(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-09A. Section 18.2: a later domain plugin passes the same core contract.

    This tests the CONTRACT with a minimal fixture. It does not build a second
    real domain, and it is not evidence of coverage in graph theory.
    """

    kind = _enum(WarrantKind, parameters["warrant_kind"], "warrant_kind")
    dossier = _plugin_dossier(kind)
    used = []
    members: list[Any] = [
        dossier.problem, dossier.formalization, dossier.semantic_alignment,
        dossier.evaluation_protocol, dossier,
    ]
    for group in (
        dossier.claims, dossier.warrants, dossier.evidence, dossier.source_applicability,
        dossier.obligations, dossier.representation_maps, dossier.verification_records,
        dossier.audit_events,
    ):
        members.extend(group)
    for item in members:
        name = type(item).__name__
        if name not in used:
            used.append(name)
    observations = _projection_observations(dossier)
    observations.update({
        "domain_id": "graph-two-colouring",
        "projection_axes": list(PROJECTION_AXES),
        "entity_types_used": sorted(used),
        "entity_types_outside_core": sorted(set(used) - CORE_ENTITY_TYPE_NAMES),
        "target_warrant_kind": kind.value,
    })
    return observations


def _engine_heldout_boundary(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """GC-09B. Section 20 scenario L: the capability boundary blocks access.

    The fixture is inline and synthetic. The control never touches the real
    frozen held-out case; `Phase6Service.resolve_heldout_case` is what binds the
    same refusal to a durable violation record.
    """

    cases = parameters["fixture"]
    if not isinstance(cases, list) or not cases:
        raise GeneralitySuiteError("fixture must be a non-empty list of cases")
    view = HeldOutView(
        benchmark_id=str(parameters["benchmark_id"]), cases=cases,
        frozen_case_ids=(str(parameters["frozen_case_id"]),),
    )
    requested = str(parameters["requested_case_id"])
    refused = False
    error_type = None
    resolved: str | None = None
    try:
        resolved = str(view.case(requested)["case_id"])
    except Exception as error:  # noqa: BLE001 - the observed type is the verdict
        refused = True
        error_type = type(error).__name__
    return {
        "requested_case_id": requested,
        "refused": refused,
        "error_type": error_type,
        "resolved_case_id": resolved,
        "visible_case_ids": list(view.visible_case_ids),
        "violation_kinds": [item["kind"] for item in view.violations],
        "violation_count": len(view.violations),
        "fixture_case_count": len(cases),
    }


@dataclass(frozen=True, slots=True)
class ControlEngine:
    engine_id: str
    parameter_fields: frozenset[str]
    observation_keys: frozenset[str]
    run: Callable[[Mapping[str, Any]], dict[str, Any]]


def _engine(
    engine_id: str, parameters: Iterable[str], observations: Iterable[str],
    run: Callable[[Mapping[str, Any]], dict[str, Any]], *, projection: bool = True,
) -> ControlEngine:
    keys = set(observations)
    if projection:
        keys |= set(_PROJECTION_KEYS)
    return ControlEngine(
        engine_id=engine_id, parameter_fields=frozenset(parameters),
        observation_keys=frozenset(keys), run=run,
    )


ENGINES: dict[str, ControlEngine] = {
    item.engine_id: item
    for item in (
        _engine(
            "phase1_target_warrant_status", ("warrant_status",), ("target_warrant_status",),
            _engine_target_warrant_status,
        ),
        _engine(
            "phase1_target_warrant_kind",
            ("warrant_kind", "evidence_kind", "target_statement"), ("target_warrant_kind",),
            _engine_target_warrant_kind,
        ),
        _engine(
            "phase1_alignment_assumption_delta", ("assumption_delta",), ("assumption_delta",),
            _engine_alignment_assumption_delta,
        ),
        _engine(
            "phase1_formal_target_binding", ("formal_statement",),
            (
                "formal_claim_logical_status", "formal_statement_hash",
                "target_statement_hash", "formal_artifact_binds_target",
            ),
            _engine_formal_target_binding,
        ),
        _engine(
            "phase1_source_applicability", ("hypothesis_compatibility",),
            (
                "discharge_allowed", "discharge_reason", "obligation_status_after_call",
                "supporting_claim_logical_status", "hypothesis_compatibility",
            ),
            _engine_source_applicability,
        ),
        _engine(
            "phase1_representation_status", ("map_status", "bridge_obligation_status"),
            ("map_status", "bridge_obligation_status"), _engine_representation_status,
        ),
        _engine(
            "phase1_helper_lemma", ("helper_statement",),
            (
                "discharge_allowed", "discharge_reason", "obligation_status_after_call",
                "helper_restates_target",
            ),
            _engine_helper_lemma,
        ),
        _engine(
            "phase5_exact_diagonal_case",
            (
                "case_id", "statement_variant", "weights", "initial_povm", "iterations",
                "expected_classification",
            ),
            (
                "case_id", "fixed_point", "nonoptimal_fixed_point", "primal_dual_gap",
                "final_objective", "independent_primal_optimum", "independent_dual_optimum",
                "independent_primal_dual_agreement", "closed_form_accumulation_point_optimal",
                "initial_full_support", "graph_admitted", "mathematical_warrant",
                "applicability_status",
            ),
            _engine_exact_diagonal_case, projection=False,
        ),
        _engine(
            "phase1_plugin_core_contract", ("warrant_kind",),
            (
                "domain_id", "projection_axes", "entity_types_used",
                "entity_types_outside_core", "target_warrant_kind",
            ),
            _engine_plugin_core_contract,
        ),
        _engine(
            "phase6_heldout_boundary",
            ("benchmark_id", "fixture", "frozen_case_id", "requested_case_id"),
            (
                "requested_case_id", "refused", "error_type", "resolved_case_id",
                "visible_case_ids", "violation_kinds", "violation_count", "fixture_case_count",
            ),
            _engine_heldout_boundary, projection=False,
        ),
    )
}


# --- suite loading and validation ----------------------------------------


def default_suite_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "fixtures" / "phase6" / "generality" / "generality-controls-v1.json"
    )


def load_suite(path: Path | None = None) -> dict[str, Any]:
    location = default_suite_path() if path is None else Path(path)
    try:
        data = location.read_bytes()
    except OSError as error:
        raise GeneralitySuiteError(f"generality suite is unreadable: {location}") from error
    try:
        suite = decode_json(data, max_bytes=MAX_SUITE_BYTES)
    except ValueError as error:
        # Malformed JSON, duplicate keys, a non-finite number, or an oversized
        # file are all rejects, reported as one fail-closed type.
        raise GeneralitySuiteError(f"generality suite is not valid canonical JSON: {error}") from error
    validate_suite(suite)
    return suite


def suite_hash(suite: Mapping[str, Any]) -> str:
    return canonical_hash(suite)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeneralitySuiteError(message)


def validate_suite(suite: Any) -> None:
    _require(isinstance(suite, dict), "generality suite must be an object")
    _require(set(suite) == set(SUITE_FIELDS), "generality suite has missing or unknown fields")
    _require(
        suite["schema_version"] == SUITE_SCHEMA_VERSION,
        "unsupported generality suite schema version",
    )
    _require(
        isinstance(suite["suite_id"], str) and bool(suite["suite_id"]),
        "generality suite id must be a non-empty string",
    )
    _require(suite["version"] == 1, "unsupported generality suite version")
    _require(
        suite["control_corpus_provenance"] in CONTROL_CORPUS_PROVENANCE,
        "unknown control corpus provenance",
    )
    _require(
        isinstance(suite["limitations"], list)
        and bool(suite["limitations"])
        and all(isinstance(item, str) and item for item in suite["limitations"]),
        "generality suite must state its limitations",
    )
    controls = suite["controls"]
    _require(isinstance(controls, list) and bool(controls), "generality suite has no controls")
    seen_controls: list[str] = []
    seen_probes: list[str] = []
    positives = 0
    for control in controls:
        _require(isinstance(control, dict), "generality control must be an object")
        _require(
            set(control) == set(CONTROL_FIELDS),
            "generality control has missing or unknown fields",
        )
        control_id = control["control_id"]
        _require(
            isinstance(control_id, str) and bool(control_id) and control_id not in seen_controls,
            "generality control ids must be non-empty and unique",
        )
        seen_controls.append(control_id)
        _require(control["category"] in GC_CATEGORIES, f"{control_id}: unknown control category")
        _require(control["polarity"] in POLARITIES, f"{control_id}: unknown control polarity")
        if control["polarity"] == "positive":
            positives += 1
        _require(
            isinstance(control["blueprint_reference"], str) and bool(control["blueprint_reference"]),
            f"{control_id}: a control must cite the requirement it enforces",
        )
        _require(
            isinstance(control["limitations"], list)
            and all(isinstance(item, str) and item for item in control["limitations"]),
            f"{control_id}: limitations must be a list of non-empty strings",
        )
        engine = ENGINES.get(control["engine"])
        _require(engine is not None, f"{control_id}: unknown control engine")
        assert engine is not None
        parameters = control["parameters"]
        _require(isinstance(parameters, dict), f"{control_id}: parameters must be an object")
        _require(
            set(parameters) == set(engine.parameter_fields),
            f"{control_id}: parameters do not match the engine signature",
        )
        expected = control["expected"]
        _require(
            isinstance(expected, dict) and bool(expected),
            f"{control_id}: a control must assert at least one observation",
        )
        unknown = sorted(set(expected) - set(engine.observation_keys))
        _require(not unknown, f"{control_id}: expects unobservable keys {unknown}")
        probe = control["probe"]
        _require(isinstance(probe, dict), f"{control_id}: probe must be an object")
        _require(
            set(probe) == set(PROBE_FIELDS), f"{control_id}: probe has missing or unknown fields"
        )
        probe_id = probe["probe_id"]
        _require(
            isinstance(probe_id, str) and bool(probe_id) and probe_id not in seen_probes,
            f"{control_id}: probe ids must be non-empty and unique",
        )
        seen_probes.append(probe_id)
        _require(
            isinstance(probe["forbidden_outcome"], str) and bool(probe["forbidden_outcome"]),
            f"{control_id}: probe must name the forbidden outcome it demonstrates",
        )
        _require(
            probe["field"] in parameters,
            f"{control_id}: probe must mutate one of the control's own parameters",
        )
        _require(
            probe["value"] != parameters[probe["field"]],
            f"{control_id}: probe mutation does not change the parameter",
        )
        probe_expected = probe["expected"]
        _require(
            isinstance(probe_expected, dict) and bool(probe_expected),
            f"{control_id}: probe must assert at least one observation",
        )
        unknown = sorted(set(probe_expected) - set(engine.observation_keys))
        _require(not unknown, f"{control_id}: probe expects unobservable keys {unknown}")
    _require(
        positives >= 1,
        "a suite with no positive control is scored full marks by a system that "
        "rejects everything; Section 18.4 names known theorems first",
    )
    categories = sorted({control["category"] for control in controls})
    missing = sorted(
        {
            "known_theorems", "false_conjectures", "missing_assumption_traps",
            "semantic_mistranslations", "inapplicable_citations",
            "cross_representation_problems",
        }
        - set(categories)
    )
    _require(not missing, f"generality suite omits Section 18.4 categories: {missing}")


# --- execution ------------------------------------------------------------


def _mismatches(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for key in sorted(expected):
        if key not in observed:
            result.append({"key": key, "expected": expected[key], "observed": None,
                           "reason": "not_observed"})
        elif observed[key] != expected[key]:
            result.append({"key": key, "expected": expected[key], "observed": observed[key],
                           "reason": "value_differs"})
    return result


def run_control(control: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one control and its falsifiability probe."""

    engine = ENGINES[control["engine"]]
    parameters = dict(control["parameters"])
    try:
        observed = engine.run(parameters)
    except GeneralitySuiteError:
        raise
    except Exception as error:  # noqa: BLE001 - a broken control is a reject
        raise GeneralitySuiteError(
            f"{control['control_id']}: control engine failed: {type(error).__name__}"
        ) from error
    mismatches = _mismatches(control["expected"], observed)

    probe = control["probe"]
    probe_parameters = dict(parameters)
    probe_parameters[probe["field"]] = probe["value"]
    try:
        probe_observed = engine.run(probe_parameters)
    except GeneralitySuiteError:
        raise
    except Exception as error:  # noqa: BLE001 - a broken probe is a reject
        raise GeneralitySuiteError(
            f"{control['control_id']}: probe engine failed: {type(error).__name__}"
        ) from error
    probe_mismatches = _mismatches(probe["expected"], probe_observed)
    control_expectation_under_probe = _mismatches(control["expected"], probe_observed)
    probe_expected_matched = not probe_mismatches
    control_expectation_broken = bool(control_expectation_under_probe)
    return {
        "control_id": control["control_id"],
        "category": control["category"],
        "blueprint_reference": control["blueprint_reference"],
        "polarity": control["polarity"],
        "engine": control["engine"],
        "parameters": parameters,
        "expected": dict(control["expected"]),
        "observed": observed,
        "mismatches": mismatches,
        "passed": not mismatches,
        "limitations": list(control["limitations"]),
        "probe": {
            "probe_id": probe["probe_id"],
            "field": probe["field"],
            "value": probe["value"],
            "forbidden_outcome": probe["forbidden_outcome"],
            "expected": dict(probe["expected"]),
            "observed": probe_observed,
            "mismatches": probe_mismatches,
            "probe_expected_matched": probe_expected_matched,
            "control_expectation_broken": control_expectation_broken,
            "broken_keys": [item["key"] for item in control_expectation_under_probe],
            "flipped": probe_expected_matched and control_expectation_broken,
        },
    }


def run_suite(suite: Mapping[str, Any]) -> dict[str, Any]:
    """Execute every control and probe in a validated suite.

    Two release gates, not one: `controls_passed == controls_total` and
    `probes_flipped == probes_total`. A control whose probe does not flip cannot
    be made to fail, so the suite is reported as failed even if every control
    "passed".
    """

    validate_suite(suite)
    results = [run_control(control) for control in suite["controls"]]
    controls_passed = sum(1 for item in results if item["passed"])
    probes_flipped = sum(1 for item in results if item["probe"]["flipped"])
    positives = [item for item in results if item["polarity"] == "positive"]
    negatives = [item for item in results if item["polarity"] == "negative"]
    value = {
        "schema_version": SUITE_RESULT_SCHEMA_VERSION,
        "suite_id": suite["suite_id"],
        "suite_version": suite["version"],
        "suite_hash": suite_hash(suite),
        "control_corpus_provenance": suite["control_corpus_provenance"],
        "controls_total": len(results),
        "controls_passed": controls_passed,
        "probes_total": len(results),
        "probes_flipped": probes_flipped,
        "categories_covered": sorted({item["category"] for item in results}),
        "positive_control_ids": [item["control_id"] for item in positives],
        "positive_controls_total": len(positives),
        "positive_controls_passed": sum(1 for item in positives if item["passed"]),
        "negative_controls_total": len(negatives),
        "negative_controls_passed": sum(1 for item in negatives if item["passed"]),
        "positive_control_admitted": bool(positives) and all(item["passed"] for item in positives),
        "failed_control_ids": [item["control_id"] for item in results if not item["passed"]],
        "unflipped_probe_ids": [
            item["probe"]["probe_id"] for item in results if not item["probe"]["flipped"]
        ],
        "suite_passed": (
            controls_passed == len(results)
            and probes_flipped == len(results)
            and bool(positives)
            and all(item["passed"] for item in positives)
        ),
        "limitations": list(suite["limitations"]),
        "controls": results,
    }
    return value
