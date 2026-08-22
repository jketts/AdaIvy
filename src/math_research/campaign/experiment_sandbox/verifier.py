"""The exact in-repository verifier that gives a sandbox candidate its meaning.

This module is the load-bearing half of ADR-0066 and it is deliberately small
and deliberately blind.

* It runs **in the host process**, never in the container.  It imports no
  process-spawning, network, ``ctypes`` or ``os`` module, so it cannot be
  induced to shell out and it cannot be reached from inside the sandbox: the
  container has no host mount, no network, and a read-only root, so no path
  exists from the program to this file.
* It reads **the candidate alone**, plus the frozen target.  It never receives
  the program source, the program's stdout, the planner's rationale, or the
  sandbox's own report of what happened.  Its only inputs are two byte strings.
* It is **exact**.  ``int`` and ``fractions.Fraction`` only.  A candidate
  containing a JSON float is a typed refusal, not a rounding.
* It **grants nothing**.  No warrant, no premise, no applicability, no graph
  admission, no novelty or significance.  A satisfied target is a verified
  computation, not a theorem.

The argument this implements: a candidate is self-verifying against the frozen
target.  The verifier rebuilds the graph from the candidate's own edge list and
recomputes every condition, so a program that lies about its output is refuted
by arithmetic rather than caught by inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Any

from ...exact_graph.graph import ExactGraphError, Graph, build_graph, is_connected, is_triangle_free
from ...exact_graph.invariants import EVEN_READINGS, inverse_even
from ...exact_graph.spectrum import distinct_eigenvalue_count
from ..records import canonical_hash

TARGET_SCHEMA = "adaivy.campaign-experiment-target.v1"
CANDIDATE_SCHEMA = "adaivy.campaign-experiment-graph-candidate.v1"
VERDICT_SCHEMA = "adaivy.campaign-experiment-verdict.v1"
TARGET_ENGINE = "exact_graph_distance_and_invariant_space_v2"

MAX_TARGET_BYTES = 16_384
MAX_CANDIDATE_BYTES = 262_144
MAX_CANDIDATE_ORDER = 64

VERDICTS = ("target_satisfied", "target_not_satisfied", "candidate_refused")

# A program may not report its own resource consumption.  Any of these keys
# anywhere in a candidate is a refusal, not a recorded measurement.
FORBIDDEN_MEASUREMENT_KEYS = frozenset({
    "cpu_milliseconds", "cpu_seconds", "cpu_usec", "elapsed_ms", "elapsed_seconds",
    "measurement_source", "memory_bytes", "output_bytes", "peak_memory_bytes",
    "process_count", "rusage", "wall_milliseconds", "wall_seconds",
})
# A program may not assert an epistemic status for its own output either.
FORBIDDEN_TRUST_KEYS = frozenset({
    "applicability", "epistemic_warrant_created", "graph_admission", "novelty_status",
    "premise", "proved", "significance_status", "verified", "warrant",
})

_TARGET_FIELDS = frozenset({
    "schema_version", "target_id", "engine", "statement", "order", "edge_count",
    "require_connected", "require_triangle_free", "distinct_distance_eigenvalues",
    "inverse_even_reading", "inverse_even_numerator", "inverse_even_denominator",
})
_CANDIDATE_FIELDS = frozenset({
    "schema_version", "target_id", "asserted_satisfies_target",
    "asserted_construction", "order", "edges",
})
_TRUST_BLOCK = {
    "candidate_class": "untrusted_sandbox_candidate",
    "epistemic_warrant_created": False,
    "graph_admission": False,
    "novelty_status": "not_assessed",
    "significance_status": "not_assessed",
    "source_applicability_asserted": False,
}


class VerifierError(ValueError):
    """A target or candidate cannot be read exactly as given."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentTarget:
    """The frozen target a candidate is checked against, and nothing else."""

    schema_version: str
    target_id: str
    engine: str
    statement: str
    order: int
    edge_count: int
    require_connected: bool
    require_triangle_free: bool
    distinct_distance_eigenvalues: int
    inverse_even_reading: str
    inverse_even_numerator: int
    inverse_even_denominator: int
    target_hash: str

    @property
    def inverse_even(self) -> Fraction:
        return Fraction(self.inverse_even_numerator, self.inverse_even_denominator)

    def to_record(self) -> dict[str, Any]:
        return {
            "distinct_distance_eigenvalues": self.distinct_distance_eigenvalues,
            "edge_count": self.edge_count,
            "engine": self.engine,
            "inverse_even_denominator": self.inverse_even_denominator,
            "inverse_even_numerator": self.inverse_even_numerator,
            "inverse_even_reading": self.inverse_even_reading,
            "order": self.order,
            "require_connected": self.require_connected,
            "require_triangle_free": self.require_triangle_free,
            "schema_version": self.schema_version,
            "statement": self.statement,
            "target_hash": self.target_hash,
            "target_id": self.target_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateVerdict:
    """One exact verdict over one candidate.  Creates no trust of any kind."""

    schema_version: str
    target_hash: str
    target_id: str
    candidate_hash: str
    verdict: str
    refusal_code: str | None
    claim_asserted: bool
    claim_refuted: bool
    conditions: tuple[dict[str, Any], ...]

    def to_record(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "candidate_hash": self.candidate_hash,
            "claim_asserted": self.claim_asserted,
            "claim_refuted": self.claim_refuted,
            "conditions": [dict(item) for item in self.conditions],
            "refusal_code": self.refusal_code,
            "schema_version": self.schema_version,
            "target_hash": self.target_hash,
            "target_id": self.target_id,
            "trust": dict(_TRUST_BLOCK),
            "verdict": self.verdict,
        }
        value["content_hash"] = canonical_hash(value)
        return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VerifierError("duplicate_json_key")
        value[key] = item
    return value


def _refuse_float(_text: str) -> Any:
    raise VerifierError("float_on_the_trust_path")


def _refuse_constant(_text: str) -> Any:
    raise VerifierError("non_finite_json_constant")


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerifierError(f"{field}_not_integer")
    if not minimum <= value <= maximum:
        raise VerifierError(f"{field}_out_of_bounds")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise VerifierError(f"{field}_not_boolean")
    return value


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise VerifierError(f"{field}_not_bounded_text")
    return value


def _forbidden_keys(value: Any) -> str | None:
    """Walk a decoded candidate for a measurement or trust assertion."""

    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            if lowered in FORBIDDEN_MEASUREMENT_KEYS:
                return "program_asserted_measurement"
            if lowered in FORBIDDEN_TRUST_KEYS:
                return "program_asserted_trust_status"
            found = _forbidden_keys(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _forbidden_keys(item)
            if found is not None:
                return found
    return None


def load_target(data: bytes) -> ExperimentTarget:
    """Load the frozen target from bytes.  No default, no clock, no network."""

    if not isinstance(data, bytes) or not data or len(data) > MAX_TARGET_BYTES:
        raise VerifierError("target_byte_bound")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_strict_object,
            parse_float=_refuse_float, parse_constant=_refuse_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerifierError("target_json_invalid") from error
    if not isinstance(value, dict) or frozenset(value) != _TARGET_FIELDS:
        raise VerifierError("target_fields_differ")
    if value["schema_version"] != TARGET_SCHEMA:
        raise VerifierError("target_schema_differs")
    if value["engine"] != TARGET_ENGINE:
        raise VerifierError("target_engine_differs")
    reading = value["inverse_even_reading"]
    if reading not in EVEN_READINGS:
        raise VerifierError("target_even_reading_unknown")
    order = _integer(value["order"], "target_order", minimum=1, maximum=MAX_CANDIDATE_ORDER)
    return ExperimentTarget(
        schema_version=TARGET_SCHEMA,
        target_id=_text(value["target_id"], "target_id", 128),
        engine=TARGET_ENGINE,
        statement=_text(value["statement"], "target_statement", 2_000),
        order=order,
        edge_count=_integer(
            value["edge_count"], "target_edge_count", minimum=0,
            maximum=order * (order - 1) // 2,
        ),
        require_connected=_boolean(value["require_connected"], "require_connected"),
        require_triangle_free=_boolean(
            value["require_triangle_free"], "require_triangle_free",
        ),
        distinct_distance_eigenvalues=_integer(
            value["distinct_distance_eigenvalues"], "target_distinct_eigenvalues",
            minimum=1, maximum=order,
        ),
        inverse_even_reading=reading,
        inverse_even_numerator=_integer(
            value["inverse_even_numerator"], "inverse_even_numerator",
            minimum=1, maximum=10 ** 12,
        ),
        inverse_even_denominator=_integer(
            value["inverse_even_denominator"], "inverse_even_denominator",
            minimum=1, maximum=10 ** 12,
        ),
        target_hash="sha256:" + hashlib.sha256(data).hexdigest(),
    )


def _condition(name: str, expected: Any, observed: Any) -> dict[str, Any]:
    return {
        "condition": name,
        "expected": expected,
        "observed": observed,
        "satisfied": expected == observed,
    }


def _rebuild(order: int, edges: list[Any]) -> Graph:
    pairs: list[tuple[int, int]] = []
    for item in edges:
        if not isinstance(item, list) or len(item) != 2:
            raise VerifierError("candidate_edge_malformed")
        u = _integer(item[0], "candidate_edge_endpoint", minimum=0, maximum=order - 1)
        v = _integer(item[1], "candidate_edge_endpoint", minimum=0, maximum=order - 1)
        if u == v:
            raise VerifierError("candidate_edge_is_a_loop")
        pairs.append((min(u, v), max(u, v)))
    if len(set(pairs)) != len(pairs):
        raise VerifierError("candidate_edge_repeated")
    return build_graph("graph.campaign-experiment-candidate", order, pairs)


def _refusal(
    target: ExperimentTarget, candidate_hash: str, code: str, *, claim: bool = False,
) -> CandidateVerdict:
    return CandidateVerdict(
        schema_version=VERDICT_SCHEMA, target_hash=target.target_hash,
        target_id=target.target_id, candidate_hash=candidate_hash,
        verdict="candidate_refused", refusal_code=code, claim_asserted=claim,
        claim_refuted=claim, conditions=(),
    )


def verify_candidate(target: ExperimentTarget, candidate: bytes) -> CandidateVerdict:
    """Re-derive the candidate exactly; this is the meaning-establishing step.

    ``candidate`` is the untrusted bytes a sandboxed program emitted.  Nothing
    else about the run is consulted, and the program's own assertion is treated
    as one more field to be refuted, never as information.
    """

    if not isinstance(candidate, bytes):
        raise VerifierError("candidate_not_bytes")
    candidate_hash = "sha256:" + hashlib.sha256(candidate).hexdigest()
    if not candidate or len(candidate) > MAX_CANDIDATE_BYTES:
        return _refusal(target, candidate_hash, "candidate_byte_bound")
    try:
        value = json.loads(
            candidate.decode("utf-8", "strict"), object_pairs_hook=_strict_object,
            parse_float=_refuse_float, parse_constant=_refuse_constant,
        )
    except VerifierError as error:
        return _refusal(target, candidate_hash, str(error.args[0]))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _refusal(target, candidate_hash, "candidate_json_invalid")
    forbidden = _forbidden_keys(value)
    if forbidden is not None:
        return _refusal(target, candidate_hash, forbidden)
    if not isinstance(value, dict) or frozenset(value) != _CANDIDATE_FIELDS:
        return _refusal(target, candidate_hash, "candidate_fields_differ")
    if value["schema_version"] != CANDIDATE_SCHEMA:
        return _refusal(target, candidate_hash, "candidate_schema_differs")
    if value["target_id"] != target.target_id:
        return _refusal(target, candidate_hash, "candidate_target_differs")
    if not isinstance(value["asserted_satisfies_target"], bool):
        return _refusal(target, candidate_hash, "candidate_assertion_not_boolean")
    claim = value["asserted_satisfies_target"]
    try:
        _text(value["asserted_construction"], "asserted_construction", 256)
        order = _integer(
            value["order"], "candidate_order", minimum=1, maximum=MAX_CANDIDATE_ORDER,
        )
        edges = value["edges"]
        if not isinstance(edges, list) or len(edges) > order * (order - 1) // 2:
            raise VerifierError("candidate_edge_list_malformed")
        graph = _rebuild(order, edges)
    except VerifierError as error:
        return _refusal(target, candidate_hash, str(error.args[0]), claim=claim)
    except ExactGraphError as error:
        return _refusal(target, candidate_hash, f"graph_{error.args[0]}", claim=claim)

    conditions = [
        _condition("order", target.order, graph.order),
        _condition("edge_count", target.edge_count, graph.size()),
    ]
    if target.require_connected:
        conditions.append(_condition("connected", True, is_connected(graph)))
    if target.require_triangle_free:
        conditions.append(_condition("triangle_free", True, is_triangle_free(graph)))
    if all(item["satisfied"] for item in conditions):
        # Both remaining invariants need connectivity and the frozen order, so
        # they are only computed once the cheap structure conditions hold.
        try:
            conditions.append(_condition(
                "distinct_distance_eigenvalues",
                target.distinct_distance_eigenvalues,
                distinct_eigenvalue_count(graph),
            ))
            observed = inverse_even(graph, target.inverse_even_reading)
            conditions.append({
                "condition": "inverse_even",
                "expected": [target.inverse_even.numerator, target.inverse_even.denominator],
                "observed": [observed.numerator, observed.denominator],
                "satisfied": observed == target.inverse_even,
            })
        except ExactGraphError as error:
            return _refusal(target, candidate_hash, f"exact_{error.args[0]}", claim=claim)
    satisfied = all(item["satisfied"] for item in conditions)
    return CandidateVerdict(
        schema_version=VERDICT_SCHEMA, target_hash=target.target_hash,
        target_id=target.target_id, candidate_hash=candidate_hash,
        verdict="target_satisfied" if satisfied else "target_not_satisfied",
        refusal_code=None, claim_asserted=claim,
        claim_refuted=claim and not satisfied, conditions=tuple(conditions),
    )


def trust_block() -> dict[str, Any]:
    """The frozen "nothing is granted" block every verdict and envelope carries."""

    return dict(_TRUST_BLOCK)


__all__ = [
    "CANDIDATE_SCHEMA", "CandidateVerdict", "ExperimentTarget",
    "FORBIDDEN_MEASUREMENT_KEYS", "FORBIDDEN_TRUST_KEYS", "MAX_CANDIDATE_BYTES",
    "MAX_CANDIDATE_ORDER", "MAX_TARGET_BYTES", "TARGET_ENGINE", "TARGET_SCHEMA",
    "VERDICTS", "VERDICT_SCHEMA", "VerifierError", "load_target",
    "trust_block", "verify_candidate",
]
