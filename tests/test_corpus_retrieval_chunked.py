"""ADR-0080 chunked retrieval: chunk spans as the retrieval unit.

One document yields many evidence cards; chunk offsets are exact character
spans over the extracted text; deltas reuse vectors without provider calls;
partition purity still fails closed; and the v1 whole-document path refuses
extractor-derived documents instead of mis-anchoring their offsets.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.corpus_retrieval import (
    ChunkingConfig,
    CorpusRetrievalError,
    build_chunked_projection,
    build_projection,
    chunk_spans,
    embed_chunked_query,
    load_chunked_projection,
    retrieve_chunked_evidence,
)
from math_research.corpus_service import (
    ARCHIVE_MANIFEST_SCHEMA_VERSION,
    TRANCHE_CONFIG_SCHEMA_VERSION,
)
from math_research.corpus_service.constants import PROVIDER
from math_research.corpus_service.dataroot import initialize_data_root, read_object
from math_research.corpus_service.extraction import (
    ExtractorRegistry,
    FixtureExtractor,
    IdentityTextExtractor,
)
from math_research.corpus_service.policy import validate_policy
from math_research.corpus_service.serialization import sealed, sha256_bytes
from math_research.corpus_service.service import ingest_tranche
from math_research.corpus_service.snapshot import validate_tranche_config
from math_research.embedding.gateways import ScriptedEmbeddingGateway
from math_research.embedding.partition import PartitionKey

T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"
T2 = "2026-08-22T02:00:00Z"

HUMAN = {
    "actor_id": "human.repository-owner",
    "actor_kind": "human",
    "authority": "human_final",
}
OPEN_LICENCE = "LicenseRef-AdaIvy-Synthetic-OpenAccess"
OPEN_LICENCE_URL = "https://example.invalid/licenses/adaivy-synthetic-open-access"
PROCESSOR = "processor.openai.synthetic-fixture-embedding"
MODEL = "synthetic-fixture-embedding-v1"

LONG_TEXT = (
    "The alpha theorem opens the exposition with an exact statement.\n\n"
    "A later paragraph revisits the alpha theorem from the dual side.\n\n"
    "The closing remarks list open problems and exact counterexamples.\n"
)
PDF_BODY = b"%PDF-1.7 synthetic binary body \x00\x01"
PDF_EXTRACTED = (
    "Extracted survey of beta structures.\n\n"
    "The survey closes with a beta conjecture.\n"
)

CHUNKING = ChunkingConfig(window_chars=64, overlap_chars=16)


def _archive() -> tuple[dict, dict[str, bytes]]:
    body_long = LONG_TEXT.encode("utf-8")
    entries = [
        {
            "document_id": "doc-long",
            "relative_path": "documents/doc-long.txt",
            "media_type": "text/plain",
            "byte_count": len(body_long),
            "sha256": sha256_bytes(body_long),
            "licence": {"licence": OPEN_LICENCE, "licence_url": OPEN_LICENCE_URL},
        },
        {
            "document_id": "doc-pdf",
            "relative_path": "documents/doc-pdf.pdf",
            "media_type": "application/pdf",
            "byte_count": len(PDF_BODY),
            "sha256": sha256_bytes(PDF_BODY),
            "licence": {"licence": OPEN_LICENCE, "licence_url": OPEN_LICENCE_URL},
        },
    ]
    manifest = sealed({
        "schema_version": ARCHIVE_MANIFEST_SCHEMA_VERSION,
        "provider": PROVIDER,
        "archive_id": "archive.adaivy-chunked-fixture",
        "archive_version": "v1",
        "documents": entries,
        "document_count": len(entries),
        "total_bytes": sum(item["byte_count"] for item in entries),
        "content_hash": None,
    })
    return manifest, {
        "documents/doc-long.txt": body_long,
        "documents/doc-pdf.pdf": PDF_BODY,
    }


class MappingArchive:
    def __init__(self, manifest: dict, bodies: dict[str, bytes]) -> None:
        self.manifest = manifest
        self.bodies = bodies

    def manifest_bytes(self) -> bytes:
        from math_research.corpus_service.serialization import canonical_bytes
        return canonical_bytes(self.manifest) + b"\n"

    def document_bytes(self, relative_path: str) -> bytes:
        return self.bodies[relative_path]


def _policy() -> dict:
    return validate_policy(sealed({
        "schema_version": "adaivy.corpus-service-source-rights-policy.v1",
        "policy_id": "policy.adaivy-chunked-fixture-v1",
        "archive": {
            "archive_id": "archive.adaivy-chunked-fixture",
            "archive_version": "v1",
        },
        "authored_by": dict(HUMAN),
        "terms_reviewed_at": "2026-08-22",
        "licence_diligence_adr": "adr-0067",
        "default_action": "quarantine",
        "rules": [{
            "rule_id": "rule.synthetic-open-access",
            "licence": OPEN_LICENCE,
            "licence_url": OPEN_LICENCE_URL,
            "acquisition": "allowed",
            "storage_and_retention": "allowed",
            "parsing": "allowed",
            "full_text": True,
            "embedding": {
                "value": "allowed",
                "processor": {
                    "processor_id": PROCESSOR,
                    "provider": "openai",
                    "model_identifier": MODEL,
                    "disclosure_kind": "text_stays_local",
                },
            },
            "model_context": {"value": "prohibited", "processor": None},
        }],
        "content_hash": None,
    }))


def _registry() -> ExtractorRegistry:
    return ExtractorRegistry((
        IdentityTextExtractor(),
        FixtureExtractor(
            tool="pdftotext-fixture", version="24.02.0",
            binary_sha256="sha256:" + "ab" * 32,
            accepted_media_types=frozenset({"application/pdf"}),
            texts_by_source_sha256={sha256_bytes(PDF_BODY): PDF_EXTRACTED},
        ),
    ))


def _key() -> PartitionKey:
    return PartitionKey(
        provider="openai", model_identifier=MODEL, dimension=3,
        normalization="round_half_even_scale_2p20",
    )


def _chunk_vectors() -> dict[str, tuple[float, float, float]]:
    vectors: dict[str, tuple[float, float, float]] = {}
    for index in range(len(chunk_spans(LONG_TEXT, CHUNKING))):
        # The first two chunks of doc-long sit closest to the query axis.
        vectors[f"doc-long.chunk-{index:05d}"] = (
            (1.0, 0.0, 0.0) if index == 0
            else (0.9, 0.1, 0.0) if index == 1
            else (0.1, 0.9, 0.0)
        )
    for index in range(len(chunk_spans(PDF_EXTRACTED, CHUNKING))):
        vectors[f"doc-pdf.chunk-{index:05d}"] = (0.0, 0.0, 1.0)
    return vectors


def _query_id(query: str) -> str:
    return "query." + sha256_bytes(query.encode("utf-8")).removeprefix("sha256:")[:24]


class ChunkedRetrievalTests(unittest.TestCase):
    def _corpus(self, root: Path) -> dict:
        manifest, bodies = _archive()
        policy = _policy()
        initialize_data_root(root, data_root_id="dataroot.chunked", initialized_at=T0)
        tranche = validate_tranche_config(sealed({
            "schema_version": TRANCHE_CONFIG_SCHEMA_VERSION,
            "tranche_id": "tranche.adaivy-chunked-fixture-v1",
            "archive_manifest_hash": manifest["content_hash"],
            "policy_content_hash": policy["content_hash"],
            "max_documents": 16,
            "max_total_bytes": 65_536,
            "max_document_bytes": 16_384,
            "selected_by": dict(HUMAN),
            "content_hash": None,
        }))
        return ingest_tranche(
            root, policy=policy, archive=MappingArchive(manifest, bodies),
            tranche_config=tranche, run_id="run.chunked", recorded_at=T1,
            extractors=_registry(),
        )

    def _gateway(self, extra: dict | None = None) -> ScriptedEmbeddingGateway:
        vectors = _chunk_vectors()
        vectors.update(extra or {})
        return ScriptedEmbeddingGateway(
            provider="openai", model_identifier=MODEL, vectors=vectors,
        )

    def test_chunk_spans_are_deterministic_exact_windows(self) -> None:
        spans = chunk_spans(LONG_TEXT, CHUNKING)
        self.assertGreaterEqual(len(spans), 3)
        stride = CHUNKING.window_chars - CHUNKING.overlap_chars
        for index, (start, end) in enumerate(spans):
            self.assertEqual(index * stride, start)
            self.assertLessEqual(end - start, CHUNKING.window_chars)
        self.assertEqual(len(LONG_TEXT), spans[-1][1])

    def test_multi_chunk_projection_retrieval_and_delta_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            total_chunks = len(chunk_spans(LONG_TEXT, CHUNKING)) + len(
                chunk_spans(PDF_EXTRACTED, CHUNKING)
            )
            first_gateway = self._gateway()
            first = build_chunked_projection(
                root, generation_id=report["generation_id"], key=_key(),
                chunking=CHUNKING, gateway=first_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            self.assertEqual(total_chunks, first["provider_calls"])
            self.assertEqual(total_chunks, first["manifest"]["vector_count"])
            self.assertEqual(
                CHUNKING.payload(), first["manifest"]["chunking"],
            )

            # Delta rebuild: zero provider calls, identical projection.
            second_gateway = self._gateway()
            second = build_chunked_projection(
                root, generation_id=report["generation_id"], key=_key(),
                chunking=CHUNKING, gateway=second_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            self.assertEqual(0, second["provider_calls"])
            self.assertEqual(0, second_gateway.call_count)
            self.assertEqual(
                first["manifest"]["projection_id"],
                second["manifest"]["projection_id"],
            )

            query = "where does the alpha theorem appear"
            query_gateway = ScriptedEmbeddingGateway(
                provider="openai", model_identifier=MODEL,
                vectors={_query_id(query): (1.0, 0.0, 0.0)},
            )
            embedded = embed_chunked_query(
                root, projection_id=first["manifest"]["projection_id"],
                query=query, gateway=query_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000,
            )
            cards = retrieve_chunked_evidence(
                root, query_embedding_id=embedded["query_embedding_id"], limit=3,
            )
            self.assertEqual(3, len(cards))
            # One document yields many cards: the top two are distinct chunks
            # of the same document.
            self.assertEqual("doc-long", cards[0]["document_id"])
            self.assertEqual("doc-long", cards[1]["document_id"])
            self.assertEqual(0, cards[0]["chunk_index"])
            self.assertEqual(1, cards[1]["chunk_index"])
            self.assertNotEqual(cards[0]["start_offset"], cards[1]["start_offset"])
            for card in cards:
                self.assertEqual("untrusted_inspiration_candidate", card["trust_status"])
                self.assertEqual("unresolved", card["applicability_status"])
                self.assertFalse(card["creates_warrant"])
                text = read_object(root, card["text_sha256"]).decode("utf-8")
                self.assertEqual(
                    text[card["start_offset"]: card["end_offset"]],
                    card["exact_text"],
                )
                self.assertEqual(
                    sha256_bytes(card["exact_text"].encode("utf-8")),
                    card["exact_text_hash"],
                )
            self.assertEqual(
                LONG_TEXT[: CHUNKING.window_chars], cards[0]["exact_text"],
            )
            # Extractor identity travels on every card.
            self.assertEqual(
                "adaivy.identity-text-extractor", cards[0]["extraction"]["tool"],
            )
            loaded = load_chunked_projection(root, first["manifest"]["projection_id"])
            self.assertEqual(first["manifest"]["content_hash"], loaded["content_hash"])

    def test_extracted_pdf_chunks_anchor_to_extracted_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            projection = build_chunked_projection(
                root, generation_id=report["generation_id"], key=_key(),
                chunking=CHUNKING, gateway=self._gateway(), processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            query = "beta structures survey"
            gateway = ScriptedEmbeddingGateway(
                provider="openai", model_identifier=MODEL,
                vectors={_query_id(query): (0.0, 0.0, 1.0)},
            )
            embedded = embed_chunked_query(
                root, projection_id=projection["manifest"]["projection_id"],
                query=query, gateway=gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000,
            )
            cards = retrieve_chunked_evidence(
                root, query_embedding_id=embedded["query_embedding_id"], limit=2,
            )
            self.assertEqual("doc-pdf", cards[0]["document_id"])
            self.assertEqual("pdftotext-fixture", cards[0]["extraction"]["tool"])
            self.assertEqual(
                sha256_bytes(PDF_EXTRACTED.encode("utf-8")), cards[0]["text_sha256"],
            )
            self.assertNotEqual(cards[0]["text_sha256"], cards[0]["source_content_hash"])
            self.assertEqual(
                PDF_EXTRACTED[cards[0]["start_offset"]: cards[0]["end_offset"]],
                cards[0]["exact_text"],
            )

    def test_partition_purity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            wrong_model = ScriptedEmbeddingGateway(
                provider="openai", model_identifier="some-other-model",
                vectors=_chunk_vectors(),
            )
            with self.assertRaises(CorpusRetrievalError):
                build_chunked_projection(
                    root, generation_id=report["generation_id"], key=_key(),
                    chunking=CHUNKING, gateway=wrong_model, processor_id=PROCESSOR,
                    max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
                )
            with self.assertRaises(CorpusRetrievalError):
                build_chunked_projection(
                    root, generation_id=report["generation_id"], key=_key(),
                    chunking=CHUNKING, gateway=self._gateway(),
                    processor_id="processor.other",
                    max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
                )

    def test_v1_whole_document_path_refuses_extractor_derived_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            with self.assertRaises(CorpusRetrievalError) as caught:
                build_projection(
                    root, generation_id=report["generation_id"], key=_key(),
                    gateway=self._gateway({"doc-long": (1.0, 0.0, 0.0)}),
                    processor_id=PROCESSOR,
                    max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
                )
            self.assertIn("chunked", str(caught.exception))

    def test_chunking_config_bounds_fail_closed(self) -> None:
        with self.assertRaises(CorpusRetrievalError):
            ChunkingConfig(window_chars=0, overlap_chars=0)
        with self.assertRaises(CorpusRetrievalError):
            ChunkingConfig(window_chars=64, overlap_chars=64)
        with self.assertRaises(CorpusRetrievalError):
            ChunkingConfig(window_chars=1_000_000, overlap_chars=0)


if __name__ == "__main__":
    unittest.main()
