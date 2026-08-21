"""Ports for the noncommuting Phase 5 expansion.

ADR-0035 scopes this slice to *verification*: a certificate is a human input
that enters through the authorized-human-steering boundary, and no
implementation of :class:`CertificateSource` may compute, search for, or
otherwise construct one.  A source reads recorded input and reports its absence;
absence produces an explicit unresolved outcome rather than an attempt.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class CertificateSource(Protocol):
    """Supplies the human-derived certificate recorded for a case, if any.

    Returning ``None`` is a first-class answer and must lead to an unresolved
    outcome.  An implementation that derives a certificate instead of reading one
    violates ADR-0035's verification-only boundary.
    """

    def certificate_for(self, case_id: str) -> Mapping[str, Any] | None:
        ...


@runtime_checkable
class ExactCertificateVerifier(Protocol):
    """Checks primal feasibility, dual feasibility, and an exactly closed gap.

    The result must carry a machine-readable coverage status distinguishing a
    verified supplied certificate from a discovered optimum, and the latter is
    never produced.
    """

    def verify(self, case: Any) -> Mapping[str, Any]:
        ...


class FrozenFixtureCertificates:
    """A :class:`CertificateSource` over an already-parsed frozen fixture.

    It only reads; there is no branch in which a missing certificate is
    replaced, defaulted, or generated.
    """

    __slots__ = ("_by_case",)

    def __init__(self, cases: Any) -> None:
        by_case: dict[str, Mapping[str, Any] | None] = {}
        for case in cases:
            case_id = case["case_id"]
            if case_id in by_case:
                raise ValueError(f"duplicate case identifier {case_id!r}")
            by_case[case_id] = case.get("certificate")
        self._by_case = by_case

    def certificate_for(self, case_id: str) -> Mapping[str, Any] | None:
        if case_id not in self._by_case:
            raise KeyError(case_id)
        return self._by_case[case_id]


__all__ = ["CertificateSource", "ExactCertificateVerifier", "FrozenFixtureCertificates"]
