"""Unit and adversarial tests for named campaign credential profiles.

The load-bearing properties: profile selection is explicit; ambient process
credentials are never consulted, even when they are present; there is no
silent fallback to another provider or to a host-agent credential; and no
record ever carries a secret value.
"""

from __future__ import annotations

import os
import pickle
import unittest
from unittest import mock

from math_research.campaign.credentials import (
    DEFAULT_LIVE_PROFILE_ID,
    CampaignRoutePolicy,
    CredentialProfile,
    CredentialProfileError,
    ProfileSelectionRecord,
    assert_no_secret_values,
    resolve_credential_profile,
    select_credential_profile,
)

SECRET = "sk-adaivy-live-0123456789abcdef"
SETTINGS = (
    ("AZURE_OPENAI_API_VERSION", "2026-03-01"),
    ("AZURE_OPENAI_DEPLOYMENT", "adaivy-lead"),
    ("AZURE_OPENAI_ENDPOINT", "https://adaivy.example.azure.com"),
)


def profile(profile_id: str = DEFAULT_LIVE_PROFILE_ID, **overrides):
    values = dict(
        profile_id=profile_id,
        provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        embedding_model_identifier="text-embedding-3-large",
        endpoint_settings=SETTINGS,
        credential_source="env-file.adaivy",
    )
    values.update(overrides)
    return CredentialProfile(**values).finalized()


class CredentialProfileTests(unittest.TestCase):
    def test_profile_hash_round_trips_and_detects_tampering(self):
        built = profile()
        built.verify_hashes()
        tampered = profile(model_identifier="gpt-other")
        self.assertNotEqual(built.content_hash, tampered.content_hash)
        forged = CredentialProfile(
            profile_id=built.profile_id, provider=built.provider,
            model_identifier="gpt-other",
            embedding_model_identifier=built.embedding_model_identifier,
            endpoint_settings=built.endpoint_settings,
            credential_source=built.credential_source,
            content_hash=built.content_hash,
        )
        with self.assertRaises(CredentialProfileError):
            forged.verify_hashes()

    def test_route_hash_is_deterministic_and_route_sensitive(self):
        self.assertEqual(profile().route_hash, profile().route_hash)
        moved = profile(endpoint_settings=(
            SETTINGS[0], SETTINGS[1],
            ("AZURE_OPENAI_ENDPOINT", "https://other.example.azure.com"),
        ))
        self.assertNotEqual(profile().route_hash, moved.route_hash)

    def test_secret_variable_name_in_settings_is_rejected(self):
        with self.assertRaises(CredentialProfileError):
            profile(endpoint_settings=SETTINGS + (
                ("AZURE_OPENAI_API_KEY", SECRET),
            ))

    def test_undeclared_missing_unsorted_and_duplicate_settings_are_rejected(self):
        with self.assertRaises(CredentialProfileError):
            profile(endpoint_settings=SETTINGS + (("SOME_OTHER_SETTING", "x"),))
        with self.assertRaises(CredentialProfileError):
            profile(endpoint_settings=SETTINGS[:2])
        with self.assertRaises(CredentialProfileError):
            profile(endpoint_settings=tuple(reversed(SETTINGS)))
        with self.assertRaises(CredentialProfileError):
            profile(endpoint_settings=SETTINGS + (SETTINGS[0],))

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(CredentialProfileError):
            profile(provider="host_codex_session", endpoint_settings=())

    def test_profile_serialization_names_no_secret_material(self):
        built = profile()
        assert_no_secret_values(built, (SECRET,))
        self.assertEqual(
            built.credential_variable_names, ("AZURE_OPENAI_API_KEY",),
        )


class ResolutionTests(unittest.TestCase):
    def test_resolution_uses_only_the_injected_profile_scoped_mapping(self):
        resolved = resolve_credential_profile(
            profile(), credential_environment={"AZURE_OPENAI_API_KEY": SECRET},
        )
        self.assertEqual(resolved.value("AZURE_OPENAI_API_KEY"), SECRET)
        self.assertEqual(resolved.secret_values(), (SECRET,))

    def test_ambient_process_environment_is_refused_by_identity(self):
        with mock.patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": SECRET}):
            with self.assertRaises(CredentialProfileError) as caught:
                resolve_credential_profile(
                    profile(), credential_environment=os.environ,
                )
        self.assertIn("ambient", str(caught.exception))

    def test_ambient_credentials_never_fill_a_missing_profile_credential(self):
        # The ambient variable exists, and the profile still fails closed:
        # there is no silent fallback from the empty scoped mapping to the
        # host process environment.
        with mock.patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": SECRET}):
            with self.assertRaises(CredentialProfileError) as caught:
                resolve_credential_profile(profile(), credential_environment={})
        message = str(caught.exception)
        self.assertIn("AZURE_OPENAI_API_KEY", message)
        self.assertIn("ambient process credentials are not consulted", message)
        self.assertIn("no fallback provider", message)

    def test_cross_provider_credential_injection_is_rejected(self):
        with self.assertRaises(CredentialProfileError):
            resolve_credential_profile(profile(), credential_environment={
                "AZURE_OPENAI_API_KEY": SECRET,
                "OPENAI_API_KEY": "sk-host-agent-credential",
            })

    def test_blank_credential_is_missing_not_present(self):
        with self.assertRaises(CredentialProfileError):
            resolve_credential_profile(
                profile(), credential_environment={"AZURE_OPENAI_API_KEY": "  "},
            )

    def test_resolved_credentials_redact_and_refuse_serialization(self):
        resolved = resolve_credential_profile(
            profile(), credential_environment={"AZURE_OPENAI_API_KEY": SECRET},
        )
        self.assertNotIn(SECRET, repr(resolved))
        with self.assertRaises(CredentialProfileError):
            pickle.dumps(resolved)


class SelectionTests(unittest.TestCase):
    def test_default_adaivy_profile_selection_is_recorded_as_default(self):
        built = profile()
        registry = {built.profile_id: built}
        selected, record = select_credential_profile(
            registry, DEFAULT_LIVE_PROFILE_ID,
            campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
        )
        self.assertIs(selected, built)
        self.assertTrue(record.is_default_profile)
        self.assertIsNone(record.alternate_selection_reason)
        self.assertEqual(record.profile_content_hash, built.content_hash)
        self.assertEqual(record.route_hash, built.route_hash)
        record.verify_hashes()
        assert_no_secret_values(record, (SECRET,))

    def test_alternate_profile_is_allowed_but_recorded_as_such(self):
        alternate = profile("adaivy-eval")
        registry = {alternate.profile_id: alternate}
        _, record = select_credential_profile(
            registry, "adaivy-eval", campaign_id="campaign.slice2",
            selected_at="2026-08-22T00:00:00Z",
            alternate_selection_reason="operator selected the evaluation route",
        )
        self.assertFalse(record.is_default_profile)
        self.assertEqual(
            record.alternate_selection_reason,
            "operator selected the evaluation route",
        )

    def test_alternate_profile_without_a_reason_is_rejected(self):
        alternate = profile("adaivy-eval")
        with self.assertRaises(CredentialProfileError):
            select_credential_profile(
                {alternate.profile_id: alternate}, "adaivy-eval",
                campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
            )

    def test_unknown_profile_is_terminal_not_a_fallback(self):
        built = profile()
        with self.assertRaises(CredentialProfileError) as caught:
            select_credential_profile(
                {built.profile_id: built}, "host-claude",
                campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
            )
        self.assertIn("never substituted", str(caught.exception))

    def test_registry_key_mismatch_and_tampered_profile_are_rejected(self):
        built = profile()
        with self.assertRaises(CredentialProfileError):
            select_credential_profile(
                {"other": built}, "other",
                campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
            )
        forged = CredentialProfile(
            profile_id=built.profile_id, provider=built.provider,
            model_identifier="gpt-swapped",
            embedding_model_identifier=built.embedding_model_identifier,
            endpoint_settings=built.endpoint_settings,
            credential_source=built.credential_source,
            content_hash=built.content_hash,
        )
        with self.assertRaises(CredentialProfileError):
            select_credential_profile(
                {forged.profile_id: forged}, forged.profile_id,
                campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
            )

    def test_selection_record_default_flag_cannot_lie(self):
        built = profile()
        with self.assertRaises(CredentialProfileError):
            ProfileSelectionRecord(
                campaign_id="campaign.slice2", profile_id=built.profile_id,
                credential_source=built.credential_source,
                provider=built.provider,
                model_identifier=built.model_identifier,
                embedding_model_identifier=built.embedding_model_identifier,
                route_hash=built.route_hash,
                profile_content_hash=built.content_hash,
                is_default_profile=False,
                alternate_selection_reason="pretending adaivy is an alternate",
                selected_at="2026-08-22T00:00:00Z",
            )

    def test_selected_at_is_operational_not_semantic(self):
        built = profile()
        registry = {built.profile_id: built}
        _, first = select_credential_profile(
            registry, built.profile_id,
            campaign_id="campaign.slice2", selected_at="2026-08-22T00:00:00Z",
        )
        _, second = select_credential_profile(
            registry, built.profile_id,
            campaign_id="campaign.slice2", selected_at="2026-08-22T01:00:00Z",
        )
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(first.operational_hash, second.operational_hash)


class RoutePolicyTests(unittest.TestCase):
    def test_provider_failure_without_named_fallback_is_terminal(self):
        policy = CampaignRoutePolicy(
            primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
            fallback_profile_id=None, fallback_authorized_reason=None,
        ).finalized()
        with self.assertRaises(CredentialProfileError) as caught:
            policy.route_after_provider_failure(DEFAULT_LIVE_PROFILE_ID)
        self.assertIn("terminal", str(caught.exception))

    def test_named_fallback_requires_a_recorded_authorization(self):
        with self.assertRaises(CredentialProfileError):
            CampaignRoutePolicy(
                primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
                fallback_profile_id="adaivy-fallback",
                fallback_authorized_reason=None,
            )
        with self.assertRaises(CredentialProfileError):
            CampaignRoutePolicy(
                primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
                fallback_profile_id=None,
                fallback_authorized_reason="reason without a route",
            )
        with self.assertRaises(CredentialProfileError):
            CampaignRoutePolicy(
                primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
                fallback_profile_id=DEFAULT_LIVE_PROFILE_ID,
                fallback_authorized_reason="a route is not its own fallback",
            )

    def test_authorized_fallback_is_named_and_single_hop(self):
        policy = CampaignRoutePolicy(
            primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
            fallback_profile_id="adaivy-fallback",
            fallback_authorized_reason="operator authorized one named fallback",
        ).finalized()
        self.assertEqual(
            policy.route_after_provider_failure(DEFAULT_LIVE_PROFILE_ID),
            "adaivy-fallback",
        )
        with self.assertRaises(CredentialProfileError):
            policy.route_after_provider_failure("adaivy-fallback")


class SecretScanTests(unittest.TestCase):
    def test_a_record_containing_a_secret_is_refused(self):
        with self.assertRaises(CredentialProfileError):
            assert_no_secret_values({"note": f"key {SECRET} leaked"}, (SECRET,))

    def test_empty_secrets_scan_nothing(self):
        assert_no_secret_values({"note": "clean"}, ("",))


if __name__ == "__main__":
    unittest.main()
