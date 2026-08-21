"""Minimal durable-workspace CLI layered onto the Phase 1 manual CLI."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .domain.entities import OpaqueId
from .interchange import write_dossier
from .phase2.artifacts import FileArtifactStore
from .phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from .phase2.fixtures import build_open_theorem_dossier
from .phase2 import SUPPORTED_LIVE_PROVIDERS
from .phase2.env_file import EnvFileError, load_repository_env
from .phase2.live_config import (
    LiveRunConfiguration,
    LiveRunConfigurationError,
    create_live_run_configuration,
    live_run_configuration_payload,
    load_live_run_configuration,
    write_live_run_configuration,
)
from .phase2.live_gate import LIVE_GATE_COMMAND_SHAPE, execute_live_gate, preflight_live_gate
from .phase2.model_gateway import OpenAIProviderConfig, OpenAIResponsesGateway, ScriptedModelGateway, redact_secrets
from .phase2.openai_schema import project_openai_schema
from .phase2.pricing import (
    PricingSnapshotError,
    create_pricing_snapshot,
    load_pricing_snapshot,
    write_pricing_snapshot,
)
from .phase2.records import BudgetLimits, PricingSnapshot, VerifierIndependence
from .phase2.reporting import durable_report_data, render_durable_report
from .phase2.serialization import canonical_json, public_value
from .phase2.sqlite_workspace import SQLiteWorkspace


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _open(root: Path) -> tuple[SQLiteWorkspace, FileArtifactStore]:
    root.mkdir(parents=True, exist_ok=True)
    return SQLiteWorkspace(root / "workspace.sqlite3"), FileArtifactStore(root / "artifacts")


def _loop(
    workspace: SQLiteWorkspace,
    artifacts: FileArtifactStore,
    provider: str,
    configuration: LiveRunConfiguration | None = None,
    pricing: PricingSnapshot | None = None,
) -> BaselineResearchLoop:
    dossier = build_open_theorem_dossier()
    if provider == "fake":
        proposer_result, verifier_result = deterministic_fake_results(
            dossier.formalization.target_claim_id.value,
            dossier.formalization.assumption_claim_ids[0].value,
        )
        gateway = ScriptedModelGateway({"proposer": [proposer_result], "verifier": [verifier_result]})
        independence = VerifierIndependence(
            context_isolated=True, separate_model_call=True,
            different_model=False, different_provider=False,
            deterministic_checker=False, independently_implemented_checker=False,
            formal_kernel=False,
        )
    else:
        if configuration is None or pricing is None:
            raise RuntimeError("explicit live run configuration and pricing snapshot are required")
        config = OpenAIProviderConfig(model_identifier=configuration.model_identifier)
        gateway = OpenAIResponsesGateway(config)
        independence = VerifierIndependence(
            context_isolated=True, separate_model_call=True,
            different_model=False, different_provider=False,
            deterministic_checker=False, independently_implemented_checker=False,
            formal_kernel=False,
        )
    return BaselineResearchLoop(
        workspace=workspace, artifacts=artifacts,
        proposer=gateway, verifier=gateway, independence=independence, now=_now,
        call_timeout_milliseconds=configuration.call_timeout_milliseconds if configuration else 20_000,
        estimated_output_tokens=configuration.per_call_output_token_reserve if configuration else 512,
        pricing_snapshot=pricing,
    )


def _json(value: object) -> None:
    print(json.dumps(public_value(value), indent=2, sort_keys=True))


_CONFIG_VARIABLES = (
    "config.schema_version", "config.configuration_id", "config.provider",
    "config.model_identifier", "config.pricing_snapshot_id",
    "config.call_timeout_milliseconds", "config.per_call_input_token_reserve",
    "config.per_call_output_token_reserve", "config.budget.max_input_tokens",
    "config.budget.max_output_tokens", "config.budget.max_cost_microusd",
    "config.budget.max_wall_milliseconds", "config.budget.max_attempts",
    "config.content_hash",
)
_PRICING_VARIABLES = (
    "pricing.schema_version", "pricing.snapshot_id", "pricing.provider",
    "pricing.model_identifier", "pricing.source", "pricing.captured_at",
    "pricing.currency", "pricing.units",
    "pricing.input_microusd_per_million_tokens",
    "pricing.output_microusd_per_million_tokens", "pricing.content_hash",
)


def _live_inputs(config_path: Path | None, pricing_path: Path | None):
    missing: list[str] = []
    failed: list[str] = []
    configuration = None
    pricing = None
    try:
        load_repository_env()
    except EnvFileError as error:
        failed.append(str(error))
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if config_path is None or not config_path.is_file():
        missing.extend(_CONFIG_VARIABLES)
    else:
        try:
            configuration = load_live_run_configuration(config_path)
        except LiveRunConfigurationError:
            missing.extend(_CONFIG_VARIABLES)
    if pricing_path is None or not pricing_path.is_file():
        missing.extend(_PRICING_VARIABLES)
    else:
        try:
            pricing = load_pricing_snapshot(pricing_path)
        except PricingSnapshotError:
            missing.extend(_PRICING_VARIABLES)
    return configuration, pricing, tuple(sorted(set(missing))), tuple(sorted(set(failed)))


def _print_incomplete(missing: tuple[str, ...], failed: tuple[str, ...] = ()) -> None:
    value: dict[str, object] = {"missing_variables": list(missing), "command_shape": LIVE_GATE_COMMAND_SHAPE}
    if failed:
        value["failed_checks"] = list(failed)
    _json(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2 durable workspace and baseline loop")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "advance"):
        item = sub.add_parser(name)
        item.add_argument("workspace", type=Path)
        item.add_argument("run_id")
        item.add_argument("--provider", choices=("fake", "openai"), default="fake")
        item.add_argument("--config", type=Path)
        item.add_argument("--pricing-snapshot", type=Path)
        if name == "start":
            item.add_argument("--execute", action="store_true")
    for name in ("jobs", "budget", "pause", "resume", "artifacts", "manifest", "review", "timeline"):
        item = sub.add_parser(name)
        item.add_argument("workspace", type=Path)
        item.add_argument("run_id")
        if name == "artifacts":
            item.add_argument("--content", action="store_true")
    export = sub.add_parser("export")
    export.add_argument("workspace", type=Path)
    export.add_argument("run_id")
    export.add_argument("output", type=Path)
    report = sub.add_parser("report")
    report.add_argument("workspace", type=Path)
    report.add_argument("run_id")
    report.add_argument("--output", type=Path)
    demo = sub.add_parser("demo")
    demo.add_argument("output", type=Path)
    pricing_create = sub.add_parser("pricing-create")
    pricing_create.add_argument("output", type=Path)
    pricing_create.add_argument("--snapshot-id", required=True)
    pricing_create.add_argument("--provider", choices=sorted(SUPPORTED_LIVE_PROVIDERS), required=True)
    pricing_create.add_argument("--model", required=True)
    pricing_create.add_argument("--source", required=True)
    pricing_create.add_argument("--captured-at", required=True)
    pricing_create.add_argument("--currency", choices=("USD",), required=True)
    pricing_create.add_argument("--input-microusd-per-million-tokens", type=int, required=True)
    pricing_create.add_argument("--output-microusd-per-million-tokens", type=int, required=True)
    config_create = sub.add_parser("live-config-create")
    config_create.add_argument("output", type=Path)
    config_create.add_argument("--configuration-id", required=True)
    config_create.add_argument("--provider", choices=sorted(SUPPORTED_LIVE_PROVIDERS), required=True)
    config_create.add_argument("--model", required=True)
    config_create.add_argument("--pricing-snapshot-id", required=True)
    config_create.add_argument("--call-timeout-milliseconds", type=int, required=True)
    config_create.add_argument("--per-call-input-token-reserve", type=int, required=True)
    config_create.add_argument("--per-call-output-token-reserve", type=int, required=True)
    config_create.add_argument("--max-input-tokens", type=int, required=True)
    config_create.add_argument("--max-output-tokens", type=int, required=True)
    config_create.add_argument("--max-cost-microusd", type=int, required=True)
    config_create.add_argument("--max-wall-milliseconds", type=int, required=True)
    config_create.add_argument("--max-attempts", type=int, required=True)
    preflight = sub.add_parser("live-preflight")
    preflight.add_argument("--config", type=Path)
    preflight.add_argument("--pricing-snapshot", type=Path)
    live_gate = sub.add_parser("live-gate")
    live_gate.add_argument("workspace", type=Path)
    live_gate.add_argument("run_id")
    live_gate.add_argument("--config", type=Path, required=True)
    live_gate.add_argument("--pricing-snapshot", type=Path, required=True)
    live_gate.add_argument("--status-artifact", type=Path, default=Path("reports/phase-2/live-provider-status.json"))
    schema_report = sub.add_parser("provider-schema-report")
    schema_report.add_argument("output", type=Path)
    schema_report.add_argument("--schema-dir", type=Path, default=Path("schemas"))
    args = parser.parse_args(argv)
    if args.command == "demo":
        from .phase2.demonstration import run_demonstration
        _json(run_demonstration(args.output))
        return 0
    if args.command == "pricing-create":
        snapshot = create_pricing_snapshot(
            snapshot_id=OpaqueId(args.snapshot_id), provider=args.provider,
            model_identifier=args.model, source=args.source,
            captured_at=args.captured_at, currency=args.currency,
            input_microusd_per_million_tokens=args.input_microusd_per_million_tokens,
            output_microusd_per_million_tokens=args.output_microusd_per_million_tokens,
        )
        write_pricing_snapshot(snapshot, args.output)
        _json({"schema_version": "2.0.0", "output": str(args.output), "snapshot_id": snapshot.snapshot_id, "content_hash": snapshot.content_hash})
        return 0
    if args.command == "live-config-create":
        configuration = create_live_run_configuration(
            configuration_id=OpaqueId(args.configuration_id), provider=args.provider,
            model_identifier=args.model, pricing_snapshot_id=OpaqueId(args.pricing_snapshot_id),
            call_timeout_milliseconds=args.call_timeout_milliseconds,
            per_call_input_token_reserve=args.per_call_input_token_reserve,
            per_call_output_token_reserve=args.per_call_output_token_reserve,
            budget=BudgetLimits(
                max_input_tokens=args.max_input_tokens, max_output_tokens=args.max_output_tokens,
                max_cost_microusd=args.max_cost_microusd,
                max_wall_milliseconds=args.max_wall_milliseconds,
                max_attempts=args.max_attempts,
            ),
        )
        write_live_run_configuration(configuration, args.output)
        _json({"schema_version": "2.0.0", "output": str(args.output), "configuration_id": configuration.configuration_id, "content_hash": configuration.content_hash})
        return 0
    if args.command == "provider-schema-report":
        args.output.mkdir(parents=True, exist_ok=True)
        generated: list[dict[str, object]] = []
        for purpose in ("proposer", "verifier"):
            source = args.schema_dir / f"model-{purpose}-v1.schema.json"
            preparation = project_openai_schema(source.read_text(encoding="utf-8"))
            prefix = args.output / f"model-{purpose}-v1.openai"
            paths = {
                "provider_schema": Path(str(prefix) + ".schema.json"),
                "transformation_manifest": Path(str(prefix) + ".manifest.json"),
                "compatibility_json": Path(str(prefix) + ".compatibility.json"),
                "compatibility_markdown": Path(str(prefix) + ".compatibility.md"),
            }
            paths["provider_schema"].write_text(preparation.provider_schema_json, encoding="utf-8")
            paths["transformation_manifest"].write_text(preparation.transformation_manifest_json, encoding="utf-8")
            paths["compatibility_json"].write_text(preparation.compatibility_report_json, encoding="utf-8")
            paths["compatibility_markdown"].write_text(preparation.compatibility_report_text, encoding="utf-8")
            generated.append({
                "purpose": purpose,
                "canonical_schema_hash": preparation.canonical_schema_hash,
                "provider_schema_hash": preparation.provider_schema_hash,
                "paths": {key: str(value) for key, value in paths.items()},
            })
        _json({"schema_version": "2.0.0", "provider": "openai", "generated": generated})
        return 0
    if args.command in {"live-preflight", "live-gate"}:
        configuration, pricing, missing, input_failures = _live_inputs(args.config, args.pricing_snapshot)
        if missing or input_failures:
            _print_incomplete(missing, input_failures)
            return 2
        assert configuration is not None and pricing is not None
        preflight_result = preflight_live_gate(configuration, pricing)
        if not preflight_result.passed:
            _json({
                "missing_variables": list(preflight_result.missing_variables),
                "failed_checks": list(preflight_result.failed_checks),
                "command_shape": LIVE_GATE_COMMAND_SHAPE,
            })
            return 2
        if args.command == "live-preflight":
            _json(preflight_result)
            return 0
        try:
            result = execute_live_gate(
                root=args.workspace, run_id=OpaqueId(args.run_id),
                configuration=configuration, pricing=pricing,
            )
        except Exception as error:
            previous = json.loads(args.status_artifact.read_text(encoding="utf-8")) if args.status_artifact.exists() else None
            failed_calls: list[dict[str, object]] = []
            database = args.workspace / "workspace.sqlite3"
            if database.exists():
                try:
                    with SQLiteWorkspace(database) as failed_workspace:
                        failed_calls = list(failed_workspace.list_model_calls(OpaqueId(args.run_id)))
                except (KeyError, RuntimeError):
                    failed_calls = []
            status = {
                "schema_version": "2.0.0", "status": "failed",
                "blocker": str(redact_secrets(str(error), (os.environ.get("OPENAI_API_KEY", ""),))),
                "calls_recorded": len(failed_calls),
                "response_ids": [item["provider_request_id"] for item in failed_calls],
                "call_statuses": [item["status"] for item in failed_calls],
                "history": [previous] if previous else [],
            }
            args.status_artifact.parent.mkdir(parents=True, exist_ok=True)
            args.status_artifact.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _json(status)
            return 1
        previous = json.loads(args.status_artifact.read_text(encoding="utf-8")) if args.status_artifact.exists() else None
        status = {**result, "history": [previous] if previous else []}
        args.status_artifact.parent.mkdir(parents=True, exist_ok=True)
        args.status_artifact.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _json(status)
        return 0
    workspace, artifacts = _open(args.workspace)
    try:
        run_id = OpaqueId(args.run_id)
        if args.command == "start":
            configuration = pricing = None
            if args.provider == "openai":
                configuration, pricing, missing, input_failures = _live_inputs(args.config, args.pricing_snapshot)
                if missing or input_failures:
                    _print_incomplete(missing, input_failures)
                    return 2
                assert configuration is not None and pricing is not None
                checked = preflight_live_gate(configuration, pricing)
                if not checked.passed:
                    _json({"missing_variables": list(checked.missing_variables), "failed_checks": list(checked.failed_checks), "command_shape": LIVE_GATE_COMMAND_SHAPE})
                    return 2
            loop = _loop(workspace, artifacts, args.provider, configuration, pricing)
            run = loop.start(
                run_id=run_id, dossier=build_open_theorem_dossier(),
                limits=configuration.budget if configuration is not None else BudgetLimits(
                    max_input_tokens=20_000, max_output_tokens=4_000,
                    max_cost_microusd=10_000_000, max_wall_milliseconds=300_000,
                    max_attempts=4,
                ),
            )
            if configuration is not None and pricing is not None:
                workspace.save_pricing_snapshot(pricing, canonical_json=canonical_json(pricing), now=_now().isoformat().replace("+00:00", "Z"))
                workspace.save_live_run_configuration(
                    run_id=run_id, configuration_id=configuration.configuration_id,
                    schema_version=configuration.schema_version, provider=configuration.provider,
                    model_identifier=configuration.model_identifier,
                    pricing_snapshot_id=configuration.pricing_snapshot_id,
                    content_hash=configuration.content_hash,
                    canonical_json=canonical_json(live_run_configuration_payload(configuration)),
                    now=_now().isoformat().replace("+00:00", "Z"),
                )
            if args.execute:
                run = loop.run_to_terminal(run_id)
            _json(run)
            return 0
        if args.command == "advance":
            configuration = pricing = None
            if args.provider == "openai":
                configuration, pricing, missing, input_failures = _live_inputs(args.config, args.pricing_snapshot)
                if missing or input_failures:
                    _print_incomplete(missing, input_failures)
                    return 2
                assert configuration is not None and pricing is not None
                checked = preflight_live_gate(configuration, pricing)
                if not checked.passed:
                    _json({"missing_variables": list(checked.missing_variables), "failed_checks": list(checked.failed_checks), "command_shape": LIVE_GATE_COMMAND_SHAPE})
                    return 2
            _json(_loop(workspace, artifacts, args.provider, configuration, pricing).advance(run_id))
            return 0
        if args.command == "jobs":
            _json(workspace.list_jobs(run_id))
            return 0
        if args.command == "budget":
            run = workspace.get_run(run_id)
            _json(workspace.budget(run.budget_id, now=_now().isoformat().replace("+00:00", "Z")))
            return 0
        if args.command == "pause":
            _json(_loop(workspace, artifacts, "fake").pause(run_id))
            return 0
        if args.command == "resume":
            _json(_loop(workspace, artifacts, "fake").resume(run_id))
            return 0
        if args.command == "artifacts":
            calls = list(workspace.list_model_calls(run_id))
            if args.content:
                for call in calls:
                    for field in ("request_hash", "result_hash"):
                        if call.get(field):
                            call[field + "_content"] = artifacts.get(str(call[field])).decode("utf-8")
            _json(calls)
            return 0
        if args.command == "manifest":
            _json(workspace.get_manifest(run_id))
            return 0
        if args.command == "review":
            values = []
            for proposal in workspace.list_proposals(run_id):
                values.append({"record": proposal, "content": json.loads(artifacts.get(proposal.artifact_hash))})
            _json(values)
            return 0
        if args.command == "export":
            run = workspace.get_run(run_id)
            write_dossier(workspace.load_dossier(run.dossier_id), args.output)
            _json({"schema_version": "2.0.0", "output": str(args.output), "dossier_hash": run.dossier_hash})
            return 0
        if args.command == "timeline":
            _json(workspace.timeline(run_id))
            return 0
        text = render_durable_report(workspace, run_id)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            _json({"schema_version": "2.0.0", "output": str(args.output), "report": durable_report_data(workspace, run_id)})
        else:
            print(text, end="")
        return 0
    finally:
        workspace.close()


if __name__ == "__main__":
    raise SystemExit(main())
