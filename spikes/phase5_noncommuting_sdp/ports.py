"""Narrow ports for the noncommuting-SDP engine comparison.

The trust boundary is encoded in the types, not only in prose:

* :class:`NumericSolution` has no ``verified``, ``warrant``, or ``proved``
  field. Its :attr:`NumericSolution.trust` is a read-only property whose value
  is the constant ``"untrusted_candidate"``, so no adapter, and no later code
  path, can construct a numerical result that claims to be anything else.
  ``engine_status`` is the engine's own word (``"Solved"``, ``"optimal"``, ...)
  and is retained verbatim; it is evidence about the engine, not about the
  mathematics.
* :class:`MissingTool` exists so an absent engine is a recorded result rather
  than a silent gap. `AGENTS.md` requires missing-tool results to be preserved
  in machine-readable output.
* :class:`ModuleResolver` is the seam the gated dynamic import goes through, so
  the acceptance suite can exercise the fail-closed path deterministically on a
  machine where the engines happen to be installed, and on one where they are
  not, with the same assertions and no skip.

Operational observations -- elapsed milliseconds, iteration counts, residuals,
and the returned floating-point matrices -- are carried in a separate
:class:`OperationalObservation` so they can be hashed separately from semantic
identity, following the Phase 3B precedent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

from .encoding import ExactProgram

UNTRUSTED = "untrusted_candidate"
"""The only trust level a numerical engine result may ever carry."""


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    """Identity and licence of one authorised engine."""

    engine_id: str
    modules: tuple[str, ...]
    license_expression: str
    license_url: str
    role: str
    formulation: str

    def public(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "modules": list(self.modules),
            "license_expression": self.license_expression,
            "license_url": self.license_url,
            "role": self.role,
            "formulation": self.formulation,
        }


@dataclass(frozen=True, slots=True)
class EngineProbe:
    """Availability of an engine. Probing must not solve anything."""

    engine_id: str
    available: bool
    reason_code: str
    modules_present: tuple[str, ...] = ()
    modules_absent: tuple[str, ...] = ()
    module_versions: tuple[tuple[str, str], ...] = ()
    network_attempted: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "available": self.available,
            "reason_code": self.reason_code,
            "modules_present": list(self.modules_present),
            "modules_absent": list(self.modules_absent),
            "module_versions": [list(item) for item in self.module_versions],
            "network_attempted": self.network_attempted,
        }


@dataclass(frozen=True, slots=True)
class MissingTool:
    """A recorded missing-tool result. Never a skip, never a silent gap."""

    engine_id: str
    reason_code: str
    detail: str
    modules_absent: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "outcome": "missing_tool",
            "engine_id": self.engine_id,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "modules_absent": list(self.modules_absent),
            "network_attempted": False,
            "creates_candidate": False,
            "creates_warrant": False,
        }


@dataclass(frozen=True, slots=True)
class OperationalObservation:
    """Run-dependent numbers. Excluded from every semantic hash."""

    elapsed_milliseconds: float | None = None
    setup_milliseconds: float | None = None
    solve_milliseconds: float | None = None
    iterations: int | None = None
    primal_residual: float | None = None
    dual_residual: float | None = None
    duality_gap_residual: float | None = None
    primal_objective: float | None = None
    dual_objective: float | None = None
    primal_blocks: tuple[tuple[tuple[float, ...], ...], ...] = ()
    dual_block: tuple[tuple[float, ...], ...] = ()
    raw_engine_fields: tuple[tuple[str, str], ...] = ()
    """Verbatim ``str()`` of what the engine returned, before any reading of it.

    The interpreted fields above apply documented sign and scale conventions;
    these are kept so the interpretation can be audited against the source.
    """
    derivation_notes: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "setup_milliseconds": self.setup_milliseconds,
            "solve_milliseconds": self.solve_milliseconds,
            "iterations": self.iterations,
            "primal_residual": self.primal_residual,
            "dual_residual": self.dual_residual,
            "duality_gap_residual": self.duality_gap_residual,
            "primal_objective": self.primal_objective,
            "dual_objective": self.dual_objective,
            "primal_blocks": [[list(row) for row in block] for block in self.primal_blocks],
            "dual_block": [list(row) for row in self.dual_block],
            "raw_engine_fields": [list(item) for item in self.raw_engine_fields],
            "derivation_notes": list(self.derivation_notes),
            "hash_class": "operational_only",
        }


@dataclass(frozen=True, slots=True)
class NumericSolution:
    """An UNTRUSTED numerical candidate returned by one engine.

    There is deliberately no field by which an engine can assert correctness.
    ``engine_status`` and ``engine_claims_optimal`` describe what the engine
    said about itself; neither is, or can become, a mathematical warrant.
    """

    engine_id: str
    engine_status: str
    engine_claims_optimal: bool
    settings: tuple[tuple[str, str], ...]
    solver_actually_used: str
    operational: OperationalObservation = field(default_factory=OperationalObservation)

    @property
    def trust(self) -> str:
        """Constant. Not a field, so it cannot be constructed differently."""

        return UNTRUSTED

    def semantic_public(self) -> dict[str, Any]:
        """The part of the observation that participates in semantic identity."""

        return {
            "outcome": "engine_observation",
            "engine_id": self.engine_id,
            "engine_status": self.engine_status,
            "engine_claims_optimal": self.engine_claims_optimal,
            "solver_actually_used": self.solver_actually_used,
            "settings": [list(item) for item in self.settings],
            "trust": self.trust,
            "creates_candidate": True,
            "creates_warrant": False,
            "status_is_evidence_about_the_engine_not_the_mathematics": True,
        }

    def public(self) -> dict[str, Any]:
        body = self.semantic_public()
        body["operational"] = self.operational.public()
        return body


@dataclass(frozen=True, slots=True)
class EngineRun:
    """Exactly one of ``solution`` or ``missing_tool`` is populated."""

    engine_id: str
    probe: EngineProbe
    solution: NumericSolution | None = None
    missing_tool: MissingTool | None = None

    def __post_init__(self) -> None:
        if (self.solution is None) == (self.missing_tool is None):
            raise ValueError("an engine run is either an observation or a missing tool")

    @property
    def executed(self) -> bool:
        return self.solution is not None


@runtime_checkable
class ModuleResolver(Protocol):
    """The seam every third-party load passes through."""

    def find(self, module_name: str) -> Any | None:
        """Return the module, or ``None`` when it is not importable."""

    def version(self, module_name: str) -> str | None:
        """Return the installed distribution version, or ``None``."""


@runtime_checkable
class SDPEngine(Protocol):
    """One numerical engine adapter. It may only ever propose a candidate."""

    descriptor: EngineDescriptor

    def probe(self) -> EngineProbe:
        """Report availability without solving anything."""

    def solve(self, program: ExactProgram) -> EngineRun:
        """Consume the exact encoding and return a candidate or a missing tool."""


def engine_ids(engines: Sequence[SDPEngine]) -> tuple[str, ...]:
    return tuple(engine.descriptor.engine_id for engine in engines)


__all__ = [
    "UNTRUSTED",
    "EngineDescriptor",
    "EngineProbe",
    "EngineRun",
    "MissingTool",
    "ModuleResolver",
    "NumericSolution",
    "OperationalObservation",
    "SDPEngine",
    "engine_ids",
]
