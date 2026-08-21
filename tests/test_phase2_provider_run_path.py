"""ADR-0038 acceptance suite: every admitted provider is selectable on the run path.

The measured gap this suite guards: `SUPPORTED_LIVE_PROVIDERS` admitted seven
providers with working adapters, shipped run configurations, and shipped pricing
snapshots, while `phase2 start` and `phase2 advance` -- the actual research-run
commands -- accepted only `("fake", "openai")`. Six providers were reachable
through `pricing-create`, `live-config-create`, `live-preflight`, and
`live-gate` and could not be selected for a run.

Thresholds are executable assertions here, and every forbidden outcome is
demonstrated impossible rather than left untested:

1. a provider selectable but unconstructable;
2. a missing required config field silently defaulted;
3. a secret appearing unredacted in any record, export, or report;
4. a network call during the offline suite;
5. an unconfirmed pricing snapshot passing as confirmed;
6. a provider in the registry absent from the CLI choices.

Isolation note: every CLI invocation patches
`math_research.phase2_cli.load_provider_environment` and clears the process
environment. Without that, this suite would read the operator's real
repository-root `.env` and its results would depend on which keys happen to be
configured on the machine running it.
"""

from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import OpaqueId, oid
from math_research.domain.policies import TrustPolicy
from math_research.phase2 import SUPPORTED_LIVE_PROVIDERS
from math_research.phase2.env_file import (
    NON_SECRET_PROVIDER_KEYS, PROVIDER_ENV_KEYS,
)
from math_research.phase2.live_config import (
    LiveRunConfiguration,
    create_live_run_configuration,
    load_live_run_configuration,
    write_live_run_configuration,
)
from math_research.phase2.live_gate import preflight_live_gate, scan_persisted_secret
from math_research.phase2.openai_compatible_gateway import (
    ProviderConfigurationError, provider_config, resolve_endpoint,
)
from math_research.phase2.bedrock_gateway import (
    BedrockCredentialError, BedrockInvokeGateway, BedrockProviderConfig,
)
from math_research.phase2.pricing import (
    PRICING_CONFIRMED,
    PRICING_UNCONFIRMED,
    PricingSnapshot,
    create_pricing_snapshot,
    load_pricing_snapshot,
    pricing_confirmation_status,
    pricing_snapshot_is_confirmed,
    write_pricing_snapshot,
)
from math_research.phase2.provider_registry import (
    PROVIDER_SPECS,
    UNCONFIRMED_SDK_VERSION,
    build_gateway,
    provider_secret_variables,
    provider_spec,
    registered_providers,
)
from math_research.phase2.records import BudgetLimits
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase2_cli import (
    CREDENTIALS_UNRESOLVED, RUN_PROVIDER_CHOICES, main as phase2_main,
)

CONFIG_DIR = Path("config")
CLI_SOURCE = Path("src/math_research/phase2_cli.py")

# Credentials that satisfy every provider's *required* set. These are obvious
# non-secrets; nothing here is a real credential and nothing reaches a provider.
FAKE_ENVIRONMENT = {
    "ANTHROPIC_API_KEY": "anthropic-not-a-real-key-000",
    "AWS_ACCESS_KEY_ID": "AKIAEXAMPLENOTREAL000",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-not-a-real-key-000",
    "AWS_REGION": "us-east-1",
    "AZURE_OPENAI_API_KEY": "azure-not-a-real-key-000",
    "AZURE_OPENAI_API_VERSION": "2026-01-01",
    "AZURE_OPENAI_DEPLOYMENT": "deployment-not-real",
    "AZURE_OPENAI_ENDPOINT": "https://example-not-real.openai.azure.com",
    "DASHSCOPE_API_KEY": "dashscope-not-a-real-key-000",
    "DEEPSEEK_API_KEY": "deepseek-not-a-real-key-000",
    "MINIMAX_API_KEY": "minimax-not-a-real-key-000",
    "OPENAI_API_KEY": "openai-not-a-real-key-000",
}


def shipped_configurations() -> dict[str, Path]:
    """Provider -> shipped live run configuration, first path by sorted name."""

    found: dict[str, Path] = {}
    for path in sorted(CONFIG_DIR.glob("phase2-live-*.json")):
        configuration = load_live_run_configuration(path)
        found.setdefault(configuration.provider, path)
    return found


def shipped_pricing() -> dict[str, Path]:
    """Provider -> the shipped snapshot its shipped configuration actually pins.

    Matched on `pricing_snapshot_id`, not on provider, so a second snapshot for
    the same provider cannot quietly stand in for the pinned one.
    """
    by_snapshot_id: dict[str, Path] = {}
    for path in sorted(CONFIG_DIR.glob("*pricing*.json")):
        by_snapshot_id[load_pricing_snapshot(path).snapshot_id.value] = path
    found: dict[str, Path] = {}
    for provider, config_path in shipped_configurations().items():
        pinned = load_live_run_configuration(config_path).pricing_snapshot_id.value
        if pinned in by_snapshot_id:
            found[provider] = by_snapshot_id[pinned]
    return found


def confirmed_pricing(configuration: LiveRunConfiguration) -> PricingSnapshot:
    """A pinned snapshot whose source carries no UNCONFIRMED marker.

    Rates are deliberately arbitrary test values with a source that says so. No
    real price is asserted anywhere in this suite.
    """
    return create_pricing_snapshot(
        snapshot_id=configuration.pricing_snapshot_id,
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        source="test-only recorded rate; not a quoted price",
        captured_at="2026-08-21T00:00:00Z",
        currency="USD",
        input_microusd_per_million_tokens=1_000,
        output_microusd_per_million_tokens=2_000,
    )


@contextmanager
def isolated(environment: dict[str, str] | None = None):
    """Cleared environment, no `.env` read, and every socket path fatal.

    The socket guard is the executable form of "make check is fully offline": if
    any command under test reaches DNS resolution or a socket, the test fails
    with the attempted target instead of quietly succeeding or hanging.
    """
    attempts: list[str] = []

    def refuse(*args: object, **kwargs: object):
        attempts.append(repr(args))
        raise AssertionError(f"offline suite attempted a network call: {args!r}")

    with patch.dict(os.environ, environment or {}, clear=True), patch(
        "math_research.phase2_cli.load_provider_environment"
    ), patch.object(socket, "socket", refuse), patch.object(
        socket, "create_connection", refuse
    ), patch.object(socket, "getaddrinfo", refuse):
        yield attempts


def run_cli(argv: list[str], environment: dict[str, str] | None = None):
    """Invoke the CLI offline and return `(status, parsed stdout, raw stdout)`."""

    output = io.StringIO()
    with isolated(environment), redirect_stdout(output):
        status = phase2_main(argv)
    text = output.getvalue()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    return status, value, text


class ProviderChoicesTests(unittest.TestCase):
    """Forbidden outcome: a provider in the registry absent from CLI choices."""

    def test_choices_equal_fake_plus_every_registered_provider(self) -> None:
        self.assertEqual(("fake", *sorted(SUPPORTED_LIVE_PROVIDERS)), RUN_PROVIDER_CHOICES)
        self.assertEqual(("fake", *registered_providers()), RUN_PROVIDER_CHOICES)
        self.assertEqual("fake", RUN_PROVIDER_CHOICES[0])
        self.assertEqual(len(set(RUN_PROVIDER_CHOICES)), len(RUN_PROVIDER_CHOICES))

    def test_choices_are_derived_from_the_registry_not_re_listed(self) -> None:
        """A re-listed literal is the defect; derivation is the fix.

        Equality above would still hold the day someone pasted the seven names
        into the CLI, and would then silently drift on the eighth provider. This
        asserts the mechanism, so drift is impossible rather than merely absent.
        """
        source = CLI_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            'RUN_PROVIDER_CHOICES: tuple[str, ...] = ("fake", *registered_providers())',
            source,
        )
        self.assertIn("choices=RUN_PROVIDER_CHOICES", source)
        for name in sorted(SUPPORTED_LIVE_PROVIDERS):
            with self.subTest(provider=name):
                self.assertNotIn(f'choices=("fake", "{name}"', source)

    def test_every_registered_provider_is_accepted_by_start_and_advance(self) -> None:
        """Selectable means the parser accepts it and the run path gates it.

        With no configuration the run must fail closed with status 2 -- a
        returned status, not an argparse `SystemExit(2)`, which is how this
        distinguishes "accepted then refused for missing config" from "rejected
        as an unknown choice".
        """
        with tempfile.TemporaryDirectory() as temporary:
            for command in ("start", "advance"):
                for name in registered_providers():
                    with self.subTest(command=command, provider=name):
                        status, value, _ = run_cli([
                            command, str(Path(temporary) / command), "run.choice.v1",
                            "--provider", name,
                        ])
                        self.assertEqual(2, status)
                        self.assertIn("missing_variables", value)

    def test_an_unadmitted_provider_is_rejected_by_the_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("", "OpenAI", "openai ", "not-a-provider", "fake2"):
                with self.subTest(provider=name):
                    with self.assertRaises(SystemExit) as raised:
                        with isolated(), redirect_stdout(io.StringIO()), patch(
                            "sys.stderr", io.StringIO()
                        ):
                            phase2_main([
                                "start", str(Path(temporary) / "ws"), "run.bad.v1",
                                "--provider", name,
                            ])
                    self.assertEqual(2, raised.exception.code)

    def test_fake_remains_the_default_and_needs_no_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "ws"
            status, value, _ = run_cli(["start", str(root), "run.default.v1"])
            self.assertEqual(0, status)
            self.assertEqual("run.default.v1", value["run_id"])
            with sqlite3.connect(root / "workspace.sqlite3") as connection:
                rows = connection.execute(
                    "SELECT COUNT(*) FROM live_run_configurations"
                ).fetchone()
            self.assertEqual((0,), rows, "the fake provider must bind no live configuration")


class ProviderConstructabilityTests(unittest.TestCase):
    """Forbidden outcome: a provider selectable but unconstructable."""

    def test_every_selectable_provider_ships_a_configuration_and_a_snapshot(self) -> None:
        configurations, pricing = shipped_configurations(), shipped_pricing()
        for name in registered_providers():
            with self.subTest(provider=name):
                self.assertIn(name, configurations, "no shipped live run configuration")
                self.assertIn(name, pricing, "no shipped pricing snapshot")
                configuration = load_live_run_configuration(configurations[name])
                snapshot = load_pricing_snapshot(pricing[name])
                self.assertEqual(configuration.provider, snapshot.provider)
                self.assertEqual(
                    configuration.model_identifier, snapshot.model_identifier
                )
                self.assertEqual(
                    configuration.pricing_snapshot_id, snapshot.snapshot_id,
                    "the shipped snapshot is not the one the configuration pins",
                )

    def test_every_selectable_provider_constructs_from_its_shipped_configuration(self) -> None:
        expected = {
            "openai": "OpenAIResponsesGateway",
            "anthropic": "AnthropicMessagesGateway",
            "bedrock": "BedrockInvokeGateway",
            "azure_openai": "OpenAICompatibleChatGateway",
            "minimax": "OpenAICompatibleChatGateway",
            "qwen_dashscope": "OpenAICompatibleChatGateway",
            "deepseek": "OpenAICompatibleChatGateway",
        }
        self.assertEqual(sorted(expected), sorted(registered_providers()))
        for name, path in shipped_configurations().items():
            configuration = load_live_run_configuration(path)
            with self.subTest(provider=name):
                gateway = build_gateway(name, configuration.model_identifier)
                self.assertEqual(expected[name], type(gateway).__name__)
                self.assertEqual(
                    configuration.model_identifier, gateway.config.model_identifier
                )
                self.assertTrue(callable(getattr(gateway, "prepare", None)))
                self.assertTrue(callable(getattr(gateway, "complete", None)))

    def test_the_selectable_set_and_the_constructable_set_are_the_same(self) -> None:
        selectable = set(RUN_PROVIDER_CHOICES) - {"fake"}
        constructable = set()
        for name, path in shipped_configurations().items():
            configuration = load_live_run_configuration(path)
            try:
                build_gateway(name, configuration.model_identifier)
            except Exception:  # noqa: BLE001 - the point is that none is raised
                continue
            constructable.add(name)
        self.assertEqual(selectable, constructable)


class RequiredConfigurationFailsClosedTests(unittest.TestCase):
    """Forbidden outcome: a missing required config field silently defaulted."""

    def _paths(self, temporary: str, provider: str) -> tuple[Path, Path]:
        configuration = load_live_run_configuration(shipped_configurations()[provider])
        root = Path(temporary)
        config_path, pricing_path = root / "config.json", root / "pricing.json"
        write_live_run_configuration(configuration, config_path)
        write_pricing_snapshot(confirmed_pricing(configuration), pricing_path)
        return config_path, pricing_path

    def test_each_azure_required_field_is_named_when_absent(self) -> None:
        spec = provider_spec("azure_openai")
        # One secret, from `.env`; three non-secret settings, from
        # `.env.settings`. All four are required and all four are reported the
        # same way when absent -- the split is about which file holds them, not
        # about which are needed.
        self.assertEqual(("AZURE_OPENAI_API_KEY",), spec.required_credentials)
        self.assertEqual(
            (
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_OPENAI_API_VERSION",
            ),
            spec.required_settings,
        )
        required = spec.required_credentials + spec.required_settings
        with tempfile.TemporaryDirectory() as temporary:
            config_path, pricing_path = self._paths(temporary, "azure_openai")
            for withheld in required:
                environment = {
                    key: value for key, value in FAKE_ENVIRONMENT.items()
                    if key != withheld
                }
                with self.subTest(withheld=withheld):
                    status, value, text = run_cli([
                        "start", str(Path(temporary) / f"ws-{withheld}"),
                        "run.azure.v1", "--provider", "azure_openai",
                        "--config", str(config_path),
                        "--pricing-snapshot", str(pricing_path),
                    ], environment)
                    self.assertEqual(2, status)
                    self.assertEqual([withheld], value["missing_variables"])
                    self.assertNotIn("fake", text)
                    self.assertFalse(
                        (Path(temporary) / f"ws-{withheld}" / "workspace.sqlite3")
                        .exists() and self._has_run(
                            Path(temporary) / f"ws-{withheld}", "run.azure.v1"
                        ),
                        "a refused run must not exist",
                    )

    def _has_run(self, root: Path, run_id: str) -> bool:
        database = root / "workspace.sqlite3"
        if not database.exists():
            return False
        with sqlite3.connect(database) as connection:
            try:
                rows = connection.execute(
                    "SELECT COUNT(*) FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
            except sqlite3.OperationalError:
                return False
        return bool(rows[0])

    def test_azure_endpoint_deployment_and_api_version_are_never_defaulted(self) -> None:
        """The adapter itself refuses, so no caller can supply a default."""

        config = provider_config("azure_openai", model_identifier="gpt-5-mini")
        complete = {
            "AZURE_OPENAI_ENDPOINT": FAKE_ENVIRONMENT["AZURE_OPENAI_ENDPOINT"],
            "AZURE_OPENAI_DEPLOYMENT": FAKE_ENVIRONMENT["AZURE_OPENAI_DEPLOYMENT"],
            "AZURE_OPENAI_API_VERSION": FAKE_ENVIRONMENT["AZURE_OPENAI_API_VERSION"],
        }
        resolved = resolve_endpoint(config, dict(complete))
        self.assertEqual(FAKE_ENVIRONMENT["AZURE_OPENAI_DEPLOYMENT"], resolved.deployment)
        self.assertIn("api-version", dict(resolved.query_parameters))
        for withheld in sorted(complete):
            environment = {k: v for k, v in complete.items() if k != withheld}
            with self.subTest(withheld=withheld):
                with self.assertRaises(ProviderConfigurationError) as raised:
                    resolve_endpoint(config, environment)
                self.assertIn(withheld, str(raised.exception))

    def test_bedrock_region_is_named_and_never_defaulted(self) -> None:
        gateway = BedrockInvokeGateway(
            BedrockProviderConfig(model_identifier="anthropic.claude-opus-5"),
            environment={
                "AWS_ACCESS_KEY_ID": FAKE_ENVIRONMENT["AWS_ACCESS_KEY_ID"],
                "AWS_SECRET_ACCESS_KEY": FAKE_ENVIRONMENT["AWS_SECRET_ACCESS_KEY"],
            },
            env_file_path=Path("/nonexistent/.env"),
        )
        with self.assertRaises(BedrockCredentialError) as raised:
            gateway.resolve_region()
        self.assertIn("AWS_REGION", str(raised.exception))
        self.assertIn("No region is", str(raised.exception))
        with tempfile.TemporaryDirectory() as temporary:
            config_path, pricing_path = self._paths(temporary, "bedrock")
            environment = {
                key: value for key, value in FAKE_ENVIRONMENT.items()
                if key != "AWS_REGION"
            }
            status, value, _ = run_cli([
                "start", str(Path(temporary) / "ws"), "run.bedrock.v1",
                "--provider", "bedrock", "--config", str(config_path),
                "--pricing-snapshot", str(pricing_path),
            ], environment)
            self.assertEqual(2, status)
            self.assertEqual(["AWS_REGION"], value["missing_variables"])

    def test_bedrock_session_token_stays_optional(self) -> None:
        self.assertEqual(
            ("AWS_SESSION_TOKEN",), provider_spec("bedrock").optional_credentials
        )
        with tempfile.TemporaryDirectory() as temporary:
            config_path, pricing_path = self._paths(temporary, "bedrock")
            status, value, _ = run_cli([
                "start", str(Path(temporary) / "ws"), "run.bedrock.optional.v1",
                "--provider", "bedrock", "--config", str(config_path),
                "--pricing-snapshot", str(pricing_path),
            ], FAKE_ENVIRONMENT)
            self.assertEqual(0, status, value)

    def test_a_selected_provider_never_falls_back_to_the_configured_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, pricing_path = self._paths(temporary, "bedrock")
            status, value, _ = run_cli([
                "start", str(Path(temporary) / "ws"), "run.mismatch.v1",
                "--provider", "deepseek", "--config", str(config_path),
                "--pricing-snapshot", str(pricing_path),
            ], FAKE_ENVIRONMENT)
            self.assertEqual(2, status)
            self.assertIn(
                "provider_mismatch:selected=deepseek:configured=bedrock",
                value["failed_checks"],
            )
            self.assertFalse(self._has_run(Path(temporary) / "ws", "run.mismatch.v1"))

    def test_a_live_provider_never_falls_back_to_the_fake_gateway(self) -> None:
        """No configuration, no run: absence never resolves to the fixture loop."""

        with tempfile.TemporaryDirectory() as temporary:
            for name in registered_providers():
                root = Path(temporary) / f"ws-{name}"
                with self.subTest(provider=name):
                    status, value, _ = run_cli([
                        "start", str(root), "run.nofallback.v1", "--provider", name,
                    ], FAKE_ENVIRONMENT)
                    self.assertEqual(2, status)
                    self.assertIn("config.provider", value["missing_variables"])
                    self.assertIn("pricing.source", value["missing_variables"])
                    self.assertFalse(self._has_run(root, "run.nofallback.v1"))
            # And with no provider named at all the requirement is reported as
            # unresolved rather than attributed to some default provider.
            status, value, _ = run_cli(["live-preflight"], FAKE_ENVIRONMENT)
            self.assertEqual(2, status)
            self.assertIn(CREDENTIALS_UNRESOLVED, value["missing_variables"])

    def test_a_missing_required_credential_is_reported_for_every_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for name, path in sorted(shipped_configurations().items()):
                configuration = load_live_run_configuration(path)
                root = Path(temporary) / name
                config_path = root / "config.json"
                pricing_path = root / "pricing.json"
                write_live_run_configuration(configuration, config_path)
                write_pricing_snapshot(confirmed_pricing(configuration), pricing_path)
                with self.subTest(provider=name):
                    status, value, _ = run_cli([
                        "start", str(root / "ws"), "run.creds.v1", "--provider", name,
                        "--config", str(config_path),
                        "--pricing-snapshot", str(pricing_path),
                    ])
                    self.assertEqual(2, status)
                    self.assertEqual(
                        sorted(provider_spec(name).required_credentials),
                        sorted(value["missing_variables"]),
                        "a provider must report exactly its own credentials",
                    )


class UnconfirmedPricingTests(unittest.TestCase):
    """Forbidden outcome: an unconfirmed snapshot passing as confirmed."""

    def test_shipped_snapshots_classify_exactly_as_their_names_declare(self) -> None:
        seen = {PRICING_CONFIRMED: 0, PRICING_UNCONFIRMED: 0}
        for path in sorted(CONFIG_DIR.glob("*pricing*.json")):
            snapshot = load_pricing_snapshot(path)
            status = pricing_confirmation_status(snapshot)
            seen[status] += 1
            with self.subTest(snapshot=path.name):
                self.assertEqual(
                    PRICING_UNCONFIRMED if "unconfirmed" in path.name
                    else PRICING_CONFIRMED,
                    status,
                    "the file name and the recorded source disagree",
                )
        self.assertGreater(seen[PRICING_UNCONFIRMED], 0, "expected placeholders")
        self.assertGreater(seen[PRICING_CONFIRMED], 0, "expected recorded rates")

    def test_the_marker_is_detected_case_insensitively(self) -> None:
        snapshot = create_pricing_snapshot(
            snapshot_id=oid("pricing.case.v1"), provider="bedrock",
            model_identifier="anthropic.claude-opus-5",
            source="unconfirmed placeholder, lowercase", captured_at="2026-08-21T00:00:00Z",
            currency="USD", input_microusd_per_million_tokens=1,
            output_microusd_per_million_tokens=1,
        )
        self.assertFalse(pricing_snapshot_is_confirmed(snapshot))

    def test_the_classifier_can_only_withhold_confirmation(self) -> None:
        """The honest limit, asserted rather than implied.

        The marker is exclusion-only: an absurd rate with a clean source is
        still reported confirmed, because no offline check can verify a price.
        Recording that here keeps the classifier from being read as a
        correctness guarantee.
        """
        snapshot = create_pricing_snapshot(
            snapshot_id=oid("pricing.residual.v1"), provider="bedrock",
            model_identifier="anthropic.claude-opus-5",
            source="operator recorded rate", captured_at="2026-08-21T00:00:00Z",
            currency="USD", input_microusd_per_million_tokens=999_999_999,
            output_microusd_per_million_tokens=999_999_999,
        )
        self.assertTrue(pricing_snapshot_is_confirmed(snapshot))

    def test_the_preflight_refuses_an_unconfirmed_snapshot(self) -> None:
        configuration = load_live_run_configuration(
            shipped_configurations()["bedrock"]
        )
        unconfirmed = load_pricing_snapshot(shipped_pricing()["bedrock"])
        result = preflight_live_gate(
            configuration, unconfirmed, environment=dict(FAKE_ENVIRONMENT),
        )
        self.assertFalse(result.passed)
        self.assertIn(
            f"pricing_snapshot_unconfirmed:{unconfirmed.snapshot_id.value}",
            result.failed_checks,
        )
        # Not vacuous: the same configuration with a confirmed snapshot passes,
        # so the refusal above is caused by the marker and nothing else.
        confirmed = preflight_live_gate(
            configuration, confirmed_pricing(configuration),
            environment=dict(FAKE_ENVIRONMENT),
        )
        self.assertTrue(confirmed.passed, confirmed)

    def test_the_run_path_refuses_a_snapshot_the_configuration_does_not_pin(self) -> None:
        """A loadable, confirmed snapshot is not enough: it must be the pinned one."""

        configuration = load_live_run_configuration(
            shipped_configurations()["bedrock"]
        )
        unpinned = create_pricing_snapshot(
            snapshot_id=oid("pricing.bedrock.not-the-pinned-one.v1"),
            provider=configuration.provider,
            model_identifier=configuration.model_identifier,
            source="test-only recorded rate; not a quoted price",
            captured_at="2026-08-21T00:00:00Z", currency="USD",
            input_microusd_per_million_tokens=1_000,
            output_microusd_per_million_tokens=2_000,
        )
        self.assertNotEqual(configuration.pricing_snapshot_id, unpinned.snapshot_id)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, pricing_path = root / "config.json", root / "pricing.json"
            write_live_run_configuration(configuration, config_path)
            write_pricing_snapshot(unpinned, pricing_path)
            status, value, _ = run_cli([
                "start", str(root / "ws"), "run.unpinned.v1", "--provider", "bedrock",
                "--config", str(config_path), "--pricing-snapshot", str(pricing_path),
            ], FAKE_ENVIRONMENT)
            self.assertEqual(2, status)
            self.assertIn("pricing_snapshot_id_mismatch", value["failed_checks"])

    def test_the_run_path_refuses_an_unconfirmed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status, value, _ = run_cli([
                "start", str(root / "ws"), "run.unconfirmed.v1",
                "--provider", "bedrock",
                "--config", str(shipped_configurations()["bedrock"]),
                "--pricing-snapshot", str(shipped_pricing()["bedrock"]),
            ], FAKE_ENVIRONMENT)
            self.assertEqual(2, status)
            self.assertTrue(
                any(
                    check.startswith("pricing_snapshot_unconfirmed:")
                    for check in value["failed_checks"]
                ),
                value,
            )

    def test_the_sdk_sentinel_and_the_pricing_marker_are_separate_refusals(self) -> None:
        """Two independent unconfirmed states, neither collapsed into the other.

        The concurrent ADR-0037 pinned the Anthropic SDK, so the sentinel rule is
        asserted against a substituted spec -- proving the rule rather than the
        current value -- plus a positive assertion that the shipped spec is now
        pinned. Without the pair, a silent revert would keep this green.
        """
        shipped = provider_spec("anthropic")
        self.assertTrue(shipped.sdk_version_is_confirmed, "ADR-0037 pins this SDK")
        self.assertNotEqual(UNCONFIRMED_SDK_VERSION, shipped.sdk_pinned_version)
        unpinned = replace(shipped, sdk_pinned_version=UNCONFIRMED_SDK_VERSION)
        self.assertTrue(unpinned.requires_sdk)
        self.assertFalse(unpinned.sdk_version_is_confirmed)
        # A provider needing no SDK has nothing to confirm, and that is not the
        # same state as an unrecorded pin.
        self.assertFalse(provider_spec("bedrock").requires_sdk)
        self.assertTrue(provider_spec("bedrock").sdk_version_is_confirmed)

    def test_every_provider_needing_an_sdk_is_refused_without_it(self) -> None:
        """No provider reaches a live call on an unpinned or absent package."""

        for name, path in sorted(shipped_configurations().items()):
            spec = provider_spec(name)
            if not spec.requires_sdk:
                continue
            configuration = load_live_run_configuration(path)
            with self.subTest(provider=name):
                result = preflight_live_gate(
                    configuration, confirmed_pricing(configuration),
                    environment=dict(FAKE_ENVIRONMENT), installed_sdk_version=None,
                )
                self.assertFalse(result.passed)
                self.assertTrue(
                    any(
                        check.endswith("_sdk_unavailable")
                        or check.endswith("_sdk_version_unconfirmed")
                        for check in result.failed_checks
                    ),
                    result.failed_checks,
                )


class SecretRedactionTests(unittest.TestCase):
    """Forbidden outcome: a secret in any record, export, or report."""

    SECRET = "aws-secret-value-that-must-never-persist-0001"

    def _environment(self) -> dict[str, str]:
        return {
            **FAKE_ENVIRONMENT,
            "AWS_SECRET_ACCESS_KEY": self.SECRET,
            "AWS_SESSION_TOKEN": self.SECRET + "-session",
        }

    def test_a_bound_live_run_persists_no_secret_anywhere(self) -> None:
        configuration = load_live_run_configuration(
            shipped_configurations()["bedrock"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, pricing_path = root / "config.json", root / "pricing.json"
            write_live_run_configuration(configuration, config_path)
            write_pricing_snapshot(confirmed_pricing(configuration), pricing_path)
            workspace_root = root / "ws"
            run_id = "run.bedrock.bound.v1"
            environment = self._environment()
            status, _, _ = run_cli([
                "start", str(workspace_root), run_id, "--provider", "bedrock",
                "--config", str(config_path), "--pricing-snapshot", str(pricing_path),
            ], environment)
            self.assertEqual(0, status)

            # The pinned snapshot and the content-hashed configuration are bound
            # to this run, so the provider that will be called is the provider
            # the operator pinned.
            with sqlite3.connect(workspace_root / "workspace.sqlite3") as connection:
                connection.row_factory = sqlite3.Row
                bound = dict(connection.execute(
                    "SELECT * FROM live_run_configurations WHERE run_id=?", (run_id,)
                ).fetchone())
                snapshots = [dict(row) for row in connection.execute(
                    "SELECT * FROM pricing_snapshots"
                )]
            self.assertEqual("bedrock", bound["provider"])
            self.assertEqual(configuration.model_identifier, bound["model_identifier"])
            self.assertEqual(configuration.content_hash, bound["content_hash"])
            self.assertEqual(
                configuration.pricing_snapshot_id.value, bound["pricing_snapshot_id"]
            )
            self.assertEqual(
                [configuration.pricing_snapshot_id.value],
                [item["snapshot_id"] for item in snapshots],
            )

            # Every reading surface: records, timeline, artifacts, export, report.
            texts = []
            for argv in (
                ["jobs", str(workspace_root), run_id],
                ["budget", str(workspace_root), run_id],
                ["timeline", str(workspace_root), run_id],
                ["artifacts", str(workspace_root), run_id, "--content"],
                ["review", str(workspace_root), run_id],
                ["export", str(workspace_root), run_id, str(root / "dossier.json")],
                ["report", str(workspace_root), run_id, "--output", str(root / "r.md")],
            ):
                status, _, text = run_cli(argv, environment)
                self.assertEqual(0, status, argv)
                texts.append(text)
            texts.append((root / "dossier.json").read_text(encoding="utf-8"))
            texts.append((root / "r.md").read_text(encoding="utf-8"))
            for secret in (self.SECRET, self.SECRET + "-session"):
                for text in texts:
                    self.assertNotIn(secret, text)
                self.assertEqual(
                    ((), ()),
                    scan_persisted_secret(
                        workspace_root, workspace_root / "workspace.sqlite3", secret
                    ),
                )
                self.assertEqual(
                    ((), ()), scan_persisted_secret(root, root / "missing.sqlite3", secret)
                )

    def test_a_refused_run_reports_no_secret(self) -> None:
        configuration = load_live_run_configuration(
            shipped_configurations()["bedrock"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, pricing_path = root / "config.json", root / "pricing.json"
            write_live_run_configuration(configuration, config_path)
            write_pricing_snapshot(confirmed_pricing(configuration), pricing_path)
            environment = {
                key: value for key, value in self._environment().items()
                if key != "AWS_REGION"
            }
            status, _, text = run_cli([
                "start", str(root / "ws"), "run.refused.v1", "--provider", "bedrock",
                "--config", str(config_path), "--pricing-snapshot", str(pricing_path),
            ], environment)
            self.assertEqual(2, status)
            self.assertNotIn(self.SECRET, text)
            self.assertIn("AWS_REGION", text)

    def test_secret_variables_exclude_non_secret_operational_settings(self) -> None:
        for name in registered_providers():
            spec = provider_spec(name)
            declared = set(spec.required_credentials + spec.optional_credentials)
            secret = set(provider_secret_variables(name))
            with self.subTest(provider=name):
                self.assertTrue(secret)
                self.assertEqual(secret, declared - NON_SECRET_PROVIDER_KEYS)
                self.assertTrue(declared <= PROVIDER_ENV_KEYS)

    def test_the_versioned_example_offers_every_provider_variable_blank(self) -> None:
        lines = Path(".env.example").read_text(encoding="utf-8").splitlines()
        assignments = {
            line.split("=", 1)[0]: line.split("=", 1)[1]
            for line in lines if "=" in line and not line.startswith("#")
        }
        for name in registered_providers():
            spec = provider_spec(name)
            for variable in spec.required_credentials + spec.optional_credentials:
                with self.subTest(provider=name, variable=variable):
                    self.assertIn(variable, assignments, ".env.example lacks a variable")
                    self.assertEqual("", assignments[variable], "value must stay blank")


class OfflineAndTrustBoundaryTests(unittest.TestCase):
    """Forbidden outcome: a network call in the offline suite; a result as warrant."""

    def test_no_command_in_this_suite_can_open_a_socket(self) -> None:
        """The guard is proved live, so its silence elsewhere means something."""

        with self.assertRaises(AssertionError):
            with isolated():
                socket.socket()
        with self.assertRaises(AssertionError):
            with isolated():
                socket.getaddrinfo("example.invalid", 443)

    def test_every_provider_selection_stays_offline_without_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for name in registered_providers():
                for command in ("start", "advance"):
                    with self.subTest(provider=name, command=command):
                        status, _, _ = run_cli([
                            command, str(Path(temporary) / f"{name}-{command}"),
                            "run.offline.v1", "--provider", name,
                        ], FAKE_ENVIRONMENT)
                        self.assertEqual(2, status)

    def test_every_shipped_configuration_stays_offline_through_the_gate(self) -> None:
        """Either fail closed, or bind the run -- never call a provider.

        Whether a given provider gets past the preflight here depends on whether
        its optional SDK happens to be installed, which is not a property of this
        slice. The invariant that is a property of this slice is asserted instead:
        no socket is attempted and no model call is recorded, for every shipped
        configuration, on every machine.
        """
        pricing = shipped_pricing()
        with tempfile.TemporaryDirectory() as temporary:
            for name, path in sorted(shipped_configurations().items()):
                root = Path(temporary) / name
                with self.subTest(provider=name):
                    status, _, _ = run_cli([
                        "start", str(root), "run.shipped.v1",
                        "--provider", name, "--config", str(path),
                        "--pricing-snapshot", str(pricing[name]),
                    ], FAKE_ENVIRONMENT)
                    self.assertIn(status, (0, 2))
                    database = root / "workspace.sqlite3"
                    if status == 0 and database.exists():
                        with sqlite3.connect(database) as connection:
                            calls = connection.execute(
                                "SELECT COUNT(*) FROM model_calls"
                            ).fetchone()
                        self.assertEqual(
                            (0,), calls, "start must not call a provider",
                        )

    def test_binding_a_live_run_creates_no_proposal_and_no_warrant(self) -> None:
        configuration = load_live_run_configuration(
            shipped_configurations()["bedrock"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, pricing_path = root / "config.json", root / "pricing.json"
            write_live_run_configuration(configuration, config_path)
            write_pricing_snapshot(confirmed_pricing(configuration), pricing_path)
            workspace_root = root / "ws"
            run_id = "run.bedrock.trust.v1"
            status, _, _ = run_cli([
                "start", str(workspace_root), run_id, "--provider", "bedrock",
                "--config", str(config_path), "--pricing-snapshot", str(pricing_path),
            ], FAKE_ENVIRONMENT)
            self.assertEqual(0, status)
            with SQLiteWorkspace(workspace_root / "workspace.sqlite3") as workspace:
                record = workspace.get_run(OpaqueId(run_id))
                dossier = workspace.load_dossier(record.dossier_id)
                self.assertEqual((), workspace.list_proposals(OpaqueId(run_id)))
                self.assertEqual((), workspace.list_model_calls(OpaqueId(run_id)))
                resolution = TrustPolicy(dossier).target_resolution()
            # Binding a live provider to a run grants nothing: no warrant kind,
            # no logical status, no novelty or significance assessment.
            self.assertEqual((), resolution.warrant_kinds)
            self.assertEqual("unknown", resolution.logical_status)
            self.assertEqual("not_assessed", resolution.novelty_status)
            self.assertEqual("not_assessed", resolution.significance_status)
            self.assertTrue(resolution.blockers)

    def test_the_registry_is_the_only_place_providers_are_enumerated(self) -> None:
        """Registry, allowlist, and CLI choices agree; drift fails here."""

        self.assertEqual(sorted(PROVIDER_SPECS), sorted(SUPPORTED_LIVE_PROVIDERS))
        self.assertEqual(
            sorted(PROVIDER_SPECS), sorted(set(RUN_PROVIDER_CHOICES) - {"fake"})
        )


if __name__ == "__main__":
    unittest.main()
