"""Bounded proof repair orchestrated strictly above the sealed Phase 3B checker.

ADR-0040. This module adds no Lean capability. It resubmits a *new*, separately
hashed request when the sealed checker reports that Lean failed to elaborate a
proof, and it stops for every other outcome. It never edits the sealed runtime,
the launcher, the fixed invocation, the wrapper generator, or the validator; it
calls `FormalCheckingService.check` exactly as an operator would.

Three properties carry the slice and are enforced here rather than assumed:

- **The theorem is frozen.** A proposer returns a proof fragment and nothing
  else. The declaration name, target statement, import manifest, and assumption
  manifest are copied from the origin request and re-checked against their
  origin hashes on every attempt, so a repair cannot weaken the statement it
  claims to prove. This is the anti-premise-smuggling control.
- **Only elaboration failure is repairable.** A policy rejection is never fed
  back, because a validator diagnostic is a description of how to evade the
  validator. Unapproved assumptions, meaning-test failures, timeouts, output
  limits, and sandbox failures are all terminal for the same class of reason:
  repairing them optimizes against a check rather than toward a proof.
- **Nothing is promoted.** Every attempt stays a proposal and the session
  reports `epistemic_warrant_created = False` unconditionally.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from ..domain.entities import OpaqueId
from . import HASH_PROFILE, SCHEMA_VERSION
from .records import (
    DeclaredAssumption,
    FormalCheckFinding,
    FormalCheckOutcome,
    FormalCheckRequest,
    SourceKind,
)
from .serialization import canonical_bytes, canonical_hash, public_value, sha256_bytes, stable_id
from .service import FormalCheckingService
from .validation import RequestValidationError, parse_request_bytes

REPAIR_POLICY_VERSION = "phase3b-proof-repair-v1"

#: The only outcome a repair attempt may follow. See the module docstring.
REPAIRABLE_OUTCOMES = frozenset({FormalCheckOutcome.ELABORATION_FAILURE})


class RepairTermination(str, Enum):
    """Why a session stopped. Exactly one applies to a completed session."""

    KERNEL_CHECKED = "kernel_checked"
    OUTCOME_NOT_REPAIRABLE = "outcome_not_repairable"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    PROPOSER_DECLINED = "proposer_declined"
    PROPOSER_REJECTED = "proposer_rejected"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    ORIGIN_UNPARSABLE = "origin_unparsable"


@dataclass(frozen=True, slots=True)
class RepairLimits:
    """Hard per-session bounds. `max_attempts` counts the origin submission."""

    max_attempts: int = 4
    max_diagnostic_bytes: int = 4_096

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 16:
            raise ValueError("max_attempts must be between 1 and 16")
        if not 256 <= self.max_diagnostic_bytes <= 65_536:
            raise ValueError("max_diagnostic_bytes must be between 256 and 65536")


@dataclass(frozen=True, slots=True)
class RepairContext:
    """Everything a proposer may see. Deliberately read-only and bounded."""

    attempt_index: int
    attempts_remaining: int
    declaration_name: str
    target_statement: str
    imports: tuple[str, ...]
    assumptions: tuple[DeclaredAssumption, ...]
    rejected_proof_fragment: str
    diagnostic: str
    diagnostic_hash: str
    diagnostic_truncated: bool


@dataclass(frozen=True, slots=True)
class ProposedProof:
    """A proposer's whole output surface: one proof fragment."""

    proof_fragment: str


class ProofProposer(Protocol):
    """Return a replacement proof fragment, or `None` to decline.

    A proposer is untrusted. Its output is validated by the unchanged Phase 3B
    validator and checked by the unchanged sealed runtime. Returning `None` is a
    first-class answer and ends the session without consuming a further attempt.

    A live implementation must treat `RepairContext.diagnostic` as data. It is
    Lean's output, influenced by the submitted proof text, and must never be
    followed as instruction.
    """

    def propose(self, context: RepairContext) -> ProposedProof | None: ...


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    """One submission to the sealed checker, with its own request and finding."""

    attempt_index: int
    source_kind: SourceKind
    request_id: OpaqueId
    request_hash: str
    proof_fragment_hash: str
    diagnostic_hash: str | None
    outcome: FormalCheckOutcome
    finding_id: OpaqueId
    finding_content_hash: str
    finding: FormalCheckFinding


@dataclass(frozen=True, slots=True)
class RepairSession:
    """Append-only record of a bounded repair run. Never a trust promotion."""

    id: OpaqueId
    claim_id: OpaqueId
    origin_request_id: OpaqueId
    declaration_name: str
    target_statement_hash: str
    import_manifest_hash: str
    assumption_manifest_hash: str
    attempts: tuple[RepairAttempt, ...]
    termination: RepairTermination
    attempts_used: int
    attempts_allowed: int
    proposer_calls: int
    theorem_identity_preserved: bool
    epistemic_warrant_created: bool
    created_at: str
    content_hash: str
    policy_version: str = REPAIR_POLICY_VERSION
    hash_profile: str = HASH_PROFILE
    schema_version: str = SCHEMA_VERSION

    @property
    def kernel_checked(self) -> bool:
        return self.termination is RepairTermination.KERNEL_CHECKED

    @property
    def final_finding(self) -> FormalCheckFinding | None:
        return self.attempts[-1].finding if self.attempts else None


def _identity_hashes(request: FormalCheckRequest) -> tuple[str, str, str]:
    """Hash the parts of a request a repair may never change."""
    return (
        canonical_hash(request.target_statement),
        canonical_hash(list(request.imports)),
        canonical_hash([public_value(item) for item in request.assumptions]),
    )


def _bounded_diagnostic(finding: FormalCheckFinding, *, limit: int) -> tuple[str, str, bool]:
    """Extract a bounded, hashed diagnostic from retained capture only.

    The full streams are never read here; `RawExecution` already holds only
    bounded retained bytes plus whole-stream hashes. Truncation is reported so a
    proposer cannot mistake a clipped diagnostic for a complete one.
    """
    execution = finding.execution
    if execution is None:
        return "", canonical_hash(""), False
    parts = [part for part in (execution.stderr.retained_utf8, execution.stdout.retained_utf8) if part]
    text = "\n".join(parts).replace("\x00", "")
    encoded = text.encode("utf-8")
    truncated = len(encoded) > limit
    if truncated:
        text = encoded[:limit].decode("utf-8", errors="ignore")
    return text, canonical_hash(text), truncated


def _repaired_request_bytes(origin: FormalCheckRequest, *, fragment: str, attempt_index: int) -> tuple[bytes, OpaqueId]:
    """Build a new, separately identified request that differs only in its proof.

    The identifier is content-derived, so a repaired candidate is a distinct
    record rather than a mutation of the rejected one.
    """
    request_id = stable_id(
        "formal-request",
        {
            "origin": origin.request_id.value,
            "attempt": attempt_index,
            "fragment": sha256_bytes(fragment.encode("utf-8")),
        },
    )
    candidate = replace(origin, request_id=request_id, source_kind=SourceKind.MODEL, proof_fragment=fragment)
    return canonical_bytes(candidate), request_id


def _session_content_hash(session: RepairSession) -> str:
    """Hash session meaning: identity, ordering, and each attempt's finding hash.

    Findings enter by content hash rather than by value so the session hash does
    not inherit the elapsed-time nondeterminism the finding hash already strips.
    """
    return canonical_hash(
        {
            "assumption_manifest_hash": session.assumption_manifest_hash,
            "attempts": [
                {
                    "attempt_index": attempt.attempt_index,
                    "diagnostic_hash": attempt.diagnostic_hash,
                    "finding_content_hash": attempt.finding_content_hash,
                    "outcome": attempt.outcome.value,
                    "proof_fragment_hash": attempt.proof_fragment_hash,
                    "request_hash": attempt.request_hash,
                    "request_id": attempt.request_id.value,
                    "source_kind": attempt.source_kind.value,
                }
                for attempt in session.attempts
            ],
            "attempts_allowed": session.attempts_allowed,
            "claim_id": session.claim_id.value,
            "declaration_name": session.declaration_name,
            "epistemic_warrant_created": session.epistemic_warrant_created,
            "import_manifest_hash": session.import_manifest_hash,
            "origin_request_id": session.origin_request_id.value,
            "policy_version": session.policy_version,
            "schema_version": session.schema_version,
            "target_statement_hash": session.target_statement_hash,
            "termination": session.termination.value,
            "theorem_identity_preserved": session.theorem_identity_preserved,
        }
    )


class TheoremIdentityViolation(RuntimeError):
    """Raised if a candidate would change the theorem rather than the proof.

    Structurally unreachable while a proposer returns only a fragment. It is
    raised rather than recorded because a session that cannot vouch for its own
    theorem identity has no meaning worth persisting.
    """


class ProofRepairService:
    """Bounded repair loop above an unchanged `FormalCheckingService`."""

    def __init__(
        self,
        checker: FormalCheckingService,
        proposer: ProofProposer,
        limits: RepairLimits | None = None,
    ) -> None:
        self.checker = checker
        self.proposer = proposer
        self.limits = limits or RepairLimits()

    def run(self, request_bytes: bytes, *, created_at: str) -> RepairSession:
        origin_finding = self.checker.check(request_bytes, created_at=created_at)
        try:
            origin = parse_request_bytes(request_bytes)
        except RequestValidationError:
            # The checker already produced the policy-rejection finding; a request
            # that does not parse has no theorem identity to freeze, so no repair
            # is possible and none is attempted.
            return self._finish(
                origin=None,
                request_bytes=request_bytes,
                attempts=(self._attempt(0, request_bytes, None, None, origin_finding, SourceKind.EXTERNAL),),
                termination=RepairTermination.ORIGIN_UNPARSABLE,
                proposer_calls=0,
                created_at=created_at,
            )

        identity = _identity_hashes(origin)
        attempts = [
            self._attempt(0, request_bytes, origin.request_id, None, origin_finding, origin.source_kind)
        ]
        current_fragment = origin.proof_fragment
        seen_fragments = {sha256_bytes(origin.proof_fragment.encode("utf-8"))}
        proposer_calls = 0
        termination = RepairTermination.OUTCOME_NOT_REPAIRABLE

        while True:
            current = attempts[-1]
            if current.outcome in {
                FormalCheckOutcome.KERNEL_CHECKED,
                FormalCheckOutcome.KERNEL_CHECKED_APPROVED_AXIOMS,
            }:
                termination = RepairTermination.KERNEL_CHECKED
                break
            if current.outcome not in REPAIRABLE_OUTCOMES:
                termination = RepairTermination.OUTCOME_NOT_REPAIRABLE
                break
            if len(attempts) >= self.limits.max_attempts:
                termination = RepairTermination.ATTEMPTS_EXHAUSTED
                break

            diagnostic, diagnostic_hash, truncated = _bounded_diagnostic(
                current.finding, limit=self.limits.max_diagnostic_bytes
            )
            context = RepairContext(
                attempt_index=len(attempts),
                attempts_remaining=self.limits.max_attempts - len(attempts),
                declaration_name=origin.declaration_name,
                target_statement=origin.target_statement,
                imports=origin.imports,
                assumptions=origin.assumptions,
                rejected_proof_fragment=current_fragment,
                diagnostic=diagnostic,
                diagnostic_hash=diagnostic_hash,
                diagnostic_truncated=truncated,
            )
            proposer_calls += 1
            proposed = self.proposer.propose(context)
            if proposed is None:
                termination = RepairTermination.PROPOSER_DECLINED
                break

            fragment_hash = sha256_bytes(proposed.proof_fragment.encode("utf-8"))
            if fragment_hash in seen_fragments:
                # Resubmitting an identical candidate cannot produce a different
                # kernel result and would only spend the remaining budget.
                termination = RepairTermination.DUPLICATE_CANDIDATE
                break
            seen_fragments.add(fragment_hash)
            current_fragment = proposed.proof_fragment

            candidate_bytes, candidate_id = _repaired_request_bytes(
                origin, fragment=proposed.proof_fragment, attempt_index=len(attempts)
            )
            identity_verified = self._assert_identity(candidate_bytes, identity, origin)
            finding = self.checker.check(candidate_bytes, created_at=created_at)
            attempts.append(
                self._attempt(len(attempts), candidate_bytes, candidate_id, diagnostic_hash, finding, SourceKind.MODEL)
            )
            if finding.outcome is FormalCheckOutcome.POLICY_REJECTION:
                # The validator refused a model-authored fragment. That is the
                # validator working, not a proof error, so the loop stops rather
                # than iterating against the validator.
                termination = RepairTermination.PROPOSER_REJECTED
                break
            if not identity_verified:
                # Unreachable: a candidate that does not parse can only produce a
                # policy rejection, handled above. Asserted so that a future
                # change to either path cannot admit an unchecked theorem.
                raise TheoremIdentityViolation("an unvalidated candidate passed the checker")

        return self._finish(
            origin=origin,
            request_bytes=request_bytes,
            attempts=tuple(attempts),
            termination=termination,
            proposer_calls=proposer_calls,
            created_at=created_at,
        )

    @staticmethod
    def _assert_identity(candidate_bytes: bytes, identity: tuple[str, str, str], origin: FormalCheckRequest) -> bool:
        """Re-derive the frozen theorem identity from the bytes about to be sent.

        Returns whether identity was verifiable. A candidate that does not parse
        is not an identity violation: the unchanged validator refuses it and the
        session records that policy rejection. `False` means "not verifiable
        here", never "accepted".
        """
        try:
            candidate = parse_request_bytes(candidate_bytes)
        except RequestValidationError:
            return False
        if _identity_hashes(candidate) != identity:
            raise TheoremIdentityViolation("a repair attempt altered the frozen theorem identity")
        if candidate.declaration_name != origin.declaration_name:
            raise TheoremIdentityViolation("a repair attempt altered the declaration name")
        if candidate.claim_id != origin.claim_id:
            raise TheoremIdentityViolation("a repair attempt altered the claim identity")
        if candidate.meaning_tests != origin.meaning_tests:
            raise TheoremIdentityViolation("a repair attempt altered the meaning tests")
        return True

    @staticmethod
    def _attempt(
        index: int,
        request_bytes: bytes,
        request_id: OpaqueId | None,
        diagnostic_hash: str | None,
        finding: FormalCheckFinding,
        source_kind: SourceKind,
    ) -> RepairAttempt:
        manifest = finding.wrapper_manifest
        return RepairAttempt(
            attempt_index=index,
            source_kind=source_kind,
            request_id=request_id or finding.request_id,
            request_hash=sha256_bytes(request_bytes),
            proof_fragment_hash=manifest.proof_fragment_hash if manifest else canonical_hash(None),
            diagnostic_hash=diagnostic_hash,
            outcome=finding.outcome,
            finding_id=finding.id,
            finding_content_hash=finding.content_hash,
            finding=finding,
        )

    def _finish(
        self,
        *,
        origin: FormalCheckRequest | None,
        request_bytes: bytes,
        attempts: tuple[RepairAttempt, ...],
        termination: RepairTermination,
        proposer_calls: int,
        created_at: str,
    ) -> RepairSession:
        source_hash = sha256_bytes(request_bytes)
        identity = _identity_hashes(origin) if origin else (canonical_hash(None),) * 3
        provisional = RepairSession(
            id=stable_id("repair-session", {"source": source_hash, "termination": termination.value, "attempts": len(attempts)}),
            claim_id=origin.claim_id if origin else attempts[0].finding.claim_id,
            origin_request_id=origin.request_id if origin else attempts[0].finding.request_id,
            declaration_name=origin.declaration_name if origin else "",
            target_statement_hash=identity[0],
            import_manifest_hash=identity[1],
            assumption_manifest_hash=identity[2],
            attempts=attempts,
            termination=termination,
            attempts_used=len(attempts),
            attempts_allowed=self.limits.max_attempts,
            proposer_calls=proposer_calls,
            theorem_identity_preserved=True,
            epistemic_warrant_created=False,
            created_at=created_at,
            content_hash="",
        )
        return replace(provisional, content_hash=_session_content_hash(provisional))
