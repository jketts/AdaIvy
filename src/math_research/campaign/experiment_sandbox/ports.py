"""Injected boundaries for the ADR-0066 campaign experiment sandbox."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .sandbox import SandboxExecution, SandboxProgramRequest
from .workspace_sandbox import WorkspaceExecution


class ExperimentSandboxPort(Protocol):
    """One bounded, digest-pinned execution of an untrusted program.

    The offline acceptance path injects a scripted implementation; the only
    production implementation is
    :class:`~math_research.campaign.experiment_sandbox.sandbox.OciExperimentSandbox`.
    """

    @property
    def policy_sha256(self) -> str: ...

    @property
    def control_policy_sha256(self) -> str: ...

    @property
    def bootstrap_sha256(self) -> str: ...

    @property
    def environment_sha256(self) -> str: ...

    def configuration_record(self) -> dict[str, Any]: ...

    def run(self, request: SandboxProgramRequest) -> SandboxExecution: ...


class WorkspaceSandboxPort(Protocol):
    """One bounded v2 execution over the persistent campaign workspace.

    The offline acceptance path injects a scripted implementation; the only
    production implementation is
    :class:`~math_research.campaign.experiment_sandbox.workspace_sandbox.WorkspaceSandbox`.
    """

    @property
    def policy_sha256(self) -> str: ...

    @property
    def control_policy_sha256(self) -> str: ...

    @property
    def bootstrap_sha256(self) -> str: ...

    @property
    def environment_sha256(self) -> str: ...

    def configuration_record(self) -> dict[str, Any]: ...

    def run(
        self, request: SandboxProgramRequest, workspace: Path,
    ) -> WorkspaceExecution: ...


__all__ = ["ExperimentSandboxPort", "WorkspaceSandboxPort"]
