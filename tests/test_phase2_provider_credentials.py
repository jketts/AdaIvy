"""Acceptance for the multi-provider `.env` credential loader.

ADR-0009 accepted a strict single-key loader. Multi-provider support keeps every
one of its controls -- 0600 permissions, no interpolation, unknown-key and
duplicate rejection, never overriding the process environment, never disclosing
a value -- and adds only the ability to resolve several keys, treating a blank
entry as "not configured" rather than an error.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.phase2.env_file import (
    NON_SECRET_PROVIDER_KEYS,
    PROVIDER_ENV_KEYS,
    PROVIDER_SECRET_KEYS,
    PROVIDER_SETTING_KEYS,
    load_provider_environment,
    load_provider_settings,
    EnvFileError,
    load_provider_credentials,
)


SECRET = "sk-provider-file-example123"


def _env_file(directory: str, body: str, *, mode: int = 0o600) -> Path:
    path = Path(directory) / ".env"
    path.write_text(body, encoding="utf-8")
    path.chmod(mode)
    return path


def _settings_file(directory: str, body: str, *, mode: int = 0o600) -> Path:
    path = Path(directory) / ".env.settings"
    path.write_text(body, encoding="utf-8")
    path.chmod(mode)
    return path


class ProviderCredentialLoaderTests(unittest.TestCase):
    def test_several_providers_resolve_without_disclosing_any_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(
                temporary,
                "# local only\n"
                f"ANTHROPIC_API_KEY='{SECRET}'\n"
                "DEEPSEEK_API_KEY=deepseek-example456\n",
            )
            environment: dict[str, str] = {}
            result = load_provider_credentials(path, environment=environment)
            self.assertEqual(
                ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"), result.from_env_file,
            )
            self.assertEqual(SECRET, environment["ANTHROPIC_API_KEY"])
            self.assertNotIn(SECRET, repr(result))
            self.assertNotIn("deepseek-example456", repr(result))

    def test_a_setting_in_the_secret_file_is_refused_by_name(self) -> None:
        """The two files are separated by the loader, not by convention.

        `AWS_REGION` was accepted in `.env` until the split. Accepting it still
        would leave the file people guard holding two kinds of thing, and would
        let a setting quietly live somewhere no template documents.
        """
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(temporary, "AWS_REGION=eu-west-2\n")
            with self.assertRaises(EnvFileError) as caught:
                load_provider_credentials(path, environment={})
        message = str(caught.exception)
        self.assertIn("AWS_REGION", message)
        self.assertIn(".env.settings", message)

    def test_a_credential_in_the_settings_file_is_refused_by_name(self) -> None:
        """The refusal is symmetric, which is the direction that matters most.

        A credential in `.env.settings` would be a secret in a file nobody
        treats as secret. It is rejected rather than merged.
        """
        with tempfile.TemporaryDirectory() as temporary:
            path = _settings_file(temporary, f"ANTHROPIC_API_KEY={SECRET}\n")
            with self.assertRaises(EnvFileError) as caught:
                load_provider_settings(path, environment={})
        message = str(caught.exception)
        self.assertIn("ANTHROPIC_API_KEY", message)
        self.assertIn(".env", message)
        self.assertNotIn(SECRET, message)

    def test_settings_resolve_and_never_override_the_process_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _settings_file(
                temporary,
                "# local only\n"
                "AWS_REGION=eu-west-2\n"
                "AZURE_OPENAI_DEPLOYMENT=from-file\n"
                "AZURE_OPENAI_ENDPOINT=\n",
            )
            environment = {"AZURE_OPENAI_DEPLOYMENT": "from-process"}
            result = load_provider_settings(path, environment=environment)
            self.assertEqual(("AWS_REGION",), result.from_settings_file)
            self.assertEqual(
                ("AZURE_OPENAI_ENDPOINT",), result.blank_in_settings_file,
            )
            self.assertEqual("eu-west-2", environment["AWS_REGION"])
            self.assertEqual("from-process", environment["AZURE_OPENAI_DEPLOYMENT"])

    def test_a_world_readable_settings_file_is_refused(self) -> None:
        """Integrity, not confidentiality: the endpoint is where a key is sent.

        Nothing in `.env.settings` is a secret, so the 0600 requirement is not
        about disclosure. `AZURE_OPENAI_ENDPOINT` names the host that receives
        the credential, so anyone who can rewrite this file can redirect it.
        """
        with tempfile.TemporaryDirectory() as temporary:
            path = _settings_file(temporary, "AWS_REGION=eu-west-2\n", mode=0o644)
            with self.assertRaises(EnvFileError) as caught:
                load_provider_settings(path, environment={})
        self.assertIn("0600", str(caught.exception))

    def test_loading_both_files_fills_one_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env = _env_file(temporary, f"AZURE_OPENAI_API_KEY={SECRET}\n")
            settings = _settings_file(
                temporary, "AZURE_OPENAI_DEPLOYMENT=a-deployment\n",
            )
            environment: dict[str, str] = {}
            credentials, resolved = load_provider_environment(
                env_path=env, settings_path=settings, environment=environment,
            )
            self.assertEqual(("AZURE_OPENAI_API_KEY",), credentials.from_env_file)
            self.assertEqual(
                ("AZURE_OPENAI_DEPLOYMENT",), resolved.from_settings_file,
            )
            self.assertEqual(
                {"AZURE_OPENAI_API_KEY": SECRET,
                 "AZURE_OPENAI_DEPLOYMENT": "a-deployment"},
                environment,
            )

    def test_process_environment_is_never_overridden_per_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(
                temporary,
                f"ANTHROPIC_API_KEY={SECRET}\nDEEPSEEK_API_KEY=from-file\n",
            )
            environment = {"ANTHROPIC_API_KEY": "already-set"}
            result = load_provider_credentials(path, environment=environment)
            self.assertEqual("already-set", environment["ANTHROPIC_API_KEY"])
            self.assertEqual("from-file", environment["DEEPSEEK_API_KEY"])
            self.assertIn("ANTHROPIC_API_KEY", result.from_process_environment)
            self.assertEqual(("DEEPSEEK_API_KEY",), result.from_env_file)

    def test_blank_entries_are_reported_and_never_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(
                temporary, "ANTHROPIC_API_KEY=\nMINIMAX_API_KEY=\nDEEPSEEK_API_KEY=real\n",
            )
            environment: dict[str, str] = {}
            result = load_provider_credentials(path, environment=environment)
            self.assertEqual(
                ("ANTHROPIC_API_KEY", "MINIMAX_API_KEY"), result.blank_in_env_file,
            )
            self.assertEqual(("DEEPSEEK_API_KEY",), result.from_env_file)
            self.assertNotIn("ANTHROPIC_API_KEY", environment)

    def test_a_blank_entry_cannot_mask_a_real_process_environment_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(temporary, "ANTHROPIC_API_KEY=\n")
            environment = {"ANTHROPIC_API_KEY": "already-set"}
            load_provider_credentials(path, environment=environment)
            self.assertEqual("already-set", environment["ANTHROPIC_API_KEY"])

    def test_insecure_or_general_dotenv_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = _env_file(temporary, "ANTHROPIC_API_KEY=secret\n", mode=0o644)
            with self.assertRaisesRegex(EnvFileError, "0600"):
                load_provider_credentials(path, environment={})
            path.chmod(0o600)
            for body, expected in (
                ("ANTHROPIC_API_KEY=a\nMODEL=forbidden\n", "unsupported"),
                ("ANTHROPIC_API_KEY=a\nANTHROPIC_API_KEY=b\n", "duplicate"),
                ("ANTHROPIC_API_KEY='unclosed\n", "unmatched"),
                ("ANTHROPIC_API_KEY\n", "invalid"),
            ):
                with self.subTest(expected=expected):
                    path.write_text(body, encoding="utf-8")
                    with self.assertRaisesRegex(EnvFileError, expected):
                        load_provider_credentials(path, environment={})

    def test_no_interpolation_or_command_substitution_is_performed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            literal = "$OTHER-${OTHER}-`id`-$(id)"
            path = _env_file(temporary, f"DEEPSEEK_API_KEY={literal}\n")
            environment: dict[str, str] = {"OTHER": "expanded"}
            load_provider_credentials(path, environment=environment)
            self.assertEqual(literal, environment["DEEPSEEK_API_KEY"])

    def test_missing_file_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = load_provider_credentials(
                Path(temporary) / "absent", environment={},
            )
            self.assertFalse(result.file_present)
            self.assertEqual((), result.from_env_file)

    def test_each_versioned_example_matches_its_own_allowlist_and_is_blank(self) -> None:
        """Each example documents exactly its own file's keys, and no others.

        Checking the union against one file would let a secret be documented in
        the settings example, or a setting in the secret example, while the
        totals still agreed.
        """
        cases = (
            (".env.example", PROVIDER_SECRET_KEYS, PROVIDER_SETTING_KEYS),
            (".env.settings.example", PROVIDER_SETTING_KEYS, PROVIDER_SECRET_KEYS),
        )
        for name, allowed, other in cases:
            with self.subTest(example=name):
                lines = Path(name).read_text(encoding="utf-8").splitlines()
                assignments = [
                    line for line in lines
                    if "=" in line and not line.strip().startswith("#")
                ]
                self.assertTrue(assignments)
                for line in assignments:
                    key, value = line.split("=", 1)
                    with self.subTest(key=key):
                        self.assertIn(key, allowed)
                        self.assertNotIn(key, other)
                        self.assertEqual("", value, "example values must stay blank")
                documented = {line.split("=", 1)[0] for line in assignments}
                self.assertEqual(
                    set(), allowed - documented,
                    f"every supported key must appear in {name}",
                )

    def test_non_secret_keys_are_a_subset_of_supported_keys(self) -> None:
        self.assertEqual(set(), NON_SECRET_PROVIDER_KEYS - PROVIDER_ENV_KEYS)

    def test_the_two_key_sets_partition_the_supported_keys(self) -> None:
        """No key is in both files, and none is in neither.

        An overlap would make the loaders disagree about where a key belongs; a
        gap would leave a declared requirement that no template documents and no
        loader resolves.
        """
        self.assertEqual(set(), PROVIDER_SECRET_KEYS & PROVIDER_SETTING_KEYS)
        self.assertEqual(
            PROVIDER_ENV_KEYS, PROVIDER_SECRET_KEYS | PROVIDER_SETTING_KEYS,
        )

    def test_every_declared_provider_requirement_has_a_home(self) -> None:
        """A spec cannot require a variable that neither file would resolve."""

        from math_research.phase2.provider_registry import PROVIDER_SPECS

        for name, spec in sorted(PROVIDER_SPECS.items()):
            with self.subTest(provider=name):
                for variable in spec.required_credentials + spec.optional_credentials:
                    self.assertIn(variable, PROVIDER_SECRET_KEYS)
                for variable in spec.required_settings + spec.optional_settings:
                    self.assertIn(variable, PROVIDER_SETTING_KEYS)


if __name__ == "__main__":
    unittest.main()
