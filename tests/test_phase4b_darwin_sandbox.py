"""Actual named-platform checks for the fail-closed Phase 4B sandbox probe."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import tempfile
import unittest

from math_research.phase4b.darwin_sandbox import DarwinSandboxProbeRunner


class Phase4BDarwinSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = DarwinSandboxProbeRunner()

    def require_darwin(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")

    def test_non_darwin_path_is_explicitly_machine_readable(self) -> None:
        result = self.runner.run("baseline")
        self.assertIn(result.status, {"allowed", "unavailable"})
        self.assertTrue(result.profile_hash.startswith("sha256:"))

    def test_actual_boundary_allows_fixed_probe_with_allowlisted_environment(self) -> None:
        self.require_darwin()
        os.environ["P4B_FORBIDDEN_PARENT_SECRET"] = "must-not-cross-boundary"
        try:
            result = self.runner.run("baseline")
        finally:
            os.environ.pop("P4B_FORBIDDEN_PARENT_SECRET", None)
        self.assertEqual("allowed", result.status, result.value())
        self.assertEqual(
            {"LANG", "LC_ALL", "PATH", "__CF_USER_TEXT_ENCODING"},
            set(result.detail["environment"]),
        )
        self.assertNotIn("P4B_FORBIDDEN_PARENT_SECRET", result.detail["environment"])

    def test_actual_boundary_denies_network_write_process_and_unapproved_read(self) -> None:
        self.require_darwin()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            forbidden_write = root / "escape.bin"
            forbidden_read = root / "secret.bin"
            forbidden_read.write_bytes(b"secret")
            results = {
                "network": self.runner.run("network"),
                "write": self.runner.run("write", target=forbidden_write),
                "process": self.runner.run("process"),
                "read": self.runner.run("read", target=forbidden_read),
            }
        self.assertEqual({"denied"}, {item.status for item in results.values()}, results)
        self.assertFalse(forbidden_write.exists())
        self.assertTrue(all(item.exit_status == 0 for item in results.values()))
        self.assertTrue(all(item.detail.get("allowed") is False for item in results.values()))

    def test_unknown_probe_action_fails_before_subprocess(self) -> None:
        with self.assertRaisesRegex(ValueError, "not closed"):
            self.runner.run("arbitrary")


if __name__ == "__main__":
    unittest.main()
