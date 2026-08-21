"""Phase 6 validation error.

It lives in its own module so the held-out view, the generality control suite,
and the confirmatory service can all raise the same fail-closed type without an
import cycle. `Phase6ValidationError` is re-exported from
`math_research.phase6.service`, which remains its documented import path.
"""

from __future__ import annotations


class Phase6ValidationError(ValueError):
    pass


class GeneralitySuiteError(Phase6ValidationError):
    """A generality suite manifest is malformed, unknown, or internally invalid.

    This is a reject, not a control failure. A control that executes and returns
    the wrong verdict is recorded as a failed control; a manifest that cannot be
    trusted to describe what was executed is refused before anything runs.
    """
