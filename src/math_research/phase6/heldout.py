"""A view that exposes exactly the frozen held-out cases and nothing else.

Blueprint Section 20 scenario L requires that an attempt to choose a method
after inspecting held-out results is blocked by the capability boundary and that
the policy violation is recorded. Passing the whole fixture into the
confirmatory execution scope makes that boundary a convention. `HeldOutView`
makes it a value object: non-frozen cases are dropped at construction, every
refused request is appended to an in-memory violation trail, and the caller
decides how to persist it durably.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .errors import Phase6ValidationError

VIOLATION_KIND = "heldout_access_violation"
VIOLATION_REASON = "case_outside_frozen_heldout_scope"


class HeldOutView:
    """Exactly the frozen held-out cases of one benchmark."""

    def __init__(
        self, *, benchmark_id: str, cases: Iterable[Mapping[str, Any]],
        frozen_case_ids: Iterable[str],
    ) -> None:
        frozen = tuple(frozen_case_ids)
        if not frozen or len(set(frozen)) != len(frozen):
            raise Phase6ValidationError("frozen held-out case ids must be unique and non-empty")
        available = tuple(cases)
        selected: dict[str, dict[str, Any]] = {}
        for case_id in frozen:
            matches = [item for item in available if item.get("case_id") == case_id]
            if len(matches) != 1:
                raise Phase6ValidationError("frozen held-out case does not resolve exactly once")
            selected[case_id] = dict(matches[0])
        self.benchmark_id = benchmark_id
        self._frozen = frozen
        self._cases = selected
        self._violations: list[dict[str, Any]] = []

    @property
    def visible_case_ids(self) -> tuple[str, ...]:
        return self._frozen

    @property
    def violations(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._violations)

    def case(self, case_id: str) -> dict[str, Any]:
        if case_id not in self._cases:
            self._violations.append({
                "kind": VIOLATION_KIND,
                "benchmark_id": self.benchmark_id,
                "requested_case_id": case_id,
                "visible_case_ids": list(self._frozen),
                "reason": VIOLATION_REASON,
            })
            raise Phase6ValidationError(
                "held-out capability boundary refused a case outside the frozen scope"
            )
        return dict(self._cases[case_id])
