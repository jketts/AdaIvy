"""Evidence class decides the environment. Demotion is the default.

The renderer never accepts an environment name as input. There is no manuscript
field, flag, or option that promotes a claim: a class is computed from the
records that back it, and every missing record makes the rendered claim weaker
rather than stronger.

A certificate is classified against the *role* the claim assigns it. A zero gap
determines an optimum and separates nothing; a nonzero gap separates two values
and determines nothing. Both mismatches demote, because reading one as the other
is exactly how an exact result becomes an overstated one.

``kernel_checked_approved_standard_axioms`` is deliberately *not* a theorem
here. The axioms it leans on are approved, so the claim is reportable, but the
reader is entitled to see the dependence in the environment rather than in an
appendix they may not reach.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import PublicationValidationError
from .manuscript import Manuscript

#: Ordered strongest to weakest. The order is load-bearing: a probe that claims
#: a demotion is checked against this index, so "demoted" cannot be satisfied by
#: a sideways move.
EVIDENCE_CLASSES = (
    "kernel_checked_theorem",
    "exact_certificate_proposition",
    "proposal",
)

ENVIRONMENTS = {
    "kernel_checked_theorem": "adatheorem",
    "exact_certificate_proposition": "adaproposition",
    "proposal": "adaconjecture",
}

HEADINGS = {
    "kernel_checked_theorem": "Theorem",
    "exact_certificate_proposition": "Proposition",
    "proposal": "Conjecture",
}


@dataclass(frozen=True, slots=True)
class EvidenceClassification:
    claim_id: str
    evidence_class: str
    environment: str
    heading: str
    reason: str
    record_refs: tuple[str, ...]
    approved_axioms: tuple[str, ...]
    unapproved_assumptions: tuple[str, ...]

    @property
    def strength(self) -> int:
        return EVIDENCE_CLASSES.index(self.evidence_class)


def classify_claim(manuscript: Manuscript, claim_id: str) -> EvidenceClassification:
    if claim_id not in manuscript.claims:
        raise PublicationValidationError("record_ref_unresolved", f"claim {claim_id!r}")
    claim: Mapping[str, Any] = manuscript.claims[claim_id]
    refs: list[str] = [claim_id]
    attestation_id = claim["attestation_id"]
    certificate_id = claim["certificate_id"]
    attestation = manuscript.attestations[attestation_id] if attestation_id else None
    certificate = manuscript.certificates[certificate_id] if certificate_id else None
    if attestation is not None:
        refs.append(str(attestation_id))
    if certificate is not None:
        refs.append(str(certificate_id))
    refs.extend(str(item) for item in claim["citations"])
    approved = tuple(attestation["approved_axioms"]) if attestation else ()
    unapproved = tuple(attestation["unapproved_assumptions"]) if attestation else ()

    def classification(evidence_class: str, reason: str) -> EvidenceClassification:
        return EvidenceClassification(
            claim_id=claim_id, evidence_class=evidence_class,
            environment=ENVIRONMENTS[evidence_class], heading=HEADINGS[evidence_class],
            reason=reason, record_refs=tuple(refs), approved_axioms=approved,
            unapproved_assumptions=unapproved,
        )

    if attestation is not None:
        outcome = attestation["outcome"]
        if outcome == "kernel_checked" and not unapproved:
            if claim["representation_status"] != "verified":
                return classification(
                    "proposal",
                    "kernel-checked, but the LaTeX/Lean representation is "
                    f"{claim['representation_status']} rather than verified",
                )
            return classification(
                "kernel_checked_theorem",
                "kernel-checked with no unapproved assumption, on a verified representation",
            )
        if outcome == "kernel_checked_approved_standard_axioms" and not unapproved:
            if claim["representation_status"] != "verified":
                return classification(
                    "proposal",
                    "kernel-checked on approved axioms, but the representation is "
                    f"{claim['representation_status']}",
                )
            return classification(
                "exact_certificate_proposition",
                "kernel-checked on approved standard axioms, which the environment names",
            )
        if unapproved:
            return classification(
                "proposal",
                "the attestation carries unapproved assumptions "
                f"({', '.join(unapproved) or 'unnamed'})",
            )
        return classification("proposal", f"the attestation outcome is {outcome}")

    if certificate is not None:
        role = claim["certificate_role"]
        gap_is_zero = certificate["gap"] == "0"
        if role == "determines_optimum":
            if not gap_is_zero:
                return classification(
                    "proposal",
                    f"the exact certificate leaves a gap of {certificate['gap']}, so it bounds "
                    "the optimum without determining it",
                )
            return classification(
                "exact_certificate_proposition",
                "an exact primal/dual certificate closes the gap to zero in "
                f"{certificate['arithmetic']} arithmetic with no floating point",
            )
        if gap_is_zero:
            return classification(
                "proposal",
                "the claim asserts a separation, but the certificate closes the gap to zero, "
                "so it certifies that there is nothing to separate",
            )
        return classification(
            "exact_certificate_proposition",
            f"an exact primal/dual certificate separates the two values by {certificate['gap']} "
            f"in {certificate['arithmetic']} arithmetic with no floating point",
        )

    return classification("proposal", "no attestation and no exact certificate back this claim")
