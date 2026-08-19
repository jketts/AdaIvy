from __future__ import annotations

import ast
import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from math_research.phase3b import HASH_PROFILE, MAX_STDIN_BYTES, RUNTIME_DIGEST
from math_research.phase3b.adapter import DockerLeanAdapter, classify_execution
from math_research.phase3b.interchange import export_workspace, import_trusted_replay
from math_research.phase3b.records import ExecutionLimits, FormalCheckOutcome, RawExecution, StreamCapture
from math_research.phase3b.serialization import (
    canonical_bytes, canonical_hash, finding_content_hash, operational_export_hash, public_value,
    semantic_export_hash, sha256_bytes,
)
from math_research.phase3b.service import FormalCheckingService
from math_research.phase3b.validation import RequestValidationError, parse_request, parse_request_bytes
from math_research.phase3b.workspace import FormalCheckWorkspace
from math_research.phase3b.wrapper import DOCKER_CREATE_OPTIONS, INVOCATION, generate_wrapper

FIXTURES = Path("fixtures/phase3b")
FIXED_TIME = "2026-08-19T00:00:00Z"


def request(name: str = "valid"):
    return parse_request_bytes((FIXTURES / f"{name}.json").read_bytes())


def capture(text: str) -> StreamCapture:
    data = text.encode()
    return StreamCapture(len(data), sha256_bytes(data), text, len(data), False)


def execution(stdout: str, *, exit_code: int = 0, reason: str = "completed") -> RawExecution:
    return RawExecution(exit_code, reason, 10, capture(stdout), capture(""), True, ())


def current_finding_value() -> dict[str, object]:
    adapter = DockerLeanAdapter()
    current = request()
    return public_value(adapter.verify_output(
        current, generate_wrapper(current),
        execution('{"severity":"information","data":"does not depend on any axioms"}\n'),
        created_at=FIXED_TIME,
    ))


def legacy_finding_value(finding: dict[str, object] | None = None) -> dict[str, object]:
    value = dict(finding or current_finding_value())
    value.pop("hash_profile", None)
    value["content_hash"] = ""
    value["content_hash"] = canonical_hash(value)
    return value


def legacy_export_value(findings: list[dict[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0.0",
        "record_type": "phase3b_formal_check_export",
        "findings": findings,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def current_export_value(findings: list[dict[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0.0",
        "record_type": "phase3b_formal_check_export",
        "hash_profile": HASH_PROFILE,
        "findings": findings,
    }
    value["content_hash"] = semantic_export_hash(value)
    value["operational_hash"] = operational_export_hash(value)
    return value


class RestrictedRequestTests(unittest.TestCase):
    def test_schema_accepts_only_restricted_fragments(self) -> None:
        value = request()
        self.assertEqual(value.declaration_name, "AdaIvyValid")
        self.assertEqual(value.imports, ())

    def test_placeholder_unknown_import_unsafe_eval_and_undeclared_axiom_are_rejected(self) -> None:
        base = json.loads((FIXTURES / "valid.json").read_text())
        cases = (("proof_fragment", "by sorry"), ("proof_fragment", "by exact _"), ("proof_fragment", "by native_decide"), ("proof_fragment", "by run_io pure ()"), ("proof_fragment", "by axiom Hidden : Prop"))
        for field, value in cases:
            candidate = dict(base); candidate[field] = value
            with self.subTest(value=value), self.assertRaises(RequestValidationError):
                parse_request(candidate)
        candidate = dict(base); candidate["imports"] = ["AdaIvy.Unknown"]
        with self.assertRaises(RequestValidationError):
            parse_request(candidate)

    def test_arbitrary_commands_comments_strings_and_extra_fields_are_rejected(self) -> None:
        base = json.loads((FIXTURES / "valid.json").read_text())
        for proof in ("by rfl\n#eval 1", "by rfl -- hidden", 'by exact "path"'):
            candidate = dict(base); candidate["proof_fragment"] = proof
            with self.assertRaises(RequestValidationError):
                parse_request(candidate)
        candidate = dict(base); candidate["source_path"] = "/tmp/input.lean"
        with self.assertRaises(RequestValidationError):
            parse_request(candidate)

    def test_malformed_non_utf8_and_oversized_input_are_policy_rejections(self) -> None:
        for data in ((FIXTURES / "malformed.json").read_bytes(), b"\xff", b"x" * (MAX_STDIN_BYTES + 1)):
            with self.subTest(length=len(data)), self.assertRaises(RequestValidationError):
                parse_request_bytes(data)

    def test_more_than_sixteen_declared_assumptions_are_rejected(self) -> None:
        value = json.loads((FIXTURES / "valid.json").read_text())
        value["assumptions"] = [{"name": f"AdaIvyAssumptionX{i:02d}", "type_expression": "Prop"} for i in range(17)]
        with self.assertRaises(RequestValidationError):
            parse_request(value)

    def test_records_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            request().declaration_name = "AdaIvyChanged"  # type: ignore[misc]


class WrapperTests(unittest.TestCase):
    def test_wrapper_is_byte_deterministic_and_fully_hashed(self) -> None:
        first, second = generate_wrapper(request()), generate_wrapper(request())
        self.assertEqual(first, second)
        self.assertEqual(first.manifest.wrapper_hash, sha256_bytes(first.source))
        self.assertEqual(first.manifest.runtime_hash, RUNTIME_DIGEST)
        self.assertNotIn(b"/Users/", first.source)
        self.assertLessEqual(len(first.source), MAX_STDIN_BYTES)

    def test_tampered_generated_wrapper_fails_before_runtime_inspection(self) -> None:
        adapter = DockerLeanAdapter()
        wrapper = generate_wrapper(request())
        tampered = replace(wrapper, source=wrapper.source + b" ")
        with patch.object(adapter, "_inspect_runtime", side_effect=AssertionError("runtime inspected")):
            result = adapter.execute(tampered)
        self.assertEqual(result.termination_reason, "sandbox_failure")

    def test_invocation_has_stdin_only_and_exact_v5_controls(self) -> None:
        self.assertEqual(INVOCATION["input_transport"], "stdin")
        self.assertEqual(INVOCATION["container_arguments"], [])
        self.assertEqual(INVOCATION["host_mounts"], [])
        self.assertEqual(INVOCATION["fixed_input_path"], "/tmp/adaivy-input.lean")
        self.assertEqual(INVOCATION["network"], "none")
        self.assertEqual(INVOCATION["tmpfs"], "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777")
        self.assertNotIn("--volume", DOCKER_CREATE_OPTIONS)
        self.assertNotIn("--mount", DOCKER_CREATE_OPTIONS)
        self.assertNotIn("--env", DOCKER_CREATE_OPTIONS)
        self.assertEqual(INVOCATION["docker_create_argv"][-1], INVOCATION["image"])

    def test_declared_assumptions_are_generated_only_by_trusted_wrapper(self) -> None:
        wrapper = generate_wrapper(request("axiom")).source.decode()
        self.assertIn("axiom AdaIvyAssumptionP : Prop", wrapper)
        self.assertIn("axiom AdaIvyAssumptionProof : AdaIvyAssumptionP", wrapper)


class ClassificationTests(unittest.TestCase):
    def classify(self, raw: RawExecution, name: str = "valid") -> FormalCheckOutcome:
        current = request(name)
        return classify_execution(current, generate_wrapper(current), raw)[0]

    def test_kernel_and_axiom_outcomes_are_distinct(self) -> None:
        empty = '{"severity":"information","data":"\'AdaIvyPhase3B.AdaIvyValid\' does not depend on any axioms"}\n'
        approved = '{"severity":"information","data":"depends on axioms: [propext, Classical.choice, Quot.sound]"}\n'
        unapproved = '{"severity":"information","data":"depends on axioms: [AdaIvyAssumptionProof]"}\n'
        self.assertEqual(self.classify(execution(empty)), FormalCheckOutcome.KERNEL_CHECKED)
        self.assertEqual(self.classify(execution(approved)), FormalCheckOutcome.KERNEL_CHECKED_APPROVED_AXIOMS)
        self.assertEqual(self.classify(execution(unapproved), "axiom"), FormalCheckOutcome.KERNEL_CHECKED_UNAPPROVED_ASSUMPTIONS)

    def test_failure_outcomes_are_distinct(self) -> None:
        self.assertEqual(self.classify(execution("", reason="timeout")), FormalCheckOutcome.TIMEOUT)
        self.assertEqual(self.classify(execution("", reason="output_limit")), FormalCheckOutcome.OUTPUT_LIMIT)
        self.assertEqual(self.classify(execution("", reason="sandbox_failure")), FormalCheckOutcome.SANDBOX_FAILURE)
        error = '{"severity":"error","pos":{"line":3},"data":"bad"}\n'
        self.assertEqual(self.classify(execution(error, exit_code=1)), FormalCheckOutcome.ELABORATION_FAILURE)
        meaning_error = '{"severity":"error","pos":{"line":5},"data":"counterexample"}\n'
        self.assertEqual(self.classify(execution(meaning_error, exit_code=1), "meaning-test"), FormalCheckOutcome.MEANING_TEST_FAILURE)
        warning = '{"severity":"warning","data":"unexpected checker warning"}\n' + '{"severity":"information","data":"does not depend on any axioms"}\n'
        self.assertEqual(self.classify(execution(warning)), FormalCheckOutcome.SANDBOX_FAILURE)


class ProposalAndPersistenceTests(unittest.TestCase):
    def test_policy_failure_never_invokes_adapter_and_never_promotes_trust(self) -> None:
        adapter = DockerLeanAdapter()
        with patch.object(adapter, "execute", side_effect=AssertionError("adapter invoked")):
            finding = FormalCheckingService(adapter).check((FIXTURES / "placeholder.json").read_bytes(), created_at=FIXED_TIME)
        self.assertEqual(finding.outcome, FormalCheckOutcome.POLICY_REJECTION)
        self.assertEqual(finding.disposition, "proposal")
        self.assertEqual(finding.trust_effect, "none")
        self.assertFalse(finding.semantic_alignment_approved)
        self.assertFalse(finding.source_applicability_approved)
        self.assertFalse(finding.epistemic_warrant_created)

    def test_runtime_mismatch_is_a_sandbox_failure_without_container_creation(self) -> None:
        adapter = DockerLeanAdapter(expected_digest="sha256:" + "0" * 64)
        with patch.object(adapter, "_inspect_runtime", return_value=(False, "runtime image seal mismatch")):
            finding = FormalCheckingService(adapter).check((FIXTURES / "valid.json").read_bytes(), created_at=FIXED_TIME)
        self.assertEqual(finding.outcome, FormalCheckOutcome.SANDBOX_FAILURE)
        self.assertTrue(finding.execution.container_removed)

    def test_generated_wrapper_bound_failure_is_a_persistable_policy_rejection(self) -> None:
        source = (FIXTURES / "valid.json").read_bytes()
        with patch("math_research.phase3b.service.generate_wrapper", side_effect=ValueError("generated wrapper exceeds bound")):
            finding = FormalCheckingService(DockerLeanAdapter()).check(source, created_at=FIXED_TIME)
        self.assertEqual(finding.outcome, FormalCheckOutcome.POLICY_REJECTION)
        with tempfile.TemporaryDirectory() as temporary, FormalCheckWorkspace(Path(temporary)) as workspace:
            workspace.save_attempt(source, finding)

    def test_append_only_restart_and_canonical_replay(self) -> None:
        adapter = DockerLeanAdapter()
        with patch.object(adapter, "execute", return_value=execution('{"severity":"information","data":"does not depend on any axioms"}\n')):
            source = (FIXTURES / "valid.json").read_bytes()
            finding = FormalCheckingService(adapter).check(source, created_at=FIXED_TIME)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with FormalCheckWorkspace(root / "workspace") as workspace:
                workspace.save_attempt(source, finding)
                workspace.save_attempt(source, finding)
                export_workspace(workspace, root / "export.json")
                self.assertIn("phase3b:0001", workspace.migration_versions)
            with FormalCheckWorkspace(root / "workspace") as restarted:
                self.assertEqual(restarted.finding(finding.id.value)["content_hash"], finding.content_hash)
            replay = import_trusted_replay((root / "export.json").read_bytes())
            self.assertEqual(len(replay["findings"]), 1)

    def test_elapsed_time_is_operational_not_semantic_identity(self) -> None:
        adapter = DockerLeanAdapter()
        current = request()
        wrapper = generate_wrapper(current)
        first_raw = execution('{"severity":"information","data":"does not depend on any axioms"}\n')
        second_raw = replace(first_raw, elapsed_milliseconds=999)
        first = adapter.verify_output(current, wrapper, first_raw, created_at=FIXED_TIME)
        second = adapter.verify_output(current, wrapper, second_raw, created_at="2026-08-20T00:00:00Z")
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.hash_profile, HASH_PROFILE)
        self.assertNotEqual(first.created_at, second.created_at)
        self.assertNotEqual(first.execution.elapsed_milliseconds, second.execution.elapsed_milliseconds)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = []
            for index, finding in enumerate((first, second), 1):
                with FormalCheckWorkspace(root / f"workspace-{index}") as workspace:
                    workspace.save_attempt((FIXTURES / "valid.json").read_bytes(), finding)
                    export_workspace(workspace, root / f"export-{index}.json")
                exports.append(json.loads((root / f"export-{index}.json").read_text()))
            self.assertEqual(exports[0]["content_hash"], exports[1]["content_hash"])
            self.assertNotEqual(exports[0]["operational_hash"], exports[1]["operational_hash"])
            self.assertEqual(exports[0]["findings"][0]["execution"]["elapsed_milliseconds"], 10)
            self.assertEqual(exports[1]["findings"][0]["execution"]["elapsed_milliseconds"], 999)
            self.assertEqual(exports[0]["findings"][0]["created_at"], FIXED_TIME)
            self.assertEqual(exports[1]["findings"][0]["created_at"], "2026-08-20T00:00:00Z")

            with FormalCheckWorkspace(root / "idempotent-workspace") as workspace:
                source = (FIXTURES / "valid.json").read_bytes()
                workspace.save_attempt(source, first)
                workspace.save_attempt(source, second)
                self.assertEqual(len(workspace.canonical_findings()), 1)
                self.assertEqual(workspace.finding(first.id.value)["execution"]["elapsed_milliseconds"], 10)

            tampered = json.loads((root / "export-1.json").read_text())
            tampered["findings"][0]["execution"]["elapsed_milliseconds"] = 11
            with self.assertRaisesRegex(ValueError, "operational hash mismatch"):
                import_trusted_replay(canonical_bytes(tampered) + b"\n")

            tampered = json.loads((root / "export-1.json").read_text())
            tampered["findings"][0]["execution"]["stdout"]["retained_utf8"] = "different checker output"
            tampered["operational_hash"] = operational_export_hash(tampered)
            with self.assertRaisesRegex(ValueError, "semantic content hash mismatch"):
                import_trusted_replay(canonical_bytes(tampered) + b"\n")

    def test_forced_termination_race_details_are_operational(self) -> None:
        adapter = DockerLeanAdapter()
        current = request("timeout")
        wrapper = generate_wrapper(current)
        first_raw = RawExecution(
            1, "timeout", 100, capture(""), capture("No such container: generated-id\n"), True, (),
        )
        second_raw = RawExecution(
            None, "timeout", 120, capture("partial output\n"),
            capture("container is marked for removal\n"), True, ("post-deadline race",),
        )
        first = adapter.verify_output(current, wrapper, first_raw, created_at=FIXED_TIME)
        second = adapter.verify_output(current, wrapper, second_raw, created_at=FIXED_TIME)
        self.assertEqual(first.outcome, FormalCheckOutcome.TIMEOUT)
        self.assertEqual(second.outcome, FormalCheckOutcome.TIMEOUT)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(public_value(first.execution), public_value(second.execution))

    def test_legacy_full_record_export_remains_importable(self) -> None:
        legacy = legacy_export_value([legacy_finding_value()])
        pre_repair_bytes = canonical_bytes(legacy)
        imported = import_trusted_replay(pre_repair_bytes)
        self.assertEqual(imported, legacy)
        self.assertEqual(canonical_bytes(imported), pre_repair_bytes)

    def test_current_profile_export_round_trips(self) -> None:
        current = current_export_value([current_finding_value()])
        self.assertEqual(import_trusted_replay(canonical_bytes(current)), current)

    def test_legacy_envelope_rejects_rehashed_current_finding(self) -> None:
        mixed = legacy_export_value([current_finding_value()])
        with self.assertRaisesRegex(ValueError, "formal finding hash profile mismatch"):
            import_trusted_replay(canonical_bytes(mixed))

    def test_current_envelope_rejects_rehashed_legacy_finding(self) -> None:
        mixed = current_export_value([legacy_finding_value()])
        with self.assertRaisesRegex(ValueError, "formal finding hash profile mismatch"):
            import_trusted_replay(canonical_bytes(mixed))

    def test_current_envelope_rejects_rehashed_unknown_finding_profile(self) -> None:
        finding = current_finding_value()
        finding["hash_profile"] = "phase3b-unknown-v9"
        finding["content_hash"] = ""
        finding["content_hash"] = canonical_hash(finding)
        mixed = current_export_value([finding])
        with self.assertRaisesRegex(ValueError, "formal finding hash profile mismatch"):
            import_trusted_replay(canonical_bytes(mixed))

    def test_unknown_rehashed_envelope_profile_is_rejected(self) -> None:
        unknown = current_export_value([current_finding_value()])
        unknown["hash_profile"] = "phase3b-unknown-v9"
        unknown["content_hash"] = semantic_export_hash(unknown)
        unknown["operational_hash"] = operational_export_hash(unknown)
        with self.assertRaisesRegex(ValueError, "unsupported Phase 3B export hash profile"):
            import_trusted_replay(canonical_bytes(unknown))

    def test_one_rehashed_mismatch_rejects_multiple_findings(self) -> None:
        first = current_finding_value()
        second = current_finding_value()
        second["id"] = "formal-finding.distinct-mixed-profile"
        second = legacy_finding_value(second)
        mixed = current_export_value([first, second])
        with self.assertRaisesRegex(ValueError, "formal finding hash profile mismatch"):
            import_trusted_replay(canonical_bytes(mixed))

    def test_phase3b_contains_no_model_network_or_external_api_client(self) -> None:
        forbidden_imports = {"openai", "anthropic", "requests", "httpx", "urllib", "socket"}
        for path in Path("src/math_research/phase3b").glob("*.py"):
            tree = ast.parse(path.read_text())
            imported = {
                alias.name.split(".")[0]
                for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
            }
            self.assertFalse(imported & forbidden_imports, path)


if __name__ == "__main__":
    unittest.main()
