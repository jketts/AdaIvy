"""The thirteen ADR-0069 falsifiability probes, plus the gate on them.

`probes_flipped == probes_total` is the release gate: a probe that cannot be made
to fail proves nothing, so the suite asserts that every probe's mutated leg
produces its named code AND that its baseline leg does not.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from math_research.embedding.probes import PROBES, PROBE_REPORT_SCHEMA_VERSION, run_probes

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Exactly the probe identifiers ADR-0069 lists, as literals. A renamed or
#: dropped probe fails here rather than quietly reducing the suite.
ADR_0062_PROBE_IDS = (
    "pr.artifact-overwrite-refused",
    "pr.cross-partition-similarity-refused",
    "pr.dimension-mismatch-refused",
    "pr.embedding-without-rights-refused",
    "pr.embedding-wrong-processor-refused",
    "pr.missing-artifact-fails-closed",
    "pr.no-fallback-partition",
    "pr.no-float-in-retrieval-path",
    "pr.normalization-mismatch-refused",
    "pr.output-tokens-are-zero",
    "pr.rebuild-makes-no-provider-call",
    "pr.saturating-coordinate-halts",
    "pr.tie-broken-by-document-id",
)

RESULT = run_probes()


class ProbeSuiteTests(unittest.TestCase):
    def test_every_probe_flips(self) -> None:
        self.assertEqual(
            RESULT["probes_flipped"], RESULT["probes_total"],
            f"probes that did not flip: {RESULT['unflipped_probe_ids']}",
        )

    def test_the_suite_is_exactly_the_thirteen_adr_probes(self) -> None:
        self.assertEqual(RESULT["probes_total"], 13)
        self.assertEqual(
            tuple(item["probe_id"] for item in RESULT["probes"]), ADR_0062_PROBE_IDS,
        )

    def test_each_probe_baseline_is_silent_and_mutation_is_loud(self) -> None:
        for probe in RESULT["probes"]:
            with self.subTest(probe=probe["probe_id"]):
                self.assertEqual(
                    probe["mutated_observed"], probe["expected_code"],
                    probe["detail"],
                )
                self.assertNotEqual(
                    probe["baseline_observed"], probe["expected_code"],
                    "the baseline already produces the forbidden outcome, so the "
                    "probe proves nothing",
                )

    def test_expected_codes_are_distinct_per_probe_intent(self) -> None:
        codes = [probe["expected_code"] for probe in RESULT["probes"]]
        self.assertEqual(len(codes), len(RESULT["probes"]))
        self.assertEqual(
            sorted({code for code in codes if code.startswith("partition_mismatch")}),
            [
                "partition_mismatch:dimension",
                "partition_mismatch:model_identifier",
                "partition_mismatch:normalization",
            ],
        )

    def test_mutation_targets_are_declared_not_implied(self) -> None:
        targets = {probe["probe_id"]: probe["mutation_target"] for probe in RESULT["probes"]}
        self.assertEqual(
            sorted(key for key, value in targets.items() if value == "instrument"),
            [
                "pr.no-float-in-retrieval-path",
                "pr.rebuild-makes-no-provider-call",
                "pr.tie-broken-by-document-id",
            ],
        )
        self.assertEqual(set(targets.values()), {"input", "instrument"})

    def test_report_declares_a_schema_and_no_epistemic_effect(self) -> None:
        self.assertEqual(RESULT["schema_version"], PROBE_REPORT_SCHEMA_VERSION)
        self.assertFalse(RESULT["creates_epistemic_warrant"])
        self.assertEqual(RESULT["novelty_status"], "not_assessed")
        self.assertEqual(RESULT["significance_status"], "not_assessed")

    def test_probe_identifiers_are_unique(self) -> None:
        identifiers = [probe.probe_id for probe in PROBES]
        self.assertEqual(len(identifiers), len(set(identifiers)))


class ProbeDeterminismTests(unittest.TestCase):
    def test_the_report_is_identical_across_hash_seeds_and_processes(self) -> None:
        script = (
            "import json\n"
            "from math_research.embedding.probes import run_probes\n"
            "print(json.dumps(run_probes(), sort_keys=True))\n"
        )
        outputs = set()
        for seed in ("0", "1", "424242", "random"):
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
                env={
                    "PYTHONPATH": "src", "PYTHONHASHSEED": seed,
                    "PATH": "/usr/bin:/bin",
                },
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            outputs.add(completed.stdout.strip())
        self.assertEqual(len(outputs), 1, "the probe report is not byte-reproducible")
        replayed = json.loads(outputs.pop())
        self.assertEqual(replayed["probes_flipped"], replayed["probes_total"])


class ProbeCliTests(unittest.TestCase):
    def test_the_cli_exits_zero_only_when_every_probe_flips(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "math_research.cli", "embedding", "probes"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["probes_flipped"], payload["probes_total"])
        self.assertEqual(payload["probes_total"], 13)


if __name__ == "__main__":
    unittest.main()
