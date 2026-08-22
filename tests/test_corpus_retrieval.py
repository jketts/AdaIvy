"""Slice 4 acceptance: persistent vectors and real-corpus retrieval."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.corpus_retrieval import (
    CorpusRetrievalError,
    build_projection,
    embed_query,
    load_projection,
    retrieve_evidence,
)
from math_research.corpus_service.dataroot import initialize_data_root
from math_research.corpus_service.generation import record_takedown
from math_research.corpus_service.policy import load_policy
from math_research.corpus_service.ports import DirectoryArchiveSource
from math_research.corpus_service.rightsstore import PolicyDerivedRightsWriter
from math_research.corpus_service.service import ingest_tranche
from math_research.corpus_service.snapshot import load_tranche_config
from math_research.embedding.gateways import ScriptedEmbeddingGateway
from math_research.embedding.partition import PartitionKey


REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures" / "corpus-service"
PROCESSOR = "processor.openai.synthetic-fixture-embedding"
MODEL = "synthetic-fixture-embedding-v1"
T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"
T2 = "2026-08-22T02:00:00Z"


class CorpusRetrievalTests(unittest.TestCase):
    def _corpus(self, root: Path) -> dict:
        initialize_data_root(root, data_root_id="dataroot.retrieval", initialized_at=T0)
        return ingest_tranche(
            root,
            policy=load_policy((FIXTURES / "fixture-source-rights-policy-v1.json").read_bytes()),
            archive=DirectoryArchiveSource(FIXTURES / "fixture-snapshot-archive-v1"),
            tranche_config=load_tranche_config(
                (FIXTURES / "fixture-tranche-config-v1.json").read_bytes()
            ),
            run_id="run.retrieval", recorded_at=T1,
        )

    @staticmethod
    def _key() -> PartitionKey:
        return PartitionKey(
            provider="openai", model_identifier=MODEL, dimension=3,
            normalization="round_half_even_scale_2p20",
        )

    @staticmethod
    def _gateway() -> ScriptedEmbeddingGateway:
        return ScriptedEmbeddingGateway(
            provider="openai", model_identifier=MODEL,
            vectors={
                "doc-open-alpha": (1.0, 0.0, 0.0),
                "doc-open-beta": (0.0, 1.0, 0.0),
            },
        )

    def test_projection_reuses_vectors_and_retrieval_calls_no_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            first_gateway = self._gateway()
            first = build_projection(
                root, generation_id=report["generation_id"], key=self._key(),
                gateway=first_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            self.assertEqual(2, first_gateway.call_count)
            self.assertEqual(2, first.provider_calls)

            second_gateway = self._gateway()
            second = build_projection(
                root, generation_id=report["generation_id"], key=self._key(),
                gateway=second_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            self.assertEqual(0, second_gateway.call_count)
            self.assertEqual(0, second.provider_calls)
            self.assertEqual(first.projection_id, second.projection_id)
            self.assertEqual(
                first.manifest["vectors"], second.manifest["vectors"],
            )

            query_gateway = ScriptedEmbeddingGateway(
                provider="openai", model_identifier=MODEL,
                vectors={"query.e86498e1af2133bad22f88dc": (1.0, 0.0, 0.0)},
            )
            query = embed_query(
                root, projection_id=second.projection_id, query="alpha theorem",
                gateway=query_gateway, processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000,
            )
            before = query_gateway.call_count
            cards = retrieve_evidence(
                root, query_embedding_id=query["query_embedding_id"], limit=2,
            )
            self.assertEqual(before, query_gateway.call_count)
            self.assertEqual("doc-open-alpha", cards[0]["document_id"])
            self.assertEqual("untrusted_inspiration_candidate", cards[0]["trust_status"])
            self.assertEqual("unresolved", cards[0]["applicability_status"])
            self.assertFalse(cards[0]["creates_warrant"])
            self.assertTrue(cards[0]["exact_text"])
            self.assertEqual(first.key, load_projection(root, first.projection_id).key)

    def test_partition_and_processor_mismatch_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            with self.assertRaises(CorpusRetrievalError):
                build_projection(
                    root, generation_id=report["generation_id"], key=self._key(),
                    gateway=self._gateway(), processor_id="processor.other",
                    max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
                )
            wrong = ScriptedEmbeddingGateway(
                provider="openai", model_identifier="wrong-model",
                vectors={
                    "doc-open-alpha": (1.0, 0.0, 0.0),
                    "doc-open-beta": (0.0, 1.0, 0.0),
                },
            )
            with self.assertRaises(CorpusRetrievalError):
                build_projection(
                    root, generation_id=report["generation_id"], key=self._key(),
                    gateway=wrong, processor_id=PROCESSOR,
                    max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
                )

    def test_takedown_invalidates_projection_for_active_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._corpus(root)
            projection = build_projection(
                root, generation_id=report["generation_id"], key=self._key(),
                gateway=self._gateway(), processor_id=PROCESSOR,
                max_input_tokens=4096, timeout_milliseconds=1000, recorded_at=T2,
            )
            writer = PolicyDerivedRightsWriter(
                root, actor_id="human.repository-owner", valid_from=T2,
                valid_until=None,
            )
            record_takedown(
                root, document_id="doc-open-beta", actor_id="human.repository-owner",
                reason_detail="retrieval invalidation drill",
                recorded_at=T2, rights_writer=writer,
            )
            with self.assertRaises(Exception):
                load_projection(root, projection.projection_id)


if __name__ == "__main__":
    unittest.main()
