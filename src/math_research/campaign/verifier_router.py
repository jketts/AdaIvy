"""Isolated campaign verifier router (end-to-end runtime plan §3.6, ADR-0073).

One selected candidate is dispatched to exactly one admitted verifier:

- the ADR-0066 exact graph verifier for its frozen experiment target;
- the sealed Phase 5 exact quantum-diagonal recomputation for its fixture
  schema;
- the ADR-0035 Phase 5 exact noncommuting certificate verifier for its fixture
  schema; and
- an injected Phase 3B formal-check port for an explicit formal-check request
  envelope.

A candidate no route admits produces an explicit ``unsupported`` outcome
recorded as a FAILED tool run -- never a silent pass and never a silent fail.

Isolation invariants, enforced structurally rather than by promise:

* The router's only per-candidate input is the runner's
  :class:`~math_research.campaign.runner.VerificationRequest`: content hashes
  and exact bytes.  It holds no planner, no gateway, no credential, and no
  corpus handle, so the campaign's persuasive narrative cannot reach a
  verifier through it.
* Every exact route runs in the host process over ``int`` and
  ``fractions.Fraction`` only.  This module imports no ``os``, ``subprocess``,
  ``socket`` or ``ctypes`` module.
* The formal-check route is an injected port.  The default port records the
  missing sealed runtime as a machine-readable missing-tool outcome instead of
  approximating a kernel check.  Free-text validator diagnostics are projected
  down to machine-readable codes before they enter the campaign ledger,
  following ADR-0040: a rejection detail must not become evasion guidance.
* No route creates a warrant, asserts applicability, admits to the graph, or
  assesses novelty or significance.  A ``completed`` verification is a checked
  computation bound to the exact encoded statement; target correspondence
  remains a separate recorded property.

A verifier rejection is a rejected candidate, not a rejected campaign: the
router returns a FAILED :class:`ExperimentResult` and the sequential runner
continues while budget and a valid next action remain.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .records import RecordStatus, UsageSource, canonical_bytes, canonical_hash
from .runner import ExperimentResult, VerificationRequest
from .experiment_sandbox.verifier import (
    CANDIDATE_SCHEMA as GRAPH_CANDIDATE_SCHEMA,
    ExperimentTarget,
    verify_candidate,
)
from ..phase5 import NONCOMMUTING_FIXTURE_VERSION
from ..phase5.noncommuting import verify_fixture
from ..phase5.quantum import DiagonalCase, QuantumInputError, run_case


ROUTER_ADAPTER_ID = "campaign_verifier_router"
ROUTER_ADAPTER_VERSION = "1.0.0"
ROUTER_RESULT_SCHEMA = "adaivy.campaign-verifier-router-result.v1"

DIAGONAL_FIXTURE_SCHEMA = "adaivy.quantum-diagonal-fixture.v1"
#: Minimal dispatch envelope for a Phase 3B formal-check request.  The Phase 3B
#: request schema_version is a bare "1.0.0" and cannot serve as a router
#: dispatch key, so the campaign wraps the exact request object.  Whether
#: formal checking should instead be a first-class campaign action with its own
#: closed action schema is an open question recorded in ADR-0073; this envelope
#: is the deliberate minimal stub.
FORMAL_CHECK_ENVELOPE_SCHEMA = "adaivy.campaign-formal-check-request.v1"

ROUTE_EXACT_GRAPH = "exact_graph"
ROUTE_PHASE5_DIAGONAL = "phase5_quantum_diagonal"
ROUTE_PHASE5_NONCOMMUTING = "phase5_noncommuting"
ROUTE_FORMAL_CHECK = "phase3b_formal_check"
ROUTE_UNSUPPORTED = "unsupported"

#: ADR-0082 verifier-class registration path.  A new exact verifier class for
#: a new problem family is added by a reviewed code change -- never at
#: runtime -- in exactly four steps:
#:
#: 1. Implement the verifier as a host-process module over ``int`` and
#:    ``fractions.Fraction`` only, importing no ``os``, ``subprocess``,
#:    ``socket`` or ``ctypes`` module (the textual isolation probe in
#:    ``experiment_sandbox/activation.py`` stays the enforcement pattern).
#: 2. Define its :class:`~math_research.campaign.experiment_sandbox.target_schema.TargetSchemaClass`
#:    with a closed field inventory and register it in
#:    ``experiment_sandbox/target_schema.py``'s ``TARGET_SCHEMA_CLASSES``.
#: 3. Map the class id to a route below, and add the candidate
#:    ``schema_version`` dispatch in :meth:`CampaignVerifierRouter._dispatch`
#:    with its handler.
#: 4. Re-run the workspace activation gate so the new class definition hash is
#:    bound into a fresh activation record; the old record does not admit the
#:    new class.
#:
#: Verifiers stay host-side, outside every container, refusing floats.
TARGET_CLASS_ROUTES: Mapping[str, str] = {
    "adaivy.campaign-target-class.exact-graph.v2": ROUTE_EXACT_GRAPH,
}


def route_for_target_class(class_id: str) -> str:
    """Resolve the admitted route for a registered target schema class."""

    route = TARGET_CLASS_ROUTES.get(class_id)
    if route is None:
        raise ValueError("no_admitted_verifier_for_target_class")
    return route

UNSUPPORTED_OUTCOME = "unsupported"
UNSUPPORTED_REASON = "no_admitted_verifier_for_candidate"
FORMAL_CHECK_UNAVAILABLE_ADAPTER_ID = "formal_check_unavailable"
FORMAL_CHECK_UNAVAILABLE_REASON = "sealed_formal_check_runtime_not_available"

#: Phase 3B outcomes that count as a completed formal verification of the exact
#: encoded statement.  Everything else -- unapproved assumptions included -- is
#: a rejected candidate, retained and nonterminal.
FORMAL_CHECK_VERIFIED_OUTCOMES = frozenset({
    "kernel_checked", "kernel_checked_approved_standard_axioms",
})

MAX_ROUTED_CANDIDATE_BYTES = 262_144

#: The frozen "nothing is granted" block every router result carries.
_ROUTER_TRUST = {
    "epistemic_warrant_created": False,
    "graph_admission": False,
    "novelty_status": "not_assessed",
    "significance_status": "not_assessed",
    "source_applicability_asserted": False,
    "target_correspondence": "not_asserted_separate_recorded_property",
}

#: The only finding fields a formal-check route may carry into the campaign
#: ledger.  Free-text rejection details and raw checker output are deliberately
#: absent: ADR-0040 forbids feeding a validator diagnostic back toward a
#: proposer, and the full finding remains reconstructable from the exact
#: request bytes through the standalone Phase 3B path.
_SAFE_FINDING_FIELDS = (
    "claim_id", "content_hash", "created_at", "disposition",
    "epistemic_warrant_created", "id", "outcome", "reason", "request_id",
    "trust_effect",
)


class FormalCheckerPort(Protocol):
    """Injected Phase 3B boundary: exact request bytes in, finding record out."""

    @property
    def adapter_id(self) -> str: ...

    def check(self, request_bytes: bytes) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class UnavailableFormalChecker:
    """Records the missing sealed Lean runtime instead of approximating it.

    ``make check`` runs with no container runtime, so the default campaign
    formal-check port is a machine-readable missing-tool result -- retained,
    never a skip that reads as a pass and never a fabricated kernel check.
    """

    adapter_id: str = FORMAL_CHECK_UNAVAILABLE_ADAPTER_ID
    reason: str = FORMAL_CHECK_UNAVAILABLE_REASON

    def check(self, request_bytes: bytes) -> Mapping[str, Any]:
        return {
            "outcome": "missing_tool",
            "reason": self.reason,
            "request_bytes_hash": _raw_hash(request_bytes),
            "epistemic_warrant_created": False,
        }


def _raw_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def safe_finding_projection(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Project a formal-check finding down to machine-readable fields.

    Policy-rejection codes and fields are retained; their free-text ``detail``
    strings and any wrapper or execution diagnostics are not, so a recorded
    rejection cannot teach validator evasion (ADR-0040).
    """

    projection: dict[str, Any] = {
        key: finding[key] for key in _SAFE_FINDING_FIELDS if key in finding
    }
    rejections = finding.get("policy_rejections")
    if isinstance(rejections, (list, tuple)):
        projection["policy_rejections"] = [
            {"code": item.get("code"), "field": item.get("field")}
            for item in rejections if isinstance(item, Mapping)
        ]
    projection["diagnostics_isolated"] = True
    projection["epistemic_warrant_created"] = False
    return projection


class _RouteRefusal(ValueError):
    """Internal: one route refused this candidate for a named reason."""

    def __init__(self, outcome: str, refusal_code: str, detail: dict[str, Any]) -> None:
        super().__init__(refusal_code)
        self.outcome = outcome
        self.refusal_code = refusal_code
        self.detail = detail


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignVerifierRouter:
    """`VerifierPort` dispatching one candidate to one admitted verifier.

    Context is reconstructed from records alone: the frozen experiment target
    bytes admit the graph route, the Phase 5 fixture schemas admit their exact
    routes, and the injected formal-check port owns the sealed boundary.
    """

    graph_target: ExperimentTarget | None
    graph_target_reason: str | None = None
    formal_checker: FormalCheckerPort = field(default_factory=UnavailableFormalChecker)

    def configuration_record(self) -> dict[str, Any]:
        return {
            "adapter": ROUTER_ADAPTER_ID,
            "version": ROUTER_ADAPTER_VERSION,
            "routes": {
                GRAPH_CANDIDATE_SCHEMA: ROUTE_EXACT_GRAPH,
                DIAGONAL_FIXTURE_SCHEMA: ROUTE_PHASE5_DIAGONAL,
                NONCOMMUTING_FIXTURE_VERSION: ROUTE_PHASE5_NONCOMMUTING,
                FORMAL_CHECK_ENVELOPE_SCHEMA: ROUTE_FORMAL_CHECK,
            },
            "graph_target_hash": (
                None if self.graph_target is None else self.graph_target.target_hash
            ),
            "graph_target_reason": self.graph_target_reason,
            "formal_check_adapter": self.formal_checker.adapter_id,
            "receives_planner_narrative": False,
            "receives_provider_credentials": False,
            "receives_source_corpus": False,
        }

    def __call__(self, request: VerificationRequest) -> ExperimentResult:
        candidate_hash, candidate = request.candidate_artifact
        route = ROUTE_UNSUPPORTED
        try:
            if not isinstance(request.determinism_unverified, bool):
                raise _RouteRefusal(
                    "refused", "determinism_status_malformed", {},
                )
            if _raw_hash(candidate) != candidate_hash:
                raise _RouteRefusal(
                    "refused", "candidate_bytes_do_not_match_their_hash", {},
                )
            if not candidate or len(candidate) > MAX_ROUTED_CANDIDATE_BYTES:
                raise _RouteRefusal("refused", "candidate_byte_bound", {})
            value = self._decode(candidate)
            route, handler = self._dispatch(value)
            status, outcome, refusal, detail = handler(value, candidate)
        except _RouteRefusal as refusal_error:
            status = RecordStatus.FAILED
            outcome = refusal_error.outcome
            refusal = refusal_error.refusal_code
            detail = refusal_error.detail
        return self._result(
            request, route=route, status=status, outcome=outcome,
            refusal_code=refusal, detail=detail,
            candidate_hash=candidate_hash,
        )

    # -- dispatch ---------------------------------------------------------- #

    @staticmethod
    def _decode(candidate: bytes) -> dict[str, Any]:
        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            seen: dict[str, Any] = {}
            for key, item in items:
                if key in seen:
                    raise ValueError("duplicate_json_key")
                seen[key] = item
            return seen

        try:
            value = json.loads(candidate.decode("utf-8", "strict"), object_pairs_hook=pairs)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise _RouteRefusal(
                UNSUPPORTED_OUTCOME, "candidate_is_not_a_json_object",
                {"reason": str(error)[:200]},
            ) from error
        if not isinstance(value, dict):
            raise _RouteRefusal(
                UNSUPPORTED_OUTCOME, "candidate_is_not_a_json_object", {},
            )
        return value

    def _dispatch(self, value: Mapping[str, Any]) -> tuple[str, Any]:
        declared = value.get("schema_version")
        table = {
            GRAPH_CANDIDATE_SCHEMA: (ROUTE_EXACT_GRAPH, self._exact_graph),
            DIAGONAL_FIXTURE_SCHEMA: (ROUTE_PHASE5_DIAGONAL, self._diagonal),
            NONCOMMUTING_FIXTURE_VERSION: (
                ROUTE_PHASE5_NONCOMMUTING, self._noncommuting,
            ),
            FORMAL_CHECK_ENVELOPE_SCHEMA: (ROUTE_FORMAL_CHECK, self._formal_check),
        }
        if not isinstance(declared, str) or declared not in table:
            raise _RouteRefusal(
                UNSUPPORTED_OUTCOME, UNSUPPORTED_REASON,
                {"declared_schema_version": str(declared)[:200]},
            )
        return table[declared]

    # -- routes ------------------------------------------------------------ #

    def _exact_graph(
        self, _value: Mapping[str, Any], raw: bytes,
    ) -> tuple[RecordStatus, str, str | None, dict[str, Any]]:
        if self.graph_target is None:
            raise _RouteRefusal(
                "refused", "graph_experiment_target_unavailable",
                {"reason": self.graph_target_reason},
            )
        # The verifier receives the EXACT selected bytes, so its verdict binds
        # the ledger's candidate hash rather than a router re-serialization.
        verdict = verify_candidate(self.graph_target, raw)
        satisfied = verdict.verdict == "target_satisfied"
        return (
            RecordStatus.COMPLETED if satisfied else RecordStatus.FAILED,
            verdict.verdict,
            verdict.refusal_code,
            {
                "experiment_target_hash": self.graph_target.target_hash,
                "verdict": verdict.to_record(),
            },
        )

    @staticmethod
    def _diagonal(
        value: Mapping[str, Any], _raw: bytes,
    ) -> tuple[RecordStatus, str, str | None, dict[str, Any]]:
        if set(value) != {"schema_version", "benchmark_id", "cases"} or (
            value["benchmark_id"] != "QD-FS-01"
        ):
            raise _RouteRefusal(
                "candidate_refused", "diagonal_fixture_fields_differ", {},
            )
        cases_value = value["cases"]
        if not isinstance(cases_value, list) or not cases_value:
            raise _RouteRefusal(
                "candidate_refused", "diagonal_fixture_has_no_cases", {},
            )
        try:
            cases = [DiagonalCase.from_value(item) for item in cases_value]
            results = [run_case(case) for case in cases]
        except (QuantumInputError, AssertionError, TypeError) as error:
            raise _RouteRefusal(
                "candidate_refused", "diagonal_exact_recomputation_failed",
                {"reason": str(error)[:500]},
            ) from error
        return (
            RecordStatus.COMPLETED,
            "exact_recomputation_completed",
            None,
            {
                # A completed diagonal route is a checked exact recomputation,
                # not a satisfaction verdict: this route defines no target.
                "semantics": "exact_recomputation_only_no_target_satisfaction",
                "case_results": [
                    {
                        "case_id": item["case_id"],
                        "final_objective": item["final_objective"],
                        "fixed_point": item["fixed_point"],
                        "independent_dual_optimum": item["independent_dual_optimum"],
                        "nonoptimal_fixed_point": item["nonoptimal_fixed_point"],
                        "primal_dual_gap": item["primal_dual_gap"],
                        "result_hash": item["result_hash"],
                        "ykl_dual_domination_certificate": item[
                            "ykl_dual_domination_certificate"
                        ],
                    }
                    for item in results
                ],
            },
        )

    @staticmethod
    def _noncommuting(
        value: Mapping[str, Any], _raw: bytes,
    ) -> tuple[RecordStatus, str, str | None, dict[str, Any]]:
        try:
            report = verify_fixture(dict(value))
        except ValueError as error:
            raise _RouteRefusal(
                "candidate_refused", "noncommuting_fixture_refused",
                {"reason": str(error)[:500]},
            ) from error
        # The Phase 5 parser REQUIRES every fixture to retain its measured
        # field-boundary case, so an outside-field case is the recorded domain
        # limit, not a rejected candidate. What rejects the candidate is a
        # withheld certificate or a gap the exact check could not close.
        unverified = sorted(
            set(report["unresolved_case_ids"])
            | set(report["gap_not_closed_case_ids"])
        )
        verified = bool(report["verified_certificate_case_ids"]) and not unverified
        return (
            RecordStatus.COMPLETED if verified else RecordStatus.FAILED,
            "certificates_verified" if verified else "certificates_not_all_verified",
            None if verified else "unverified_noncommuting_case_present",
            {
                "case_count": report["case_count"],
                "coverage_status_counts": dict(report["coverage_status_counts"]),
                "field_boundary_case_ids": list(report["field_boundary_case_ids"]),
                "report_hash": report["content_hash"],
                "unverified_case_ids": unverified,
                "verified_certificate_case_ids": list(
                    report["verified_certificate_case_ids"]
                ),
            },
        )

    def _formal_check(
        self, value: Mapping[str, Any], _raw: bytes,
    ) -> tuple[RecordStatus, str, str | None, dict[str, Any]]:
        if set(value) != {"schema_version", "request"} or not isinstance(
            value["request"], dict
        ):
            raise _RouteRefusal(
                "candidate_refused", "formal_check_envelope_fields_differ", {},
            )
        request_bytes = canonical_bytes(value["request"])
        finding = self.formal_checker.check(request_bytes)
        projection = safe_finding_projection(finding)
        verified = projection.get("outcome") in FORMAL_CHECK_VERIFIED_OUTCOMES
        return (
            RecordStatus.COMPLETED if verified else RecordStatus.FAILED,
            "formal_check_verified" if verified else "formal_check_not_verified",
            None if verified else str(projection.get("outcome")),
            {
                "checker_adapter_id": self.formal_checker.adapter_id,
                "finding": projection,
                "request_bytes_hash": _raw_hash(request_bytes),
            },
        )

    # -- result envelope ---------------------------------------------------- #

    def _result(
        self, request: VerificationRequest, *, route: str, status: RecordStatus,
        outcome: str, refusal_code: str | None, detail: dict[str, Any],
        candidate_hash: str,
    ) -> ExperimentResult:
        payload: dict[str, Any] = {
            "schema_version": ROUTER_RESULT_SCHEMA,
            "adapter_id": ROUTER_ADAPTER_ID,
            "route": route,
            "outcome": outcome,
            "refusal_code": refusal_code,
            "campaign_target_hash": request.target_hash,
            "candidate_hash": candidate_hash,
            "tool_artifact_hashes": [item for item, _ in request.tool_artifacts],
            "detail": detail,
            "trust": dict(_ROUTER_TRUST),
            "epistemic_warrant_created": False,
        }
        if request.determinism_unverified:
            payload["input_determinism_unverified"] = True
        payload["content_hash"] = canonical_hash(payload)
        result = canonical_bytes(payload)
        return ExperimentResult(
            adapter_id=ROUTER_ADAPTER_ID,
            adapter_version=ROUTER_ADAPTER_VERSION,
            adapter_configuration_hash=canonical_hash(self.configuration_record()),
            environment_hash=canonical_hash({
                "arithmetic": "int_and_fraction_only",
                "location": "host_process",
                "network": "none",
            }),
            status=status,
            result=result,
            stdout=b"",
            stderr=b"",
            # The router reads no clock and asserts no resource observation:
            # its measurement source is `unavailable` and every observation is
            # absent, which the ledger's own record validation enforces.
            measurement_source=UsageSource.UNAVAILABLE,
            cpu_milliseconds=None,
            wall_milliseconds=None,
            peak_memory_bytes=None,
            output_bytes=None,
            determinism_unverified=request.determinism_unverified,
        )


__all__ = [
    "CampaignVerifierRouter", "DIAGONAL_FIXTURE_SCHEMA",
    "FORMAL_CHECK_ENVELOPE_SCHEMA", "FORMAL_CHECK_UNAVAILABLE_ADAPTER_ID",
    "FORMAL_CHECK_UNAVAILABLE_REASON", "FORMAL_CHECK_VERIFIED_OUTCOMES",
    "FormalCheckerPort", "MAX_ROUTED_CANDIDATE_BYTES", "ROUTER_ADAPTER_ID",
    "ROUTER_ADAPTER_VERSION", "ROUTER_RESULT_SCHEMA", "ROUTE_EXACT_GRAPH",
    "ROUTE_FORMAL_CHECK", "ROUTE_PHASE5_DIAGONAL", "ROUTE_PHASE5_NONCOMMUTING",
    "ROUTE_UNSUPPORTED", "TARGET_CLASS_ROUTES", "UNSUPPORTED_OUTCOME",
    "UNSUPPORTED_REASON", "UnavailableFormalChecker",
    "route_for_target_class", "safe_finding_projection",
]
