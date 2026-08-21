"""Typed, coded refusals for the publication projection.

Every refusal carries a stable ``code``. The acceptance suite and the probe
manifest name codes rather than message text, so a reworded message never
silently turns a demonstrated refusal into an untested one.
"""

from __future__ import annotations


class PublicationValidationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
