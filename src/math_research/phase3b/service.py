"""Application service joining validation, wrapper generation, and the formal tool."""

from __future__ import annotations

from dataclasses import replace

from .adapter import DockerLeanAdapter
from .records import FormalCheckFinding, FormalCheckOutcome, FormalCheckRequest, PolicyRejection, SourceKind
from .serialization import canonical_hash, sha256_bytes, stable_id
from .validation import RequestValidationError, parse_request_bytes
from .wrapper import generate_wrapper


class FormalCheckingService:
    def __init__(self, adapter: DockerLeanAdapter) -> None:
        self.adapter = adapter

    def check(self, request_bytes: bytes, *, created_at: str) -> FormalCheckFinding:
        try:
            request = parse_request_bytes(request_bytes)
        except RequestValidationError as error:
            return self._policy_finding(request_bytes, error.rejections, created_at=created_at)
        self.adapter.validate(request)
        try:
            wrapper = generate_wrapper(request)
        except ValueError as error:
            rejection = PolicyRejection("generated_wrapper_too_large", "$", str(error))
            return self._policy_finding(request_bytes, (rejection,), request=request, created_at=created_at)
        execution = self.adapter.execute(wrapper)
        return self.adapter.verify_output(request, wrapper, execution, created_at=created_at)

    @staticmethod
    def _policy_finding(
        request_bytes: bytes,
        rejections: tuple[PolicyRejection, ...],
        *,
        created_at: str,
        request: FormalCheckRequest | None = None,
    ) -> FormalCheckFinding:
        source_hash = sha256_bytes(request_bytes)
        provisional = FormalCheckFinding(
            id=stable_id("formal-finding", {"source": source_hash, "rejections": rejections}),
            request_id=request.request_id if request else stable_id("rejected-request", {"source": source_hash}),
            claim_id=request.claim_id if request else stable_id("rejected-claim", {"source": source_hash}),
            semantic_alignment_id=request.semantic_alignment_id if request else None,
            source_kind=request.source_kind if request else SourceKind.EXTERNAL,
            outcome=FormalCheckOutcome.POLICY_REJECTION, disposition="proposal", trust_effect="none",
            exact_statement_only=True, approved_axioms=(), unapproved_assumptions=(), policy_rejections=rejections,
            wrapper_manifest=None, execution=None, meaning_tests_diagnostic_only=True,
            semantic_alignment_approved=False, source_applicability_approved=False, novelty_approved=False,
            significance_approved=False, contribution_approved=False, epistemic_warrant_created=False,
            created_at=created_at, content_hash="",
        )
        return replace(provisional, content_hash=canonical_hash(provisional))
