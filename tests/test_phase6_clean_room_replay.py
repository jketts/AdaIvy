"""Clean-room replay acceptance suite for the ADR-0044 Phase 6 verifier.

Per AGENTS.md:86-89 a scenario's forbidden outcomes must be demonstrated
impossible, not merely left untested. Every tamper case below mutates a valid
bundle and then RE-SEALS the hashes a forger could plausibly re-seal, at one of
four escalating levels, before asserting that verification refuses it:

  ``envelope``    only the top-level export ``content_hash``. This is exactly
                  what ``Phase6Workspace.save_verified_export`` checks today, so
                  a bundle re-sealed at this level is a forgery the producer
                  currently ACCEPTS, with every record's own ``content_hash``
                  left stale because nothing re-derives it.
  ``records``     additionally every record's own ``content_hash``.
  ``identities``  additionally every derived ``record_id`` and ``release_hash``.
  ``release``     additionally every release cross-reference, so the bundle is
                  internally perfect and only an independent re-derivation of
                  the mathematics, or a refusal invariant, can reject it.

Without the re-seal these tests would only be re-testing the one envelope hash
that already worked.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from math_research import phase6_cli
from math_research.phase5 import EXPORT_VERSION as PHASE5_EXPORT_VERSION
from math_research.phase5 import SCHEMA_VERSION as PHASE5_RECORD_VERSION
from math_research.phase5.quantum import DiagonalCase, run_case
from math_research.phase5.serialization import (
    canonical_bytes, canonical_hash, content_hash, stable_id,
)
from math_research.phase5.service import Phase5Service
from math_research.phase6 import EXPORT_VERSION as PHASE6_EXPORT_VERSION
from math_research.phase6 import SCHEMA_VERSION as PHASE6_RECORD_VERSION
from math_research.phase6 import replay as replay_module
from math_research.phase6 import service as producer
from math_research.phase6.replay import (
    ALLOWED_CAPABILITIES, EXPECTED_CONTROLS, EXPECTED_METHOD, EXPECTED_RECORD_TYPES,
    MAX_VERIFY_BYTES, NOT_DERIVED_FIELDS, PROTOCOL_FIELDS, Phase6ReplayError,
    UNVERIFIABLE_FIELDS, verify_release_bundle,
)
from math_research.phase6.service import Phase6Service
from math_research.phase6.workspace import Phase6Workspace

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE5_FIXTURE_PATH = REPO_ROOT / "fixtures/phase5/quantum-diagonal-v1.json"
PROTOCOL_PATH = REPO_ROOT / "fixtures/phase6/confirmatory-protocol-v1.json"
PHASE5_FIXTURE = json.loads(PHASE5_FIXTURE_PATH.read_text("utf-8"))
PROTOCOL = json.loads(PROTOCOL_PATH.read_text("utf-8"))
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T14:00:00Z"

# The canonical hash of the whole verdict, computed in a different process and
# pinned here. Determinism across runs, restarts, and processes is a requirement
# (README.md:24-28, AGENTS.md:69-71), and a literal computed in another process
# is the cross-process evidence available without spawning a subprocess.
VERDICT_HASH = "sha256:d413855eaac2a3b9df335cd0fac4a4a14536e030ae45233cfcf03d8284770099"

# The producer this slice must not touch. ADR-0044's core claim is that the
# clean-room verifier was added without editing the thing it verifies, so the
# claim is asserted structurally rather than described. If a producer change is
# ever intended, update ADR-0044 and this pin in the same change.
PRODUCER_DIGESTS = {
    "src/math_research/phase6/service.py":
        "940c4834cc1167c7f1051abd361e2c0a380e99d8b5c041ec91c6580680df0ed5",
    "src/math_research/phase6/workspace.py":
        "ef2385efc26d57e87a94e3fd6152122a704df3a1f9be1fddd297b27bb9fb79aa",
    "fixtures/phase6/confirmatory-protocol-v1.json":
        "befbb3c206a75610b0b420f19b3a9f09d53c8063908943eed4faa5e56ea2f8b2",
    "migrations/phase6/0001_confirmatory_release.sql":
        "19f470af7a73247b8042cfb8e0dac6146b9c2a7f7da945178d7a03556a255743",
}

RESEAL_LEVELS = ("envelope", "records", "identities", "release")


# --------------------------------------------------------------------------
# bundle production and the forger's re-sealing toolkit
# --------------------------------------------------------------------------


def build_bundle(fixture: dict, protocol: dict) -> tuple[bytes, bytes, bytes]:
    """Produce one genuine bundle with the untouched producer."""

    with tempfile.TemporaryDirectory() as directory:
        with Phase6Workspace(Path(directory)) as workspace:
            phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                fixture, recorded_at=T0
            )
            Phase6Service(workspace).confirm(
                protocol=protocol, phase5_fixture=fixture,
                phase5_run_id=phase5["run_id"], recorded_at=T1,
            )
            return (
                workspace.export_bytes(),
                workspace.phase5.export_bytes(),
                canonical_bytes(fixture),
            )


def dead_end_inputs() -> tuple[dict, dict]:
    """A fixture that really produces a Phase 5 ``dead_end`` record.

    Repeating a case yields a duplicate exact result hash, which is the
    producer's dead-end condition (phase5/service.py:403-409). The frozen
    held-out case is a different case, so it still resolves exactly once.
    """

    fixture = copy.deepcopy(PHASE5_FIXTURE)
    fixture["cases"].append(copy.deepcopy(fixture["cases"][0]))
    protocol = copy.deepcopy(PROTOCOL)
    protocol["phase5_fixture_hash"] = canonical_hash(fixture)
    return fixture, protocol


def _derived_id(record: dict) -> str:
    identity = {
        "record_type": record["record_type"],
        "subject_id": record["subject_id"],
        "payload": record["payload"],
    }
    return stable_id(record["record_type"].replace("_", "-"), identity)


def reseal(value: dict, level: str = "envelope") -> bytes:
    """Re-seal a mutated Phase 6 export at one of the four escalating levels."""

    if level not in RESEAL_LEVELS:
        raise AssertionError(f"unknown reseal level: {level}")
    value = copy.deepcopy(value)
    records = value["records"]
    if level == "envelope":
        value["content_hash"] = content_hash(value)
        return canonical_bytes(value)
    for index, record in enumerate(records):
        record["sequence"] = index
    if level == "records":
        for record in records:
            record["content_hash"] = content_hash(record)
        value["content_hash"] = content_hash(value)
        return canonical_bytes(value)

    ctx: dict = {}
    contributions: list[dict] = []
    for record in records:
        kind = record["record_type"]
        payload = record["payload"]
        if kind == "confirmatory_protocol":
            payload["protocol_hash"] = canonical_hash(payload["protocol"])
            ctx["protocol_hash"] = payload["protocol_hash"]
            ctx["protocol_id"] = payload["protocol"]["protocol_id"]
            record["subject_id"] = record["record_id"] = ctx["protocol_id"]
        elif kind == "confirmatory_run":
            run_id = stable_id("run.phase6", {
                "protocol_hash": ctx["protocol_hash"],
                "phase5_run_id": payload["phase5_run_id"],
            })
            payload["run_id"] = run_id
            ctx["run_id"] = run_id
            ctx["phase5_run_id"] = payload["phase5_run_id"]
            record["subject_id"] = record["record_id"] = run_id
        elif kind == "confirmatory_result":
            record["subject_id"] = ctx["run_id"]
            record["record_id"] = stable_id(
                "evaluation.phase6", {"run_id": ctx["run_id"], "result": payload}
            )
            ctx["result_id"] = record["record_id"]
            ctx["result"] = copy.deepcopy(payload)
        elif kind in {"novelty_assessment", "significance_assessment", "contribution"}:
            record["subject_id"] = ctx["result_id"]
            if kind == "contribution" and level == "release":
                # A thorough forger re-points the contribution artifacts too.
                # `exact_computation` is left alone: it names the recomputed
                # case-result hash, which no re-seal can invent.
                if payload["contribution_type"] == "protocol_freeze":
                    payload["artifact_id"] = ctx["protocol_id"]
                elif payload["contribution_type"] == "verification":
                    payload["artifact_id"] = ctx["result_id"]
            record["record_id"] = _derived_id(record)
            if kind == "contribution":
                contributions.append(record)
            else:
                short = kind.split("_")[0]
                ctx[short] = copy.deepcopy(payload)
                ctx[f"{short}_record_id"] = record["record_id"]
        elif kind == "release_package":
            if level == "release":
                payload["protocol_id"] = ctx["protocol_id"]
                payload["protocol_hash"] = ctx["protocol_hash"]
                payload["phase5_run_id"] = ctx["phase5_run_id"]
                payload["confirmatory_run_id"] = ctx["run_id"]
                payload["confirmatory_run_hash"] = ctx["run_hash"]
                payload["confirmatory_result_id"] = ctx["result_id"]
                payload["confirmatory_result_hash"] = ctx["result_hash"]
                payload["confirmatory_result"] = copy.deepcopy(ctx["result"])
                payload["novelty"] = copy.deepcopy(ctx["novelty"])
                payload["novelty_record_id"] = ctx["novelty_record_id"]
                payload["significance"] = copy.deepcopy(ctx["significance"])
                payload["significance_record_id"] = ctx["significance_record_id"]
                payload["contributions"] = [
                    copy.deepcopy(item["payload"]) for item in contributions
                ]
                payload["contribution_record_ids"] = [
                    item["record_id"] for item in contributions
                ]
            payload["release_hash"] = canonical_hash(
                {k: v for k, v in payload.items() if k != "release_hash"}
            )
            record["subject_id"] = ctx["run_id"]
            record["record_id"] = stable_id(
                "release.phase6",
                {"run_id": ctx["run_id"], "release_hash": payload["release_hash"]},
            )
        record["content_hash"] = content_hash(record)
        if kind == "confirmatory_run":
            ctx["run_hash"] = record["content_hash"]
        elif kind == "confirmatory_result":
            ctx["result_hash"] = record["content_hash"]
    value["content_hash"] = content_hash(value)
    return canonical_bytes(value)


def reseal_phase5(value: dict) -> bytes:
    """Re-seal a mutated Phase 5 export as its own producer would."""

    value = copy.deepcopy(value)
    for index, record in enumerate(value["records"]):
        record["sequence"] = index
        record["content_hash"] = content_hash(record)
    value["content_hash"] = content_hash(value)
    return canonical_bytes(value)


def record_of(value: dict, record_type: str) -> dict:
    found = [item for item in value["records"] if item["record_type"] == record_type]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one {record_type} record")
    return found[0]


class BundleCase(unittest.TestCase):
    """Shared genuine bundle. Built once; every test mutates its own copy."""

    p6_bytes: bytes
    p5_bytes: bytes
    fixture_bytes: bytes

    @classmethod
    def setUpClass(cls) -> None:
        cls.p6_bytes, cls.p5_bytes, cls.fixture_bytes = build_bundle(
            PHASE5_FIXTURE, PROTOCOL
        )

    def p6(self) -> dict:
        return json.loads(self.p6_bytes)

    def p5(self) -> dict:
        return json.loads(self.p5_bytes)

    def fixture(self) -> dict:
        return json.loads(self.fixture_bytes)

    def verify(
        self, p6: bytes | None = None, p5: bytes | None = None,
        fixture: bytes | None = None,
    ) -> dict:
        return verify_release_bundle(
            self.p6_bytes if p6 is None else p6,
            self.p5_bytes if p5 is None else p5,
            self.fixture_bytes if fixture is None else fixture,
        )

    def refuses(
        self, *, p6: bytes | None = None, p5: bytes | None = None,
        fixture: bytes | None = None, because: str = "",
    ) -> str:
        with self.assertRaises(Phase6ReplayError) as caught:
            self.verify(p6=p6, p5=p5, fixture=fixture)
        message = str(caught.exception)
        if because:
            self.assertIn(because, message)
        return message

    def detail(self, name: str, verdict: dict | None = None) -> dict:
        verdict = self.verify() if verdict is None else verdict
        return {item["check"]: item["detail"] for item in verdict["checks"]}[name]


# --------------------------------------------------------------------------
# positive properties
# --------------------------------------------------------------------------


class CleanRoomPositiveTests(BundleCase):
    def test_demo_bundle_verifies(self) -> None:
        verdict = self.verify()
        self.assertIs(True, verdict["verified"])
        self.assertEqual("adaivy.phase6-clean-room-replay.v1", verdict["schema_version"])
        self.assertEqual(15, len(verdict["checks"]))
        self.assertTrue(all(item["status"] == "passed" for item in verdict["checks"]))

    def test_verdict_is_byte_deterministic_across_calls_and_processes(self) -> None:
        first = canonical_bytes(self.verify())
        second = canonical_bytes(self.verify())
        self.assertEqual(first, second)
        # Pinned in a different process; a restart that changed the verdict
        # fails here rather than passing silently.
        self.assertEqual(VERDICT_HASH, canonical_hash(json.loads(first)))

    def test_non_canonical_fixture_file_is_bound_by_value_not_bytes(self) -> None:
        raw = PHASE5_FIXTURE_PATH.read_bytes()
        self.assertNotEqual(raw, canonical_bytes(json.loads(raw)))
        detail = self.detail("canonical_input_encoding", self.verify(fixture=raw))
        self.assertIs(False, detail["phase5_fixture_bytes_canonical"])
        self.assertEqual("by_value_hash", detail["phase5_fixture_binding"])

    def test_case_result_hash_is_really_recomputed(self) -> None:
        self.assertEqual("qd-fs-01-orthogonal-2d", PROTOCOL["heldout_case_ids"][0])
        expected = run_case(
            DiagonalCase.from_value(PHASE5_FIXTURE["cases"][2])
        )["result_hash"]
        verdict = self.verify()
        self.assertEqual(expected, verdict["bound_identities"]["case_result_hash"])
        self.assertEqual(
            expected, self.detail("heldout_case_independently_recomputed", verdict)[
                "case_result_hash"
            ],
        )
        other = run_case(
            DiagonalCase.from_value(PHASE5_FIXTURE["cases"][0])
        )["result_hash"]
        self.assertNotEqual(other, expected)

    def test_negative_attempts_are_observed_from_records(self) -> None:
        detail = self.detail("negative_and_superseded_attempts_observed")
        self.assertEqual(0, detail["dead_end_records"])
        self.assertEqual(0, detail["derived_dead_ends"])
        self.assertEqual(1, detail["falsification_branches"])
        self.assertEqual(["restricts"], detail["negative_classifications"])

    def test_dead_end_records_are_observed_when_the_fixture_produces_them(self) -> None:
        fixture, protocol = dead_end_inputs()
        p6, p5, fixture_bytes = build_bundle(fixture, protocol)
        verdict = verify_release_bundle(p6, p5, fixture_bytes)
        detail = {item["check"]: item["detail"] for item in verdict["checks"]}[
            "negative_and_superseded_attempts_observed"
        ]
        self.assertEqual(1, detail["dead_end_records"])
        self.assertEqual(1, detail["derived_dead_ends"])

    def test_unverifiable_and_not_derived_sets_are_pinned_exactly(self) -> None:
        """Silently verifying one, or adding another, must fail here.

        The two categories are distinct on purpose: `unverifiable` is a claim
        about facts outside the system's view, `not_derived` is a constant the
        release presents as a measured outcome. Collapsing them would let a
        reader treat a number carrying zero bits as evidence.
        """

        verdict = self.verify()
        self.assertEqual(
            ["semantic_fidelity", "negative_and_superseded_attempts_retained"],
            [item["field"] for item in verdict["unverifiable"]],
        )
        self.assertEqual(
            ["researcher_approved", True],
            [item["release_value"] for item in verdict["unverifiable"]],
        )
        self.assertEqual(
            ["baseline_comparison", "baseline_comparison.simplest_baseline_passed"],
            [item["field"] for item in verdict["not_derived"]],
        )
        self.assertEqual(
            [0],
            [
                item["release_value"] for item in verdict["not_derived"]
                if not isinstance(item["release_value"], dict)
            ],
        )
        self.assertEqual(
            set(),
            {item["field"] for item in verdict["unverifiable"]}
            & {item["field"] for item in verdict["not_derived"]},
        )
        for item in verdict["unverifiable"] + verdict["not_derived"]:
            self.assertTrue(item["reason"])
        for item in verdict["not_derived"]:
            self.assertIs(False, item["varies"])

    def test_no_named_gap_is_counted_as_evidence(self) -> None:
        verdict = self.verify()
        named = verdict["unverifiable"] + verdict["not_derived"]
        for item in named:
            self.assertIs(False, item["counted_as_evidence"])
        # No named gap is presented as a passing check.
        self.assertEqual(
            set(),
            {item["field"] for item in named}
            & {item["check"] for item in verdict["checks"]},
        )
        detail = self.detail("generality_controls_reexecuted", verdict)
        self.assertIs(True, detail["measures_capability"])
        self.assertIs(True, detail["positive_control_present"])

    def test_not_derived_baseline_value_does_not_gate_the_verdict(self) -> None:
        """`simplest_baseline_passed` is reported, never signed off.

        Both operands of the advertised 5-versus-0 advantage are literals, so
        there is nothing to check the baseline operand against. The verifier
        therefore still verifies a bundle whose baseline literal was changed,
        and reports the changed value -- rather than pretending it validated it.
        """

        value = self.p6()
        record_of(value, "release_package")["payload"]["baseline_comparison"][
            "simplest_baseline_passed"
        ] = 4
        verdict = self.verify(p6=reseal(value, level="release"))
        self.assertIs(True, verdict["verified"])
        reported = {
            item["field"]: item["release_value"] for item in verdict["not_derived"]
        }
        self.assertEqual(4, reported["baseline_comparison.simplest_baseline_passed"])

    def test_generality_controls_include_positive_controls_and_flipped_probes(self) -> None:
        suite = record_of(self.p6(), "generality_control_suite")["payload"]
        self.assertEqual(13, suite["controls_total"])
        self.assertEqual(["GC-01", "GC-09A"], suite["positive_control_ids"])
        self.assertTrue(suite["positive_control_admitted"])
        self.assertEqual(suite["probes_total"], suite["probes_flipped"])


# --------------------------------------------------------------------------
# side-effect freedom and the producer boundary
# --------------------------------------------------------------------------


class CleanRoomBoundaryTests(BundleCase):
    def test_verification_writes_nothing_to_a_caller_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Phase6Workspace(root) as workspace:
                phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                    PHASE5_FIXTURE, recorded_at=T0
                )
                Phase6Service(workspace).confirm(
                    protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                    phase5_run_id=phase5["run_id"], recorded_at=T1,
                )
                p6 = workspace.export_bytes()
                p5 = workspace.phase5.export_bytes()

            def snapshot() -> dict[str, bytes]:
                return {
                    str(path.relative_to(root)): path.read_bytes()
                    for path in sorted(root.rglob("*")) if path.is_file()
                }

            before = snapshot()
            self.assertTrue(before)
            verify_release_bundle(p6, p5, canonical_bytes(PHASE5_FIXTURE))
            self.assertEqual(before, snapshot())
            with Phase6Workspace(root) as reopened:
                rows = reopened.connection.execute(
                    "SELECT COUNT(*) FROM phase6_verified_exports"
                ).fetchone()[0]
            self.assertEqual(0, rows)

    def test_clean_room_is_created_and_discarded(self) -> None:
        pattern = "adaivy-phase6-replay-*"
        temporary = Path(tempfile.gettempdir())
        before = sorted(temporary.glob(pattern))
        observed: list[str] = []
        real = tempfile.TemporaryDirectory

        class Watched(real):  # type: ignore[misc,valid-type]
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)
                observed.append(self.name)

        with mock.patch.object(tempfile, "TemporaryDirectory", Watched):
            self.verify()
        self.assertEqual(1, len(observed))
        self.assertIn("adaivy-phase6-replay-", observed[0])
        self.assertFalse(Path(observed[0]).exists())
        self.assertEqual(before, sorted(temporary.glob(pattern)))

    def test_verifier_module_is_read_only_by_construction(self) -> None:
        """A static audit of executable code, not of the prose around it.

        The docstring necessarily names the producer path it exists because of,
        so a text scan would be useless. This walks the AST instead.
        """

        source = (REPO_ROOT / "src/math_research/phase6/replay.py").read_text("utf-8")
        tree = ast.parse(source)
        names: set[str] = set()
        attributes: set[str] = set()
        literals: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                attributes.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.append(node.value)
        forbidden_names = {
            "Phase6Workspace", "Phase5Workspace", "sqlite3", "open", "print",
            "connection", "durable", "cursor",
        }
        self.assertEqual(set(), names & forbidden_names)
        forbidden_attributes = {
            "save_verified_export", "execute", "executemany", "commit",
            "transaction", "unlink", "rmdir", "mkdir", "write_text",
            "rmtree", "connection", "durable", "verify_integrity",
        }
        # `append` is deliberately absent from that set: the module appends to
        # local lists. That no durable append is reachable follows from the
        # import-set assertion below, which admits no workspace module.
        self.assertEqual(set(), attributes & forbidden_attributes)
        # The only mutating filesystem call is the clean-room copy, and the
        # clean room is a context manager that removes itself.
        self.assertEqual({"write_bytes"}, attributes & {"write_bytes", "write_text"})
        self.assertEqual(1, source.count("write_bytes"))
        self.assertIn("tempfile.TemporaryDirectory", source)
        # No SQL anywhere, including the docstrings the AST also collects, apart
        # from the two prose mentions of the table this module refuses to write.
        for literal in literals:
            for statement in ("INSERT ", "UPDATE ", "DELETE ", "SELECT "):
                self.assertNotIn(statement, literal)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(("." * node.level) + (node.module or ""))
        self.assertEqual(
            set(),
            imported & {
                "sqlite3", "socket", "ssl", "urllib.request", "http.client",
                "subprocess", "..phase6.workspace", "..phase6.service",
                ".workspace", ".service",
            },
        )
        self.assertEqual(
            {"..phase5.quantum", "..phase5.serialization", ".generality", "json", "tempfile",
             "collections.abc", "pathlib", "typing", "__future__"},
            imported,
            "replay.py's import set changed; a clean-room verifier must not "
            "acquire a workspace, database, or network dependency",
        )

    def test_producer_files_are_untouched(self) -> None:
        for relative, expected in sorted(PRODUCER_DIGESTS.items()):
            digest = hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(
                expected, digest,
                f"{relative} changed; ADR-0044 claims the producer is untouched, "
                "so update the ADR and this pin in the same change",
            )

    def test_restated_producer_constants_do_not_drift(self) -> None:
        self.assertEqual(frozenset(producer.PROTOCOL_FIELDS), PROTOCOL_FIELDS)
        self.assertEqual(frozenset(producer.ALLOWED_CAPABILITIES), ALLOWED_CAPABILITIES)
        suite = record_of(self.p6(), "generality_control_suite")["payload"]
        self.assertEqual(
            list(EXPECTED_CONTROLS),
            [item["control_id"] for item in suite["controls"]],
        )
        self.assertEqual(PHASE6_EXPORT_VERSION, replay_module.PHASE6_EXPORT_VERSION)
        self.assertEqual(PHASE6_RECORD_VERSION, replay_module.PHASE6_RECORD_VERSION)
        self.assertEqual(PHASE5_EXPORT_VERSION, replay_module.PHASE5_EXPORT_VERSION)
        self.assertEqual(PHASE5_RECORD_VERSION, replay_module.PHASE5_RECORD_VERSION)
        value = self.p6()
        self.assertEqual(
            EXPECTED_RECORD_TYPES,
            tuple(item["record_type"] for item in value["records"]),
        )
        self.assertEqual(
            EXPECTED_METHOD, record_of(value, "confirmatory_run")["payload"]["method"]
        )
        self.assertEqual(
            set(replay_module.RELEASE_FIELDS),
            set(record_of(value, "release_package")["payload"]),
        )
        self.assertEqual(
            {item[0] for item in UNVERIFIABLE_FIELDS}
            | {item[0] for item in NOT_DERIVED_FIELDS},
            {
                "semantic_fidelity", "negative_and_superseded_attempts_retained",
                "baseline_comparison", "baseline_comparison.simplest_baseline_passed",
            },
        )

    def test_verify_integrity_cannot_stand_in_for_bundle_verification(self) -> None:
        """The forged export lands in a table no integrity check reads.

        ``verify_integrity`` queries ``phase6_records``; an imported export lands
        in ``phase6_verified_exports``. So the workspace reports itself intact
        while holding a forged bundle whose per-record ``content_hash`` values
        are stale. Nobody may delete the clean-room verifier believing
        ``verify_integrity`` already covers this.
        """

        value = self.p6()
        record_of(value, "confirmatory_result")["payload"]["graph_admitted"] = True
        forged = reseal(value, level="envelope")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Phase6Workspace(root) as workspace:
                phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                    PHASE5_FIXTURE, recorded_at=T0
                )
                Phase6Service(workspace).confirm(
                    protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                    phase5_run_id=phase5["run_id"], recorded_at=T1,
                )
                stored = workspace.save_verified_export(forged)
                self.assertTrue(
                    record_of(stored, "confirmatory_result")["payload"]["graph_admitted"]
                )
                # Still reports itself intact.
                workspace.verify_integrity()
                self.assertEqual(
                    1,
                    workspace.connection.execute(
                        "SELECT COUNT(*) FROM phase6_verified_exports"
                    ).fetchone()[0],
                )
        self.refuses(p6=forged, because="content hash is not derived")


# --------------------------------------------------------------------------
# tamper cases: records and identities
# --------------------------------------------------------------------------


class RecordTamperTests(BundleCase):
    def test_tampered_payload_with_stale_record_hash_is_refused(self) -> None:
        """The forgery the producer accepts today: only the envelope re-sealed."""

        value = self.p6()
        record_of(value, "confirmatory_result")["payload"]["status"] = "failed"
        self.refuses(
            p6=reseal(value, level="envelope"),
            because="content hash is not derived",
        )

    def test_tampered_payload_with_rederived_record_hash_fails_on_identity(self) -> None:
        value = self.p6()
        record_of(value, "novelty_assessment")["payload"]["limitations"] = [
            "A literature search was in fact performed."
        ]
        self.refuses(
            p6=reseal(value, level="records"),
            because="novelty assessment identity is not derived from its content",
        )

    def test_removed_record_is_refused(self) -> None:
        value = self.p6()
        value["records"] = [
            item for item in value["records"]
            if item["record_type"] != "novelty_assessment"
        ]
        self.refuses(
            p6=reseal(value, level="identities"), because="record type order differs"
        )

    def test_reordered_records_are_refused(self) -> None:
        value = self.p6()
        records = value["records"]
        records[5], records[6] = records[6], records[5]
        self.refuses(
            p6=reseal(value, level="identities"), because="record type order differs"
        )

    def test_reordered_contributions_are_refused(self) -> None:
        value = self.p6()
        records = value["records"]
        records[7], records[9] = records[9], records[7]
        self.refuses(
            p6=reseal(value, level="release"),
            because="contribution 0 is not the derived contribution",
        )

    def test_duplicate_record_id_is_refused(self) -> None:
        value = self.p6()
        value["records"].insert(6, copy.deepcopy(value["records"][5]))
        self.refuses(
            p6=reseal(value, level="records"), because="duplicate record identity"
        )

    def test_non_canonical_export_bytes_with_a_correct_hash_are_refused(self) -> None:
        pretty = json.dumps(self.p6(), indent=2, sort_keys=True).encode("utf-8")
        self.assertEqual(self.p6()["content_hash"], json.loads(pretty)["content_hash"])
        self.refuses(p6=pretty, because="is not canonical JSON bytes")

    def test_oversized_input_is_refused_before_parsing(self) -> None:
        self.refuses(p6=b"x" * (MAX_VERIFY_BYTES + 1), because="exceeds the bounded")

    def test_duplicate_json_key_and_malformed_json_are_refused(self) -> None:
        self.refuses(
            p6=b'{"schema_version":"a","schema_version":"b"}',
            because="duplicate JSON key",
        )
        self.refuses(p6=b"{not json", because="not valid UTF-8 JSON")
        self.refuses(p6=b"[]", because="must be a JSON object")
        self.refuses(p6=b'{"records":NaN}', because="non-finite number")
        self.refuses(p6=b"\xff\xfe", because="not valid UTF-8 JSON")
        deep = b'{"a":' * 40 + b"1" + b"}" * 40
        self.refuses(p6=deep, because="bounded nesting depth")


# --------------------------------------------------------------------------
# tamper cases: trust promotion and refusal invariants
# --------------------------------------------------------------------------


class RefusalInvariantTamperTests(BundleCase):
    def test_graph_admitted_flipped_true_is_refused_at_every_reseal_level(self) -> None:
        """The demonstrated defect. AGENTS.md:53-57 forbids this promotion."""

        expected = {
            # Only the envelope re-sealed: the record's own hash is stale.
            "envelope": "content hash is not derived",
            # Record hash re-sealed: the derived record identity no longer holds.
            "records": "confirmatory result identity is not derived",
            # Identities re-derived but downstream references left dangling: the
            # contribution that names the confirmatory result id diverges.
            "identities": "contribution 2 is not the derived contribution",
            # Internally perfect bundle: only the refusal invariant is left.
            "release": "may never admit its result to the trusted claim graph",
        }
        for level in RESEAL_LEVELS:
            with self.subTest(level=level):
                value = self.p6()
                record_of(value, "confirmatory_result")["payload"][
                    "graph_admitted"
                ] = True
                self.refuses(p6=reseal(value, level=level), because=expected[level])

    def test_embedded_release_result_graph_admission_is_refused(self) -> None:
        value = self.p6()
        release = record_of(value, "release_package")["payload"]
        release["confirmatory_result"]["graph_admitted"] = True
        self.refuses(
            p6=reseal(value, level="identities"),
            because="embedded confirmatory result differs from the record",
        )

    def test_novelty_status_moved_off_not_assessed_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "novelty_assessment")["payload"]["status"] = "novel"
        self.refuses(
            p6=reseal(value, level="release"),
            because="novelty must remain not_assessed",
        )

    def test_novelty_inferred_from_warrant_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "novelty_assessment")["payload"]["inferred_from_warrant"] = True
        self.refuses(
            p6=reseal(value, level="release"),
            because="never be inferred from a warrant",
        )

    def test_significance_status_changed_is_refused(self) -> None:
        value = self.p6()
        payload = record_of(value, "significance_assessment")["payload"]
        payload["status"] = "significant"
        payload["assessor_id"] = "principal.reviewer"
        self.refuses(
            p6=reseal(value, level="release"),
            because="significance must remain not_assessed",
        )

    def test_inflated_controls_passed_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "release_package")["payload"]["controls_passed"] = 6
        self.refuses(
            p6=reseal(value, level="release"),
            because="release control or probe counts are not the derived counts",
        )

    def test_extra_generality_control_is_refused(self) -> None:
        value = self.p6()
        result = record_of(value, "confirmatory_result")["payload"]
        result["generality_controls"]["controls"].append(
            copy.deepcopy(result["generality_controls"]["controls"][0])
        )
        result["generality_controls"]["controls"][-1]["control_id"] = "invented_control"
        self.refuses(
            p6=reseal(value, level="release"),
            because="confirmatory result generality suite binding differs",
        )

    def test_weakened_generality_control_is_refused(self) -> None:
        value = self.p6()
        result = record_of(value, "confirmatory_result")["payload"]
        result["generality_controls"]["controls"][0]["passed"] = False
        self.refuses(
            p6=reseal(value, level="release"),
            because="confirmatory result generality suite binding differs",
        )

    def test_heldout_accesses_above_one_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_run")["payload"]["access_manifest"][
            "access_count"
        ] = 2
        record_of(value, "release_package")["payload"]["heldout_accesses"] = 2
        self.refuses(
            p6=reseal(value, level="release"), because="must be accessed exactly once"
        )

    def test_adaptations_after_access_above_zero_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_run")["payload"]["access_manifest"][
            "adaptations_after_access"
        ] = 1
        record_of(value, "release_package")["payload"]["adaptations_after_access"] = 1
        self.refuses(
            p6=reseal(value, level="release"),
            because="adaptations after held-out access must be the integer zero",
        )

    def test_exploratory_access_during_execution_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_run")["payload"]["access_manifest"][
            "exploratory_result_access_during_execution"
        ] = True
        self.refuses(
            p6=reseal(value, level="release"),
            because="read exploratory results during execution",
        )

    def test_nonzero_model_network_and_cost_counters_are_refused(self) -> None:
        for field, phrase in (
            ("model_calls", "model calls must be the integer zero"),
            ("network_calls", "network calls must be the integer zero"),
            ("external_cost_usd", "external cost must be the integer zero"),
        ):
            with self.subTest(field=field):
                value = self.p6()
                record_of(value, "confirmatory_result")["payload"][field] = 1
                self.refuses(p6=reseal(value, level="release"), because=phrase)


# --------------------------------------------------------------------------
# tamper cases: the mathematics and the Phase 5 side of the bundle
# --------------------------------------------------------------------------


class RecomputationTamperTests(BundleCase):
    def test_case_result_hash_swapped_for_another_case_is_refused(self) -> None:
        """Proves the recomputation is real and not a tautology."""

        other = run_case(
            DiagonalCase.from_value(PHASE5_FIXTURE["cases"][0])
        )["result_hash"]
        value = self.p6()
        result = record_of(value, "confirmatory_result")["payload"]
        self.assertNotEqual(other, result["case_result_hash"])
        result["case_result_hash"] = other
        self.refuses(
            p6=reseal(value, level="release"),
            because="recomputed held-out case result hash differs",
        )

    def test_altered_phase5_fixture_is_refused(self) -> None:
        fixture = self.fixture()
        fixture["cases"][1]["iterations"] = 4
        self.refuses(
            fixture=canonical_bytes(fixture),
            because="held-out fixture hash differs from the frozen protocol",
        )

    def test_fixture_hash_is_checked_before_any_heldout_recomputation(self) -> None:
        fixture = self.fixture()
        fixture["cases"][1]["iterations"] = 4
        sentinel = RuntimeError("run_case must not be reached")
        with mock.patch.object(replay_module, "run_case", side_effect=sentinel):
            self.refuses(
                fixture=canonical_bytes(fixture),
                because="held-out fixture hash differs from the frozen protocol",
            )

    def test_wrong_but_self_consistent_phase5_export_is_refused(self) -> None:
        other_fixture, other_protocol = dead_end_inputs()
        _p6, other_p5, _fixture = build_bundle(other_fixture, other_protocol)
        # A valid, self-consistent export of a different run.
        self.assertEqual(
            json.loads(other_p5)["content_hash"],
            content_hash(json.loads(other_p5)),
        )
        # Level 1: swap the export outright.
        self.refuses(
            p5=other_p5,
            because="does not contain exactly one matching exploratory run",
        )
        # Level 2: re-point the whole Phase 6 bundle at the other export and
        # re-seal everything. The fixture binding still refuses it.
        other = json.loads(other_p5)
        other_run = [
            item for item in other["records"] if item["record_type"] == "run"
        ][0]
        value = self.p6()
        value["phase5_export_hash"] = other["content_hash"]
        record_of(value, "confirmatory_run")["payload"].update({
            "phase5_run_id": other_run["subject_id"],
            "phase5_run_hash": other_run["content_hash"],
        })
        release = record_of(value, "release_package")["payload"]
        release["phase5_export_hash"] = other["content_hash"]
        release["material_result_count"] = len(other["material_results"])
        self.refuses(
            p6=reseal(value, level="release"), p5=other_p5,
            because="exploratory run used another fixture",
        )

    def test_phase5_export_hash_disagreement_is_refused(self) -> None:
        value = self.p6()
        value["phase5_export_hash"] = "sha256:" + "0" * 64
        self.refuses(
            p6=reseal(value, level="release"),
            because="Phase 6 export cites a different Phase 5 export",
        )

    def test_emptied_phase5_material_results_are_refused(self) -> None:
        phase5 = self.p5()
        phase5["material_results"] = []
        p5 = reseal_phase5(phase5)
        digest = json.loads(p5)["content_hash"]
        value = self.p6()
        value["phase5_export_hash"] = digest
        release = record_of(value, "release_package")["payload"]
        release["phase5_export_hash"] = digest
        release["material_result_count"] = 0
        self.refuses(
            p6=reseal(value, level="release"), p5=p5,
            because="requires a non-empty Phase 5 material-result trace",
        )

    def test_inflated_material_result_count_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "release_package")["payload"]["material_result_count"] = 7
        self.refuses(
            p6=reseal(value, level="release"),
            because="material-result count differs from the Phase 5 material-result trace",
        )

    def test_stripped_dead_end_records_are_refused(self) -> None:
        fixture, protocol = dead_end_inputs()
        p6_bytes, p5_bytes, fixture_bytes = build_bundle(fixture, protocol)
        phase5 = json.loads(p5_bytes)
        self.assertEqual(
            1, sum(1 for item in phase5["records"] if item["record_type"] == "dead_end")
        )
        phase5["records"] = [
            item for item in phase5["records"] if item["record_type"] != "dead_end"
        ]
        stripped = reseal_phase5(phase5)
        digest = json.loads(stripped)["content_hash"]
        value = json.loads(p6_bytes)
        value["phase5_export_hash"] = digest
        record_of(value, "release_package")["payload"]["phase5_export_hash"] = digest
        with self.assertRaises(Phase6ReplayError) as caught:
            verify_release_bundle(
                reseal(value, level="release"), stripped, fixture_bytes
            )
        self.assertIn(
            "retained dead-end records are not the dead ends", str(caught.exception)
        )

    def test_forged_dead_end_record_is_refused(self) -> None:
        phase5 = self.p5()
        branch = [
            item for item in phase5["records"] if item["record_type"] == "branch"
        ][0]
        phase5["records"].append({
            "schema_version": PHASE5_RECORD_VERSION,
            "record_id": "dead-end.forged",
            "record_type": "dead_end",
            "subject_id": branch["subject_id"],
            "sequence": len(phase5["records"]),
            "recorded_at": T0,
            "payload": {
                "run_id": branch["payload"]["run_id"],
                "branch_id": branch["subject_id"],
                "reason": "duplicate exact semantic result",
            },
            "content_hash": "sha256:" + "0" * 64,
        })
        forged = reseal_phase5(phase5)
        digest = json.loads(forged)["content_hash"]
        value = self.p6()
        value["phase5_export_hash"] = digest
        record_of(value, "release_package")["payload"]["phase5_export_hash"] = digest
        self.refuses(
            p6=reseal(value, level="release"), p5=forged,
            because="identity is not derived from its content",
        )


# --------------------------------------------------------------------------
# tamper cases: release package and protocol
# --------------------------------------------------------------------------


class ReleaseAndProtocolTamperTests(BundleCase):
    def test_altered_release_hash_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "release_package")["payload"]["release_hash"] = (
            "sha256:" + "1" * 64
        )
        self.refuses(
            p6=reseal(value, level="records"),
            because="release hash is not derived from the release package",
        )

    def test_stale_release_hash_is_refused(self) -> None:
        value = self.p6()
        release = record_of(value, "release_package")["payload"]
        release["semantic_fidelity"] = "peer_reviewed"
        # `release_hash` deliberately left at its pre-mutation value.
        self.refuses(
            p6=reseal(value, level="records"),
            because="release hash is not derived from the release package",
        )

    def test_release_embedded_result_diverging_from_the_record_is_refused(self) -> None:
        value = self.p6()
        release = record_of(value, "release_package")["payload"]
        release["confirmatory_result"]["status"] = "failed"
        self.refuses(
            p6=reseal(value, level="identities"),
            because="embedded confirmatory result differs from the record",
        )

    def test_release_embedded_contributions_diverging_are_refused(self) -> None:
        value = self.p6()
        release = record_of(value, "release_package")["payload"]
        release["contributions"][1]["artifact_id"] = "sha256:" + "2" * 64
        self.refuses(
            p6=reseal(value, level="identities"),
            because="embedded contributions differ from the records",
        )

    def test_inconsistent_protocol_hash_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_protocol")["payload"]["protocol_hash"] = (
            "sha256:" + "3" * 64
        )
        self.refuses(
            p6=reseal(value, level="records"),
            because="protocol hash is not derived from the embedded protocol",
        )

    def test_release_protocol_hash_disagreement_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "release_package")["payload"]["protocol_hash"] = (
            "sha256:" + "4" * 64
        )
        self.refuses(
            p6=reseal(value, level="identities"),
            because="release protocol binding differs from the protocol record",
        )

    def test_retroactively_loosened_protocol_is_refused(self) -> None:
        cases = {
            "01_extra_field": (
                {"unreviewed_extension": True},
                "confirmatory protocol field set differs",
            ),
            "02_expanded_capabilities": (
                {
                    "allowed_capabilities": sorted(ALLOWED_CAPABILITIES)
                    + ["read_exploratory_results"]
                },
                "capability boundary differs from the frozen allowlist",
            ),
            "03_two_heldout_cases": (
                {
                    "heldout_case_ids": [
                        "qd-fs-01-orthogonal-2d", "qd-fs-01-scalar-full-support",
                    ]
                },
                "requires exactly one frozen held-out case",
            ),
            "04_changed_stopping_rule": (
                {"stopping_rule": "adapt_until_passed"},
                "unsupported or unfrozen confirmatory protocol",
            ),
            "05_changed_schema_version": (
                {"schema_version": "adaivy.confirmatory-protocol.v2"},
                "unsupported or unfrozen confirmatory protocol",
            ),
            "06_changed_phase": (
                {"phase": "exploratory"},
                "unsupported or unfrozen confirmatory protocol",
            ),
            "07_frozen_after_execution": (
                {"frozen_at": "2026-08-21T00:00:00Z"},
                "must be frozen before execution",
            ),
            "08_changed_benchmark": (
                {"benchmark_id": "QD-FS-02"},
                "unsupported or unfrozen confirmatory protocol",
            ),
        }
        for name, (mutation, phrase) in sorted(cases.items()):
            with self.subTest(mutation=name):
                value = self.p6()
                record_of(value, "confirmatory_protocol")["payload"][
                    "protocol"
                ].update(mutation)
                self.refuses(p6=reseal(value, level="release"), because=phrase)

    def test_unfrozen_protocol_flag_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_protocol")["payload"]["frozen"] = False
        self.refuses(p6=reseal(value, level="release"), because="not marked frozen")

    def test_altered_execution_method_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_run")["payload"]["method"]["arithmetic"] = (
            "floating-point"
        )
        self.refuses(
            p6=reseal(value, level="release"),
            because="confirmatory execution method differs",
        )

    def test_unknown_release_field_is_refused(self) -> None:
        value = self.p6()
        record_of(value, "release_package")["payload"]["peer_reviewed"] = True
        self.refuses(
            p6=reseal(value, level="release"),
            because="release package field set differs",
        )


# --------------------------------------------------------------------------
# CLI surface
# --------------------------------------------------------------------------


class CleanRoomCliTests(BundleCase):
    def _run(self, argv: list[str]) -> tuple[int, dict]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = phase6_cli.main(argv)
        return code, json.loads(stream.getvalue())

    def _paths(self, root: Path, p6: bytes | None = None) -> list[str]:
        (root / "p6.json").write_bytes(self.p6_bytes if p6 is None else p6)
        (root / "p5.json").write_bytes(self.p5_bytes)
        (root / "fx.json").write_bytes(self.fixture_bytes)
        return [str(root / "p6.json"), str(root / "p5.json"), str(root / "fx.json")]

    def test_verify_subcommand_verifies_a_genuine_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, verdict = self._run(["verify", *self._paths(Path(directory))])
        self.assertEqual(0, code)
        self.assertIs(True, verdict["verified"])

    def test_verify_subcommand_reports_a_rejection_as_machine_readable_output(self) -> None:
        value = self.p6()
        record_of(value, "confirmatory_result")["payload"]["graph_admitted"] = True
        with tempfile.TemporaryDirectory() as directory:
            code, verdict = self._run([
                "verify", *self._paths(Path(directory), reseal(value, level="release")),
            ])
        self.assertEqual(1, code)
        self.assertIs(False, verdict["verified"])
        self.assertIn("trusted claim graph", verdict["rejection"])

    def test_replay_subcommand_still_ingests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "p6.json"
            path.write_bytes(self.p6_bytes)
            code, summary = self._run(["replay", str(root / "workspace"), str(path)])
        self.assertEqual(0, code)
        self.assertEqual(11, summary["records"])


if __name__ == "__main__":
    unittest.main()
