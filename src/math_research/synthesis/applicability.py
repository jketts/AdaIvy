"""Effective Phase 4A applicability resolution.

Contract Section 2.1 requires importing the *effective* human
`ApplicabilityReview`. Phase 4A validates each review as it is written but has no
resolver for which review is currently in force, so this module supplies the
rule and imports the result without ever producing it.

Two Phase 4A properties make the rule non-obvious and are handled explicitly:

* a review's `subject_id` is the source id, not the evidence card, so reviews for
  different cards over one source share a subject; and
* unlike rights decisions, an applicability review's `supersedes` edge is not
  forced to point at the latest prior review, so a chain can fork.

A fork is ambiguous rather than resolvable, and ambiguity fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .records import identifier
from .serialization import canonical_hash
from .state import SourceApplicability, SynthesisValidationError, parse_enum

REVIEW_RECORD_TYPE = "applicability_review"
REQUIRED_ACTOR_KIND = "human"
REQUIRED_AUTHORITY = "human_final"
REQUIRED_CHECKS = frozenset(
    {
        "bibliographic_identity_checked",
        "hypotheses_checked",
        "definitions_checked",
        "scope_exceptions_checked",
        "implication_checked",
    }
)


class AmbiguousApplicability(SynthesisValidationError):
    """A forked supersession chain has no single effective review."""


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectiveApplicability:
    """The imported effective decision for one evidence card."""

    evidence_card_id: str
    source_id: str
    review_record_id: str
    status: SourceApplicability
    outcome: str
    actor_id: str
    authority: str
    sequence: int
    superseded_review_ids: tuple[str, ...]

    @property
    def permits_use(self) -> bool:
        """Only `checked` with an `applicable` outcome permits a downstream use.

        Section 11: a rejected or unresolved effective review fails closed.
        """
        return self.status is SourceApplicability.CHECKED and self.outcome == "applicable"

    def value(self) -> dict[str, Any]:
        return {
            "evidence_card_id": self.evidence_card_id,
            "source_id": self.source_id,
            "review_record_id": self.review_record_id,
            "status": self.status.value,
            "outcome": self.outcome,
            "actor_id": self.actor_id,
            "authority": self.authority,
            "sequence": self.sequence,
            "superseded_review_ids": list(self.superseded_review_ids),
            "permits_use": self.permits_use,
        }


def _review_id(row: Mapping[str, Any]) -> str:
    """Read the identity from Phase 4A's public ``AuditRecord`` shape."""
    if "id" not in row:
        raise SynthesisValidationError("applicability review is missing its Phase 4A id")
    return identifier(row["id"], field="applicability review id")


def _review_rows(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if any(not isinstance(row, Mapping) for row in records):
        raise SynthesisValidationError("Phase 4A records must be objects")
    rows = [row for row in records if row.get("record_type") == REVIEW_RECORD_TYPE]
    identities: set[str] = set()
    for row in rows:
        review_id = _review_id(row)
        if review_id in identities:
            raise SynthesisValidationError(
                f"duplicate applicability review identity: {review_id}"
            )
        identities.add(review_id)
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise SynthesisValidationError("applicability review payload must be an object")
        missing = {"evidence_card_id", "status", "outcome", "source_id"} - set(payload)
        if missing:
            raise SynthesisValidationError(
                f"applicability review payload missing: {', '.join(sorted(missing))}"
            )
        identifier(payload["evidence_card_id"], field="evidence_card_id")
        identifier(payload["source_id"], field="source_id")
        sequence = row.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise SynthesisValidationError(
                f"applicability review {review_id} sequence must be a non-negative integer"
            )
        supersedes = row.get("supersedes")
        if supersedes is not None:
            identifier(supersedes, field="supersedes")
    return rows


def _validate_chain(
    rows: Sequence[Mapping[str, Any]],
    *,
    all_rows_by_id: Mapping[str, Mapping[str, Any]],
    evidence_card_id: str,
) -> None:
    """Validate one card's supersession graph before selecting its head."""
    rows_by_id = {_review_id(row): row for row in rows}
    source_ids = {row["payload"]["source_id"] for row in rows}
    if len(source_ids) != 1:
        raise SynthesisValidationError(
            f"applicability reviews for {evidence_card_id} disagree on source identity"
        )

    for review_id, row in rows_by_id.items():
        target_id = row.get("supersedes")
        if target_id is None:
            continue
        target = all_rows_by_id.get(target_id)
        if target is None:
            raise SynthesisValidationError(
                f"applicability review {review_id} supersedes missing review {target_id}"
            )
        if target_id not in rows_by_id:
            raise SynthesisValidationError(
                f"applicability review {review_id} crosses evidence-card chains"
            )
        if target["payload"]["source_id"] != row["payload"]["source_id"]:
            raise SynthesisValidationError(
                f"applicability review {review_id} crosses source chains"
            )
        if target["sequence"] >= row["sequence"]:
            raise SynthesisValidationError(
                f"applicability review {review_id} does not supersede an earlier review"
            )

    # Sequence ordering rejects ordinary cycles, but retain an explicit walk so
    # malformed imported mappings cannot hide a disconnected cyclic component.
    for start_id in rows_by_id:
        visited: set[str] = set()
        current_id: str | None = start_id
        while current_id is not None:
            if current_id in visited:
                raise SynthesisValidationError(
                    f"cyclic applicability supersession chain for {evidence_card_id}"
                )
            visited.add(current_id)
            current_id = rows_by_id[current_id].get("supersedes")


def resolve_effective(
    records: Sequence[Mapping[str, Any]], *, evidence_card_id: str
) -> EffectiveApplicability:
    """Resolve the single effective review for one evidence card.

    The head of the chain is the highest-sequence review that no other review for
    the same card supersedes. A fork, a missing review, or a review whose
    authority does not permit its status all fail closed.
    """
    identifier(evidence_card_id, field="evidence_card_id")
    review_rows = _review_rows(records)
    rows = [
        row
        for row in review_rows
        if row["payload"]["evidence_card_id"] == evidence_card_id
    ]
    if not rows:
        raise SynthesisValidationError(
            f"no applicability review exists for evidence card {evidence_card_id}"
        )

    all_rows_by_id = {_review_id(row): row for row in review_rows}
    _validate_chain(
        rows,
        all_rows_by_id=all_rows_by_id,
        evidence_card_id=evidence_card_id,
    )
    superseded = {row["supersedes"] for row in rows if row.get("supersedes")}
    heads = [row for row in rows if _review_id(row) not in superseded]
    if not heads:
        raise SynthesisValidationError(
            f"cyclic applicability supersession chain for {evidence_card_id}"
        )
    if len(heads) > 1:
        # Section 2.1 admits exactly one effective decision. A fork means the
        # reviewers disagree about which prior review they replaced.
        raise AmbiguousApplicability(
            "forked applicability supersession chain for "
            f"{evidence_card_id}: {sorted(_review_id(row) for row in heads)}"
        )
    head = heads[0]
    payload = head["payload"]
    status = parse_enum(SourceApplicability, payload["status"], field="status")
    actor_kind = head.get("actor_kind")
    authority = head.get("authority")

    # Only Phase 4A named-human authority may produce the effective
    # checked/applicable outcome. Anything else is imported as unresolved rather
    # than trusted, so a mislabelled record cannot widen permission.
    if status is not SourceApplicability.PROPOSED:
        if actor_kind != REQUIRED_ACTOR_KIND or authority != REQUIRED_AUTHORITY:
            raise SynthesisValidationError(
                "a non-proposed applicability review requires named human final authority"
            )
    if status is SourceApplicability.CHECKED and payload["outcome"] == "applicable":
        checks = {key: payload.get(key) for key in REQUIRED_CHECKS}
        if not all(value is True for value in checks.values()):
            raise SynthesisValidationError(
                "checked/applicable requires every human review dimension to be checked"
            )

    return EffectiveApplicability(
        evidence_card_id=evidence_card_id,
        source_id=payload["source_id"],
        review_record_id=_review_id(head),
        status=status,
        outcome=payload["outcome"],
        actor_id=head.get("actor_id", ""),
        authority=authority or "",
        sequence=int(head.get("sequence", 0)),
        superseded_review_ids=tuple(
            sorted(_review_id(row) for row in rows if _review_id(row) in superseded)
        ),
    )


def resolve_all(records: Sequence[Mapping[str, Any]]) -> dict[str, EffectiveApplicability]:
    """Resolve the effective review for every card present in the records."""
    cards = sorted({row["payload"]["evidence_card_id"] for row in _review_rows(records)})
    return {card: resolve_effective(records, evidence_card_id=card) for card in cards}


def applicability_snapshot(records: Sequence[Mapping[str, Any]]) -> str:
    """Deterministic identity of the resolved applicability state."""
    resolved = resolve_all(records)
    return canonical_hash(
        {card: decision.value() for card, decision in sorted(resolved.items())}
    )


__all__ = [
    "AmbiguousApplicability",
    "EffectiveApplicability",
    "REQUIRED_ACTOR_KIND",
    "REQUIRED_AUTHORITY",
    "REQUIRED_CHECKS",
    "REVIEW_RECORD_TYPE",
    "applicability_snapshot",
    "resolve_all",
    "resolve_effective",
]
