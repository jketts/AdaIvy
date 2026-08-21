"""The provider registry is the single source of per-provider requirements.

ADR-0030 admits several providers. These tests pin the properties that keep the
registry honest: it covers exactly the admitted set, building an adapter touches
no network and imports no SDK, and the preflight derives every check from the
registry rather than assuming OpenAI.
"""

from __future__ import annotations

import glob
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from math_research.phase2 import SUPPORTED_LIVE_PROVIDERS
from math_research.phase2.live_config import load_live_run_configuration
from math_research.phase2.live_gate import preflight_live_gate
from math_research.phase2.pricing import load_pricing_snapshot
from math_research.phase2.provider_registry import (
    PROVIDER_SPECS,
    UNCONFIRMED_SDK_VERSION,
    UnknownProviderError,
    build_gateway,
    provider_spec,
    registered_providers,
)

# A representative model identifier per provider, for construction only.
MODEL_IDENTIFIERS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-opus-5",
    "bedrock": "anthropic.claude-opus-5",
    "azure_openai": "gpt-5-mini",
    "minimax": "MiniMax-M3",
    "qwen_dashscope": "qwen-plus",
    "deepseek": "deepseek-v4-flash",
}


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_covers_exactly_the_admitted_providers(self) -> None:
        self.assertEqual(
            sorted(SUPPORTED_LIVE_PROVIDERS), sorted(registered_providers()),
            "every admitted provider needs a spec, and vice versa",
        )

    def test_every_provider_has_a_representative_model_for_these_tests(self) -> None:
        self.assertEqual(sorted(MODEL_IDENTIFIERS), sorted(registered_providers()))

    def test_an_unknown_provider_raises_rather_than_defaulting(self) -> None:
        for name in ("", "openai ", "OpenAI", "not-a-provider"):
            with self.subTest(name=name):
                with self.assertRaises(UnknownProviderError):
                    provider_spec(name)

    def test_every_spec_declares_at_least_one_credential_and_output_mode(self) -> None:
        for name, spec in PROVIDER_SPECS.items():
            with self.subTest(provider=name):
                self.assertTrue(spec.required_credentials)
                self.assertTrue(spec.output_mode_capabilities)
                self.assertTrue(spec.required_capabilities)
                overlap = set(spec.required_credentials) & set(spec.optional_credentials)
                self.assertEqual(set(), overlap, "a credential is required or optional")

    def test_each_adapter_declares_the_capabilities_its_spec_requires(self) -> None:
        for name, spec in PROVIDER_SPECS.items():
            with self.subTest(provider=name):
                gateway = build_gateway(name, MODEL_IDENTIFIERS[name])
                declared = frozenset(getattr(gateway.config, "capabilities", ()))
                self.assertTrue(
                    spec.required_capabilities.issubset(declared),
                    f"{name} lacks {spec.required_capabilities - declared}",
                )
                self.assertTrue(
                    spec.output_mode_capabilities & declared,
                    f"{name} declares no accepted output mode",
                )

    def test_each_provider_routes_to_its_own_adapter_not_a_default(self) -> None:
        """The regression this pins: every provider silently getting OpenAI's adapter.

        `execute_live_gate` once constructed `OpenAIResponsesGateway` directly, so
        a configuration naming another provider would have been served by OpenAI's
        adapter against OpenAI's endpoint. Routing must be driven by the provider
        named in the content-hashed configuration.
        """
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
        for name, class_name in expected.items():
            with self.subTest(provider=name):
                gateway = build_gateway(name, MODEL_IDENTIFIERS[name])
                self.assertEqual(class_name, type(gateway).__name__)
        # And the provider identity survives onto the adapter's own config.
        for name in ("anthropic", "bedrock", "minimax"):
            with self.subTest(provider=name):
                gateway = build_gateway(name, MODEL_IDENTIFIERS[name])
                self.assertEqual(
                    MODEL_IDENTIFIERS[name], gateway.config.model_identifier,
                )

    def test_built_gateways_satisfy_the_model_gateway_protocol_shape(self) -> None:
        for name in registered_providers():
            with self.subTest(provider=name):
                gateway = build_gateway(name, MODEL_IDENTIFIERS[name])
                self.assertTrue(callable(getattr(gateway, "prepare", None)))
                self.assertTrue(callable(getattr(gateway, "complete", None)))

    def test_sdk_confirmation_distinguishes_none_needed_from_unconfirmed(self) -> None:
        bedrock = provider_spec("bedrock")
        self.assertFalse(bedrock.requires_sdk)
        self.assertTrue(
            bedrock.sdk_version_is_confirmed,
            "a provider needing no SDK has nothing to confirm",
        )
        anthropic = provider_spec("anthropic")
        self.assertTrue(anthropic.requires_sdk)
        self.assertTrue(
            anthropic.sdk_version_is_confirmed,
            "the anthropic wheel digest is recorded in the requirements file",
        )
        # The distinction still has to hold for a spec that needs an SDK and has
        # no confirmed pin, which no admitted provider is any more.
        unpinned = replace(anthropic, sdk_pinned_version=UNCONFIRMED_SDK_VERSION)
        self.assertTrue(unpinned.requires_sdk)
        self.assertFalse(unpinned.sdk_version_is_confirmed)

    def test_every_pinned_sdk_matches_the_provider_requirements_file(self) -> None:
        """A pin is only a pin if the installable requirement agrees with it.

        The preflight refuses a live call when the installed SDK differs from
        `sdk_pinned_version`, so a registry pin that no requirement line
        installs would fail every run for a reason nothing explains. Each
        requirement also needs its wheel digest recorded above it: an
        unverifiable package is the supply-chain risk the pin exists to close.
        """
        lines = Path("requirements-phase2-provider.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        requirements: dict[str, str] = {}
        digests: dict[str, str] = {}
        previous = ""
        for line in lines:
            if line.startswith("#"):
                previous = line
                continue
            if not line.strip():
                continue
            package, _, version = line.partition("==")
            self.assertTrue(version, f"requirement must be pinned exactly: {line}")
            requirements[package] = version
            self.assertIn(
                "SHA-256:", previous, f"no wheel digest recorded for {package}",
            )
            digests[package] = previous.rsplit(":", 1)[1].strip()
        for name, spec in PROVIDER_SPECS.items():
            if not spec.requires_sdk:
                continue
            with self.subTest(provider=name):
                self.assertIn(spec.sdk_package, requirements)
                self.assertEqual(
                    spec.sdk_pinned_version, requirements[spec.sdk_package],
                )
                self.assertRegex(digests[spec.sdk_package], r"^[0-9a-f]{64}$")

    def test_importing_and_building_loads_no_sdk_and_opens_no_socket(self) -> None:
        script = (
            "import sys\n"
            "from math_research.phase2.provider_registry import "
            "build_gateway, registered_providers\n"
            f"models = {MODEL_IDENTIFIERS!r}\n"
            "for name in registered_providers():\n"
            "    build_gateway(name, models[name])\n"
            "leaked = [m for m in ('openai','anthropic','boto3','botocore',"
            "'socket','ssl','http.client','urllib.request','requests') "
            "if m in sys.modules]\n"
            "print('LEAKED:' + ','.join(leaked))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=60,
            env={"PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("LEAKED:", completed.stdout)
        leaked = completed.stdout.strip().removeprefix("LEAKED:")
        self.assertEqual("", leaked, f"import-time leak: {leaked}")


class ProviderAwarePreflightTests(unittest.TestCase):
    def _pricing_by_provider(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for candidate in sorted(glob.glob("config/*pricing*.json")):
            snapshot = load_pricing_snapshot(Path(candidate))
            found.setdefault(snapshot.provider, Path(candidate))
        return found

    def test_each_shipped_configuration_reports_only_its_own_credentials(self) -> None:
        pricing = self._pricing_by_provider()
        checked = 0
        for candidate in sorted(glob.glob("config/phase2-live-*.json")):
            configuration = load_live_run_configuration(Path(candidate))
            snapshot_path = pricing.get(configuration.provider)
            if snapshot_path is None:
                continue
            spec = provider_spec(configuration.provider)
            with self.subTest(configuration=Path(candidate).name):
                result = preflight_live_gate(
                    configuration, load_pricing_snapshot(snapshot_path), environment={},
                )
                self.assertEqual(
                    sorted(spec.required_credentials + spec.required_settings),
                    sorted(result.missing_variables),
                    "a provider must report exactly its own credentials and"
                    " settings, and nothing belonging to another provider",
                )
                # The specific regression this replaces: OpenAI's credential name
                # surfacing for a run that never involved OpenAI.
                if configuration.provider != "openai":
                    self.assertNotIn("OPENAI_API_KEY", result.missing_variables)
                self.assertNotIn(
                    "structured_output_path_unsupported", result.failed_checks,
                )
                checked += 1
        self.assertGreater(checked, 1, "expected several providers to be covered")

    def test_a_provider_with_no_sdk_gets_no_sdk_failure(self) -> None:
        configuration = load_live_run_configuration(
            Path("config/phase2-live-bedrock-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/bedrock-anthropic-claude-opus-5-pricing-unconfirmed-2026-08-21.json")
        )
        result = preflight_live_gate(configuration, pricing, environment={})
        self.assertFalse(provider_spec("bedrock").requires_sdk)
        for check in result.failed_checks:
            self.assertNotIn("_sdk_", check)

    def test_an_unconfirmed_sdk_pin_fails_closed(self) -> None:
        """No admitted provider is unpinned now, so the rule is proved directly.

        Until 2026-08-21 the anthropic spec itself carried the `UNCONFIRMED`
        sentinel and this test read it off the shipped registry. Its pin is now
        recorded, so the check is made against a substituted spec: the rule must
        still hold for whatever provider is admitted next, and the substitution
        proves it is the sentinel that closes the gate rather than anything
        specific to one provider.
        """
        configuration = load_live_run_configuration(
            Path("config/phase2-live-anthropic-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/anthropic-claude-opus-5-pricing-2026-08-21.json")
        )
        environment = {"ANTHROPIC_API_KEY": "sk-test-only"}
        unpinned = replace(
            provider_spec("anthropic"), sdk_pinned_version=UNCONFIRMED_SDK_VERSION,
        )
        with patch.dict(PROVIDER_SPECS, {"anthropic": unpinned}):
            result = preflight_live_gate(
                configuration, pricing, environment=environment,
            )
        self.assertFalse(result.passed)
        self.assertEqual((), result.missing_variables)
        self.assertIn("anthropic_sdk_version_unconfirmed", result.failed_checks)

    def test_a_confirmed_pin_no_longer_reports_an_unconfirmed_sdk(self) -> None:
        """The shipped anthropic spec must not still be reported as unpinned.

        Without this the previous test would keep passing if the pin silently
        reverted: it patches the spec, so it can no longer see the real one.
        """
        configuration = load_live_run_configuration(
            Path("config/phase2-live-anthropic-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/anthropic-claude-opus-5-pricing-2026-08-21.json")
        )
        result = preflight_live_gate(
            configuration, pricing, environment={"ANTHROPIC_API_KEY": "sk-test-only"},
        )
        self.assertNotIn("anthropic_sdk_version_unconfirmed", result.failed_checks)
        # The SDK is deliberately absent from the offline environment, so the
        # remaining SDK check is availability -- not a missing pin.
        self.assertIn("anthropic_sdk_unavailable", result.failed_checks)

    def test_an_unknown_provider_is_named_and_refused(self) -> None:
        configuration = load_live_run_configuration(
            Path("config/phase2-live-gpt5-mini-v1.json")
        )
        forged = type(configuration)(
            **{
                **{
                    field: getattr(configuration, field)
                    for field in configuration.__dataclass_fields__
                },
                "provider": "not-a-provider",
            }
        )
        pricing = load_pricing_snapshot(
            Path("config/openai-gpt5-mini-pricing-2026-08-19.json")
        )
        result = preflight_live_gate(forged, pricing, environment={})
        self.assertFalse(result.passed)
        self.assertEqual(
            ("preflight_unknown_provider:not-a-provider",), result.failed_checks,
        )
        self.assertIsNone(result.estimated_two_call_cost_microusd)


if __name__ == "__main__":
    unittest.main()
