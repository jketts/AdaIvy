"""Acceptance suite for the local report index.

The index exists so a reader can tell what a report directory holds and whether
the bytes are the ones that were produced. Its two load-bearing properties are
therefore that it is a pure function of its inputs, and that it hashes rather
than summarises: an index that restated a finding would create a second, unbacked
copy of that finding.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from math_research.report_index import (  # noqa: E402
    ReportIndexError,
    build_index,
    render_index,
    write_index,
)

INSTANT = "2026-08-21T00:00:00Z"


def _populate(root: Path) -> None:
    (root / "phase6").mkdir(parents=True)
    (root / "publication").mkdir(parents=True)
    (root / "phase6/confirmatory-report.md").write_text("# report\n", encoding="utf-8")
    (root / "phase6/release.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    (root / "publication/paper.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    (root / "notes.txt").write_text("loose file\n", encoding="utf-8")


class ReportIndexTests(unittest.TestCase):
    def test_the_index_is_a_pure_function_of_directory_and_instant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            first = build_index(root, INSTANT)
            second = build_index(root, INSTANT)
            self.assertEqual(first, second)
            self.assertEqual(render_index(first), render_index(second))

    def test_a_changed_byte_changes_the_index_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            before = build_index(root, INSTANT)["index_hash"]
            (root / "phase6/release.json").write_text('{"status":"failed"}\n', encoding="utf-8")
            self.assertNotEqual(build_index(root, INSTANT)["index_hash"], before)

    def test_a_different_instant_changes_the_index_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            self.assertNotEqual(
                build_index(root, INSTANT)["index_hash"],
                build_index(root, "2026-08-22T00:00:00Z")["index_hash"],
            )

    def test_every_recorded_hash_matches_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            index = build_index(root, INSTANT)
            self.assertEqual(index["file_count"], 4)
            for entry in index["files"]:
                path = root / str(entry["path"])
                data = path.read_bytes()
                self.assertEqual(
                    "sha256:" + hashlib.sha256(data).hexdigest(), entry["sha256"], entry["path"]
                )
                self.assertEqual(len(data), entry["bytes"])

    def test_the_index_names_the_readable_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            index = build_index(root, INSTANT)
            highlighted = {item["path"] for item in index["highlights"]}
            self.assertEqual(
                highlighted,
                {"phase6/confirmatory-report.md", "phase6/release.json", "publication/paper.tex"},
            )
            self.assertNotIn("notes.txt", highlighted)

    def test_the_index_records_that_a_local_run_is_not_committed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            index = build_index(root, INSTANT)
            self.assertIs(index["committed"], False)
            self.assertIn("gitignored", index["note"])
            self.assertIn("Committed: `false`", render_index(index))

    def test_the_index_does_not_index_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            first = write_index(root, INSTANT)
            self.assertTrue((root / "index.json").exists())
            self.assertTrue((root / "INDEX.md").exists())
            second = write_index(root, INSTANT)
            self.assertEqual(first, second)
            paths = {str(entry["path"]) for entry in second["files"]}
            self.assertNotIn("index.json", paths)
            self.assertNotIn("INDEX.md", paths)

    def test_an_empty_or_missing_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            with self.assertRaises(ReportIndexError):
                build_index(empty, INSTANT)
            with self.assertRaises(ReportIndexError):
                build_index(Path(directory) / "absent", INSTANT)

    def test_a_malformed_instant_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            for bad in ("2026-08-21", "yesterday", "2026-08-21T00:00:00", ""):
                with self.subTest(instant=bad):
                    with self.assertRaises(ReportIndexError):
                        build_index(root, bad)

    def test_the_index_states_no_finding_of_its_own(self) -> None:
        """It hashes; it does not summarise. Nothing about evidence class here."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            _populate(root)
            rendered = render_index(build_index(root, INSTANT))
            for word in ("proved", "theorem", "verified", "novel", "significant"):
                self.assertNotIn(word, rendered.lower(), word)


class GitignoreBoundaryTests(unittest.TestCase):
    """reports/local/ is the boundary between a local run and recorded evidence."""

    def test_the_local_subtree_is_ignored_and_the_evidence_tree_is_not(self) -> None:
        rules = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("reports/local/", rules)
        self.assertIn("work/", rules)
        self.assertNotIn("reports/", rules)
        self.assertNotIn("reports/*", rules)

    def test_committed_evidence_is_still_tracked(self) -> None:
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", "reports"], cwd=str(REPO_ROOT), capture_output=True, text=True,
            check=True,
        ).stdout.splitlines()
        self.assertGreater(len(tracked), 100, "the recorded evidence tree lost its files")
        self.assertEqual(
            [path for path in tracked if path.startswith("reports/local/")], [],
            "a local run was committed into the evidence tree",
        )


if __name__ == "__main__":
    unittest.main()
