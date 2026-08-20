"""Gate-only tests for the nonproduction Phase 4A contract spike."""

from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPIKE_PATH = ROOT / "spikes/phase4_gate/gate_spike.py"
VALIDATOR_AVAILABLE = importlib.util.find_spec("jsonschema") is not None
SPIKE = None
if VALIDATOR_AVAILABLE:
    SPEC = importlib.util.spec_from_file_location("phase4_gate_spike", SPIKE_PATH)
    assert SPEC is not None and SPEC.loader is not None
    SPIKE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(SPIKE)


@unittest.skipUnless(
    VALIDATOR_AVAILABLE,
    "requires owner-approved isolated Phase 4 gate validator environment",
)
class Phase4GateFixtureTests(unittest.TestCase):
    def load_inputs(self):
        assert SPIKE is not None
        manifest = SPIKE.load_json(ROOT / "fixtures/phase4-gate/manifest.json")
        corpus = SPIKE.load_json(ROOT / "fixtures/phase4-gate/corpus.json")
        validator = SPIKE.load_validator(ROOT / "schemas/phase4-gate-fixture-v1.schema.json")
        return manifest, corpus, validator

    def test_draft_2020_12_schema_and_all_valid_fixtures(self) -> None:
        assert SPIKE is not None
        _, corpus, validator = self.load_inputs()
        self.assertEqual(validator.META_SCHEMA["$id"], "https://json-schema.org/draft/2020-12/schema")
        for fixture in corpus["fixtures"]:
            self.assertEqual(SPIKE.schema_errors(validator, fixture), [])
            SPIKE.validate_fixture(fixture)

    def test_manifest_metrics_and_audit_complete_export(self) -> None:
        assert SPIKE is not None
        manifest, corpus, validator = self.load_inputs()
        export, metrics = SPIKE.evaluate_corpus(corpus, manifest, validator)
        self.assertEqual(metrics["fixture_count"], 16)
        self.assertEqual(len(export["records"]), 68)
        required = {
            "record_id", "record_type", "schema_version", "subject_id",
            "actor_id", "actor_type", "authority", "reason_code",
            "reason_detail", "evidence_ids", "recorded_at", "sequence",
            "supersedes", "superseded_by", "lifecycle_target", "use_scope",
            "original_semantic_content_hash", "previous_event_id", "payload",
        }
        self.assertTrue(all(set(record) == required for record in export["records"]))
        raw, _ = SPIKE.stream_json_bytes(export, newline=True)
        accepted = SPIKE.verify_export_bytes(raw, validator)
        self.assertEqual(accepted, export)
        self.assertIsNot(accepted, export)
        export["records"][0]["actor_id"] = "actor.caller-mutation"
        self.assertNotEqual(accepted, export)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate-export.json"
            SPIKE.write_verified_export_atomic(path, accepted, validator)
            self.assertEqual(
                SPIKE.load_verified_export_file(path, validator), accepted
            )

    def test_all_adversarial_cases_and_nonhuman_matrix(self) -> None:
        assert SPIKE is not None
        _, corpus, validator = self.load_inputs()
        results = SPIKE.run_cases(ROOT, corpus, validator)
        self.assertEqual(results["case_count"], 31)
        self.assertEqual(results["actor_outcome_matrix_cells"], 20)
        self.assertEqual(results["nonhuman_actor_outcome_matrix_cells"], 15)
        self.assertEqual(results["human_actor_outcome_matrix_cells"], 5)
        self.assertEqual(results["replay_mutation_rejections"], 7)
        self.assertEqual(
            {results["results"][f"phase4.case.rights-{name}"] for name in (
                "permitted", "explicitly-prohibited", "missing", "expired",
                "revoked", "incompatible",
            )},
            {"permitted", "explicitly_prohibited", "missing", "expired", "revoked", "incompatible"},
        )

    def test_resource_boundaries_are_executed(self) -> None:
        assert SPIKE is not None
        checks = SPIKE.resource_boundary_tests()
        self.assertTrue(all(checks.values()))
        self.assertEqual(SPIKE.MAX_SOURCE_BYTES, 2_097_152)
        self.assertEqual(SPIKE.MAX_RECORDS, 256)
        self.assertEqual(SPIKE.MAX_OUTPUT_BYTES, 67_108_864)
        self.assertEqual(SPIKE.MAX_WALL_SECONDS, 600.0)

    def test_real_streaming_encoder_and_sink_do_not_prebuild_output(self) -> None:
        assert SPIKE is not None
        stream = io.BytesIO()
        sink = SPIKE.BoundedOutputSink(stream, limit=4096)
        value = {"items": ["é", "x", "y"], "schema_version": "test.v1"}
        with patch.object(
            SPIKE,
            "canonical_bytes",
            side_effect=AssertionError("complete canonical bytes constructed"),
        ):
            result = SPIKE.stream_json_to_sink(value, sink)
        expected = (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(stream.getvalue(), expected)
        self.assertEqual(result.bytes_written, len(expected))
        self.assertEqual(result.sha256, hashlib.sha256(expected).hexdigest())
        self.assertGreater(result.write_calls, 1)

    def test_cooperative_deadline_discards_partial_atomic_output(self) -> None:
        assert SPIKE is not None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "candidate.json"
            budget = SPIKE.DeadlineBudget(
                0.05, clock=SPIKE._AdvancingClock()
            )
            with self.assertRaises(SPIKE.GateResourceLimitError):
                SPIKE.write_bounded_json_atomic(
                    output,
                    {"items": list(range(128))},
                    deadline=budget,
                )
            self.assertFalse(output.exists())
            self.assertEqual(
                list(root.glob(f".{output.name}.*.tmp")), []
            )

    def test_parent_timeout_hard_terminates_and_reaps_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "child.pid"
            child = (
                "import os, pathlib, sys, time; "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run(
                    [sys.executable, "-c", child, str(pid_path)],
                    check=True,
                    timeout=0.5,
                    env={"PYTHONDONTWRITEBYTECODE": "1"},
                )
            pid = int(pid_path.read_text(encoding="utf-8"))
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_external_schema_reference_is_rejected_without_retrieval(self) -> None:
        assert SPIKE is not None
        schema = SPIKE.load_json(ROOT / "schemas/phase4-gate-fixture-v1.schema.json")
        schema["properties"]["fixture_id"] = {"$ref": "https://example.invalid/remote.json"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(SPIKE.GateValidationError):
                SPIKE.load_validator(path)

    def test_two_runs_and_fresh_process_restart_under_real_parent_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = []
            for state_dir, output in (
                (root / "state-a", root / "run-1.json"),
                (root / "state-b", root / "run-2.json"),
                (root / "state-a", root / "restart.json"),
            ):
                subprocess.run(
                    [sys.executable, str(SPIKE_PATH), "--state-dir", str(state_dir), "--output", str(output)],
                    cwd=ROOT, check=True, capture_output=True, text=True,
                    timeout=600, env={"PYTHONDONTWRITEBYTECODE": "1"},
                )
                outputs.append(json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(len({item["candidate_export_hash"] for item in outputs}), 1)
            self.assertEqual([item["restart_loaded"] for item in outputs], [False, False, True])
            self.assertTrue(all(item["observations"]["elapsed_seconds"] < 600 for item in outputs))
            self.assertTrue(all(item["observations"]["external_cost_usd"] == 0 for item in outputs))
            self.assertTrue(
                all(item["controls"]["strict_raw_export_boundary"] for item in outputs)
            )
            self.assertTrue(
                all(item["controls"]["streaming_output_enforced"] for item in outputs)
            )
            self.assertTrue(
                all(item["controls"]["cooperative_deadline_enforced"] for item in outputs)
            )


if __name__ == "__main__":
    unittest.main()
