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

ADR-0058 adds a second, independent demotion axis. Everything above answers "how
well is this checked?"; the scope cap answers "under which reading is it even
being asserted?". A claim whose verdict flips with a definitional reading is not
a proposition about the conjecture, and the reader meets that in the environment
name rather than in a footnote. The two axes compose by taking the weaker: a
convention-relative claim can be demoted further by a bad certificate, and never
promoted by a good one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .errors import PublicationValidationError
from .manuscript import Manuscript

#: Ordered strongest to weakest. The order is load-bearing: a probe that claims
#: a demotion is checked against this index, so "demoted" cannot be satisfied by
#: a sideways move.
EVIDENCE_CLASSES = (
    "kernel_checked_theorem",
    "exact_certificate_proposition",
    # ADR-0058. Inserted, never appended: strictly weaker than an exact
    # certificate proposition and strictly stronger than a proposal, because the
    # arithmetic is exact and only the reading is contested.
    "convention_relative_proposition",
    "proposal",
)

ENVIRONMENTS = {
    "kernel_checked_theorem": "adatheorem",
    "exact_certificate_proposition": "adaproposition",
    "convention_relative_proposition": "adaconditional",
    "proposal": "adaconjecture",
}

HEADINGS = {
    "kernel_checked_theorem": "Theorem",
    "exact_certificate_proposition": "Proposition",
    "convention_relative_proposition": "Proposition (convention-relative)",
    "proposal": "Conjecture",
}

#: ADR-0058 section 4.1, as data. The value is the *weakest class this scope
#: admits*; a claim already at or below it keeps what it had. ``unconditional``
#: is absent on purpose: it caps nothing, so the existing ladder stands.
SCOPE_CAPS = {
    "convention_relative": "convention_relative_proposition",
    "contested_unevaluated": "proposal",
    "no_reading_refutes": "proposal",
}

SCOPE_CAP_REASONS = {
    "convention_relative": (
        "the verdict matrix refutes under some enumerated readings and not under "
        "others, so the result is asserted relative to a reading rather than "
        "about the conjecture"
    ),
    "contested_unevaluated": (
        "at least one enumerated reading was never evaluated, so no sweep of the "
        "readings exists to be relative to"
    ),
    "no_reading_refutes": (
        "no enumerated reading yields a refutation, so the records support no "
        "resolution of the target at all"
    ),
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


def apply_scope_cap(
    manuscript: Manuscript, claim_id: str, base: EvidenceClassification
) -> EvidenceClassification:
    """Cap a classification at what its derived reading scope admits.

    The cap is read from the verdict matrix a claim *names*, not from whether the
    claim happens to carry a ``resolution_target``: dropping the target must not
    be a way to shed the cap while keeping the matrix. Only ever weakens.
    """

    matrix = manuscript.verdict_matrix_for(claim_id)
    if matrix is None:
        return base
    scope = manuscript.derived_scope(claim_id)
    cap = SCOPE_CAPS.get(str(scope))
    if cap is None:
        return base
    refs = tuple(dict.fromkeys(base.record_refs + (matrix.matrix_id, matrix.convention_id)))
    if EVIDENCE_CLASSES.index(base.evidence_class) >= EVIDENCE_CLASSES.index(cap):
        # Already at or below the cap. The scope still belongs in the record
        # references, because it is part of why the claim reads as it does.
        return replace(base, record_refs=refs)
    return replace(
        base,
        evidence_class=cap,
        environment=ENVIRONMENTS[cap],
        heading=HEADINGS[cap],
        reason=(
            f"{base.reason}; capped at {cap} because the derived scope is {scope}: "
            f"{SCOPE_CAP_REASONS[str(scope)]}"
        ),
        record_refs=refs,
    )


def classify_claim(manuscript: Manuscript, claim_id: str) -> EvidenceClassification:
    return apply_scope_cap(manuscript, claim_id, _classify_evidence(manuscript, claim_id))


def _classify_evidence(manuscript: Manuscript, claim_id: str) -> EvidenceClassification:
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
                # A partial formalization cannot create a theorem, but it must
                # not erase a separate exact certificate attached to the same
                # claim. Fall through to that independent evidence channel.
                if certificate is None:
                    return classification(
                        "proposal",
                        "kernel-checked, but the LaTeX/Lean representation is "
                        f"{claim['representation_status']} rather than verified",
                    )
            else:
                return classification(
                    "kernel_checked_theorem",
                    "kernel-checked with no unapproved assumption, on a verified representation",
                )
        elif outcome == "kernel_checked_approved_standard_axioms" and not unapproved:
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
        elif unapproved:
            return classification(
                "proposal",
                "the attestation carries unapproved assumptions "
                f"({', '.join(unapproved) or 'unnamed'})",
            )
        elif outcome != "kernel_checked":
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
                "an exact certificate closes the gap to zero in "
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
            f"an exact certificate separates the two values by {certificate['gap']} "
            f"in {certificate['arithmetic']} arithmetic with no floating point",
        )

    return classification("proposal", "no attestation and no exact certificate back this claim")
