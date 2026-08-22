"""ADR-0069 partition keys, quantization, and the content-hashed artifact store."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from math_research.embedding.authoring import author_partition, load_authoring_spec
from math_research.embedding.constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
    FIXTURE_SYNTHETIC_PROVIDER,
    NORMALIZATION_SCHEMES,
)
from math_research.embedding.errors import (
    ArtifactHashMismatchError,
    ArtifactMissingError,
    ArtifactOverwriteRefused,
    CoordinateSaturatedError,
    DocumentAbsentError,
    FixtureProviderNotIngestibleError,
    ManifestHashMismatchError,
    ManifestKeyMismatchError,
    NonIntegerCoordinateError,
    PartitionAbsentError,
    PartitionKeyError,
    PartitionSchemaError,
)
from math_research.embedding.partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    ARTIFACT_SCHEMA_VERSION,
    DEFAULT_HASH_RULE,
    HASH_RULE_POP,
    HASH_RULE_SET_NULL,
    MANIFEST_FILENAME,
    PARTITION_SCHEMA_VERSION,
    PartitionKey,
    artifact_relative_path,
    create_vector_artifact,
    load_partition,
    write_partition,
    write_vector_artifact,
)
from math_research.embedding.quantization import (
    quantize,
    quantize_coordinate,
    round_half_even,
    scale_exponent,
)
from math_research.embedding.readpath import (
    READ_PATH_MODULES,
    sweep_read_path,
    sweep_source,
)
from math_research.embedding.replay import replay_partition

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "fixtures/embedding/fixture-synthetic-partition-v1.json"
SCALE = 1 << 30


def _key(
    *, provider: str = FIXTURE_SYNTHETIC_PROVIDER,
    model_identifier: str = "project-authored-v1", dimension: int = 3,
    normalization: str = "round_half_even_scale_2p30",
) -> PartitionKey:
    return PartitionKey(
        provider=provider, model_identifier=model_identifier,
        dimension=dimension, normalization=normalization,
    )


def _artifact(key: PartitionKey, document_id: str, coordinates: tuple[int, ...], **kwargs):
    return create_vector_artifact(
        key, document_id=document_id,
        source_content_hash="sha256:" + "0" * 64,
        coordinates=coordinates, **kwargs,
    )


class TemporaryRootMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="adaivy-embedding-test.")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)


class PartitionKeyTests(unittest.TestCase):
    def test_key_string_is_the_four_component_tuple(self) -> None:
        key = _key(provider="openai", model_identifier="text-embedding-3-small",
                   dimension=1536)
        self.assertEqual(
            key.key_string(),
            "openai~text-embedding-3-small~d1536~round_half_even_scale_2p30",
        )

    def test_key_string_is_injective_over_the_four_components(self) -> None:
        seen: dict[str, tuple] = {}
        for provider in ("openai", "azure_openai", FIXTURE_SYNTHETIC_PROVIDER):
            for model in ("model-a", "model-b", "model-a-d8"):
                for dimension in (8, 16):
                    for normalization in sorted(NORMALIZATION_SCHEMES):
                        key = PartitionKey(
                            provider=provider, model_identifier=model,
                            dimension=dimension, normalization=normalization,
                        )
                        components = (provider, model, dimension, normalization)
                        rendered = key.key_string()
                        self.assertNotIn(
                            rendered, seen,
                            f"{components} collides with {seen.get(rendered)}",
                        )
                        seen[rendered] = components

    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(PartitionKeyError):
            _key(provider="acme_vectors")

    def test_unknown_normalization_is_refused(self) -> None:
        with self.assertRaises(PartitionKeyError):
            _key(normalization="l2_float64")

    def test_model_identifier_must_be_path_safe_and_lowercase(self) -> None:
        for candidate in ("Text-Embedding-3", "../escape", "a/b", "", "x" * 200):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PartitionKeyError):
                    _key(model_identifier=candidate)

    def test_fixture_synthetic_forces_project_authored(self) -> None:
        self.assertEqual(
            _key().required_corpus_provenance(), CORPUS_PROVENANCE_PROJECT_AUTHORED,
        )
        self.assertEqual(
            _key(provider="openai", model_identifier="m1").required_corpus_provenance(),
            CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
        )

    def test_coordinate_limit_is_the_declared_power_of_two(self) -> None:
        self.assertEqual(_key().coordinate_limit, SCALE)
        self.assertEqual(_key(normalization="round_half_even_scale_2p20").coordinate_limit,
                         1 << 20)


class QuantizationTests(unittest.TestCase):
    def test_round_half_even_on_exact_rationals(self) -> None:
        cases = {
            Fraction(1, 2): 0, Fraction(3, 2): 2, Fraction(5, 2): 2,
            Fraction(7, 2): 4, Fraction(-1, 2): 0, Fraction(-3, 2): -2,
            Fraction(-5, 2): -2, Fraction(2, 5): 0, Fraction(3, 5): 1,
            Fraction(-3, 5): -1, Fraction(0): 0, Fraction(4): 4,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(round_half_even(value), expected)

    def test_quantization_is_exact_scaling_of_the_double(self) -> None:
        exponent = scale_exponent("round_half_even_scale_2p30")
        for value in (0.5, 0.25, -0.125, 0.0, 1.0, -1.0, 0.1, -0.3):
            with self.subTest(value=value):
                self.assertEqual(
                    quantize_coordinate(value, normalization="round_half_even_scale_2p30"),
                    round_half_even(Fraction(value) * (1 << exponent)),
                )

    def test_boundary_magnitude_is_in_range(self) -> None:
        vector = quantize((1.0, -1.0), normalization="round_half_even_scale_2p30")
        self.assertEqual(vector.coordinates, (SCALE, -SCALE))
        self.assertEqual(vector.saturated_coordinate_count, 0)

    def test_strictly_above_the_scale_halts(self) -> None:
        for value in (1.0000001, -1.5, 2.0):
            with self.subTest(value=value):
                with self.assertRaises(CoordinateSaturatedError) as caught:
                    quantize((0.5, value), normalization="round_half_even_scale_2p30")
                self.assertEqual(caught.exception.code, "coordinate_saturated")

    def test_non_finite_and_non_real_are_refused(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(CoordinateSaturatedError):
                    quantize((value,), normalization="round_half_even_scale_2p30")
        with self.assertRaises(CoordinateSaturatedError):
            quantize(("0.5",), normalization="round_half_even_scale_2p30")

    def test_scale_change_changes_the_integers(self) -> None:
        coarse = quantize((0.5,), normalization="round_half_even_scale_2p20")
        fine = quantize((0.5,), normalization="round_half_even_scale_2p30")
        self.assertNotEqual(coarse.coordinates, fine.coordinates)


class ArtifactStoreTests(TemporaryRootMixin):
    def test_write_then_load_reproduces_the_manifest_hash(self) -> None:
        key = _key()
        partition = write_partition(
            self.root, key,
            [_artifact(key, "alpha", (1, 2, 3)), _artifact(key, "beta", (3, 2, 1))],
        )
        replayed = load_partition(self.root, key)
        self.assertEqual(replayed.manifest_hash, partition.manifest_hash)
        self.assertEqual(replayed.document_ids(), ("alpha", "beta"))
        self.assertEqual(replayed.vector("alpha").coordinates, (1, 2, 3))

    def test_document_ids_are_sorted_regardless_of_input_order(self) -> None:
        key = _key()
        artifacts = [
            _artifact(key, "zulu", (1, 0, 0)), _artifact(key, "alpha", (0, 1, 0)),
            _artifact(key, "mike", (0, 0, 1)),
        ]
        first = write_partition(self.root, key, artifacts)
        other = Path(self._temporary.name).joinpath("second")
        second = write_partition(other, key, list(reversed(artifacts)))
        self.assertEqual(first.document_ids(), ("alpha", "mike", "zulu"))
        self.assertEqual(first.manifest_hash, second.manifest_hash)

    def test_absent_document_raises(self) -> None:
        key = _key()
        partition = write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        with self.assertRaises(DocumentAbsentError):
            partition.vector("missing")

    def test_absent_partition_never_falls_back(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        with self.assertRaises(PartitionAbsentError):
            load_partition(self.root, _key(model_identifier="project-authored-v2"))

    def test_identical_artifact_bytes_are_idempotent(self) -> None:
        key = _key()
        artifact = _artifact(key, "alpha", (1, 2, 3))
        path = write_vector_artifact(self.root, key, artifact)
        before = path.read_bytes()
        write_vector_artifact(self.root, key, artifact)
        self.assertEqual(path.read_bytes(), before)

    def test_different_artifact_bytes_are_refused(self) -> None:
        key = _key()
        write_vector_artifact(self.root, key, _artifact(key, "alpha", (1, 2, 3)))
        with self.assertRaises(ArtifactOverwriteRefused):
            write_vector_artifact(self.root, key, _artifact(key, "alpha", (1, 2, 4)))

    def test_manifest_overwrite_with_different_bytes_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        with self.assertRaises(ArtifactOverwriteRefused):
            write_partition(
                self.root, key,
                [_artifact(key, "alpha", (1, 2, 3)), _artifact(key, "beta", (0, 0, 1))],
            )

    def test_tampered_coordinate_is_detected(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(artifact_relative_path("alpha"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["coordinates"] = [1, 2, 4]
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with self.assertRaises(ArtifactHashMismatchError):
            load_partition(self.root, key)

    def test_tampered_manifest_is_detected(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(MANIFEST_FILENAME)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["vector_count"] = 2
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with self.assertRaises(ManifestHashMismatchError):
            load_partition(self.root, key)

    def test_missing_artifact_fails_closed(self) -> None:
        key = _key()
        write_partition(
            self.root, key,
            [_artifact(key, "alpha", (1, 2, 3)), _artifact(key, "beta", (3, 2, 1))],
        )
        key.directory(self.root).joinpath(artifact_relative_path("beta")).unlink()
        with self.assertRaises(ArtifactMissingError):
            load_partition(self.root, key)

    def test_artifact_moved_between_partitions_is_refused(self) -> None:
        key = _key()
        other = _key(model_identifier="project-authored-v2")
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        write_partition(self.root, other, [_artifact(other, "alpha", (1, 2, 3))])
        source = key.directory(self.root).joinpath(artifact_relative_path("alpha"))
        target = other.directory(self.root).joinpath(artifact_relative_path("alpha"))
        target.write_bytes(source.read_bytes())
        with self.assertRaises(ManifestKeyMismatchError):
            load_partition(self.root, other)

    def test_manifest_declaring_another_key_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        other = _key(model_identifier="project-authored-v2")
        other.directory(self.root).mkdir(parents=True, exist_ok=True)
        other.directory(self.root).joinpath(MANIFEST_FILENAME).write_bytes(
            key.directory(self.root).joinpath(MANIFEST_FILENAME).read_bytes()
        )
        with self.assertRaises(ManifestKeyMismatchError):
            load_partition(self.root, other)

    def test_decimal_coordinate_on_the_read_path_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(artifact_relative_path("alpha"))
        raw = path.read_text(encoding="utf-8").replace("[1,2,3]", "[1.5,2,3]")
        path.write_text(raw, encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_partition(self.root, key)

    def test_unknown_artifact_field_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(artifact_relative_path("alpha"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["provider_score"] = "x"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_partition(self.root, key)

    def test_duplicate_json_key_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(MANIFEST_FILENAME)
        raw = path.read_text(encoding="utf-8")
        raw = raw.replace('{"', '{"vector_count":1,"', 1)
        path.write_text(raw, encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_partition(self.root, key)

    def test_coordinate_above_the_declared_scale_is_refused(self) -> None:
        key = _key()
        with self.assertRaises(CoordinateSaturatedError):
            _artifact(key, "alpha", (SCALE + 1, 0, 0))
        boundary = _artifact(key, "alpha", (SCALE, -SCALE, 0))
        self.assertEqual(boundary.coordinates, (SCALE, -SCALE, 0))

    def test_non_integer_coordinate_is_refused(self) -> None:
        key = _key()
        with self.assertRaises(NonIntegerCoordinateError):
            _artifact(key, "alpha", (1, 2, True))

    def test_dimension_must_match_the_partition_key(self) -> None:
        key = _key()
        with self.assertRaises(PartitionSchemaError):
            _artifact(key, "alpha", (1, 2))


class ArtifactKindTests(TemporaryRootMixin):
    def test_document_and_query_share_one_partition(self) -> None:
        key = _key()
        partition = write_partition(self.root, key, [
            _artifact(key, "doc-one", (1, 2, 3)),
            _artifact(key, "query-one", (3, 2, 1), artifact_kind=ARTIFACT_KIND_QUERY),
        ])
        self.assertEqual(partition.document_ids(), ("doc-one", "query-one"))
        self.assertEqual(partition.corpus_document_ids(), ("doc-one",))
        self.assertEqual(partition.query_ids(), ("query-one",))
        self.assertEqual(
            partition.artifact_kinds(),
            {"doc-one": ARTIFACT_KIND_DOCUMENT, "query-one": ARTIFACT_KIND_QUERY},
        )

    def test_absent_artifact_kind_reads_as_document(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        directory = key.directory(self.root)
        artifact_path = directory.joinpath(artifact_relative_path("alpha"))
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        # A minimal hand-authored artifact: required fields only.
        minimal = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "document_id": "alpha",
            "source_content_hash": payload["source_content_hash"],
            "coordinates": payload["coordinates"],
            "content_hash": None,
        }
        from math_research.embedding.partition import payload_hash

        minimal["content_hash"] = payload_hash(
            minimal, hash_field="content_hash", hash_rule=DEFAULT_HASH_RULE,
        )
        artifact_path.write_text(
            json.dumps(minimal, separators=(",", ":"), sort_keys=True), encoding="utf-8",
        )
        manifest_path = directory.joinpath(MANIFEST_FILENAME)
        manifest = {
            "schema_version": PARTITION_SCHEMA_VERSION,
            "partition_key": key.payload(),
            "vectors": [{
                "document_id": "alpha",
                "artifact_content_hash": minimal["content_hash"],
            }],
            "manifest_hash": None,
        }
        manifest["manifest_hash"] = payload_hash(
            manifest, hash_field="manifest_hash", hash_rule=DEFAULT_HASH_RULE,
        )
        manifest_path.write_text(
            json.dumps(manifest, separators=(",", ":"), sort_keys=True), encoding="utf-8",
        )
        partition = load_partition(self.root, key)
        self.assertEqual(partition.corpus_document_ids(), ("alpha",))
        self.assertEqual(partition.query_ids(), ())
        # An unstated provenance may never claim provider evidence.
        self.assertEqual(partition.corpus_provenance, CORPUS_PROVENANCE_PROJECT_AUTHORED)

    def test_manifest_kind_must_agree_with_the_artifact(self) -> None:
        key = _key()
        write_partition(self.root, key, [
            _artifact(key, "alpha", (1, 2, 3), artifact_kind=ARTIFACT_KIND_QUERY),
        ])
        path = key.directory(self.root).joinpath(MANIFEST_FILENAME)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["vectors"][0]["artifact_kind"] = ARTIFACT_KIND_DOCUMENT
        from math_research.embedding.partition import payload_hash

        payload["manifest_hash"] = payload_hash(
            payload, hash_field="manifest_hash", hash_rule=payload["hash_rule"],
        )
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_partition(self.root, key)

    def test_unknown_artifact_kind_is_refused(self) -> None:
        key = _key()
        with self.assertRaises(PartitionSchemaError):
            _artifact(key, "alpha", (1, 2, 3), artifact_kind="passage")


class HashRuleTests(TemporaryRootMixin):
    def test_both_declared_rules_round_trip(self) -> None:
        for rule in (HASH_RULE_SET_NULL, HASH_RULE_POP):
            with self.subTest(rule=rule):
                key = _key(model_identifier=f"rule-{rule.replace('_', '-')}")
                artifact = create_vector_artifact(
                    key, document_id="alpha",
                    source_content_hash="sha256:" + "0" * 64,
                    coordinates=(1, 2, 3), hash_rule=rule,
                )
                partition = write_partition(
                    self.root, key, [artifact], hash_rule=rule,
                )
                self.assertEqual(partition.hash_rule, rule)
                self.assertEqual(
                    load_partition(self.root, key).manifest_hash,
                    partition.manifest_hash,
                )

    def test_the_two_rules_produce_different_hashes(self) -> None:
        key = _key()
        popped = create_vector_artifact(
            key, document_id="alpha", source_content_hash="sha256:" + "0" * 64,
            coordinates=(1, 2, 3), hash_rule=HASH_RULE_POP,
        )
        nulled = create_vector_artifact(
            key, document_id="alpha", source_content_hash="sha256:" + "0" * 64,
            coordinates=(1, 2, 3), hash_rule=HASH_RULE_SET_NULL,
        )
        self.assertNotEqual(popped.content_hash, nulled.content_hash)

    def test_unknown_hash_rule_is_refused(self) -> None:
        key = _key()
        write_partition(self.root, key, [_artifact(key, "alpha", (1, 2, 3))])
        path = key.directory(self.root).joinpath(MANIFEST_FILENAME)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["hash_rule"] = "hash_the_whole_directory"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_partition(self.root, key)


class ReadPathPurityTests(unittest.TestCase):
    def test_the_replay_path_constructs_no_float_and_never_divides(self) -> None:
        findings = sweep_read_path()
        self.assertEqual(
            [item.render() for item in findings], [],
            "the replay path must construct no float and perform no division",
        )

    def test_every_declared_read_path_module_exists(self) -> None:
        from math_research.embedding.readpath import package_root

        for name in READ_PATH_MODULES:
            with self.subTest(module=name):
                self.assertTrue(package_root().joinpath(name).is_file())

    def test_the_sweep_can_be_made_to_fail(self) -> None:
        findings = sweep_source(
            "def f(a, b):\n    return float(a) / b + 1.5\n", module="impure.py",
        )
        kinds = sorted({item.kind for item in findings})
        self.assertEqual(kinds, ["division", "inexact_literal", "inexact_name"])


class AuthoredFixtureTests(TemporaryRootMixin):
    def test_the_fixture_authors_and_replays_deterministically(self) -> None:
        spec = load_authoring_spec(FIXTURE)
        self.assertEqual(spec.key.provider, FIXTURE_SYNTHETIC_PROVIDER)
        self.assertEqual(spec.key.model_identifier, "adaivy-cooccurrence-anchor-v1")
        self.assertEqual(spec.key.dimension, 32)
        self.assertEqual(spec.key.normalization, "round_half_even_scale_2p30")
        first = author_partition(self.root, spec)
        self.assertEqual(first.corpus_provenance, CORPUS_PROVENANCE_PROJECT_AUTHORED)
        self.assertTrue(first.is_project_authored)
        second = author_partition(
            Path(self._temporary.name).joinpath("again"), spec,
        )
        self.assertEqual(first.manifest_hash, second.manifest_hash)

    def test_the_fixture_attains_the_scale_boundary_exactly(self) -> None:
        spec = load_authoring_spec(FIXTURE)
        limit = spec.key.coordinate_limit
        self.assertEqual(limit, SCALE)
        attained = max(
            max(abs(value) for value in artifact.coordinates)
            for artifact in spec.artifacts
        )
        self.assertEqual(attained, limit)

    def test_the_fixture_carries_both_artifact_kinds(self) -> None:
        partition = author_partition(self.root, load_authoring_spec(FIXTURE))
        self.assertTrue(partition.corpus_document_ids())
        self.assertTrue(partition.query_ids())

    def test_a_decimal_coordinate_in_a_spec_is_refused(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["vectors"][0]["coordinates"][0] = 0.5
        path = Path(self._temporary.name).joinpath("decimal-spec.json")
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(PartitionSchemaError):
            load_authoring_spec(path)

    def test_a_real_provider_may_not_be_authored_by_hand(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["provider"] = "openai"
        path = Path(self._temporary.name).joinpath("provider-spec.json")
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(FixtureProviderNotIngestibleError):
            load_authoring_spec(path)

    def test_authored_manifest_hash_is_stable_across_hash_seeds(self) -> None:
        script = (
            "from pathlib import Path\n"
            "import sys, tempfile\n"
            "from math_research.embedding.authoring import author_partition, "
            "load_authoring_spec\n"
            "spec = load_authoring_spec(Path(sys.argv[1]))\n"
            "with tempfile.TemporaryDirectory() as d:\n"
            "    print(author_partition(Path(d), spec).manifest_hash)\n"
        )
        hashes = set()
        for seed in ("0", "1", "9999", "random"):
            completed = subprocess.run(
                [sys.executable, "-c", script, str(FIXTURE)],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                env={
                    "PYTHONPATH": "src", "PYTHONHASHSEED": seed,
                    "PATH": "/usr/bin:/bin",
                },
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            hashes.add(completed.stdout.strip())
        self.assertEqual(len(hashes), 1, hashes)


class ArtifactDirectoryIsTrackedTests(unittest.TestCase):
    """The ADR-0069 / `.gitignore` conflict, and the amendment that resolved it.

    ADR-0069 wants artifacts to be durable evidence bytes. `.gitignore` ignores
    `vectors/`, `vector-store/`, and `embeddings/`, and `AGENTS.md` gives the
    reason: a committed derived index can outlive the corpus it was built from.
    Slice B shipped under the ignored name so a partition could never be HALF
    committed, and recorded the collision rather than papering over it.

    The 2026-08-22 amendment resolved it on the ground that the two rules are
    about different things. A derived index is rebuildable FROM THE RECORDS. A
    vector artifact is not -- it required a provider call that is not
    bit-reproducible, which is precisely why `TECHNICAL_BLUEPRINT.md:1667-1671`
    says to store the bytes and have a rebuild replay them. An artifact is
    therefore primary evidence of a disclosure, and the ignore rule was never
    aimed at it. An index built OVER the artifacts stays ignored.

    Both halves are asserted, because the hazard slice B identified was the
    ASYMMETRY: whichever way it is resolved, the manifest and its artifacts must
    share a fate.
    """

    def _ignored(self, path: str) -> int:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        if completed.returncode == 128:
            self.skipTest("git is unavailable")
        return completed.returncode

    def test_the_artifact_directory_name_is_tracked(self) -> None:
        from math_research.embedding.partition import VECTOR_DIRNAME

        self.assertEqual(
            self._ignored(f"reports/embedding/partition/{VECTOR_DIRNAME}/x.json"), 1,
            f"'{VECTOR_DIRNAME}/' is gitignored, so artifact bytes a rebuild "
            "depends on cannot be committed. TECHNICAL_BLUEPRINT.md:1667-1671 "
            "requires a rebuild to replay stored bytes rather than re-call the "
            "provider, which is impossible if the bytes are dropped.",
        )

    def test_the_manifest_and_its_artifacts_share_one_fate(self) -> None:
        """The asymmetry is the hazard, so it is the thing under test."""

        from math_research.embedding.partition import VECTOR_DIRNAME

        manifest = self._ignored("reports/embedding/partition/manifest.json")
        artifact = self._ignored(f"reports/embedding/partition/{VECTOR_DIRNAME}/x.json")
        self.assertEqual(
            manifest, artifact,
            "a partition can now be half-committed: manifest ignored="
            f"{manifest == 0}, artifacts ignored={artifact == 0}. A tracked "
            "manifest whose artifacts were silently dropped is worse than "
            "neither being tracked.",
        )

    def test_a_derived_index_name_is_still_ignored(self) -> None:
        """The rule the amendment did NOT relax."""

        for name in ("vectors", "vector-store", "embeddings"):
            with self.subTest(name=name):
                self.assertEqual(
                    self._ignored(f"reports/embedding/partition/{name}/x.sqlite3"), 0,
                    f"'{name}/' stopped being ignored; a derived index is "
                    "rebuildable from the records and a committed one lets a "
                    "stale index outlive its corpus",
                )


class ReplayTests(TemporaryRootMixin):
    def test_replay_reports_zero_provider_calls(self) -> None:
        partition = author_partition(self.root, load_authoring_spec(FIXTURE))
        _, report = replay_partition(
            self.root, partition.key,
            expected_manifest_hash=partition.manifest_hash,
        )
        self.assertEqual(report["provider_calls"], 0)
        self.assertEqual(report["network_requests"], 0)
        self.assertFalse(report["creates_epistemic_warrant"])
        self.assertEqual(report["novelty_status"], "not_assessed")

    def test_replay_refuses_an_unexpected_manifest_hash(self) -> None:
        partition = author_partition(self.root, load_authoring_spec(FIXTURE))
        from math_research.embedding.errors import EmbeddingError

        with self.assertRaises(EmbeddingError) as caught:
            replay_partition(
                self.root, partition.key,
                expected_manifest_hash="sha256:" + "1" * 64,
            )
        self.assertEqual(caught.exception.code, "manifest_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
