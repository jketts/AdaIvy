"""Transitive influence closure and append-only lifecycle propagation.

Contract Section 11. Every derived artifact records its transitive source and
result influence identities. When a trigger changes what a source permits, the
closure is recomputed, every influenced artifact is invalidated by an appended
record, and the current view is rebuilt deterministically. Original records stay
immutable and addressable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .records import identifier, text
from .serialization import canonical_hash, stable_id
from .state import SynthesisValidationError, ValueEnum, parse_enum


class InfluencedKind(ValueEnum):
    """Every artifact class Section 11 requires closure tracking for."""

    EXTRACTION = "extraction"
    STRUCTURED_RESULT = "structured_result"
    RESULT_RELATION = "result_relation"
    GRAPH_ADMISSION = "graph_admission"
    BRANCH_INPUT = "branch_input"
    RETRIEVAL_DECISION = "retrieval_decision"
    SYNTHESIS_PROPOSAL = "synthesis_proposal"
    BRIDGE_CANDIDATE = "bridge_candidate"
    VERIFICATION_INPUT = "verification_input"
    SURFACED_PARTIAL_RESULT = "surfaced_partial_result"


class TriggerKind(ValueEnum):
    """The Section 11 triggers that force a closure recomputation."""

    SOURCE_CORRECTION = "source_correction"
    REVOCATION = "revocation"
    TAKEDOWN = "takedown"
    SUPPRESSION = "suppression"
    DELETION_REQUEST = "deletion_request"
    DELETION_COMPLETION = "deletion_completion"
    RIGHTS_EXPIRY = "rights_expiry"
    RIGHTS_PROHIBITION = "rights_prohibition"
    RIGHTS_CHANGE = "rights_change"
    APPLICABILITY_REJECTED = "applicability_rejected"
    APPLICABILITY_UNRESOLVED = "applicability_unresolved"
    APPLICABILITY_SCOPE_NARROWED = "applicability_scope_narrowed"
    APPLICABILITY_CONDITIONS_CHANGED = "applicability_conditions_changed"
    APPLICABILITY_AUTHORITY_CHANGED = "applicability_authority_changed"


@dataclass(frozen=True, slots=True, kw_only=True)
class InfluenceNode:
    """One artifact plus its direct inputs and directly cited sources."""

    node_id: str
    kind: InfluencedKind
    direct_source_ids: tuple[str, ...]
    direct_input_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        identifier(self.node_id, field="node_id")
        for source_id in self.direct_source_ids:
            identifier(source_id, field="direct_source_ids[]")
        for input_id in self.direct_input_ids:
            identifier(input_id, field="direct_input_ids[]")
        if self.node_id in self.direct_input_ids:
            raise SynthesisValidationError("a node cannot be its own input")

    def value(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "direct_source_ids": sorted(self.direct_source_ids),
            "direct_input_ids": sorted(self.direct_input_ids),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class InvalidationRecord:
    """An appended invalidation for one influenced artifact."""

    invalidation_id: str
    trigger_id: str
    node_id: str
    node_kind: InfluencedKind
    trigger_kind: TriggerKind
    source_id: str
    influence_path: tuple[str, ...]
    replacement_node_id: str | None

    def value(self) -> dict[str, Any]:
        return {
            "invalidation_id": self.invalidation_id,
            "trigger_id": self.trigger_id,
            "node_id": self.node_id,
            "node_kind": self.node_kind.value,
            "trigger_kind": self.trigger_kind.value,
            "source_id": self.source_id,
            "influence_path": list(self.influence_path),
            "replacement_node_id": self.replacement_node_id,
            "graph_admission": "invalidated_by_later_record",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PropagationTrigger:
    """The triggering record itself, appended before any invalidation."""

    trigger_id: str
    kind: TriggerKind
    source_id: str
    actor_id: str
    authority: str
    detail: str
    prohibits_use: bool

    def value(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "kind": self.kind.value,
            "source_id": self.source_id,
            "actor_id": self.actor_id,
            "authority": self.authority,
            "detail": self.detail,
            "prohibits_use": self.prohibits_use,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PropagationResult:
    """Complete evidence for one propagation, including the rebuilt view."""

    trigger: PropagationTrigger
    invalidations: tuple[InvalidationRecord, ...]
    current_node_ids: tuple[str, ...]
    invalidated_node_ids: tuple[str, ...]
    closure_identity_before: str
    closure_identity_after: str

    def value(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger.value(),
            "invalidations": [item.value() for item in self.invalidations],
            "current_node_ids": list(self.current_node_ids),
            "invalidated_node_ids": list(self.invalidated_node_ids),
            "closure_identity_before": self.closure_identity_before,
            "closure_identity_after": self.closure_identity_after,
        }


class InfluenceGraph:
    """Append-only influence graph with deterministic closure and rebuild."""

    def __init__(self) -> None:
        self._nodes: dict[str, InfluenceNode] = {}
        self._triggers: list[PropagationTrigger] = []
        self._invalidations: list[InvalidationRecord] = []
        self._prohibited_sources: set[str] = set()

    def register(
        self,
        *,
        node_id: str,
        kind: InfluencedKind | str,
        direct_source_ids: Iterable[str] = (),
        direct_input_ids: Iterable[str] = (),
    ) -> InfluenceNode:
        """Register an artifact. Inputs must already exist, so cycles cannot form."""
        resolved = parse_enum(InfluencedKind, kind, field="kind")
        inputs = tuple(sorted(set(direct_input_ids)))
        for input_id in inputs:
            if input_id not in self._nodes:
                raise SynthesisValidationError(
                    f"input {input_id} must be registered before {node_id}"
                )
        if node_id in self._nodes:
            raise SynthesisValidationError(f"node {node_id} is already registered")
        node = InfluenceNode(
            node_id=node_id,
            kind=resolved,
            direct_source_ids=tuple(sorted(set(direct_source_ids))),
            direct_input_ids=inputs,
        )
        self._nodes[node_id] = node
        return node

    def nodes(self) -> tuple[InfluenceNode, ...]:
        return tuple(self._nodes[key] for key in sorted(self._nodes))

    def get(self, node_id: str) -> InfluenceNode:
        """Original records remain addressable, including invalidated ones."""
        if node_id not in self._nodes:
            raise KeyError(node_id)
        return self._nodes[node_id]

    def transitive_sources(self, node_id: str) -> tuple[str, ...]:
        """Every source identity that transitively influences this artifact."""
        seen: set[str] = set()
        sources: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            node = self._nodes[current]
            sources.update(node.direct_source_ids)
            stack.extend(node.direct_input_ids)
        return tuple(sorted(sources))

    def influence_path(self, node_id: str, source_id: str) -> tuple[str, ...]:
        """A deterministic shortest path from the artifact to the source."""
        # Breadth-first over sorted inputs so the recorded path is stable.
        queue: list[tuple[str, tuple[str, ...]]] = [(node_id, (node_id,))]
        seen: set[str] = set()
        while queue:
            current, path = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            node = self._nodes[current]
            if source_id in node.direct_source_ids:
                return path + (source_id,)
            for input_id in node.direct_input_ids:
                queue.append((input_id, path + (input_id,)))
        return ()

    def influenced_by(self, source_id: str) -> tuple[str, ...]:
        """Every artifact transitively influenced by one source."""
        return tuple(
            sorted(
                node.node_id
                for node in self._nodes.values()
                if source_id in self.transitive_sources(node.node_id)
            )
        )

    def invalidated_node_ids(self) -> frozenset[str]:
        return frozenset(record.node_id for record in self._invalidations)

    def current_node_ids(self) -> tuple[str, ...]:
        """The rebuilt current view: everything not yet invalidated."""
        invalidated = self.invalidated_node_ids()
        return tuple(sorted(key for key in self._nodes if key not in invalidated))

    def prohibited_sources(self) -> tuple[str, ...]:
        return tuple(sorted(self._prohibited_sources))

    def closure_identity(self) -> str:
        """Deterministic identity of the current influence closure."""
        return canonical_hash(
            {
                "nodes": [
                    {
                        "node_id": node_id,
                        "transitive_sources": list(self.transitive_sources(node_id)),
                    }
                    for node_id in self.current_node_ids()
                ],
                "prohibited_sources": list(self.prohibited_sources()),
            }
        )

    def eligible_inputs(self, candidate_ids: Sequence[str]) -> tuple[str, ...]:
        """Filter candidate inputs to those with zero prohibited influence.

        Used before parsing, context assembly, relation proposal, synthesis,
        verification, and partial-result surfacing, so a prohibited source is
        absent from the input rather than merely ranked lower.
        """
        invalidated = self.invalidated_node_ids()
        eligible = []
        for node_id in candidate_ids:
            if node_id in invalidated:
                continue
            sources = set(self.transitive_sources(node_id))
            if sources & self._prohibited_sources:
                continue
            eligible.append(node_id)
        return tuple(sorted(eligible))

    def propagate(
        self,
        *,
        kind: TriggerKind | str,
        source_id: str,
        actor_id: str,
        authority: str,
        detail: str,
        prohibits_use: bool = True,
        replacements: Mapping[str, str] | None = None,
    ) -> PropagationResult:
        """Append the trigger, invalidate the closure, and rebuild the view."""
        resolved = parse_enum(TriggerKind, kind, field="kind")
        identifier(source_id, field="source_id")
        identifier(actor_id, field="actor_id")
        text(detail, field="detail")
        before = self.closure_identity()

        trigger = PropagationTrigger(
            trigger_id=stable_id(
                "propagation-trigger",
                {"kind": resolved.value, "source_id": source_id, "detail": detail},
            ),
            kind=resolved,
            source_id=source_id,
            actor_id=actor_id,
            authority=authority,
            detail=detail,
            prohibits_use=prohibits_use,
        )
        self._triggers.append(trigger)
        if prohibits_use:
            self._prohibited_sources.add(source_id)

        already = self.invalidated_node_ids()
        appended: list[InvalidationRecord] = []
        for node_id in self.influenced_by(source_id):
            if node_id in already:
                continue
            node = self._nodes[node_id]
            record = InvalidationRecord(
                invalidation_id=stable_id(
                    "invalidation", {"trigger_id": trigger.trigger_id, "node_id": node_id}
                ),
                trigger_id=trigger.trigger_id,
                node_id=node_id,
                node_kind=node.kind,
                trigger_kind=resolved,
                source_id=source_id,
                influence_path=self.influence_path(node_id, source_id),
                replacement_node_id=(replacements or {}).get(node_id),
            )
            appended.append(record)
        self._invalidations.extend(appended)

        return PropagationResult(
            trigger=trigger,
            invalidations=tuple(sorted(appended, key=lambda item: item.node_id)),
            current_node_ids=self.current_node_ids(),
            invalidated_node_ids=tuple(sorted(self.invalidated_node_ids())),
            closure_identity_before=before,
            closure_identity_after=self.closure_identity(),
        )

    def triggers(self) -> tuple[PropagationTrigger, ...]:
        return tuple(self._triggers)

    def invalidations(self) -> tuple[InvalidationRecord, ...]:
        return tuple(self._invalidations)

    def value(self) -> dict[str, Any]:
        return {
            "nodes": [node.value() for node in self.nodes()],
            "triggers": [item.value() for item in self.triggers()],
            "invalidations": [item.value() for item in self.invalidations()],
            "current_node_ids": list(self.current_node_ids()),
            "prohibited_sources": list(self.prohibited_sources()),
            "closure_identity": self.closure_identity(),
        }


__all__ = [
    "InfluenceGraph",
    "InfluenceNode",
    "InfluencedKind",
    "InvalidationRecord",
    "PropagationResult",
    "PropagationTrigger",
    "TriggerKind",
]
