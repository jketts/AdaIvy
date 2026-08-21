"""The Phase 5 noncommuting-SDP engine-comparison experiment.

This is the experiment specified at
``spikes/phase5_noncommuting_sdp/DEPENDENCY_LICENSE_COMPARISON.md``: run the
same frozen real and complex fixtures through at least two independent SDP
engines, retain raw solver status/residuals and exact problem encodings, and
attempt rational/algebraic or interval reconstruction.

The trust rule is enforced structurally, in one place:

    A case's disposition is derived ONLY from an exact check. An engine's
    ``optimal`` status contributes nothing to it. Two engines agreeing
    contributes nothing to it.

``certified_by`` lists the exact checks that succeeded -- the file-based
rational baseline (``validator.validate_fixture``) and/or the exact algebraic
reconstruction. If neither succeeded the case is ``unresolved``, whatever the
engines said.

Hashing follows the Phase 3B precedent. Any object carrying
``"hash_class": "operational_only"`` -- timings, iteration counts, residuals,
returned floating-point matrices, and every value derived from them -- is
replaced by a marker in the semantic preimage, so scheduling variance, a
different CPU, or a different engine build cannot change the semantic identity
of the experiment. The operational hash covers the complete report including
those observations.

Nothing here integrates with Phase 5, touches its sealed records, enables search
tiers 2--4, or creates an ``EpistemicWarrant``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

from . import comparison_algebraic as alg
from .encoding import (
    ExactProgram,
    encode_case,
    load_fixture,
)
from .engines import (
    AUTHORIZED_ENGINE_IDS,
    AUTHORIZED_MODULES,
    EXCLUDED_MODULES,
    PERMITTED_LICENSE_EXPRESSIONS,
    default_engines,
)
from .ports import SDPEngine
from .reconstruction import (
    ABSENT_HYPOTHESIS,
    NumericHypothesis,
    attempt_reconstruction,
    float_point_exact_audit,
    to_algebraic,
)
from .comparison_validator import CertificateInputError, canonical_bytes, validate_fixture

COMPARISON_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-comparison.v1"

REQUIRED_INDEPENDENT_ENGINES = 2
"""The spec clause: "at least two independent SDP engines"."""

OPERATIONAL_MARKER = "operational_only"
SEMANTIC_PLACEHOLDER = "excluded_from_semantic_hash"

SPEC_REFERENCE = (
    "spikes/phase5_noncommuting_sdp/DEPENDENCY_LICENSE_COMPARISON.md#adoption-result"
)

AUTHORIZATION = {
    "adr": "ADR-0045",
    "authorised_by": "repository owner, explicit implementation request",
    "scope": "spike-local comparison experiment only",
    "license_restriction": "permissive licences only",
    "permitted_license_expressions": sorted(PERMITTED_LICENSE_EXPRESSIONS),
    "permitted_modules": {
        name: {
            "license_expression": entry.license_expression,
            "license_url": entry.license_url,
            "role": entry.role,
        }
        for name, entry in sorted(AUTHORIZED_MODULES.items())
    },
    "excluded_modules": dict(sorted(EXCLUDED_MODULES.items())),
    "excluded_modules_are_out_of_scope": True,
    "phase5_integration_authorised": False,
    "search_tiers_2_to_4_authorised": False,
    "warrant_creation_authorised": False,
}


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def semantic_preimage(value: Any) -> Any:
    """Strip every operational observation, recursively and by marker."""

    if isinstance(value, dict):
        if value.get("hash_class") == OPERATIONAL_MARKER:
            return SEMANTIC_PLACEHOLDER
        return {
            key: semantic_preimage(item)
            for key, item in value.items()
            if key not in {"content_hash", "operational_hash"}
        }
    if isinstance(value, list):
        return [semantic_preimage(item) for item in value]
    return value


def semantic_hash(report: dict[str, Any]) -> str:
    return _hash(semantic_preimage(report))


def operational_hash(report: dict[str, Any]) -> str:
    body = {key: item for key, item in report.items() if key != "operational_hash"}
    return _hash(body)


def _operational(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "hash_class": OPERATIONAL_MARKER}


def _declared_tolerance(settings: Sequence[tuple[str, str]]) -> float | None:
    for key in ("tol_gap_abs", "eps_abs"):
        for name, value in settings:
            if name == key:
                try:
                    return float(value)
                except ValueError:
                    return None
    return None


def _baseline(case: dict[str, Any]) -> dict[str, Any]:
    """The file-based exact rational baseline, on the same fixture."""

    try:
        result = validate_fixture(copy.deepcopy(case))
    except CertificateInputError as error:
        return {
            "source": "spikes/phase5_noncommuting_sdp/validator.py",
            "status": "rejected",
            "reason": str(error),
            "exact_optimum_certificate": False,
        }
    return {
        "source": "spikes/phase5_noncommuting_sdp/validator.py",
        "status": "checked",
        "schema_version": result["schema_version"],
        "noncommuting": result["noncommuting"],
        "primal_value": result["primal_value"],
        "dual_value": result["dual_value"],
        "primal_dual_gap": result["primal_dual_gap"],
        "complementarity_exact": result["complementarity_exact"],
        "exact_optimum_certificate": result["exact_optimum_certificate"],
        "disposition": result["disposition"],
        "content_hash_of_baseline_result": "sha256:" + result["content_hash"],
    }


def _cross_check(baseline: dict[str, Any], optimum: Any) -> dict[str, Any]:
    """Compare the exact reconstruction against the baseline rational candidate."""

    record: dict[str, Any] = {
        "check": "baseline_rational_candidate_versus_exact_optimum",
        "compared_with": "spikes/phase5_noncommuting_sdp/validator.py",
    }
    if optimum is None or baseline.get("status") != "checked":
        record.update(status="not_attempted", reason_code="missing_exact_optimum_or_baseline")
        return record
    candidate = alg.Surd.rational(Fraction(baseline["primal_value"]))
    sign = alg.compare(candidate, optimum)
    record.update(
        status="checked",
        baseline_primal_value=baseline["primal_value"],
        exact_optimum=optimum.public(),
        comparison=("equal" if sign == 0 else "baseline_below_optimum" if sign < 0 else "baseline_above_optimum"),
        baseline_candidate_proved_optimal=sign == 0,
        baseline_candidate_proved_suboptimal=sign < 0,
        exact_shortfall=(optimum - candidate).public(),
        detail=(
            "an exact comparison in the quadratic field, not a numerical one; "
            "a strictly positive shortfall proves the rational candidate is not optimal."
        ),
    )
    return record


def _engine_record(engine: SDPEngine, program: ExactProgram) -> tuple[dict[str, Any], Any]:
    descriptor = engine.descriptor
    authorised = descriptor.engine_id in AUTHORIZED_ENGINE_IDS
    run = engine.solve(program)
    body: dict[str, Any] = {
        "engine": descriptor.public(),
        "authorised_registry_entry": authorised,
        "probe": run.probe.public(),
        "executed": run.executed,
    }
    if run.missing_tool is not None:
        body["result"] = run.missing_tool.public()
        body["counts_towards_independent_engines"] = False
        return (body, None)
    solution = run.solution
    body["result"] = solution.semantic_public()
    body["operational"] = _operational(solution.operational.public())
    body["counts_towards_independent_engines"] = authorised
    return (body, solution)


def _agreement(solutions: Sequence[Any]) -> dict[str, Any]:
    values = [
        (item.engine_id, item.operational.primal_objective)
        for item in solutions
        if item.operational.primal_objective is not None
    ]
    pairs = []
    for index, (left_id, left) in enumerate(values):
        for right_id, right in values[index + 1 :]:
            pairs.append(
                {"engines": [left_id, right_id], "absolute_difference": abs(left - right)}
            )
    return _operational(
        {
            "check": "engine_pairwise_agreement",
            "reported_primal_objectives": [
                {"engine_id": name, "value": value} for name, value in values
            ],
            "pairwise_absolute_differences": pairs,
            "is_evidence_of_correctness": False,
            "contributes_to_disposition": False,
            "note": (
                "two engines agreeing is NOT evidence of correctness: they can share a "
                "formulation error, a conditioning failure, or the same wrong optimum. "
                "Only the exact check decides anything here."
            ),
        }
    )


def run_case(
    case: dict[str, Any],
    engines: Sequence[SDPEngine],
) -> dict[str, Any]:
    """Run one fixture case through every engine plus the exact checks."""

    program = encode_case(case)
    baseline = _baseline(case)
    encoding = program.public()

    engine_records: list[dict[str, Any]] = []
    solutions: list[Any] = []
    for engine in engines:
        record, solution = _engine_record(engine, program)
        engine_records.append(record)
        if solution is not None and record["counts_towards_independent_engines"]:
            solutions.append(solution)

    hypothesis = ABSENT_HYPOTHESIS
    for solution in solutions:
        value = solution.operational.primal_objective
        if value is not None:
            hypothesis = NumericHypothesis(
                provenance="engine_observed",
                engine_id=solution.engine_id,
                value=value,
                declared_tolerance=_declared_tolerance(solution.settings),
            )
            break

    reconstruction = attempt_reconstruction(case, program, hypothesis)
    states = tuple(to_algebraic(item) for item in _states(case))
    audits = [
        _operational(
            {
                **float_point_exact_audit(
                    program,
                    states,
                    solution.operational.primal_blocks,
                    solution.operational.dual_block,
                    source=f"engine:{solution.engine_id}",
                ),
                "engine_id": solution.engine_id,
            }
        )
        for solution in solutions
    ]

    certified_by: list[str] = []
    if baseline.get("exact_optimum_certificate"):
        certified_by.append("baseline_rational_candidate")
    if reconstruction.certified:
        certified_by.append("exact_algebraic_reconstruction")
    executed = [item for item in engine_records if item["counts_towards_independent_engines"]]

    return {
        "case_id": program.case_id,
        "field": encoding["field"],
        "noncommuting": baseline.get("noncommuting"),
        "exact_encoding": encoding,
        "baseline_rational_check": baseline,
        "engine_records": engine_records,
        "independent_engines_executed": len(executed),
        "independent_engines_required": REQUIRED_INDEPENDENT_ENGINES,
        "two_engine_clause_satisfied": len(executed) >= REQUIRED_INDEPENDENT_ENGINES,
        "engine_agreement": _agreement(solutions),
        "engine_point_exact_audits": audits,
        "reconstruction": reconstruction.record,
        "baseline_cross_check": _cross_check(baseline, reconstruction.optimum),
        "certified_by": certified_by,
        "exact_optimum_certified": bool(certified_by),
        "disposition": (
            "exact_optimum_certified_by_exact_check"
            if certified_by
            else "unresolved_no_exact_certificate"
        ),
        "engine_status_contributed_to_disposition": False,
        "warrant_created": False,
    }


def _states(case: dict[str, Any]) -> Sequence[Any]:
    from .encoding import parse_matrix

    raw = case.get("weighted_states")
    if not isinstance(raw, list):
        raise CertificateInputError("weighted_states must be an array")
    return [
        parse_matrix(item, label=f"weighted state {index}") for index, item in enumerate(raw)
    ]


def run_comparison(
    fixture_path: Path,
    *,
    engines: Sequence[SDPEngine] | None = None,
) -> dict[str, Any]:
    """Run the whole experiment over the frozen real and complex fixtures."""

    document, fixture_content_hash = load_fixture(fixture_path)
    active = tuple(engines) if engines is not None else default_engines()
    cases = [run_case(case, active) for case in document["cases"]]

    executed_counts = [item["independent_engines_executed"] for item in cases]
    missing: list[dict[str, Any]] = []
    for case in cases:
        for record in case["engine_records"]:
            if record["result"]["outcome"] == "missing_tool":
                missing.append(
                    {
                        "case_id": case["case_id"],
                        "engine_id": record["result"]["engine_id"],
                        "reason_code": record["result"]["reason_code"],
                    }
                )
    minimum_executed = min(executed_counts) if executed_counts else 0
    executed_any = any(count > 0 for count in executed_counts)
    two_engine_clause = bool(cases) and minimum_executed >= REQUIRED_INDEPENDENT_ENGINES
    all_certified = bool(cases) and all(item["exact_optimum_certified"] for item in cases)

    body: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "experiment_id": "phase5-noncommuting-sdp-engine-comparison",
        "spec_reference": SPEC_REFERENCE,
        "authorization": AUTHORIZATION,
        "fixture_path": str(fixture_path.as_posix()),
        "fixture_schema_version": document.get("schema_version"),
        "fixture_content_hash": fixture_content_hash,
        "cases_evaluated": len(cases),
        "engines_declared": [engine.descriptor.public() for engine in active],
        "independent_engines_required": REQUIRED_INDEPENDENT_ENGINES,
        "minimum_independent_engines_executed": minimum_executed,
        "missing_tool_records": missing,
        "cases": cases,
        "spec_clauses": {
            "two_independent_engines_run": two_engine_clause,
            "exact_encodings_retained": True,
            # Retention cannot be claimed as satisfied when nothing was produced
            # to retain; that would read as a pass for an unexercised clause.
            "raw_solver_status_retained": (
                "satisfied" if executed_any else "not_exercised_no_engine_executed"
            ),
            "raw_residuals_iterations_timings_retained": (
                "satisfied" if executed_any else "not_exercised_no_engine_executed"
            ),
            "reconstruction_attempted": True,
            "failed_attempts_retained": True,
        },
        "experiment_status": (
            "comparison_complete"
            if two_engine_clause
            else "incomplete_engines_absent_or_refused"
        ),
        "all_cases_exactly_certified": all_certified,
        "guardrails": {
            "warrant_created": False,
            "phase5_integrated": False,
            "phase5_sealed_records_touched": False,
            "search_tiers_enabled": False,
            "network_attempted": False,
            "model_calls": 0,
            "external_cost_usd": 0,
            "solver_status_may_create_warrant": False,
            "engine_agreement_is_evidence_of_correctness": False,
            "tolerance_sized_gap_accepted_as_exact": False,
        },
        "semantic_hash_policy": {
            "rule": (
                "any object carrying hash_class=operational_only is replaced by "
                f"'{SEMANTIC_PLACEHOLDER}' in the semantic preimage"
            ),
            "excluded": [
                "elapsed/setup/solve milliseconds",
                "iteration counts",
                "solver residuals and objective floats",
                "returned floating-point matrices",
                "every check derived from those floats",
            ],
            "precedent": "Phase 3B semantic/operational hash split",
        },
    }
    body["content_hash"] = semantic_hash(body)
    body["operational_hash"] = operational_hash(body)
    return body


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    """Recompute both hashes. Fails closed on a missing or altered field."""

    if not isinstance(report, dict):
        raise CertificateInputError("report must be an object")
    if report.get("schema_version") != COMPARISON_SCHEMA_VERSION:
        raise CertificateInputError(
            f"unsupported report schema version {report.get('schema_version')!r}"
        )
    for key in ("content_hash", "operational_hash"):
        if not isinstance(report.get(key), str):
            raise CertificateInputError(f"report is missing {key}")
    semantic_ok = report["content_hash"] == semantic_hash(report)
    operational_ok = report["operational_hash"] == operational_hash(report)
    return {
        "verified": semantic_ok and operational_ok,
        "semantic_hash_verified": semantic_ok,
        "operational_hash_verified": operational_ok,
        "content_hash": report["content_hash"],
        "operational_hash": report["operational_hash"],
    }


@dataclass(frozen=True, slots=True)
class Summary:
    """A projection for humans; the canonical artifact is the full report."""

    report: dict[str, Any]

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": self.report["schema_version"],
            "content_hash": self.report["content_hash"],
            "operational_hash": self.report["operational_hash"],
            "fixture_content_hash": self.report["fixture_content_hash"],
            "experiment_status": self.report["experiment_status"],
            "independent_engines_required": self.report["independent_engines_required"],
            "minimum_independent_engines_executed": self.report[
                "minimum_independent_engines_executed"
            ],
            "missing_tool_records": self.report["missing_tool_records"],
            "all_cases_exactly_certified": self.report["all_cases_exactly_certified"],
            "spec_clauses": self.report["spec_clauses"],
            "guardrails": self.report["guardrails"],
            "cases": [
                {
                    "case_id": case["case_id"],
                    "field": case["field"],
                    "noncommuting": case["noncommuting"],
                    "baseline_primal_dual_gap": case["baseline_rational_check"].get(
                        "primal_dual_gap"
                    ),
                    "exact_optimum": case["reconstruction"]["exact_optimum"],
                    "optimum_is_rational": case["reconstruction"]["optimum_is_rational"],
                    "certified_by": case["certified_by"],
                    "disposition": case["disposition"],
                    "failed_reconstruction_attempts": case["reconstruction"][
                        "failed_attempts"
                    ],
                    "engines": [
                        {
                            "engine_id": record["engine"]["engine_id"],
                            "outcome": record["result"]["outcome"],
                            "engine_status": record["result"].get("engine_status"),
                            "reason_code": record["result"].get("reason_code"),
                        }
                        for record in case["engine_records"]
                    ],
                }
                for case in self.report["cases"]
            ],
        }


def canonical_report_bytes(report: dict[str, Any]) -> bytes:
    return canonical_bytes(report)


def read_report(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
    """Read an emitted report, failing closed on size, encoding, or duplicates."""

    from .encoding import reject_duplicate_keys

    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise CertificateInputError(f"{path}: {len(raw)} bytes exceeds the {max_bytes}-byte bound")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificateInputError(f"{path} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CertificateInputError(f"{path} must contain an object")
    return value


__all__ = [
    "AUTHORIZATION",
    "COMPARISON_SCHEMA_VERSION",
    "OPERATIONAL_MARKER",
    "REQUIRED_INDEPENDENT_ENGINES",
    "SEMANTIC_PLACEHOLDER",
    "SPEC_REFERENCE",
    "Summary",
    "canonical_report_bytes",
    "operational_hash",
    "read_report",
    "run_case",
    "run_comparison",
    "semantic_hash",
    "semantic_preimage",
    "verify_report",
]
