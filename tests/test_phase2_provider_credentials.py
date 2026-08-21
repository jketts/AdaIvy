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
    EnvFileError,
    load_provider_credentials,
)


SECRET = "sk-provider-file-example123"


def _env_file(directory: str, body: str, *, mode: int = 0o600) -> Path:
    path = Path(directory) / ".env"
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
                "DEEPSEEK_API_KEY=deepseek-example456\n"
                "AWS_REGION=eu-west-2\n",
            )
            environment: dict[str, str] = {}
            result = load_provider_credentials(path, environment=environment)
            self.assertEqual(
                ("ANTHROPIC_API_KEY", "AWS_REGION", "DEEPSEEK_API_KEY"),
                result.from_env_file,
            )
            self.assertEqual(SECRET, environment["ANTHROPIC_API_KEY"])
            self.assertEqual("eu-west-2", environment["AWS_REGION"])
            self.assertNotIn(SECRET, repr(result))
            self.assertNotIn("deepseek-example456", repr(result))

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

    def test_versioned_example_matches_the_loader_allowlist_and_is_blank(self) -> None:
        lines = Path(".env.example").read_text(encoding="utf-8").splitlines()
        assignments = [
            line for line in lines if "=" in line and not line.strip().startswith("#")
        ]
        self.assertTrue(assignments)
        for line in assignments:
            key, value = line.split("=", 1)
            with self.subTest(key=key):
                self.assertIn(key, PROVIDER_ENV_KEYS)
                self.assertEqual("", value, "example values must stay blank")
        documented = {line.split("=", 1)[0] for line in assignments}
        self.assertEqual(
            set(), PROVIDER_ENV_KEYS - documented,
            "every supported key must appear in .env.example",
        )

    def test_non_secret_keys_are_a_subset_of_supported_keys(self) -> None:
        self.assertEqual(set(), NON_SECRET_PROVIDER_KEYS - PROVIDER_ENV_KEYS)


if __name__ == "__main__":
    unittest.main()
