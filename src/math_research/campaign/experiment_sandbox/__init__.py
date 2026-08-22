"""ADR-0066 digest-pinned campaign experiment boundary.

Exports are resolved lazily.  ``sandbox`` (and everything that imports it)
holds a module-level ``import subprocess``, and the campaign operator
entrypoint imports the pure exact verifier from this package on its default
offline path.  Eager package imports would put the process-spawning module on
that path for every command; lazy resolution keeps the container-requiring
modules out of the import graph until an activated runner is actually wired.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "PROBE_IDS": "activation",
    "load_campaign_experiment_activation": "activation",
    "run_campaign_experiment_activation": "activation",
    "verify_campaign_experiment_activation": "activation",
    "SandboxActivation": "attestation",
    "load_campaign_image_lock": "image_lock",
    "load_phase4b_image_lock": "image_lock",
    "ActivatedCampaignExperimentRunner": "runner",
    "ExactGraphCampaignVerifier": "runner",
    "build_activated_campaign_experiment_runner": "runner",
    "CampaignSandboxLimits": "sandbox",
    "OciExperimentSandbox": "sandbox",
    "SandboxProgramRequest": "sandbox",
    "load_target": "verifier",
    "verify_candidate": "verifier",
    # ADR-0082 v2 workspace sandbox (alongside, never replacing, the v1
    # instrument above).
    "EXACT_GRAPH_TARGET_CLASS": "target_schema",
    "TARGET_SCHEMA_CLASSES": "target_schema",
    "TargetSchemaClass": "target_schema",
    "resolve_target_class": "target_schema",
    "load_workspace_image_lock": "workspace_image_lock",
    "WorkspaceActivation": "workspace_activation",
    "load_workspace_activation": "workspace_activation",
    "require_activatable_workspace_lock": "workspace_activation",
    "verify_workspace_activation": "workspace_activation",
    "WorkspaceSandbox": "workspace_sandbox",
    "WorkspaceSandboxLimits": "workspace_sandbox",
    "workspace_manifest": "workspace_sandbox",
    "ActivatedWorkspaceCampaignRunner": "workspace_runner",
    "limits_from_request_v2": "workspace_runner",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
