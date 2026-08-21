"""ADR-0039 acceptance suite: the declarative problem-definition loader.

The thresholds of this slice are these assertions. Three properties carry the
slice and are asserted as properties rather than exercised on a happy path:

- one named rejection fixture per rejection class, each producing exactly one
  code, so a class cannot silently stop being enforced;
- the published JSON Schema is derived from the Phase 1 enums, so it cannot
  drift from `domain/entities.py`;
- the built dossier is a pure function of (document bytes, instant), verified
  across processes and hash seeds.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from math_research.application import problem_intake
from math_research.application.problem_intake import (
    ISSUE_CODES,
    PROBLEM_DEFINITION_SCHEMA_VERSION,
    ProblemDefinitionError,
    build_dossier,
    load_problem_definition,
    load_problem_definition_file,
    parse_instant,
    parse_problem_definition,
    problem_definition_schema,
    problem_definition_schema_text,
)
from math_research.domain.entities import (
    AlignmentStatus,
    ApprovalStatus,
    ClaimOrigin,
    ClaimScope,
    ProblemType,
    ProtocolPhase,
    StrengthRelation,
)
from math_research.interchange import export_dossier_bytes, export_dossier_dict, import_trusted_replay

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "problem-intake"
INVALID = FIXTURES / "invalid"
SCHEMA_PATH = REPO_ROOT / "schemas" / "problem-definition-v1.schema.json"
INSTANT = parse_instant("2026-08-21T00:00:00Z")

VALID_FIXTURES = (
    "asserts-its-own-proof-v1.json",
    "graph-cycle-edge-bound-v1.json",
    "odd-perfect-number-search-v1.json",
)

# Rejection class -> the fixture that exhibits exactly that class. Every code in
# ISSUE_CODES except `instant` (which is an argument, not a document field) must
# appear here, and every fixture in fixtures/problem-intake/invalid must appear.
REJECTION_FIXTURES: dict[str, str] = {
    "control_character": "control-character-carriage-return.json",
    "duplicate_item": "duplicate-item-repeated-quantifier.json",
    "duplicate_key": "duplicate-key-declared-domain.json",
    "duplicate_local_id": "duplicate-local-id-target-collides.json",
    "empty": "empty-target-statement.json",
    "enum": "enum-unknown-claim-scope.json",
    "identifier": "identifier-bad-problem-definition-id.json",
    "malformed_json": "malformed-json-truncated.json",
    "non_finite_number": "non-finite-number-nan-version.json",
    "not_nfc": "not-nfc-decomposed-statement.json",
    "not_utf8": "not-utf8-invalid-byte.json",
    "reference": "reference-unresolved-assumption-local-id.json",
    "required": "required-missing-target-claim.json",
    "too_long": "too-long-title.json",
    "too_many": "too-many-tags.json",
    "type": "type-tags-not-array.json",
    "unknown_field": "unknown-field-priority.json",
    "version": "version-unsupported-schema-version.json",
    "whitespace": "whitespace-padded-title.json",
    # Two named trust classes, each with more than one fixture below.
    "forbidden_field": "forbidden-field-warrants.json",
    "forbidden_enum_value": "forbidden-enum-value-approved-formalization.json",
}
ADDITIONAL_REJECTIONS: dict[str, str] = {
    "forbidden-field-alignment-approval.json": "forbidden_field",
    "forbidden-field-claim-origin.json": "forbidden_field",
    "forbidden-field-created-at.json": "forbidden_field",
    "forbidden-field-logical-status.json": "forbidden_field",
    "forbidden-enum-value-confirmatory-protocol.json": "forbidden_enum_value",
    "identifier-bad-principal.json": "identifier",
    "type-version-not-integer.json": "type",
}


def _codes(path: Path) -> tuple[str, ...]:
    with unittest.TestCase().assertRaises(ProblemDefinitionError) as caught:
        parse_problem_definition(path.read_bytes())
    return caught.exception.codes


class RejectionClassTests(unittest.TestCase):
    def test_each_rejection_class_has_a_fixture_producing_exactly_that_code(self) -> None:
        for code, name in sorted(REJECTION_FIXTURES.items()):
            with self.subTest(code=code):
                self.assertEqual((code,), _codes(INVALID / name))

    def test_additional_rejection_fixtures_stay_in_their_class(self) -> None:
        for name, code in sorted(ADDITIONAL_REJECTIONS.items()):
            with self.subTest(fixture=name):
                self.assertEqual((code,), _codes(INVALID / name))

    def test_every_invalid_fixture_is_claimed_and_every_code_is_covered(self) -> None:
        on_disk = {path.name for path in INVALID.iterdir() if path.suffix == ".json"}
        claimed = set(REJECTION_FIXTURES.values()) | set(ADDITIONAL_REJECTIONS)
        self.assertEqual(on_disk, claimed)
        # `instant` is raised for the explicit argument, not for a document field.
        self.assertEqual(ISSUE_CODES - {"instant", "too_large"}, set(REJECTION_FIXTURES))

    def test_every_invalid_fixture_is_rejected_and_never_builds_a_dossier(self) -> None:
        for path in sorted(INVALID.iterdir()):
            with self.subTest(fixture=path.name), self.assertRaises(ProblemDefinitionError):
                load_problem_definition(path.read_bytes(), instant=INSTANT)

    def test_rejection_is_one_typed_exception_carrying_machine_readable_issues(self) -> None:
        with self.assertRaises(ProblemDefinitionError) as caught:
            parse_problem_definition((INVALID / "forbidden-field-warrants.json").read_bytes())
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(1, len(error.issues))
        issue = error.issues[0]
        self.assertEqual("$.warrants", issue.path)
        self.assertEqual("forbidden_field", issue.code)
        self.assertEqual(PROBLEM_DEFINITION_SCHEMA_VERSION, issue.schema_version)
        self.assertIn("creates no warrant", issue.message)

    def test_multiple_failures_are_reported_together_in_a_stable_order(self) -> None:
        document = json.loads((FIXTURES / "graph-cycle-edge-bound-v1.json").read_text(encoding="utf-8"))
        document["problem"]["title"] = ""
        document["target_claim"]["scope"] = "sometimes_universal"
        document["declared_domain"] = "Graph Theory"
        data = json.dumps(document).encode("utf-8")
        with self.assertRaises(ProblemDefinitionError) as first:
            parse_problem_definition(data)
        with self.assertRaises(ProblemDefinitionError) as second:
            parse_problem_definition(data)
        paths = [item.path for item in first.exception.issues]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(
            [(item.path, item.code) for item in first.exception.issues],
            [(item.path, item.code) for item in second.exception.issues],
        )
        self.assertEqual(("empty", "enum", "identifier"), first.exception.codes)

    def test_oversized_documents_are_rejected_without_being_parsed(self) -> None:
        # The only rejection class with no committed fixture, because a
        # quarter-megabyte fixture is not worth the bytes. Generated instead.
        document = json.loads((FIXTURES / "graph-cycle-edge-bound-v1.json").read_text(encoding="utf-8"))
        document["problem"]["tags"] = ["x" * 60] * 4
        padding = "y" * (problem_intake.MAX_DOCUMENT_BYTES + 1)
        data = json.dumps(document).encode("utf-8") + b"\n" + padding.encode("utf-8")
        with self.assertRaises(ProblemDefinitionError) as caught:
            parse_problem_definition(data)
        self.assertEqual(("too_large",), caught.exception.codes)
        self.assertEqual("$", caught.exception.issues[0].path)

    def test_no_coercion_and_no_silent_default(self) -> None:
        document = json.loads((FIXTURES / "graph-cycle-edge-bound-v1.json").read_text(encoding="utf-8"))
        document["formalization"]["version"] = True  # bool is an int subclass
        with self.assertRaises(ProblemDefinitionError) as caught:
            parse_problem_definition(json.dumps(document).encode("utf-8"))
        self.assertEqual(("type",), caught.exception.codes)


class DerivedSchemaTests(unittest.TestCase):
    def test_published_schema_file_is_byte_identical_to_the_derived_schema(self) -> None:
        self.assertEqual(problem_definition_schema_text(), SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_every_schema_enum_is_derived_from_a_phase_1_domain_enum(self) -> None:
        schema = problem_definition_schema()
        properties = schema["properties"]
        cases = {
            "problem_type": (
                properties["problem"]["properties"]["problem_type"]["enum"],
                sorted(item.value for item in ProblemType),
            ),
            "target_scope": (
                properties["target_claim"]["properties"]["scope"]["enum"],
                sorted(item.value for item in ClaimScope),
            ),
            "assumption_scope": (
                properties["assumption_claims"]["items"]["properties"]["scope"]["enum"],
                sorted(item.value for item in ClaimScope),
            ),
            "strength_relation": (
                properties["semantic_alignment"]["properties"]["strength_relation"]["enum"],
                sorted(item.value for item in StrengthRelation),
            ),
            "approval_status": (
                properties["formalization"]["properties"]["approval_status"]["enum"],
                sorted(
                    item.value for item in ApprovalStatus
                    if item not in problem_intake.FORBIDDEN_APPROVAL_STATUS
                ),
            ),
            "protocol_phase": (
                properties["evaluation_protocol"]["properties"]["phase"]["enum"],
                sorted(
                    item.value for item in ProtocolPhase
                    if item not in problem_intake.FORBIDDEN_PROTOCOL_PHASE
                ),
            ),
        }
        for name, (published, derived) in sorted(cases.items()):
            with self.subTest(field=name):
                self.assertEqual(derived, published)

    def test_every_restricted_enum_member_is_named_with_a_reason(self) -> None:
        for member, reason in problem_intake.FORBIDDEN_APPROVAL_STATUS.items():
            self.assertIsInstance(member, ApprovalStatus)
            self.assertTrue(reason.strip())
        for member, reason in problem_intake.FORBIDDEN_PROTOCOL_PHASE.items():
            self.assertIsInstance(member, ProtocolPhase)
            self.assertTrue(reason.strip())
        self.assertNotIn(ApprovalStatus.APPROVED.value, problem_intake.INTAKE_APPROVAL_STATUSES)
        self.assertNotIn(ProtocolPhase.CONFIRMATORY.value, problem_intake.INTAKE_PROTOCOL_PHASES)

    def test_schema_forbids_unknown_keys_at_every_level(self) -> None:
        schema = problem_definition_schema()
        self.assertFalse(schema["additionalProperties"])
        for name in ("problem", "target_claim", "formalization", "semantic_alignment", "evaluation_protocol"):
            with self.subTest(object=name):
                self.assertFalse(schema["properties"][name]["additionalProperties"])
        self.assertFalse(schema["properties"]["assumption_claims"]["items"]["additionalProperties"])

    def test_schema_declares_no_trust_bearing_field(self) -> None:
        text = json.dumps(problem_definition_schema(), sort_keys=True)
        payload = json.loads(text)

        def keys(value: object) -> set[str]:
            found: set[str] = set()
            if isinstance(value, dict):
                if "properties" in value and isinstance(value["properties"], dict):
                    found |= set(value["properties"])
                for item in value.values():
                    found |= keys(item)
            elif isinstance(value, list):
                for item in value:
                    found |= keys(item)
            return found

        declared = keys(payload)
        self.assertEqual(set(), declared & set(problem_intake.FORBIDDEN_FIELDS))


class DeterminismTests(unittest.TestCase):
    def test_same_document_and_instant_produce_identical_bytes(self) -> None:
        for name in VALID_FIXTURES:
            with self.subTest(fixture=name):
                first = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                second = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                self.assertEqual(export_dossier_bytes(first), export_dossier_bytes(second))
                self.assertEqual(first, second)

    def test_dossier_bytes_are_stable_across_processes_and_hash_seeds(self) -> None:
        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "from pathlib import Path;"
            "from math_research.application.problem_intake import load_problem_definition_file, parse_instant;"
            "from math_research.interchange import export_dossier_bytes;"
            "result = load_problem_definition_file(Path(sys.argv[1]), instant=parse_instant(sys.argv[2]));"
            "sys.stdout.buffer.write(export_dossier_bytes(result.dossier))"
        ) % str(REPO_ROOT / "src")
        observed = set()
        for seed in ("0", "1", "12345"):
            environment = dict(os.environ, PYTHONHASHSEED=seed)
            completed = subprocess.run(
                [sys.executable, "-c", script, str(FIXTURES / "graph-cycle-edge-bound-v1.json"), "2026-08-21T00:00:00Z"],
                capture_output=True, check=True, env=environment, timeout=120,
            )
            observed.add(completed.stdout)
        self.assertEqual(1, len(observed))
        in_process = export_dossier_bytes(
            load_problem_definition_file(FIXTURES / "graph-cycle-edge-bound-v1.json", instant=INSTANT).dossier
        )
        self.assertEqual({in_process}, observed)

    def test_loader_reads_no_clock_and_no_randomness(self) -> None:
        for module in (
            REPO_ROOT / "src" / "math_research" / "application" / "problem_intake.py",
            REPO_ROOT / "src" / "math_research" / "problem_intake_cli.py",
        ):
            with self.subTest(module=module.name):
                tree = ast.parse(module.read_text(encoding="utf-8"))
                imported = {
                    alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                } | {
                    node.module.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module
                }
                self.assertNotIn("random", imported)
                self.assertNotIn("secrets", imported)
                self.assertNotIn("time", imported)
                attributes = {
                    node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                }
                for forbidden in ("now", "utcnow", "today", "monotonic", "time_ns"):
                    self.assertNotIn(forbidden, attributes)
                names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
                self.assertNotIn("utc_now", names)

    def test_instant_must_be_an_explicit_utc_instant(self) -> None:
        for value in ("2026-08-21", "2026-08-21T00:00:00+02:00", "2026-08-21T00:00:00", "now", ""):
            with self.subTest(value=value), self.assertRaises(ProblemDefinitionError) as caught:
                parse_instant(value)
            self.assertEqual(("instant",), caught.exception.codes)

    def test_naive_instant_is_rejected_by_the_builder(self) -> None:
        definition = parse_problem_definition((FIXTURES / "graph-cycle-edge-bound-v1.json").read_bytes())
        with self.assertRaises(ProblemDefinitionError) as caught:
            build_dossier(definition, instant=datetime(2026, 8, 21))
        self.assertEqual(("instant",), caught.exception.codes)

    def test_a_different_instant_changes_only_timestamps_not_identity_binding(self) -> None:
        path = FIXTURES / "graph-cycle-edge-bound-v1.json"
        first = load_problem_definition_file(path, instant=INSTANT)
        later = load_problem_definition_file(path, instant=parse_instant("2026-09-01T12:00:00Z"))
        self.assertEqual(first.dossier.id, later.dossier.id)
        self.assertEqual(
            first.definition.canonical_document_hash, later.definition.canonical_document_hash
        )
        self.assertNotEqual(
            export_dossier_dict(first.dossier)["content_hash"],
            export_dossier_dict(later.dossier)["content_hash"],
        )
        self.assertEqual(datetime(2026, 9, 1, 12, tzinfo=timezone.utc), later.dossier.created_at)


class ProvenanceBindingTests(unittest.TestCase):
    def test_canonical_problem_hash_is_bound_into_dossier_identity(self) -> None:
        result = load_problem_definition_file(FIXTURES / "odd-perfect-number-search-v1.json", instant=INSTANT)
        digest = result.definition.canonical_document_hash.removeprefix("sha256:")[:16]
        self.assertTrue(result.dossier.id.value.endswith(f"intake.sha256-{digest}"))
        event = result.dossier.audit_events[0]
        payload = dict(event.payload)
        self.assertEqual("problem_definition_recorded", event.event_type)
        self.assertEqual(result.definition.canonical_document_hash, payload["problem_definition_canonical_hash"])
        self.assertEqual("odd-perfect-number-search", payload["problem_definition_id"])
        self.assertEqual("number-theory", payload["declared_domain"])
        self.assertEqual("true", payload["intake_creates_no_warrant"])
        self.assertEqual(tuple(sorted(event.payload)), event.payload)
        exported = export_dossier_dict(result.dossier)
        self.assertIn(
            result.definition.canonical_document_hash,
            json.dumps(exported, sort_keys=True),
        )

    def test_changing_one_document_byte_changes_the_dossier_identity(self) -> None:
        original = (FIXTURES / "graph-cycle-edge-bound-v1.json").read_bytes()
        document = json.loads(original)
        document["problem"]["title"] = document["problem"]["title"] + " (revised)"
        mutated = load_problem_definition(json.dumps(document).encode("utf-8"), instant=INSTANT)
        baseline = load_problem_definition(original, instant=INSTANT)
        self.assertNotEqual(baseline.dossier.id, mutated.dossier.id)
        self.assertNotEqual(
            baseline.definition.canonical_document_hash, mutated.definition.canonical_document_hash
        )

    def test_reformatting_preserves_semantic_identity_and_moves_the_operational_hash(self) -> None:
        original = (FIXTURES / "graph-cycle-edge-bound-v1.json").read_bytes()
        reformatted = json.dumps(json.loads(original), indent=7, sort_keys=True).encode("utf-8")
        self.assertNotEqual(original, reformatted)
        baseline = load_problem_definition(original, instant=INSTANT)
        rewrapped = load_problem_definition(reformatted, instant=INSTANT)
        self.assertEqual(
            baseline.definition.canonical_document_hash, rewrapped.definition.canonical_document_hash
        )
        self.assertNotEqual(
            baseline.definition.source_bytes_hash, rewrapped.definition.source_bytes_hash
        )
        self.assertEqual(export_dossier_bytes(baseline.dossier), export_dossier_bytes(rewrapped.dossier))
        self.assertNotIn(
            baseline.definition.source_bytes_hash,
            json.dumps(export_dossier_dict(baseline.dossier), sort_keys=True),
            "the operational source-byte hash must stay out of the semantic content hash",
        )


class ShapeTests(unittest.TestCase):
    def test_both_declared_shapes_load_and_keep_their_declared_scope(self) -> None:
        existential = load_problem_definition_file(FIXTURES / "odd-perfect-number-search-v1.json", instant=INSTANT)
        universal = load_problem_definition_file(FIXTURES / "graph-cycle-edge-bound-v1.json", instant=INSTANT)
        self.assertEqual(ClaimScope.EXISTENTIAL, existential.definition.target_claim.scope)
        self.assertEqual(ProblemType.PROVE, existential.definition.problem.problem_type)
        self.assertEqual(ClaimScope.UNRESTRICTED_UNIVERSAL, universal.definition.target_claim.scope)
        for result in (existential, universal):
            target = result.dossier.formalization.target_claim_id
            claim = next(item for item in result.dossier.claims if item.id == target)
            self.assertEqual(result.definition.target_claim.scope, claim.scope)
            self.assertEqual(
                len(result.definition.assumption_claims) + 1, len(result.dossier.claims)
            )

    def test_assumption_links_resolve_to_minted_claim_ids(self) -> None:
        result = load_problem_definition_file(FIXTURES / "odd-perfect-number-search-v1.json", instant=INSTANT)
        linked = result.dossier.formalization.assumption_claim_ids
        self.assertEqual(3, len(linked))
        known = {item.id for item in result.dossier.claims}
        self.assertTrue(set(linked) <= known)
        target = next(
            item for item in result.dossier.claims
            if item.id == result.dossier.formalization.target_claim_id
        )
        self.assertEqual(linked, target.assumption_claim_ids)

    def test_built_dossiers_pass_full_phase_1_interchange_validation(self) -> None:
        for name in VALID_FIXTURES:
            with self.subTest(fixture=name):
                dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                replayed = import_trusted_replay(export_dossier_bytes(dossier))
                self.assertEqual(dossier, replayed)

    def test_no_fixture_is_quantum(self) -> None:
        for name in VALID_FIXTURES:
            text = (FIXTURES / name).read_text(encoding="utf-8").lower()
            with self.subTest(fixture=name):
                for token in ("quantum", "qubit", "hilbert", "density matrix", "povm"):
                    self.assertNotIn(token, text)


class DomainImmutabilityTests(unittest.TestCase):
    """This slice is a builder. The trust model must be untouched by it."""

    def test_intake_forces_the_untrusted_values_it_will_not_accept(self) -> None:
        for name in VALID_FIXTURES:
            with self.subTest(fixture=name):
                dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                self.assertIs(AlignmentStatus.PROPOSED, dossier.semantic_alignment.status)
                self.assertIsNone(dossier.semantic_alignment.approved_by)
                self.assertIsNone(dossier.evaluation_protocol.frozen_at)
                self.assertIsNone(dossier.evaluation_protocol.frozen_by)
                self.assertFalse(dossier.evaluation_protocol.is_frozen)
                self.assertIs(ProtocolPhase.EXPLORATORY, dossier.evaluation_protocol.phase)
                self.assertIn(dossier.formalization.approval_status, {
                    ApprovalStatus.PROPOSED, ApprovalStatus.NEEDS_CLARIFICATION,
                })
                for claim in dossier.claims:
                    self.assertIs(ClaimOrigin.USER, claim.origin)
                    self.assertIsNone(claim.novelty_assessment_id)
                    self.assertIsNone(claim.significance_assessment_id)
                    self.assertEqual((), claim.contribution_ids)
                    self.assertEqual((), claim.representation_map_ids)


if __name__ == "__main__":
    unittest.main()
