"""Minimal durable-workspace CLI layered onto the Phase 1 manual CLI."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .application.problem_intake import (
    ProblemDefinitionError,
    load_problem_definition_file,
    parse_instant,
)
from .domain.entities import OpaqueId, ResearchDossier
from .interchange import write_dossier
from .phase2.artifacts import FileArtifactStore
from .phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from .phase2.fixtures import build_open_theorem_dossier
from .phase2 import SUPPORTED_LIVE_PROVIDERS
from .phase2.env_file import EnvFileError, load_provider_environment
from .phase2.live_config import (
    LiveRunConfiguration,
    LiveRunConfigurationError,
    create_live_run_configuration,
    live_run_configuration_payload,
    load_live_run_configuration,
    write_live_run_configuration,
)
from .phase2.live_gate import LIVE_GATE_COMMAND_SHAPE, execute_live_gate, preflight_live_gate
from .phase2.model_gateway import ScriptedModelGateway, redact_secrets
from .phase2.openai_schema import project_openai_schema
from .phase2.pricing import (
    PricingSnapshotError,
    create_pricing_snapshot,
    load_pricing_snapshot,
    write_pricing_snapshot,
)
from .phase2.provider_registry import (
    UnknownProviderError,
    build_gateway,
    provider_secret_values,
    provider_spec,
    registered_providers,
)
from .phase2.records import BudgetLimits, PricingSnapshot, VerifierIndependence
from .phase2.reporting import durable_report_data, render_durable_report
from .phase2.serialization import canonical_json, public_value
from .phase2.sqlite_workspace import SQLiteWorkspace


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Read-only subcommands. Some Phase 2 workspaces are sealed evidence pinned
# byte-for-byte by the ADR-0022 Phase 4A protected-evidence manifest, so a
# reporting command must never open one read-write: a pending migration would
# rewrite committed evidence in place. ADR-0041 added the first migration that
# would have done so, and did once before this guard existed.
_READ_ONLY_COMMANDS = frozenset({
    "report", "jobs", "budget", "artifacts", "manifest", "review", "timeline",
    "export", "rounds",
})


def _open(root: Path, *, read_only: bool = False) -> tuple[SQLiteWorkspace, FileArtifactStore]:
    if not read_only:
        root.mkdir(parents=True, exist_ok=True)
    return (
        SQLiteWorkspace(root / "workspace.sqlite3", read_only=read_only),
        FileArtifactStore(root / "artifacts"),
    )


def _run_dossier(workspace: SQLiteWorkspace, run_id: OpaqueId) -> ResearchDossier:
    """Reload the dossier this run was started with, from durable state."""

    return workspace.load_dossier(workspace.get_run(run_id).dossier_id)


def _start_dossier(args: argparse.Namespace) -> ResearchDossier:
    """Resolve the dossier for a new run.

    A problem definition is the only external intake path. It is deliberately
    NOT a canonical dossier file: the problem grammar cannot express a warrant,
    evidence, or a verification record, so an intake document can never inject
    proof status. Accepting a dossier here through `import_trusted_replay`
    would, which is why that option does not exist.
    """

    problem = getattr(args, "problem", None)
    if problem is None:
        return build_open_theorem_dossier()
    instant = getattr(args, "intake_instant", None)
    if not instant:
        raise ValueError(
            "--problem requires --intake-instant (an explicit UTC instant such "
            "as 2026-08-21T00:00:00Z); the intake reads no clock"
        )
    return load_problem_definition_file(problem, instant=parse_instant(instant)).dossier


def _declared_independence() -> VerifierIndependence:
    """What an operator is still permitted to assert.

    ADR-0041 has the loop MEASURE `different_provider`, `different_model`,
    `separate_model_call` and `context_isolated` from the run itself, so whatever
    is written for those four here is overwritten by what actually happened. Only
    the three checker-construction dimensions remain declarations, and they are
    declared false: nothing in this CLI supplies a deterministic, independently
    implemented, or formal checker.
    """
    return VerifierIndependence(
        context_isolated=True, separate_model_call=True,
        different_model=False, different_provider=False,
        deterministic_checker=False, independently_implemented_checker=False,
        formal_kernel=False,
    )


def _role_gateway(
    provider: str,
    configuration: LiveRunConfiguration | None,
    pricing: PricingSnapshot | None,
    role: str,
    dossier: ResearchDossier,
):
    """Build one role's adapter. No role falls back to a default provider.

    Both roles pass through exactly the same ADR-0038 gate. Before ADR-0041 the
    verifier had no gate of its own because it had no gateway of its own: one
    object served both roles, which made the two strongest independence axes
    unreachable from the run path.
    """
    if provider == "fake":
        if not dossier.formalization.assumption_claim_ids:
            raise ValueError(
                "the fake provider scripts its results from the first assumption "
                "claim, and this dossier declares none"
            )
        proposer_result, verifier_result = deterministic_fake_results(
            dossier.formalization.target_claim_id.value,
            dossier.formalization.assumption_claim_ids[0].value,
        )
        return ScriptedModelGateway({"proposer": [proposer_result], "verifier": [verifier_result]})
    # Every live provider takes the same path: the content-hashed configuration
    # names the provider, the registry builds that provider's adapter, and there
    # is no fallback. Constructing an adapter opens no socket and imports no SDK;
    # the credential and endpoint requirements are resolved inside the adapter's
    # own call path and fail closed there.
    if configuration is None or pricing is None:
        raise RuntimeError(
            f"{role} provider {provider} requires an explicit live run"
            " configuration and a pinned pricing snapshot"
        )
    if configuration.provider != provider:
        raise RuntimeError(
            f"selected {role} provider {provider} is not the configured provider"
            f" {configuration.provider}"
        )
    if pricing.provider != provider:
        raise RuntimeError(
            f"pinned {role} pricing snapshot names provider {pricing.provider},"
            f" not {provider}"
        )
    if configuration.pricing_snapshot_id != pricing.snapshot_id:
        raise RuntimeError(
            f"pinned {role} pricing snapshot is not the one the configuration names"
        )
    if configuration.model_identifier != pricing.model_identifier:
        raise RuntimeError(
            f"pinned {role} pricing snapshot is not bound to the configured model"
        )
    return build_gateway(provider, configuration.model_identifier)


def _loop(
    workspace: SQLiteWorkspace,
    artifacts: FileArtifactStore,
    provider: str,
    configuration: LiveRunConfiguration | None = None,
    pricing: PricingSnapshot | None = None,
    *,
    dossier: ResearchDossier,
    verifier_provider: str | None = None,
    verifier_configuration: LiveRunConfiguration | None = None,
    verifier_pricing: PricingSnapshot | None = None,
) -> BaselineResearchLoop:
    # The dossier is supplied, never rebuilt here. `start` resolves it from the
    # problem definition (or the built-in fixture); every later command reloads
    # the one the run was actually started with. Re-deriving it would silently
    # run a different problem than the one on record.
    #
    # ADR-0041: the proposer and the verifier resolve independently. Omitting the
    # verifier selection reuses the proposer's provider, which is the unchanged
    # single-provider path and records `different_provider=false` because that is
    # what actually happened.
    verifier_provider = verifier_provider or provider
    if verifier_provider == provider:
        verifier_configuration = verifier_configuration or configuration
        verifier_pricing = verifier_pricing or pricing
    proposer_gateway = _role_gateway(provider, configuration, pricing, "proposer", dossier)
    verifier_gateway = _role_gateway(
        verifier_provider, verifier_configuration, verifier_pricing, "verifier", dossier,
    )
    # Two providers mean two rate cards and two declared reserves. Cost has to
    # aggregate across roles, so neither may be assumed from the other.
    pricing_snapshots: dict[str, PricingSnapshot] = {}
    if pricing is not None:
        pricing_snapshots["proposer"] = pricing
    if verifier_pricing is not None:
        pricing_snapshots["verifier"] = verifier_pricing
    reserves: dict[str, int] = {}
    if configuration is not None:
        reserves["proposer"] = configuration.per_call_output_token_reserve
    if verifier_configuration is not None:
        reserves["verifier"] = verifier_configuration.per_call_output_token_reserve
    return BaselineResearchLoop(
        workspace=workspace, artifacts=artifacts,
        proposer=proposer_gateway, verifier=verifier_gateway,
        independence=_declared_independence(), now=_now,
        call_timeout_milliseconds=configuration.call_timeout_milliseconds if configuration else 20_000,
        estimated_output_tokens=configuration.per_call_output_token_reserve if configuration else 512,
        pricing_snapshot=pricing,
        pricing_snapshots=pricing_snapshots or None,
        output_token_reserves=reserves or None,
    )


# Derived from the provider registry, never re-listed. A provider added to the
# registry appears here automatically, so it cannot be admitted at the model
# boundary while remaining unselectable on the run path -- the measured gap this
# closes. "fake" is first and stays the default: no run reaches a provider
# without being asked for by name.
RUN_PROVIDER_CHOICES: tuple[str, ...] = ("fake", *registered_providers())

# Reported when no readable configuration names a provider, so the credential
# requirement cannot be derived. Naming OPENAI_API_KEY here would misattribute a
# requirement to a provider the run never selected.
CREDENTIALS_UNRESOLVED = "credentials.unresolved_until_config_provider_is_readable"


def _provider_secrets(provider: str | None) -> tuple[str, ...]:
    """Configured secret values for redaction only. Never placed in a record."""

    if provider is None or provider == "fake":
        return ()
    try:
        return provider_secret_values(provider, os.environ)
    except UnknownProviderError:
        return ()


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


def _live_inputs(
    config_path: Path | None,
    pricing_path: Path | None,
    *,
    selected_provider: str | None = None,
):
    """Resolve the live inputs for whichever provider the run actually selects.

    Credentials come from `.env` and non-secret settings from `.env.settings`,
    both resolved by `load_provider_environment` under ADR-0009's controls. Both
    files are loaded because a provider needs both: a resolved key with an
    unresolved endpoint would otherwise pass here and fail inside the adapter.
    The single-key loader is unchanged and no longer used here: it rejects any
    key other than OPENAI_API_KEY, so a populated multi-provider `.env` made
    every live command fail before its provider was even read.

    Which credentials are required is derived from the provider named by the
    caller, falling back to the provider inside the content-hashed
    configuration. When neither is available the requirement is reported as
    unresolved rather than guessed.
    """
    missing: list[str] = []
    failed: list[str] = []
    configuration = None
    pricing = None
    try:
        load_provider_environment()
    except EnvFileError as error:
        failed.append(str(error))
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
    if (
        selected_provider is not None
        and configuration is not None
        and configuration.provider != selected_provider
    ):
        # Never silently run the configured provider instead of the selected
        # one, and never the reverse.
        failed.append(
            f"provider_mismatch:selected={selected_provider}"
            f":configured={configuration.provider}"
        )
    effective = selected_provider or (
        configuration.provider if configuration is not None else None
    )
    if effective is None:
        missing.append(CREDENTIALS_UNRESOLVED)
    else:
        try:
            spec = provider_spec(effective)
        except UnknownProviderError:
            failed.append(f"unknown_provider:{effective}")
        else:
            missing.extend(
                variable for variable in spec.required_credentials
                if not os.environ.get(variable)
            )
    return configuration, pricing, tuple(sorted(set(missing))), tuple(sorted(set(failed)))


def _print_incomplete(missing: tuple[str, ...], failed: tuple[str, ...] = ()) -> None:
    value: dict[str, object] = {"missing_variables": list(missing), "command_shape": LIVE_GATE_COMMAND_SHAPE}
    if failed:
        value["failed_checks"] = list(failed)
    _json(value)


def _print_adapter_refusal(provider: str, error: Exception) -> None:
    """Report a refused adapter by name, with no value and no traceback."""

    _json({
        "missing_variables": [],
        "failed_checks": [
            f"adapter_unconstructable:{provider}:{type(error).__name__}:"
            + str(redact_secrets(str(error), _provider_secrets(provider)))
        ],
        "command_shape": LIVE_GATE_COMMAND_SHAPE,
    })


def _prepare_live_run(args) -> tuple[LiveRunConfiguration, PricingSnapshot] | int:
    """Resolve and gate the live inputs, or return the exit status to use.

    The same gate for every provider: the configuration and the pinned pricing
    snapshot must load, the selected provider must be the configured one, and
    the provider-aware preflight must pass. There is no default, no fallback to
    another provider, and no fallback to the fake gateway.
    """
    configuration, pricing, missing, input_failures = _live_inputs(
        args.config, args.pricing_snapshot, selected_provider=args.provider,
    )
    if missing or input_failures:
        _print_incomplete(missing, input_failures)
        return 2
    assert configuration is not None and pricing is not None
    checked = preflight_live_gate(configuration, pricing)
    if not checked.passed:
        _json({
            "missing_variables": list(checked.missing_variables),
            "failed_checks": list(checked.failed_checks),
            "command_shape": LIVE_GATE_COMMAND_SHAPE,
        })
        return 2
    return configuration, pricing


def _prepare_verifier_role(args) -> tuple[LiveRunConfiguration | None, PricingSnapshot | None] | int:
    """Gate the verifier role's live inputs when it selects its own provider.

    Returns ``(None, None)`` when the verifier reuses the proposer's already
    gated inputs, which is the unchanged single-provider path. A verifier
    provider that is asked for and unconfigured refuses the run rather than
    starting it half-configured or quietly borrowing the proposer's credentials,
    and a verifier configuration supplied without a verifier provider is refused
    rather than silently ignored.
    """
    verifier_provider = getattr(args, "verifier_provider", None)
    config_path = getattr(args, "verifier_config", None)
    pricing_path = getattr(args, "verifier_pricing_snapshot", None)
    supplied = config_path is not None or pricing_path is not None
    if verifier_provider is None:
        if supplied:
            _json({
                "missing_variables": ["--verifier-provider"],
                "failed_checks": [
                    "verifier_inputs_without_verifier_provider: a verifier"
                    " configuration or pricing snapshot was supplied with no"
                    " --verifier-provider, and would have been ignored"
                ],
                "command_shape": LIVE_GATE_COMMAND_SHAPE,
            })
            return 2
        return None, None
    if verifier_provider == "fake":
        if supplied:
            _json({
                "missing_variables": [],
                "failed_checks": [
                    "verifier_provider_fake_with_live_inputs: the scripted"
                    " verifier calls no provider, so a configuration or pricing"
                    " snapshot for it cannot be honoured"
                ],
                "command_shape": LIVE_GATE_COMMAND_SHAPE,
            })
            return 2
        return None, None
    if verifier_provider == args.provider and not supplied:
        # Same provider, no separate inputs: reuse the proposer's gated
        # configuration rather than demanding a duplicate of it.
        return None, None
    configuration, pricing, missing, failures = _live_inputs(
        config_path, pricing_path, selected_provider=verifier_provider,
    )
    if missing or failures:
        _print_incomplete(missing, failures)
        return 2
    assert configuration is not None and pricing is not None
    checked = preflight_live_gate(configuration, pricing)
    if not checked.passed:
        _json({
            "missing_variables": list(checked.missing_variables),
            "failed_checks": list(checked.failed_checks),
            "command_shape": LIVE_GATE_COMMAND_SHAPE,
        })
        return 2
    return configuration, pricing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2 durable workspace and baseline loop")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "advance"):
        item = sub.add_parser(name)
        item.add_argument("workspace", type=Path)
        item.add_argument("run_id")
        item.add_argument("--provider", choices=RUN_PROVIDER_CHOICES, default="fake")
        item.add_argument("--config", type=Path)
        item.add_argument("--pricing-snapshot", type=Path)
        # ADR-0041. The verifier role may resolve to its own provider and model.
        # Derived from the same registry as --provider, for the same reason.
        item.add_argument("--verifier-provider", choices=RUN_PROVIDER_CHOICES)
        item.add_argument("--verifier-config", type=Path)
        item.add_argument("--verifier-pricing-snapshot", type=Path)
        if name == "start":
            item.add_argument("--execute", action="store_true")
            # ADR-0041 declared refinement-round cap. One is the identity: the
            # historical single-round behaviour. A caller that wants refinement
            # must say how many rounds it will pay for.
            item.add_argument("--max-refinement-rounds", type=int, default=1)
            item.add_argument(
                "--problem", type=Path,
                help="problem definition to run instead of the built-in fixture",
            )
            item.add_argument(
                "--intake-instant",
                help="explicit UTC intake instant, required with --problem",
            )
    for name in ("jobs", "budget", "pause", "resume", "artifacts", "manifest", "review", "timeline", "rounds"):
        item = sub.add_parser(name)
        item.add_argument("workspace", type=Path)
        item.add_argument("run_id")
        if name == "artifacts":
            item.add_argument("--content", action="store_true")
        if name == "manifest":
            item.add_argument("--round", type=int, dest="round_index")
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
        configuration, pricing, missing, input_failures = _live_inputs(
            args.config, args.pricing_snapshot,
        )
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
                "blocker": str(redact_secrets(
                    str(error), _provider_secrets(configuration.provider),
                )),
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
    workspace, artifacts = _open(
        args.workspace, read_only=args.command in _READ_ONLY_COMMANDS,
    )
    try:
        run_id = OpaqueId(args.run_id)
        if args.command == "start":
            configuration = pricing = None
            if args.provider != "fake":
                prepared = _prepare_live_run(args)
                if isinstance(prepared, int):
                    return prepared
                configuration, pricing = prepared
            verifier_prepared = _prepare_verifier_role(args)
            if isinstance(verifier_prepared, int):
                return verifier_prepared
            verifier_configuration, verifier_pricing = verifier_prepared
            if args.max_refinement_rounds < 1:
                _json({
                    "missing_variables": [],
                    "failed_checks": ["--max-refinement-rounds must be at least 1"],
                    "command_shape": LIVE_GATE_COMMAND_SHAPE,
                })
                return 2
            try:
                dossier = _start_dossier(args)
            except ProblemDefinitionError as error:
                _json({"command": "start", "accepted": False,
                       "issues": [item.to_record() for item in error.issues]})
                return 2
            except ValueError as error:
                _json({"command": "start", "accepted": False, "error": str(error)})
                return 2
            try:
                loop = _loop(workspace, artifacts, args.provider, configuration, pricing,
                             dossier=dossier,
                             verifier_provider=args.verifier_provider,
                             verifier_configuration=verifier_configuration,
                             verifier_pricing=verifier_pricing)
            except Exception as error:  # adapter refusal is a fail-closed gate
                _print_adapter_refusal(args.provider, error)
                return 2
            declared = configuration.budget if configuration is not None else BudgetLimits(
                max_input_tokens=20_000, max_output_tokens=4_000,
                max_cost_microusd=10_000_000, max_wall_milliseconds=300_000,
                max_attempts=4,
            )
            run = loop.start(
                run_id=run_id, dossier=dossier,
                limits=replace(declared, max_refinement_rounds=args.max_refinement_rounds),
            )
            stamp = _now().isoformat().replace("+00:00", "Z")
            for role, role_configuration, role_pricing in (
                ("proposer", configuration, pricing),
                ("verifier", verifier_configuration, verifier_pricing),
            ):
                if role_configuration is None or role_pricing is None:
                    continue
                workspace.save_pricing_snapshot(
                    role_pricing, canonical_json=canonical_json(role_pricing), now=stamp,
                )
                workspace.save_live_run_configuration(
                    run_id=run_id, configuration_id=role_configuration.configuration_id,
                    schema_version=role_configuration.schema_version,
                    provider=role_configuration.provider,
                    model_identifier=role_configuration.model_identifier,
                    pricing_snapshot_id=role_configuration.pricing_snapshot_id,
                    content_hash=role_configuration.content_hash,
                    canonical_json=canonical_json(live_run_configuration_payload(role_configuration)),
                    now=stamp, role=role,
                )
            if args.execute:
                run = loop.run_to_terminal(run_id)
            _json(run)
            return 0
        if args.command == "advance":
            configuration = pricing = None
            if args.provider != "fake":
                prepared = _prepare_live_run(args)
                if isinstance(prepared, int):
                    return prepared
                configuration, pricing = prepared
            verifier_prepared = _prepare_verifier_role(args)
            if isinstance(verifier_prepared, int):
                return verifier_prepared
            verifier_configuration, verifier_pricing = verifier_prepared
            try:
                loop = _loop(workspace, artifacts, args.provider, configuration, pricing,
                             dossier=_run_dossier(workspace, run_id),
                             verifier_provider=args.verifier_provider,
                             verifier_configuration=verifier_configuration,
                             verifier_pricing=verifier_pricing)
            except Exception as error:  # adapter refusal is a fail-closed gate
                _print_adapter_refusal(args.provider, error)
                return 2
            _json(loop.advance(run_id))
            return 0
        if args.command == "jobs":
            _json(workspace.list_jobs(run_id))
            return 0
        if args.command == "budget":
            run = workspace.get_run(run_id)
            _json(workspace.budget(run.budget_id, now=_now().isoformat().replace("+00:00", "Z")))
            return 0
        if args.command == "pause":
            _json(_loop(workspace, artifacts, "fake",
                        dossier=_run_dossier(workspace, run_id)).pause(run_id))
            return 0
        if args.command == "resume":
            _json(_loop(workspace, artifacts, "fake",
                        dossier=_run_dossier(workspace, run_id)).resume(run_id))
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
            _json(workspace.get_manifest(run_id, round_index=args.round_index))
            return 0
        if args.command == "rounds":
            _json({
                "schema_version": "2.0.0",
                "budget": workspace.budget(
                    workspace.get_run(run_id).budget_id,
                    now=_now().isoformat().replace("+00:00", "Z"),
                ),
                "refinement_rounds": workspace.list_refinement_rounds(run_id),
                "run_stop": workspace.get_run_stop(run_id),
                "verifier_context_manifests": workspace.list_manifests(run_id),
            })
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
