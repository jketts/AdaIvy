"""Narrow Phase 3B formal-tool boundary."""

from __future__ import annotations

from typing import Protocol

from .records import FormalCheckFinding, FormalCheckRequest, GeneratedWrapper, RawExecution


class MathTool(Protocol):
    def validate(self, request: FormalCheckRequest) -> None: ...
    def execute(self, wrapper: GeneratedWrapper) -> RawExecution: ...
    def verify_output(self, request: FormalCheckRequest, wrapper: GeneratedWrapper, execution: RawExecution, *, created_at: str) -> FormalCheckFinding: ...

