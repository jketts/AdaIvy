"""Bounded preflight and executor for the Phase 2 live-provider gate."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..domain.entities import OpaqueId
from .artifacts import FileArtifactStore
from .baseline_loop import BaselineResearchLoop
from .fixtures import build_open_theorem_dossier
from .live_config import LiveRunConfiguration, live_run_configuration_payload
from .model_gateway import (
    OPENAI_SDK_PINNED_VERSION,
    OpenAIProviderConfig,
    OpenAIResponsesGateway,
    openai_sdk_version,
    redact_secrets,
)
from .openai_schema import ProviderSchemaError, project_openai_schema
from .pricing import estimate_cost_microusd
from .records import PricingSnapshot, RunStatus, VerifierIndependence
from .reporting import render_durable_report, report_hash
from .serialization import canonical_hash, canonical_json
from .sqlite_workspace import SQLiteWorkspace


LIVE_GATE_COMMAND_SHAPE = (
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "
    "python3 -m math_research.cli phase2 live-gate <workspace> <run-id> "
    "--config <live-run-config.json> --pricing-snapshot <pricing-snapshot.json>"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class LivePreflightResult:
    schema_version: str = "2.0.0"
    passed: bool
    missing_variables: tuple[str, ...]
    failed_checks: tuple[str, ...]
    estimated_two_call_cost_microusd: int | None


def preflight_live_gate(
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
    *,
    environment: Mapping[str, str] | None = None,
    schema_dir: Path | None = None,
    installed_sdk_version: str | None = None,
) -> LivePreflightResult:
    environment = os.environ if environment is None else environment
    missing: list[str] = []
    failed: list[str] = []
    api_key = environment.get("OPENAI_API_KEY")
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if not configuration.provider:
        missing.append("config.provider")
    if not configuration.model_identifier:
        missing.append("config.model_identifier")
    if configuration.pricing_snapshot_id != pricing.snapshot_id:
        failed.append("pricing_snapshot_id_mismatch")
    if configuration.provider != pricing.provider:
        failed.append("pricing_provider_mismatch")
    if configuration.model_identifier != pricing.model_identifier:
        failed.append("pricing_model_identifier_mismatch")
    adapter = OpenAIProviderConfig(model_identifier=configuration.model_identifier)
    required_capabilities = {"responses_api", "structured_output"}
    if not required_capabilities.issubset(adapter.capabilities):
        failed.append("structured_output_path_unsupported")
    observed_sdk = openai_sdk_version() if installed_sdk_version is None else installed_sdk_version
    if observed_sdk is None:
        failed.append("openai_sdk_unavailable")
    elif observed_sdk != OPENAI_SDK_PINNED_VERSION:
        failed.append("openai_sdk_version_mismatch")
    directory = schema_dir or Path(__file__).resolve().parents[3] / "schemas"
    for purpose in ("proposer", "verifier"):
        try:
            project_openai_schema(
                (directory / f"model-{purpose}-v1.schema.json").read_text(encoding="utf-8")
            )
        except (OSError, ProviderSchemaError) as error:
            if isinstance(error, ProviderSchemaError):
                failed.extend(
                    f"provider_schema_{purpose}:{issue.code}:{issue.path or '/'}"
                    for issue in error.report.issues
                )
            else:
                failed.append(f"provider_schema_{purpose}:unreadable")
    per_call_cost = estimate_cost_microusd(
        pricing,
        input_tokens=configuration.per_call_input_token_reserve,
        output_tokens=configuration.per_call_output_token_reserve,
    )
    limits = configuration.budget
    if limits.max_attempts < 2:
        failed.append("budget_attempts_below_two")
    if limits.max_input_tokens < 2 * configuration.per_call_input_token_reserve:
        failed.append("budget_input_tokens_below_two_calls")
    if limits.max_output_tokens < 2 * configuration.per_call_output_token_reserve:
        failed.append("budget_output_tokens_below_two_calls")
    if limits.max_cost_microusd < 2 * per_call_cost:
        failed.append("budget_cost_below_two_calls")
    if limits.max_wall_milliseconds < 2 * configuration.call_timeout_milliseconds:
        failed.append("budget_time_below_two_calls")
    if api_key:
        probe = canonical_json(redact_secrets(
            {"authorization": f"Bearer {api_key}", "message": f"credential={api_key}"},
            (api_key,),
        ))
        if api_key in probe:
            failed.append("credential_redaction_failed")
    return LivePreflightResult(
        passed=not missing and not failed,
        missing_variables=tuple(sorted(missing)),
        failed_checks=tuple(sorted(failed)),
        estimated_two_call_cost_microusd=2 * per_call_cost,
    )


def execute_live_gate(
    *,
    root: Path,
    run_id: OpaqueId,
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
) -> dict[str, object]:
    """Execute exactly one proposer and one verifier call after a passing preflight."""

    preflight = preflight_live_gate(configuration, pricing)
    if not preflight.passed:
        raise RuntimeError("live-provider preflight did not pass")
    root.mkdir(parents=True, exist_ok=True)
    database = root / "workspace.sqlite3"
    artifacts = FileArtifactStore(root / "artifacts")
    dossier = build_open_theorem_dossier()
    gateway = OpenAIResponsesGateway(OpenAIProviderConfig(model_identifier=configuration.model_identifier))
    independence = VerifierIndependence(
        context_isolated=True,
        separate_model_call=True,
        different_model=False,
        different_provider=False,
        deterministic_checker=False,
        independently_implemented_checker=False,
        formal_kernel=False,
    )
    with SQLiteWorkspace(database) as workspace:
        workspace.save_pricing_snapshot(pricing, canonical_json=canonical_json(pricing), now=_now())
        loop = BaselineResearchLoop(
            workspace=workspace,
            artifacts=artifacts,
            proposer=gateway,
            verifier=gateway,
            independence=independence,
            call_timeout_milliseconds=configuration.call_timeout_milliseconds,
            estimated_output_tokens=configuration.per_call_output_token_reserve,
            pricing_snapshot=pricing,
        )
        run = loop.start(run_id=run_id, dossier=dossier, limits=configuration.budget)
        workspace.save_live_run_configuration(
            run_id=run_id,
            configuration_id=configuration.configuration_id,
            schema_version=configuration.schema_version,
            provider=configuration.provider,
            model_identifier=configuration.model_identifier,
            pricing_snapshot_id=configuration.pricing_snapshot_id,
            content_hash=configuration.content_hash,
            canonical_json=canonical_json(live_run_configuration_payload(configuration)),
            now=_now(),
        )
        final = loop.run_to_terminal(run_id, max_steps=2)
        calls = workspace.list_model_calls(run_id)
        if len(calls) != 2:
            raise RuntimeError(f"live gate stopped after {len(calls)} model call(s)")
        response_ids = tuple(call["provider_request_id"] for call in calls)
        if any(not value for value in response_ids) or len(set(response_ids)) != 2:
            raise RuntimeError("live proposer/verifier response IDs are absent or not distinct")
        if any(call["status"] != "succeeded" for call in calls):
            raise RuntimeError("live proposer or verifier did not return validated structured output")
        if any(call["usage_source"] != "api_reported" or call["total_tokens"] <= 0 for call in calls):
            raise RuntimeError("live API usage is absent or incomplete")
        if any(call["pricing_snapshot_id"] != pricing.snapshot_id.value for call in calls):
            raise RuntimeError("live call cost lacks the pinned pricing snapshot ID")
        if final.status not in {RunStatus.AWAITING_REVIEW, RunStatus.UNRESOLVED}:
            raise RuntimeError(f"unexpected live terminal state: {final.status.value}")
        manifest = workspace.get_manifest(run_id)
        if manifest.independence.fully_independent or manifest.independence.different_provider:
            raise RuntimeError("same-provider verifier independence was overstated")
        first_report = render_durable_report(workspace, run_id)
        report_path = root / "traceable-report.md"
        report_path.write_text(first_report, encoding="utf-8")
        replay_hash = canonical_hash(workspace.timeline(run_id))
        manifest_hash = manifest.serialized_context_hash
        call_records = [dict(value) for value in calls]
        budget = workspace.budget(final.budget_id, now=final.updated_at)
    with SQLiteWorkspace(database) as replayed:
        regenerated = render_durable_report(replayed, run_id)
        regenerated_hash = report_hash(replayed, run_id)
        if regenerated != first_report:
            raise RuntimeError("report regeneration changed after database restart")
    api_key = os.environ["OPENAI_API_KEY"]
    leaked_paths, leaked_database_fields = scan_persisted_secret(root, database, api_key)
    if leaked_paths or leaked_database_fields:
        raise RuntimeError("credential leakage detected in persisted live-gate state")
    return {
        "schema_version": "2.0.0",
        "status": "passed",
        "fixture": "known-valid-even-sum",
        "run_id": run_id.value,
        "configuration_id": configuration.configuration_id.value,
        "pricing_snapshot_id": pricing.snapshot_id.value,
        "response_ids": list(response_ids),
        "calls": call_records,
        "estimated_cost_microusd": budget.used_cost_microusd,
        "manifest_hash": manifest_hash,
        "event_replay_hash": replay_hash,
        "report_hash": regenerated_hash,
        "credential_leak_matches": 0,
    }


def scan_persisted_secret(root: Path, database: Path, secret: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return locations only; never return or print matched secret material."""

    path_matches: list[str] = []
    needle = secret.encode("utf-8")
    if needle:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                if needle in path.read_bytes():
                    path_matches.append(str(path.relative_to(root)))
            except OSError:
                path_matches.append(str(path.relative_to(root)) + ":unreadable")
    field_matches: list[str] = []
    if database.exists() and secret:
        connection = sqlite3.connect(database)
        try:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            for table in tables:
                columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
                rows = connection.execute(f'SELECT * FROM "{table}"')
                for row_number, row in enumerate(rows, start=1):
                    for column, value in zip(columns, row):
                        if isinstance(value, str) and secret in value:
                            field_matches.append(f"{table}.{column}.row{row_number}")
        finally:
            connection.close()
    return tuple(path_matches), tuple(field_matches)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
