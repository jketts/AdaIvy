"""Executable evidence for feasible offline Phase 4B gate controls."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest

from math_research.phase4b.gate import (
    REPORT_SCHEMA, _deny_ambient_network, load_feasible_gate_report,
    run_feasible_gate, verify_feasible_gate_report, verify_fixture_manifest,
)
from math_research.phase4b.serialization import canonical_bytes, canonical_hash


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "fixtures/phase4b/acceptance/feasible-gate-policy.json"


class Phase4BFeasibleGateTests(unittest.TestCase):
    def test_gate_report_matches_exact_policy_and_never_promotes_blockers(self) -> None:
        policy = json.loads(POLICY.read_text("utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            report = run_feasible_gate(ROOT, Path(temporary))
        self.assertEqual(REPORT_SCHEMA, report["schema_version"])
        self.assertEqual(policy["activation_status"], report["activation_status"])
        required = policy["required_passes"]
        self.assertEqual(required["fixture_manifest_total"], report["manifest"]["counts"]["total"])
        self.assertEqual(
            required["acquisition_fixture_executions"],
            report["fixture_execution"]["executed"]["acquisition"],
        )
        self.assertEqual(
            required["parser_fixture_executions"],
            report["fixture_execution"]["executed"]["parsing"],
        )
        self.assertEqual(
            required["lifecycle_fixture_executions"],
            report["fixture_execution"]["executed"]["lifecycle_integration"],
        )
        lifecycle = report["fixture_execution"]["lifecycle_evidence"]
        self.assertEqual(6, len(lifecycle))
        self.assertEqual(6, len({item["case_id"] for item in lifecycle}))
        self.assertTrue(all(item["status"] == "passed" for item in lifecycle))
        self.assertTrue(all(item["expected_outcome"] == item["observed_outcome"] for item in lifecycle))
        self.assertTrue(all(item["production_paths"] for item in lifecycle))
        for item in lifecycle:
            supplied = item["evidence_hash"]
            unhashed = dict(item)
            unhashed.pop("evidence_hash")
            self.assertEqual(supplied, canonical_hash(unhashed))
        sandbox = report["os_sandbox_probe"]
        self.assertFalse(sandbox["production_parser_connected"])
        self.assertFalse(sandbox["portable_claim"])
        self.assertIn(
            sandbox["status"],
            {"passed_named_platform_probe", "unavailable", "failed_closed"},
        )
        bridge = report["exact_parser_sandbox_bridge"]
        self.assertIn(
            bridge["status"],
            {"passed_named_darwin_html_tex_pdf", "unavailable", "failed_closed"},
        )
        self.assertFalse(bridge["strict_transient_memory_enforcement"])
        self.assertFalse(bridge["portable_claim"])
        self.assertFalse(bridge["production_activated"])
        if bridge["status"] == "passed_named_darwin_html_tex_pdf":
            self.assertTrue(bridge["production_parser_connected"])
            self.assertTrue(bridge["pdf_connected"])
            self.assertEqual(["html", "pdf", "tex"], bridge["profiles_connected"])
            self.assertTrue(all(
                item["disposition"] == "candidate_proposal"
                for item in bridge["cases"]
            ))
        corpus = report["parser_corpus_authorization"]
        self.assertEqual(12, corpus["counts"]["total"])
        self.assertEqual(0, corpus["counts"]["false_admissions"])
        self.assertEqual("authorized", corpus["status"])
        self.assertEqual(12, corpus["counts"]["exact_disposition_matches"])
        self.assertEqual(required["parser_corpus_authorized"], corpus["status"] == "authorized")
        self.assertFalse(corpus["production_activated"])
        self.assertTrue(all(item["content_signature_match"] for item in corpus["cases"]))
        self.assertEqual(required["ambient_network_calls"], report["network_isolation"]["ambient_network_calls"])
        self.assertEqual(required["phase3a_writes_caused"], report["phase3a_preservation"]["writes_caused"])
        self.assertEqual(required["protected_evidence_mismatches"], report["protected_evidence"]["mismatches"])
        self.assertEqual(required["credential_marker_matches"], report["credential_marker_scan"]["exact_marker_matches"])
        for field in (
            "in_process_repeat_count", "independent_process_count", "restart_count",
            "replay_count", "reverse_order_rebuild_count", "semantic_hashes_identical",
        ):
            self.assertEqual(required[field], report["determinism"][field])
        blocked = {item["control"]: item for item in report["blocked_controls"]}
        self.assertEqual(set(policy["required_blocked_controls"]), set(blocked))
        self.assertTrue(all(item["status"] == "blocked" for item in blocked.values()))
        self.assertTrue(all(item["counted_as_pass"] is False for item in blocked.values()))

        supplied_hash = report["content_hash"]
        unhashed = dict(report)
        unhashed.pop("content_hash")
        self.assertEqual(supplied_hash, canonical_hash(unhashed))
        self.assertIs(report, verify_feasible_gate_report(report, ROOT))
        self.assertEqual(report, load_feasible_gate_report(canonical_bytes(report), ROOT))

    def test_strict_report_verifier_rejects_self_rehashed_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original = run_feasible_gate(ROOT, Path(temporary))

        def rehash(report: dict[str, object]) -> None:
            report["content_hash"] = canonical_hash({
                key: value for key, value in report.items() if key != "content_hash"
            })

        def corpus_rehash(report: dict[str, object]) -> None:
            corpus = report["parser_corpus_authorization"]
            assert isinstance(corpus, dict)
            corpus["content_hash"] = canonical_hash({
                key: value for key, value in corpus.items() if key != "content_hash"
            })

        mutations = {
            "status promotion": lambda report: report.__setitem__("activation_status", "activated"),
            "policy identity": lambda report: report.__setitem__("gate_policy_hash", "sha256:" + "0" * 64),
            "blocker removal": lambda report: report["blocked_controls"].pop(),
            "forged execution count": lambda report: report["fixture_execution"]["executed"].__setitem__("acquisition", 11),
            "forged case hash": lambda report: report["fixture_evidence"][0].__setitem__("fixture_sha256", "sha256:" + "0" * 64),
            "forged lifecycle hash": lambda report: report["fixture_execution"]["lifecycle_evidence"][0].__setitem__("evidence_hash", "sha256:" + "0" * 64),
            "sandbox activation": lambda report: report["exact_parser_sandbox_bridge"].__setitem__("production_activated", True),
            "sandbox malformed count": lambda report: report["exact_parser_sandbox_bridge"]["cases"][0].__setitem__("segment_count", -1),
            "corpus activation": lambda report: report["parser_corpus_authorization"].__setitem__("production_activated", True),
            "corpus fixture substitution": lambda report: report["parser_corpus_authorization"]["cases"][0].__setitem__("fixture_sha256", "sha256:" + "0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                forged = copy.deepcopy(original)
                mutate(forged)
                if label.startswith("corpus"):
                    corpus_rehash(forged)
                rehash(forged)
                with self.assertRaises(ValueError):
                    verify_feasible_gate_report(forged, ROOT)

    def test_report_import_rejects_noncanonical_and_duplicate_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_feasible_gate(ROOT, Path(temporary))
        with self.assertRaisesRegex(ValueError, "canonical"):
            load_feasible_gate_report(json.dumps(report, indent=2).encode("utf-8"), ROOT)
        duplicate = canonical_bytes(report)[:-1] + b',"schema_version":"forged"}'
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_feasible_gate_report(duplicate, ROOT)

    def test_all_manifest_bytes_and_exact_fixture_evidence_are_verified(self) -> None:
        summary, evidence = verify_fixture_manifest(ROOT)
        self.assertEqual("passed", summary["status"])
        self.assertEqual(30, len(evidence))
        self.assertEqual(30, len({item["case_id"] for item in evidence}))
        self.assertTrue(all(item["manifest_verified"] for item in evidence))

        with tempfile.TemporaryDirectory() as temporary:
            copied_root = Path(temporary)
            shutil.copytree(ROOT / "fixtures/phase4b", copied_root / "fixtures/phase4b")
            target = copied_root / "fixtures/phase4b/acceptance/acquisition/allowed-direct.json"
            target.write_bytes(target.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "fixture bytes differ"):
                verify_fixture_manifest(copied_root)

    def test_network_trap_rejects_real_socket_and_dns_boundaries(self) -> None:
        counters = {"socket_attempts": 0, "dns_attempts": 0}
        with _deny_ambient_network(counters):
            with self.assertRaisesRegex(AssertionError, "socket"):
                socket.socket()
            with self.assertRaisesRegex(AssertionError, "DNS"):
                socket.getaddrinfo("example.invalid", 443)
        self.assertEqual({"socket_attempts": 1, "dns_attempts": 1}, counters)

    def test_gate_report_is_deterministic_across_fresh_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = run_feasible_gate(ROOT, Path(first))
            right = run_feasible_gate(ROOT, Path(second))
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
