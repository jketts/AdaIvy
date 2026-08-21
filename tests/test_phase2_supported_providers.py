"""The live-provider allowlist is defined once and must not drift.

ADR-0030 admits several providers at the Phase 2 model boundary. The allowlist
lives in `math_research.phase2.SUPPORTED_LIVE_PROVIDERS`; the pricing validator,
the live-run configuration validator, and both JSON schemas all derive from it.
These tests fail if any copy diverges, and if a shipped configuration or pricing
snapshot names a provider the allowlist does not admit.
"""

from __future__ import annotations

from dataclasses import replace
import json
import tempfile
import unittest
from pathlib import Path

from math_research.phase2 import SUPPORTED_LIVE_PROVIDERS
from math_research.phase2.live_config import (
    LiveRunConfigurationError, load_live_run_configuration,
)
from math_research.phase2.pricing import PricingSnapshotError, load_pricing_snapshot
from math_research.phase2.live_gate import (
    PREFLIGHT_SUPPORTED_PROVIDERS, preflight_live_gate,
)


SCHEMAS = (
    Path("schemas/pricing-snapshot-v1.schema.json"),
    Path("schemas/live-run-config-v1.schema.json"),
)


class SupportedProviderAllowlistTests(unittest.TestCase):
    def test_openai_remains_admitted(self) -> None:
        self.assertIn("openai", SUPPORTED_LIVE_PROVIDERS)

    def test_every_schema_enum_equals_the_single_allowlist(self) -> None:
        for schema_path in SCHEMAS:
            with self.subTest(schema=schema_path.name):
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                declared = schema["properties"]["provider"]
                self.assertIn("enum", declared, "provider must be an enum, not a const")
                self.assertEqual(
                    sorted(SUPPORTED_LIVE_PROVIDERS), sorted(declared["enum"]),
                    f"{schema_path.name} provider enum has drifted from the allowlist",
                )

    def test_shipped_pricing_snapshots_name_admitted_providers(self) -> None:
        snapshots = sorted(Path("config").glob("*pricing*.json"))
        self.assertTrue(snapshots)
        for path in snapshots:
            with self.subTest(snapshot=path.name):
                snapshot = load_pricing_snapshot(path)
                self.assertIn(snapshot.provider, SUPPORTED_LIVE_PROVIDERS)

    def test_shipped_live_configurations_name_admitted_providers(self) -> None:
        configurations = sorted(Path("config").glob("phase2-live-*.json"))
        self.assertTrue(configurations)
        for path in configurations:
            with self.subTest(configuration=path.name):
                configuration = load_live_run_configuration(path)
                self.assertIn(configuration.provider, SUPPORTED_LIVE_PROVIDERS)

    def test_an_unadmitted_provider_is_still_rejected(self) -> None:
        source = json.loads(
            Path("config/phase2-live-gpt5-mini-v1.json").read_text(encoding="utf-8")
        )
        source["provider"] = "not-a-real-provider"
        self.assertNotIn("not-a-real-provider", SUPPORTED_LIVE_PROVIDERS)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "configuration.json"
            target.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(LiveRunConfigurationError):
                load_live_run_configuration(target)

        snapshot = json.loads(
            Path("config/openai-gpt5-mini-pricing-2026-08-19.json").read_text(
                encoding="utf-8"
            )
        )
        snapshot["provider"] = "not-a-real-provider"
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "pricing.json"
            target.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaises(PricingSnapshotError):
                load_pricing_snapshot(target)


class PreflightProviderScopeTests(unittest.TestCase):
    """The preflight checks every admitted provider on its own terms."""

    def test_the_preflight_can_check_every_admitted_provider(self) -> None:
        """No admitted provider may fall outside the preflight's knowledge.

        This replaces an earlier transitional guard that asserted the opposite:
        while only OpenAI was preflightable, every other provider had to refuse.
        ADR-0030 closed that gap, so the invariant is now equality -- a provider
        admitted at the boundary but unknown to the preflight would be a run
        nobody checked.
        """
        self.assertEqual(
            frozenset(SUPPORTED_LIVE_PROVIDERS), PREFLIGHT_SUPPORTED_PROVIDERS,
        )

    def test_a_non_openai_provider_reports_only_its_own_credentials(self) -> None:
        configuration = load_live_run_configuration(
            Path("config/phase2-live-minimax-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/minimax-m3-pricing-2026-08-21.json")
        )
        result = preflight_live_gate(configuration, pricing, environment={})
        self.assertFalse(result.passed)
        self.assertEqual(("MINIMAX_API_KEY",), result.missing_variables)
        # The specific bug this guards: reporting a missing OPENAI_API_KEY for a
        # run that never involved the OpenAI provider. Note that the string
        # "openai" may still legitimately appear in a failed check -- MiniMax is
        # an OpenAI-compatible endpoint and its adapter really does need the
        # `openai` package -- so the assertion is on credentials, not substrings.
        self.assertNotIn("OPENAI_API_KEY", repr(result))
        self.assertNotIn("OPENAI_API_KEY", result.missing_variables)

    def test_a_provider_outside_the_allowlist_still_fails_closed(self) -> None:
        configuration = load_live_run_configuration(
            Path("config/phase2-live-minimax-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/minimax-m3-pricing-2026-08-21.json")
        )
        unadmitted = replace(configuration, provider="not-a-real-provider")
        self.assertNotIn(unadmitted.provider, SUPPORTED_LIVE_PROVIDERS)
        result = preflight_live_gate(unadmitted, pricing, environment={})
        self.assertFalse(result.passed)
        self.assertEqual(
            (f"preflight_unknown_provider:{unadmitted.provider}",),
            result.failed_checks,
        )
        self.assertEqual((), result.missing_variables)
        self.assertIsNone(result.estimated_two_call_cost_microusd)

    def test_openai_still_preflights_normally(self) -> None:
        configuration = load_live_run_configuration(
            Path("config/phase2-live-gpt5-mini-v1.json")
        )
        pricing = load_pricing_snapshot(
            Path("config/openai-gpt5-mini-pricing-2026-08-19.json")
        )
        result = preflight_live_gate(configuration, pricing, environment={})
        self.assertIn("OPENAI_API_KEY", result.missing_variables)
        self.assertNotIn(
            f"preflight_unsupported_provider:{configuration.provider}",
            result.failed_checks,
        )


if __name__ == "__main__":
    unittest.main()
