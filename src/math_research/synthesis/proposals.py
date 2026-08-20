"""Captured proposal envelopes for nondeterministic generation.

Contract Section 12. A nondeterministically generated proposal is captured once,
immutably, and thereafter its identity and digest are explicit inputs to
normalization, admission, export, and replay. Replay never calls the generator,
and regeneration creates a new proposal identity even when content is equal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import CANONICALIZATION_VERSION
from .records import content_hash_value, identifier, text
from .serialization import canonical_hash, stable_id
from .state import SynthesisValidationError, ValueEnum, parse_enum


class GenerationOutcome(ValueEnum):
    """Captured outcome, including refusal and failure (Section 12)."""

    PRODUCED = "produced"
    REFUSED = "refused"
    FAILED = "failed"


class GeneratorCalledDuringReplay(SynthesisValidationError):
    """Replay attempted to invoke a generator."""


def _identity_preimage(
    *,
    generator_id: str,
    generator_version: str,
    generator_configuration_digest: str,
    prompt_input_identities: Sequence[str],
    source_graph_snapshot_identity: str,
    seed: int | None,
    ordered_event_identity: str,
    parent_branch_id: str | None,
    proposal_digest_value: str,
    resource_units_consumed: int,
    outcome: GenerationOutcome,
    failure_detail: str,
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "generator_id": generator_id,
        "generator_version": generator_version,
        "generator_configuration_digest": generator_configuration_digest,
        "prompt_input_identities": list(prompt_input_identities),
        "source_graph_snapshot_identity": source_graph_snapshot_identity,
        "seed": seed,
        "ordered_event_identity": ordered_event_identity,
        "parent_branch_id": parent_branch_id,
        "proposal_digest": proposal_digest_value,
        "resource_units_consumed": resource_units_consumed,
        "outcome": outcome.value,
        "failure_detail": failure_detail,
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class CapturedProposal:
    """One immutable capture of a nondeterministic generation."""

    proposal_id: str
    generator_id: str
    generator_version: str
    generator_configuration_digest: str
    prompt_input_identities: tuple[str, ...]
    source_graph_snapshot_identity: str
    seed: int | None
    ordered_event_identity: str
    parent_branch_id: str | None
    raw_payload: str
    proposal_digest: str
    resource_units_consumed: int
    outcome: GenerationOutcome
    failure_detail: str

    def __post_init__(self) -> None:
        identifier(self.proposal_id, field="proposal_id")
        identifier(self.generator_id, field="generator_id")
        text(self.generator_version, field="generator_version")
        text(self.ordered_event_identity, field="ordered_event_identity")
        content_hash_value(
            self.generator_configuration_digest, field="generator_configuration_digest"
        )
        content_hash_value(
            self.source_graph_snapshot_identity, field="source_graph_snapshot_identity"
        )
        if not isinstance(self.raw_payload, str) or not isinstance(self.failure_detail, str):
            raise SynthesisValidationError("proposal payload and failure detail must be strings")
        for input_id in self.prompt_input_identities:
            identifier(input_id, field="prompt_input_identities[]")
        if self.parent_branch_id is not None:
            identifier(self.parent_branch_id, field="parent_branch_id")
        if self.outcome is GenerationOutcome.PRODUCED and not self.raw_payload:
            raise SynthesisValidationError("a produced proposal must capture its raw payload")
        if self.outcome is not GenerationOutcome.PRODUCED and not self.failure_detail:
            raise SynthesisValidationError(
                "a refused or failed generation must capture its failure detail"
            )
        if isinstance(self.resource_units_consumed, bool) or not isinstance(
            self.resource_units_consumed, int
        ):
            raise SynthesisValidationError("resource units consumed must be an integer")
        if self.resource_units_consumed < 0:
            raise SynthesisValidationError("resource units consumed must be zero or positive")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise SynthesisValidationError("seed must be an integer or null")
        expected = proposal_digest(self.raw_payload)
        if self.proposal_digest != expected:
            raise SynthesisValidationError("proposal digest does not match the captured payload")
        expected_id = stable_id(
            "captured-proposal",
            _identity_preimage(
                generator_id=self.generator_id,
                generator_version=self.generator_version,
                generator_configuration_digest=self.generator_configuration_digest,
                prompt_input_identities=self.prompt_input_identities,
                source_graph_snapshot_identity=self.source_graph_snapshot_identity,
                seed=self.seed,
                ordered_event_identity=self.ordered_event_identity,
                parent_branch_id=self.parent_branch_id,
                proposal_digest_value=self.proposal_digest,
                resource_units_consumed=self.resource_units_consumed,
                outcome=self.outcome,
                failure_detail=self.failure_detail,
            ),
        )
        if self.proposal_id != expected_id:
            raise SynthesisValidationError("captured proposal identity does not match its inputs")

    @classmethod
    def from_value(cls, value: object) -> CapturedProposal:
        fields = frozenset(
            {
                "proposal_id",
                "generator_id",
                "generator_version",
                "generator_configuration_digest",
                "prompt_input_identities",
                "source_graph_snapshot_identity",
                "seed",
                "ordered_event_identity",
                "parent_branch_id",
                "raw_payload",
                "proposal_digest",
                "resource_units_consumed",
                "outcome",
                "failure_detail",
                "canonicalization_version",
            }
        )
        if not isinstance(value, Mapping) or set(value) != fields:
            raise SynthesisValidationError("captured proposal field set is not exact")
        if value["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise SynthesisValidationError("captured proposal canonicalization version mismatch")
        inputs = value["prompt_input_identities"]
        if isinstance(inputs, (str, bytes)) or not isinstance(inputs, Sequence):
            raise SynthesisValidationError("prompt_input_identities must be a list")
        return cls(
            proposal_id=value["proposal_id"],
            generator_id=value["generator_id"],
            generator_version=value["generator_version"],
            generator_configuration_digest=value["generator_configuration_digest"],
            prompt_input_identities=tuple(inputs),
            source_graph_snapshot_identity=value["source_graph_snapshot_identity"],
            seed=value["seed"],
            ordered_event_identity=value["ordered_event_identity"],
            parent_branch_id=value["parent_branch_id"],
            raw_payload=value["raw_payload"],
            proposal_digest=value["proposal_digest"],
            resource_units_consumed=value["resource_units_consumed"],
            outcome=parse_enum(GenerationOutcome, value["outcome"], field="outcome"),
            failure_detail=value["failure_detail"],
        )

    def value(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "generator_configuration_digest": self.generator_configuration_digest,
            "prompt_input_identities": list(self.prompt_input_identities),
            "source_graph_snapshot_identity": self.source_graph_snapshot_identity,
            "seed": self.seed,
            "ordered_event_identity": self.ordered_event_identity,
            "parent_branch_id": self.parent_branch_id,
            "raw_payload": self.raw_payload,
            "proposal_digest": self.proposal_digest,
            "resource_units_consumed": self.resource_units_consumed,
            "outcome": self.outcome.value,
            "failure_detail": self.failure_detail,
            "canonicalization_version": CANONICALIZATION_VERSION,
        }


def proposal_digest(raw_payload: str) -> str:
    return canonical_hash(
        {"canonicalization_version": CANONICALIZATION_VERSION, "raw_payload": raw_payload}
    )


def capture(
    *,
    generator_id: str,
    generator_version: str,
    generator_configuration: Mapping[str, Any],
    prompt_input_identities: Sequence[str],
    source_graph_snapshot_identity: str,
    ordered_event_identity: str,
    raw_payload: str,
    outcome: GenerationOutcome | str = GenerationOutcome.PRODUCED,
    seed: int | None = None,
    parent_branch_id: str | None = None,
    resource_units_consumed: int = 0,
    failure_detail: str = "",
) -> CapturedProposal:
    """Capture one generation.

    `ordered_event_identity` is part of the proposal identity, so regenerating
    identical content at a later ordered position yields a new proposal id.
    """
    resolved = parse_enum(GenerationOutcome, outcome, field="outcome")
    configuration_digest = canonical_hash(dict(generator_configuration))
    digest = proposal_digest(raw_payload)
    proposal_id = stable_id(
        "captured-proposal",
        _identity_preimage(
            generator_id=generator_id,
            generator_version=generator_version,
            generator_configuration_digest=configuration_digest,
            prompt_input_identities=prompt_input_identities,
            source_graph_snapshot_identity=source_graph_snapshot_identity,
            seed=seed,
            ordered_event_identity=ordered_event_identity,
            parent_branch_id=parent_branch_id,
            proposal_digest_value=digest,
            resource_units_consumed=resource_units_consumed,
            outcome=resolved,
            failure_detail=failure_detail,
        ),
    )
    return CapturedProposal(
        proposal_id=proposal_id,
        generator_id=generator_id,
        generator_version=generator_version,
        generator_configuration_digest=configuration_digest,
        prompt_input_identities=tuple(prompt_input_identities),
        source_graph_snapshot_identity=source_graph_snapshot_identity,
        seed=seed,
        ordered_event_identity=ordered_event_identity,
        parent_branch_id=parent_branch_id,
        raw_payload=raw_payload,
        proposal_digest=digest,
        resource_units_consumed=resource_units_consumed,
        outcome=resolved,
        failure_detail=failure_detail,
    )


class ProposalStore:
    """Immutable capture store with a replay mode that forbids generation."""

    def __init__(self, *, replay: bool = False) -> None:
        self.replay = replay
        self._captures: dict[str, CapturedProposal] = {}

    def captures(self) -> tuple[CapturedProposal, ...]:
        return tuple(self._captures[key] for key in sorted(self._captures))

    def get(self, proposal_id: str) -> CapturedProposal:
        if proposal_id not in self._captures:
            raise KeyError(proposal_id)
        return self._captures[proposal_id]

    def generate(self, generator, **kwargs) -> CapturedProposal:
        """Invoke a generator and capture the result.

        Refused in replay mode: Section 12 requires that replay never calls the
        generator.
        """
        if self.replay:
            raise GeneratorCalledDuringReplay(
                "replay must consume captured proposals and never invoke a generator"
            )
        raw_payload = generator()
        captured = capture(raw_payload=raw_payload, **kwargs)
        return self.admit(captured)

    def admit(self, captured: CapturedProposal) -> CapturedProposal:
        """Store a capture. An identical id must carry identical content."""
        existing = self._captures.get(captured.proposal_id)
        if existing is not None:
            if existing.value() != captured.value():
                raise SynthesisValidationError(
                    "captured proposal identity cannot be rewritten"
                )
            return existing
        self._captures[captured.proposal_id] = captured
        return captured

    def value(self) -> dict[str, Any]:
        return {"captured_proposals": [item.value() for item in self.captures()]}


__all__ = [
    "CapturedProposal",
    "GenerationOutcome",
    "GeneratorCalledDuringReplay",
    "ProposalStore",
    "capture",
    "proposal_digest",
]
