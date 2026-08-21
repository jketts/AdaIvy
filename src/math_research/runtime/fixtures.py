"""Deterministic offline gateways, so the runtime is testable without a model.

Nothing here is a model and nothing here pretends to be. Every result is
labelled `provider="fixture"` and `usage_source="fixture"`, and the report
renderer reads those labels back out, so an offline rehearsal can never be
mistaken for a live run in the record it leaves behind.

The point of the rehearsal gateway is that the *runtime* -- iteration,
duplicate detection, stagnation, bounds, replay -- is exercised on the offline
`make check` path, where a provider, a key, and a network are all absent.
"""

from __future__ import annotations

import json
from typing import Any

from ..phase2.records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderSchemaPreparation,
)

FIXTURE_PROVIDER = "fixture"
FIXTURE_MODEL = "offline-rehearsal-v1"


def _usage(input_tokens: int = 120, output_tokens: int = 80) -> ModelUsage:
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        usage_source="fixture",
    )


def _result(structured: dict[str, Any]) -> ModelResult:
    return ModelResult(
        status=ModelResultStatus.SUCCEEDED,
        provider=FIXTURE_PROVIDER,
        model_identifier=FIXTURE_MODEL,
        capabilities=("structured_output", "deterministic"),
        structured_output=json.dumps(structured, sort_keys=True, separators=(",", ":")),
        declared_rationale=str(structured.get("declared_rationale", "")),
        refusal=None,
        usage=_usage(),
        retry_classification="none",
        provider_request_id=None,
    )


class RehearsalGateway:
    """Offline stand-in that varies its output per call, then repeats itself.

    The repetition is deliberate. After `distinct_attempts` proposals it starts
    resubmitting the last one, which is what drives the duplicate-detection and
    stagnation paths in a run nobody had to pay for. `verdict` chooses what the
    isolated verifier half returns, so the same fixture can rehearse a run that
    ends in review and one that never does.
    """

    def __init__(
        self,
        *,
        target_claim_id: str,
        referenced_entity_ids: tuple[str, ...],
        distinct_attempts: int = 3,
        verdict: str = "unresolved",
        final_verdict: str | None = None,
        final_after: int | None = None,
    ) -> None:
        self.target_claim_id = target_claim_id
        self.referenced_entity_ids = tuple(referenced_entity_ids)
        self.distinct_attempts = max(1, distinct_attempts)
        self.verdict = verdict
        self.final_verdict = final_verdict
        self.final_after = final_after
        self.requests: list[ModelRequest] = []
        self._proposals = 0
        self._verdicts = 0

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation | None:
        return None

    def complete(
        self, request: ModelRequest, preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        self.requests.append(request)
        if request.purpose == "proposer":
            return self._propose()
        if request.purpose == "verifier":
            return self._verify(request)
        return ModelResult(
            status=ModelResultStatus.FAILED, provider=FIXTURE_PROVIDER,
            model_identifier=FIXTURE_MODEL, capabilities=(), structured_output=None,
            declared_rationale=None, refusal=None, usage=_usage(0, 0),
            retry_classification=f"fatal:unsupported_purpose:{request.purpose}",
        )

    def _propose(self) -> ModelResult:
        self._proposals += 1
        index = min(self._proposals, self.distinct_attempts)
        return _result({
            "schema_version": "2.0.0",
            "result_type": "proof_attempt",
            "target_claim_id": self.target_claim_id,
            "mathematical_payload": {
                "statement": f"Offline rehearsal attempt {index} restates the frozen target.",
                "steps": [
                    f"Rehearsal step {index}.1 -- this text is a fixture, not an argument.",
                    f"Rehearsal step {index}.2 -- it establishes nothing.",
                ],
                "witness": None,
            },
            "declared_rationale": f"offline rehearsal proposal {index}",
            "referenced_entity_ids": list(self.referenced_entity_ids),
        })

    def _verify(self, request: ModelRequest) -> ModelResult:
        self._verdicts += 1
        context = json.loads(request.serialized_context)
        artifact_hash = context["candidate"]["artifact_hash"]
        recommendation = self.verdict
        if self.final_verdict is not None and self.final_after is not None:
            if self._verdicts >= self.final_after:
                recommendation = self.final_verdict
        return _result({
            "schema_version": "2.0.0",
            "result_type": "finding",
            "target_claim_id": self.target_claim_id,
            "candidate_artifact_hash": artifact_hash,
            "findings": [{
                "code": f"rehearsal.gap.{self._verdicts}",
                "outcome": "unresolved",
                "detail": "Offline rehearsal finding. Carries no mathematical content.",
                "referenced_entity_ids": [self.target_claim_id],
            }],
            "recommendation": recommendation,
            "declared_rationale": f"offline rehearsal verdict {self._verdicts}",
        })
