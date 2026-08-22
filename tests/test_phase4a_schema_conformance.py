from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from math_research.phase4a.interchange import build_envelope
from math_research.phase4a.records import (
    ActorKind, DisclosureKind, Processor, RightsReason, RightsUse, RightsValue,
)
from math_research.phase4a.service import Phase4Service
from math_research.phase4a.validation import (
    Phase4ValidationError, schema_path, validate_schema_contract, validate_structure,
)
from math_research.phase4a.workspace import Phase4Workspace

HAS_ORACLE = importlib.util.find_spec("jsonschema") is not None
T0 = "2026-08-20T00:00:00Z"
# ADR-0064. The oracle envelope carries one disclosing decision with a named
# processor, so the new field round-trips through the real Draft 2020-12
# validator and not only through the hand-written closed-envelope checker.
ORACLE_PROCESSOR = Processor(
    processor_id="processor.azure-openai.text-embedding-3-large",
    provider="azure_openai", model_identifier="text-embedding-3-large",
    disclosure_kind=DisclosureKind.TEXT_LEAVES_PROCESS,
)
STABLE_AGGREGATE = "sha256:3965809035292ae610ebf483ea2600a7b216a12dffc7679ca3e9d1857a8debfb"
HISTORICAL_AGGREGATE = "sha256:cab6d6fb718af616c7be919a147799bc4eadf3a508e547eb6b83acc7ae83d5e5"
EXCLUSIONS = [
    ("reports/.DS_Store", "host_generated_macos_directory_metadata"),
    ("reports/phase-2/.DS_Store", "host_generated_macos_directory_metadata"),
    ("reports/phase-3a/acceptance-v1/workspace.sqlite3-shm", "transient_sqlite_shared_memory_index"),
    ("reports/phase-3a/acceptance-v1/workspace.sqlite3-wal", "lifecycle_dependent_sqlite_transaction_sidecar"),
]


def _manifest_hash(value: dict[str, object]) -> str:
    preimage = copy.deepcopy(value)
    preimage["content_hash"] = "sha256:" + "0" * 64
    data = json.dumps(preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _verify_protected_manifest(
    value: dict[str, object], loader: Callable[[str], bytes],
) -> None:
    if set(value) != {"schema_version", "profile", "derivation", "stable_object_count", "stable_objects", "aggregation", "content_hash"}:
        raise ValueError("manifest fields differ")
    if value["schema_version"] != "adaivy.phase4a-protected-evidence.v2" or value["profile"] != "phase4a-stable-protected-evidence-v2":
        raise ValueError("manifest version/profile differs")
    if value["content_hash"] != _manifest_hash(value):
        raise ValueError("manifest content hash differs")
    derivation = value["derivation"]
    if not isinstance(derivation, dict) or set(derivation) != {"source_profile", "historical_object_count", "historical_aggregate_sha256", "excluded_objects"}:
        raise ValueError("manifest derivation differs")
    if derivation["source_profile"] != "phase4-entry-gate-historical-protected-evidence-v1" or derivation["historical_object_count"] != 199 or derivation["historical_aggregate_sha256"] != HISTORICAL_AGGREGATE:
        raise ValueError("historical manifest identity differs")
    exclusions = derivation["excluded_objects"]
    if not isinstance(exclusions, list) or [(item.get("path"), item.get("reason")) for item in exclusions if isinstance(item, dict)] != EXCLUSIONS:
        raise ValueError("volatile exclusions differ")
    entries = value["stable_objects"]
    if not isinstance(entries, list) or value["stable_object_count"] != 195 or len(entries) != 195:
        raise ValueError("stable entry count differs")
    if len(entries) + len(exclusions) != derivation["historical_object_count"]:
        raise ValueError("stable derivation count differs")
    paths: list[str] = []
    lines: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("stable entry fields differ")
        path, expected = item["path"], item["sha256"]
        if not isinstance(path, str) or not isinstance(expected, str):
            raise ValueError("stable entry types differ")
        if not path.startswith("reports/") or path.startswith("/") or "//" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ValueError("stable path is not normalized")
        if path.endswith("/.DS_Store") or path.endswith("-wal") or path.endswith("-shm"):
            raise ValueError("volatile artifact entered stable manifest")
        observed = "sha256:" + hashlib.sha256(loader(path)).hexdigest()
        if observed != expected:
            raise ValueError("stable object bytes differ")
        paths.append(path)
        lines.append(f"{expected.removeprefix('sha256:')}  {path}\n")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("stable paths are unsorted or duplicated")
    aggregation = value["aggregation"]
    if not isinstance(aggregation, dict) or set(aggregation) != {"algorithm", "line_format", "ordering", "aggregate_sha256"}:
        raise ValueError("aggregation fields differ")
    observed_aggregate = "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    if aggregation["algorithm"] != "sha256_utf8_sorted_path_lines_v1" or aggregation["aggregate_sha256"] != STABLE_AGGREGATE or observed_aggregate != STABLE_AGGREGATE:
        raise ValueError("stable aggregate differs")


class Phase4SchemaContractTests(unittest.TestCase):
    def test_schema_digest_and_unsupported_keyword_fail_closed(self) -> None:
        digest = validate_schema_contract()
        self.assertTrue(digest.startswith("sha256:"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            value = json.loads(schema_path().read_text(encoding="utf-8"))
            value["unevaluatedProperties"] = False
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(Phase4ValidationError):
                validate_schema_contract(path)

    def test_production_import_graph_has_no_gate_validator_packages(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "src"
        text = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))
        for package in ("jsonschema", "attrs", "referencing", "rpds"):
            self.assertNotIn(f"import {package}", text)
            self.assertNotIn(f"from {package}", text)

        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "reports/phase-4a-production/protected-evidence-v2.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        loader = lambda path: (root / path).read_bytes()
        _verify_protected_manifest(manifest, loader)

        first_path = manifest["stable_objects"][0]["path"]
        mutation_loaders = (
            lambda path: (_ for _ in ()).throw(FileNotFoundError(path)) if path == first_path else loader(path),
            lambda path: b"tampered" if path == first_path else loader(path),
        )
        for changed_loader in mutation_loaders:
            with self.assertRaises((FileNotFoundError, ValueError)):
                _verify_protected_manifest(manifest, changed_loader)

        mutations: list[dict[str, object]] = []
        extra = copy.deepcopy(manifest); extra["stable_objects"].append({"path": "reports/extra", "sha256": "sha256:" + "0" * 64}); mutations.append(extra)
        duplicate = copy.deepcopy(manifest); duplicate["stable_objects"][-1] = copy.deepcopy(duplicate["stable_objects"][0]); mutations.append(duplicate)
        nonnormalized = copy.deepcopy(manifest); nonnormalized["stable_objects"][0]["path"] = "reports/phase-0/../phase-0/results.json"; mutations.append(nonnormalized)
        altered_exclusion = copy.deepcopy(manifest); altered_exclusion["derivation"]["excluded_objects"][0]["reason"] = "changed"; mutations.append(altered_exclusion)
        volatile = copy.deepcopy(manifest); volatile["stable_objects"][0]["path"] = "reports/.DS_Store"; mutations.append(volatile)
        for mutation in mutations:
            mutation["content_hash"] = _manifest_hash(mutation)
            with self.assertRaises((FileNotFoundError, ValueError)):
                _verify_protected_manifest(mutation, loader)


@unittest.skipUnless(HAS_ORACLE, "run separately in the approved offline jsonschema oracle environment")
class Phase4DifferentialConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from jsonschema import Draft202012Validator

        cls.schema = json.loads(schema_path().read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.oracle = Draft202012Validator(cls.schema)
        cls.temp = tempfile.TemporaryDirectory()
        with Phase4Workspace(Path(cls.temp.name) / "workspace") as workspace:
            service = Phase4Service(workspace)
            service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
            source_id = "source.schema-oracle"
            for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING, RightsUse.EXCERPTING):
                service.append_rights(
                    source_id=source_id, intended_use=use, value=RightsValue.ALLOWED,
                    reason_code=RightsReason.PERMITTED, reason_detail="schema oracle right",
                    evidence_refs=(f"evidence.oracle-{use.value.replace('_', '-')}",), actor_id="actor.owner",
                    valid_from=T0, valid_until=None, recorded_at=T0,
                    lifecycle_id=f"rights-lifecycle.oracle-{use.value}",
                )
            service.append_rights(
                source_id=source_id, intended_use=RightsUse.EMBEDDING, value=RightsValue.ALLOWED,
                reason_code=RightsReason.PERMITTED, reason_detail="schema oracle embedding right",
                evidence_refs=("evidence.oracle-embedding",), actor_id="actor.owner",
                valid_from=T0, valid_until=None, recorded_at=T0,
                lifecycle_id="rights-lifecycle.oracle-embedding", processor=ORACLE_PROCESSOR,
            )
            source = Path(cls.temp.name) / "oracle.txt"; source.write_text("oracle statement\n", encoding="utf-8")
            service.intake_local(source, source_id=source_id, actor_id="actor.operator", recorded_at=T0)
            service.create_evidence_card(
                source_id=source_id, span_byte_ranges=((0, 16),), bibliographic_identity="Oracle fixture",
                imported_statement="oracle statement", hypotheses=("h",), definitions=("d",),
                scope=("s",), exceptions=(), actor_id="actor.curator", actor_kind=ActorKind.HUMAN,
                reason_detail="schema numeric coverage", recorded_at=T0,
            )
            cls.valid = build_envelope(workspace.records(), exported_at=T0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def assert_agrees(self, value: object) -> None:
        oracle_accepts = not tuple(self.oracle.iter_errors(value))
        try:
            validate_structure(copy.deepcopy(value))
            production_accepts = True
        except Phase4ValidationError:
            production_accepts = False
        self.assertEqual(oracle_accepts, production_accepts)

    def test_valid_and_independent_structural_mutations_agree(self) -> None:
        self.assert_agrees(self.valid)
        mutations = []

        def changed(function):
            value = copy.deepcopy(self.valid); function(value); mutations.append(value)

        changed(lambda value: value.__setitem__("unknown", 1))
        changed(lambda value: value.pop("profile"))
        changed(lambda value: value.__setitem__("profile", "phase4-review-v2"))
        changed(lambda value: value["policy_versions"].append("unknown"))
        changed(lambda value: value["records"][0].__setitem__("unknown", 1))
        changed(lambda value: value["records"][0].pop("actor_id"))
        changed(lambda value: value["records"][0].__setitem__("sequence", True))
        changed(lambda value: value["records"][0].__setitem__("record_type", "unknown"))
        changed(lambda value: value["records"][0].__setitem__("payload", {"source_id": "source.x"}))
        changed(lambda value: value["operational"].__setitem__("elapsed_milliseconds", True))
        changed(lambda value: value["operational"].__setitem__("external_cost_usd", 1))
        changed(lambda value: value["operational"]["source_path_hashes"].__setitem__("Bad ID", "sha256:" + "0" * 64))
        changed(lambda value: value["records"].extend(copy.deepcopy(value["records"][0]) for _ in range(256)))
        for value in mutations:
            self.assert_agrees(value)

    def _rights_index(self, intended_use: str) -> int:
        return next(
            index for index, record in enumerate(self.valid["records"])
            if record["record_type"] == "source_rights_decision"
            and record["payload"]["intended_use"] == intended_use
        )

    def test_adr_0061_processor_mutations_are_refused_by_both_validators(self) -> None:
        """The new field round-trips, and every one-field mutation of it refuses.

        Agreement alone would be satisfied by two validators that both accept,
        so the oracle is asserted to REJECT each mutation and the closed-envelope
        checker is then asserted to agree.
        """

        self.assert_agrees(self.valid)
        self.assertEqual([], list(self.oracle.iter_errors(self.valid)))
        embedding = self._rights_index("embedding")
        acquisition = self._rights_index("acquisition")
        authorized = copy.deepcopy(self.valid["records"][embedding]["payload"]["processor"])
        self.assertEqual(
            {"processor_id", "provider", "model_identifier", "disclosure_kind"}, set(authorized),
        )
        mutations: list[Callable[[dict], None]] = [
            lambda value: value["records"][embedding]["payload"].pop("processor"),
            lambda value: value["records"][embedding]["payload"].__setitem__("processor", None),
            lambda value: value["records"][embedding]["payload"]["processor"].__setitem__("region", "eastus"),
            lambda value: value["records"][embedding]["payload"]["processor"].pop("provider"),
            lambda value: value["records"][embedding]["payload"]["processor"].__setitem__("provider", "not-a-real-provider"),
            lambda value: value["records"][embedding]["payload"]["processor"].__setitem__("model_identifier", ""),
            lambda value: value["records"][embedding]["payload"]["processor"].__setitem__("disclosure_kind", "text_maybe_leaves"),
            lambda value: value["records"][embedding]["payload"]["processor"].__setitem__("processor_id", "Not An Id"),
            lambda value: value["records"][acquisition]["payload"].__setitem__("processor", copy.deepcopy(authorized)),
            lambda value: value["records"][acquisition]["payload"].pop("processor"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                value = copy.deepcopy(self.valid)
                mutate(value)
                self.assertTrue(
                    tuple(self.oracle.iter_errors(value)),
                    "the Draft 2020-12 oracle accepted a processor mutation",
                )
                self.assert_agrees(value)

    def test_all_used_schema_keywords_are_exercised(self) -> None:
        seen: set[str] = set()

        def walk(value: object, *, property_map: bool = False) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if not property_map:
                        seen.add(key)
                    walk(child, property_map=key in {"properties", "$defs"})
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(self.schema)
        expected = {
            "$schema", "$id", "$defs", "$ref", "title", "type", "additionalProperties",
            "required", "properties", "const", "enum", "items", "minItems", "maxItems",
            "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
            "oneOf", "allOf", "if", "then", "maxProperties", "propertyNames",
        }
        self.assertEqual(expected, seen)

    def test_booleans_are_rejected_for_every_numeric_field(self) -> None:
        locations: list[tuple[str, ...]] = [
            ("operational", "external_cost_usd"),
            ("operational", "elapsed_milliseconds"),
        ]
        for index, record in enumerate(self.valid["records"]):
            locations.append(("records", str(index), "sequence"))
            if record["record_type"] == "source_provenance":
                locations.append(("records", str(index), "payload", "byte_length"))
            if record["record_type"] == "evidence_card":
                for field in (
                    "bibliographic_identity_bytes", "imported_statement_bytes", "hypotheses_count",
                    "definitions_count", "scope_count", "exceptions_count",
                ):
                    locations.append(("records", str(index), "payload", field))
                locations.extend(("records", str(index), "payload", "span_byte_ranges", "0", field) for field in ("start", "end"))
        for location in locations:
            for boolean in (False, True):
                with self.subTest(location=location, boolean=boolean):
                    value = copy.deepcopy(self.valid)
                    cursor: object = value
                    for item in location[:-1]:
                        cursor = cursor[int(item)] if isinstance(cursor, list) else cursor[item]
                    if isinstance(cursor, list):
                        cursor[int(location[-1])] = boolean
                    else:
                        cursor[location[-1]] = boolean
                    self.assertTrue(tuple(self.oracle.iter_errors(value)))
                    self.assert_agrees(value)


if __name__ == "__main__":
    unittest.main()
