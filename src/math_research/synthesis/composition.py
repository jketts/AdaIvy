"""Composition comparison under a finite declared rule.

Contract Section 8. Every dimension is compared before composition, every
mismatch opens an obligation, and the rule is versioned so a later change cannot
silently reinterpret a recorded comparison.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import COMPARISON_RULE_VERSION
from .records import StructuredResearchResult, identifier, text
from .serialization import stable_id
from .state import MismatchKind, SynthesisValidationError

# Section 8: the exact dimensions compared before any composition. Declared as
# an ordered tuple so the exported comparison names every dimension actually
# evaluated, and a future addition is a visible rule-version change.
COMPARED_DIMENSIONS: tuple[str, ...] = (
    "assumptions",
    "consumed_term",
    "implication_direction",
    "quantifier_kinds_and_bounds",
    "domains",
    "codomains",
    "object_types",
    "regularity",
    "definition_correspondence",
    "notation_correspondence",
    "scope_and_exceptions",
    "source_versions",
    "conclusion_strength",
)

# Strength ordering is intentionally explicit and local to composition: a premise
# may supply a conclusion at least as strong as the consumer requires. This is a
# comparison rule over declared strength labels, not a warrant ordering.
_STRENGTH_RANK = {
    "exact": 4,
    "bounded": 3,
    "asymptotic": 2,
    "existential_witness": 1,
    "conditional": 0,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Mismatch:
    """One named mismatch and the obligation it opens (Section 8)."""

    kind: MismatchKind
    dimension: str
    detail: str
    obligation_id: str

    def value(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "dimension": self.dimension,
            "detail": self.detail,
            "obligation_id": self.obligation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CompositionComparison:
    """The complete comparison evidence for one attempted composition."""

    comparison_id: str
    rule_version: str
    premise_result_id: str
    consumer_result_id: str
    consumed_term: str
    compared_dimensions: tuple[str, ...]
    mismatches: tuple[Mismatch, ...]

    @property
    def compatible(self) -> bool:
        return not self.mismatches

    def mismatch_kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.kind.value for item in self.mismatches}))

    def obligation_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.obligation_id for item in self.mismatches}))

    def value(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "rule_version": self.rule_version,
            "premise_result_id": self.premise_result_id,
            "consumer_result_id": self.consumer_result_id,
            "consumed_term": self.consumed_term,
            "compared_dimensions": list(self.compared_dimensions),
            "compatible": self.compatible,
            "mismatches": [item.value() for item in self.mismatches],
        }


def _obligation(kind: MismatchKind, premise_id: str, consumer_id: str, detail: str) -> str:
    return stable_id(
        "obligation",
        {
            "kind": kind.value,
            "premise_result_id": premise_id,
            "consumer_result_id": consumer_id,
            "detail": detail,
            "rule_version": COMPARISON_RULE_VERSION,
        },
    )


def compare_for_composition(
    premise: StructuredResearchResult,
    consumer: StructuredResearchResult,
    *,
    consumed_term: str,
) -> CompositionComparison:
    """Compare every Section 8 dimension for `premise` feeding `consumer`.

    `consumed_term` is the exact term the consumer takes from the premise's
    conclusion. Returns the full comparison including an obligation per mismatch;
    it never composes and never decides admission.
    """
    text(consumed_term, field="consumed_term")
    if premise.result_id == consumer.result_id:
        raise SynthesisValidationError("a composition requires two distinct results")

    mismatches: list[Mismatch] = []

    def note(kind: MismatchKind, dimension: str, detail: str) -> None:
        mismatches.append(
            Mismatch(
                kind=kind,
                dimension=dimension,
                detail=detail,
                obligation_id=_obligation(kind, premise.result_id, consumer.result_id, detail),
            )
        )

    # 1. The exact term consumed by the next result must be produced by the
    #    premise's conclusion and occur as one complete consumer assumption.
    #    Every other assumption must be carried unchanged by both results. This
    #    deliberately fails closed: the comparator cannot silently insert an
    #    additional hypothesis or discard one on which the premise depends.
    if consumed_term not in premise.conclusion:
        note(
            MismatchKind.CONSUMED_TERM,
            "consumed_term",
            f"premise conclusion does not produce the consumed term {consumed_term!r}",
        )
    if consumed_term not in consumer.assumptions:
        note(
            MismatchKind.CONSUMED_TERM,
            "consumed_term",
            f"consumer assumptions do not require the consumed term {consumed_term!r}",
        )

    premise_assumptions = set(premise.assumptions)
    consumer_context = set(consumer.assumptions) - {consumed_term}
    for assumption in sorted(premise_assumptions - consumer_context):
        note(
            MismatchKind.ASSUMPTION,
            "assumptions",
            f"premise assumption {assumption!r} is not carried by the consumer",
        )
    for assumption in sorted(consumer_context - premise_assumptions):
        note(
            MismatchKind.ASSUMPTION,
            "assumptions",
            f"consumer requires additional assumption {assumption!r} not carried by the premise",
        )

    # 2. Implication direction: a premise cannot depend on the result that is
    #    supposed to consume it. The consumer may declare the premise as a
    #    dependency, but the reverse edge is circular even when only that edge
    #    is present in the two records under comparison.
    if consumer.result_id in premise.dependencies:
        note(
            MismatchKind.IMPLICATION_DIRECTION,
            "implication_direction",
            "premise declares the consumer as a dependency",
        )

    # 3. Quantifier kinds and bounds must agree for every shared variable. This
    #    is what prevents a universal premise being consumed as an existential
    #    conclusion, or a differently bounded one.
    premise_quantifiers = {variable: (kind, bound) for variable, kind, bound in premise.quantifiers}
    consumer_quantifiers = {
        variable: (kind, bound) for variable, kind, bound in consumer.quantifiers
    }
    for variable in sorted(set(premise_quantifiers) | set(consumer_quantifiers)):
        if variable not in premise_quantifiers:
            note(
                MismatchKind.QUANTIFIER,
                "quantifier_kinds_and_bounds",
                f"variable {variable!r} is quantified only by the consumer",
            )
            continue
        if variable not in consumer_quantifiers:
            note(
                MismatchKind.QUANTIFIER,
                "quantifier_kinds_and_bounds",
                f"variable {variable!r} is quantified only by the premise",
            )
            continue
        premise_kind, premise_bound = premise_quantifiers[variable]
        kind, bound = consumer_quantifiers[variable]
        if premise_kind is not kind:
            note(
                MismatchKind.QUANTIFIER,
                "quantifier_kinds_and_bounds",
                f"variable {variable!r} is {premise_kind.value} in the premise "
                f"and {kind.value} in the consumer",
            )
        elif premise_bound != bound:
            note(
                MismatchKind.QUANTIFIER,
                "quantifier_kinds_and_bounds",
                f"variable {variable!r} is bounded {premise_bound!r} in the premise "
                f"and {bound!r} in the consumer",
            )

    # 4-7. These declarations have no project-wide semantic subsumption rule.
    #      Exact set agreement is therefore the only deterministic, fail-closed
    #      compatibility rule. A future hierarchy must use a new rule version.
    for kind, dimension, required, supplied in (
        (MismatchKind.DOMAIN, "domains", consumer.domains, premise.domains),
        (MismatchKind.CODOMAIN, "codomains", consumer.codomains, premise.codomains),
        (MismatchKind.OBJECT_TYPE, "object_types", consumer.object_types, premise.object_types),
        (MismatchKind.REGULARITY, "regularity", consumer.regularity, premise.regularity),
    ):
        required_set = set(required)
        supplied_set = set(supplied)
        for item in sorted(required_set - supplied_set):
            note(kind, dimension, f"consumer requires {item!r} which the premise does not supply")
        for item in sorted(supplied_set - required_set):
            note(kind, dimension, f"premise restriction {item!r} is not carried by the consumer")

    # 8-9. Definition and notation correspondence. Every declared symbol must
    #      correspond; a missing definition also fails closed.
    premise_definitions = dict(premise.notation.definition_mapping)
    consumer_definitions = dict(consumer.notation.definition_mapping)
    for symbol in sorted(set(premise_definitions) & set(consumer_definitions)):
        if premise_definitions[symbol] != consumer_definitions[symbol]:
            note(
                MismatchKind.DEFINITION,
                "definition_correspondence",
                f"symbol {symbol!r} is defined as {premise_definitions[symbol]!r} in the premise "
                f"and {consumer_definitions[symbol]!r} in the consumer",
            )
    for symbol in sorted(set(premise_definitions) - set(consumer_definitions)):
        note(
            MismatchKind.DEFINITION,
            "definition_correspondence",
            f"premise definition for symbol {symbol!r} is absent from the consumer",
        )
    for symbol in sorted(set(consumer_definitions) - set(premise_definitions)):
        note(
            MismatchKind.DEFINITION,
            "definition_correspondence",
            f"consumer definition for symbol {symbol!r} is absent from the premise",
        )
    if premise.notation.rule_id != consumer.notation.rule_id or (
        premise.notation.rule_version != consumer.notation.rule_version
    ):
        note(
            MismatchKind.NOTATION,
            "notation_correspondence",
            f"normalization rule {premise.notation.rule_id}@{premise.notation.rule_version} "
            f"differs from {consumer.notation.rule_id}@{consumer.notation.rule_version}",
        )

    # 10. Scope and exception labels likewise have no declared subsumption
    #     relation, so a composition is compatible only on exact set agreement.
    premise_scope = set(premise.scope)
    consumer_scope = set(consumer.scope)
    for scope in sorted(consumer_scope - premise_scope):
        note(
            MismatchKind.SCOPE_OR_EXCEPTION,
            "scope_and_exceptions",
            f"consumer scope {scope!r} is not supplied by the premise",
        )
    for scope in sorted(premise_scope - consumer_scope):
        note(
            MismatchKind.SCOPE_OR_EXCEPTION,
            "scope_and_exceptions",
            f"premise scope restriction {scope!r} is not carried by the consumer",
        )
    premise_exceptions = set(premise.exceptions)
    consumer_exceptions = set(consumer.exceptions)
    for exception in sorted(premise_exceptions - consumer_exceptions):
        note(
            MismatchKind.SCOPE_OR_EXCEPTION,
            "scope_and_exceptions",
            f"premise exception {exception!r} is not carried by the consumer",
        )
    for exception in sorted(consumer_exceptions - premise_exceptions):
        note(
            MismatchKind.SCOPE_OR_EXCEPTION,
            "scope_and_exceptions",
            f"consumer exception {exception!r} is not carried by the premise",
        )

    # 11. Source versions must agree wherever both cite the same source.
    premise_versions = {anchor.source_id: anchor.source_version for anchor in premise.anchors}
    for anchor in consumer.anchors:
        recorded = premise_versions.get(anchor.source_id)
        if recorded is not None and recorded != anchor.source_version:
            note(
                MismatchKind.SOURCE_VERSION,
                "source_versions",
                f"source {anchor.source_id} is cited at version {recorded!r} by the premise "
                f"and {anchor.source_version!r} by the consumer",
            )

    # 12. The premise must conclude at least as strongly as the consumer needs.
    if _STRENGTH_RANK[premise.conclusion_strength] < _STRENGTH_RANK[consumer.conclusion_strength]:
        note(
            MismatchKind.CONCLUSION_STRENGTH,
            "conclusion_strength",
            f"premise concludes {premise.conclusion_strength!r} but the consumer requires "
            f"{consumer.conclusion_strength!r}",
        )

    ordered = tuple(sorted(mismatches, key=lambda item: (item.dimension, item.kind.value, item.detail)))
    comparison_id = stable_id(
        "comparison",
        {
            "premise": premise.semantic_digest(),
            "consumer": consumer.semantic_digest(),
            "consumed_term": consumed_term,
            "rule_version": COMPARISON_RULE_VERSION,
        },
    )
    return CompositionComparison(
        comparison_id=comparison_id,
        rule_version=COMPARISON_RULE_VERSION,
        premise_result_id=premise.result_id,
        consumer_result_id=consumer.result_id,
        consumed_term=consumed_term,
        compared_dimensions=COMPARED_DIMENSIONS,
        mismatches=ordered,
    )


def compare_chain(
    results: Sequence[StructuredResearchResult], *, consumed_terms: Sequence[str]
) -> tuple[CompositionComparison, ...]:
    """Compare each adjacent pair in a multi-result composition chain."""
    if len(results) < 2:
        raise SynthesisValidationError("a composition chain requires at least two results")
    if len(consumed_terms) != len(results) - 1:
        raise SynthesisValidationError(
            "a composition chain requires one consumed term per adjacent pair"
        )
    return tuple(
        compare_for_composition(results[index], results[index + 1], consumed_term=consumed_terms[index])
        for index in range(len(results) - 1)
    )


__all__ = [
    "COMPARED_DIMENSIONS",
    "CompositionComparison",
    "Mismatch",
    "compare_chain",
    "compare_for_composition",
]
