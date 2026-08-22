"""Target *schema classes* for the ADR-0082 workspace sandbox.

ADR-0066's activation bound execution to ONE fixture target file's hash, so
the only runnable mathematics was the checked-in fixture.  ADR-0082 widens the
binding to a target schema *class*: the activation records the content hash of
a closed class definition, and any target whose bytes validate exactly against
that class is runnable -- one activation, many targets, still fail-closed.

The class definition itself is data: a closed record naming the target schema
version, the exact verifier engine, and the complete field inventory, hashed
with :func:`~math_research.campaign.records.canonical_hash`.  A target that
fails class admission is a typed refusal carrying the underlying verifier
refusal code, never a silent pass.

This module imports no ``os``, ``subprocess``, ``socket`` or ``ctypes`` module
and performs no I/O; admission is pure byte checking in the host process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..records import canonical_hash
from .verifier import (
    TARGET_ENGINE,
    TARGET_SCHEMA,
    ExperimentTarget,
    VerifierError,
    load_target,
)

TARGET_CLASS_SCHEMA = "adaivy.campaign-target-schema-class.v1"
EXACT_GRAPH_CLASS_ID = "adaivy.campaign-target-class.exact-graph.v2"


class TargetClassError(ValueError):
    """A target's bytes do not validate against the bound schema class."""

    def __init__(self, refusal_code: str) -> None:
        super().__init__(refusal_code)
        self.refusal_code = refusal_code


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetSchemaClass:
    """One closed, content-hashed target family an activation may bind to."""

    class_id: str
    target_schema_version: str
    engine: str
    field_names: tuple[str, ...]
    verifier_route: str

    def definition_record(self) -> dict[str, Any]:
        return {
            "arithmetic": "int_and_fraction_only",
            "class_id": self.class_id,
            "engine": self.engine,
            "field_names": list(self.field_names),
            "schema_version": TARGET_CLASS_SCHEMA,
            "target_schema_version": self.target_schema_version,
            "verifier_location": "host_process_outside_container",
            "verifier_route": self.verifier_route,
        }

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.definition_record())

    def admit_target(self, target_bytes: bytes) -> ExperimentTarget:
        """Admit any target validating exactly against this class, or refuse.

        Admission proves membership of the class, nothing more: no warrant, no
        applicability, no assertion that the target is satisfiable.
        """

        try:
            target = load_target(target_bytes)
        except VerifierError as error:
            raise TargetClassError(
                f"target_outside_schema_class:{error.args[0]}"
            ) from error
        if target.schema_version != self.target_schema_version:
            raise TargetClassError("target_outside_schema_class:schema_version")
        if target.engine != self.engine:
            raise TargetClassError("target_outside_schema_class:engine")
        record_fields = frozenset(target.to_record()) - {"target_hash"}
        if record_fields != frozenset(self.field_names):
            raise TargetClassError("target_outside_schema_class:field_inventory")
        return target

    def admission_record(self, target: ExperimentTarget) -> dict[str, Any]:
        """The ledgerable fact of one admission: class hash plus target hash."""

        value = {
            "class_definition_hash": self.definition_hash,
            "class_id": self.class_id,
            "epistemic_warrant_created": False,
            "schema_version": "adaivy.campaign-target-class-admission.v1",
            "target_hash": target.target_hash,
            "target_id": target.target_id,
        }
        value["content_hash"] = canonical_hash(value)
        return value


#: The first registered class: the ADR-0066 exact-graph target's 12-field
#: schema, unchanged, now addressed as a class rather than as one file hash.
EXACT_GRAPH_TARGET_CLASS = TargetSchemaClass(
    class_id=EXACT_GRAPH_CLASS_ID,
    target_schema_version=TARGET_SCHEMA,
    engine=TARGET_ENGINE,
    field_names=tuple(sorted(
        frozenset(ExperimentTarget.__dataclass_fields__) - {"target_hash"}
    )),
    verifier_route="exact_graph",
)

#: Closed registry.  Adding a class is a reviewed code change following the
#: registration path documented in ``campaign/verifier_router.py``; nothing
#: registers a class at runtime.
TARGET_SCHEMA_CLASSES: dict[str, TargetSchemaClass] = {
    EXACT_GRAPH_TARGET_CLASS.class_id: EXACT_GRAPH_TARGET_CLASS,
}


def resolve_target_class(class_id: str) -> TargetSchemaClass:
    schema_class = TARGET_SCHEMA_CLASSES.get(class_id)
    if schema_class is None:
        raise TargetClassError("target_schema_class_unknown")
    return schema_class


__all__ = [
    "EXACT_GRAPH_CLASS_ID", "EXACT_GRAPH_TARGET_CLASS", "TARGET_CLASS_SCHEMA",
    "TARGET_SCHEMA_CLASSES", "TargetClassError", "TargetSchemaClass",
    "resolve_target_class",
]
