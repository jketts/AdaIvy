"""ADR-0069 ingestion: the port, the input-only budget, and the rights ordering.

Ordering is the substance of two probes, so it is asserted here as an ordering
and not only as an outcome: the rights check names the processor and runs BEFORE
the source is opened, and the provider is reached only after both.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from math_research.domain.entities import OpaqueId
from math_research.embedding.constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
    FIXTURE_SYNTHETIC_PROVIDER,
    LIVE_EMBEDDING_ACKNOWLEDGEMENT,
    OUTPUT_TOKENS_CONSTANT,
    SUPPORTED_EMBEDDING_PROVIDERS,
)
from math_research.embedding.errors import (
    CoordinateSaturatedError,
    EmbeddingError,
    EmbeddingIngestionError,
    EmbeddingRunConfigurationError,
    FixtureProviderNotIngestibleError,
    OutputTokensNotZeroError,
    ProcessorNotNamedError,
    ProviderCallForbiddenError,
    RightsSeamUnavailableError,
)
from math_research.embedding.gateways import (
    ForbiddingEmbeddingGateway,
    OpenAIEmbeddingGateway,
    ScriptedEmbeddingGateway,
    azure_openai_embedding_config,
    gateway_corpus_provenance,
    openai_embedding_config,
)
from math_research.embedding.ingestion import (
    DocumentRequest,
    ingest_partition,
    ingestion_record_payload,
    load_ingestion_record,
    plan_ingestion,
    write_ingestion_record,
)
from math_research.embedding.partition import (
    MANIFEST_FILENAME,
    PartitionKey,
    load_partition,
)
from math_research.embedding.records import (
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
)
from math_research.embedding.replay import replay_partition
from math_research.embedding.rights import (
    EMBEDDING_RIGHTS_USE,
    DirectorySourceTextReader,
    Phase4ProcessorRightsGate,
    processor_bound_rights_supported,
)
from math_research.embedding.run_config import (
    EMBEDDING_RUN_CONFIG_SCHEMA_VERSION,
    EmbeddingBudget,
    create_embedding_run_configuration,
    embedding_run_configuration_payload,
    load_embedding_run_configuration,
    write_embedding_run_configuration,
)
from math_research.phase2.pricing import create_pricing_snapshot
from math_research.phase4a.records import RightsUse

PROCESSOR = "processor.openai.embeddings.v1"
OTHER_PROCESSOR = "processor.azure-openai.embeddings.v1"
MODEL = "text-embedding-probe"
TEXTS = {
    "source.alpha": "alpha source text",
    "source.beta": "beta source text",
}
VECTORS = {
    "alpha-doc": (0.5, 0.25, -0.125, 0.0),
    "beta-doc": (0.25, 0.5, 0.125, 0.0),
}
DOCUMENTS = (
    DocumentRequest(document_id="alpha-doc", source_id="source.alpha"),
    DocumentRequest(document_id="beta-doc", source_id="source.beta"),
)

PRICING = create_pricing_snapshot(
    snapshot_id=OpaqueId("pricing.embedding.test.v1"),
    provider="openai", model_identifier=MODEL,
    source="project-authored test fixture rate",
    captured_at="2026-08-22T00:00:00Z", currency="USD",
    input_microusd_per_million_tokens=20_000,
    output_microusd_per_million_tokens=0,
)
UNCONFIRMED_PRICING = create_pricing_snapshot(
    snapshot_id=OpaqueId("pricing.embedding.test.unconfirmed.v1"),
    provider="openai", model_identifier=MODEL,
    source="UNCONFIRMED placeholder rate",
    captured_at="2026-08-22T00:00:00Z", currency="USD",
    input_microusd_per_million_tokens=20_000,
    output_microusd_per_million_tokens=0,
)
OUTPUT_PRICING = create_pricing_snapshot(
    snapshot_id=OpaqueId("pricing.embedding.test.output.v1"),
    provider="openai", model_identifier=MODEL,
    source="project-authored test fixture rate",
    captured_at="2026-08-22T00:00:00Z", currency="USD",
    input_microusd_per_million_tokens=20_000,
    output_microusd_per_million_tokens=5,
)


class TraceGate:
    """Records the ORDER of rights checks so ordering can be asserted."""

    def __init__(self, grants: Mapping[str, str], trace: list[str] | None = None) -> None:
        self._grants = dict(sorted(grants.items()))
        self.trace = trace if trace is not None else []

    def require_rights(
        self, source_id: str, intended_use: Any, *, at: str,
        processor_id: str | None = None,
    ) -> Any:
        self.trace.append(f"rights:{source_id}:{processor_id}")
        if intended_use is not RightsUse.EMBEDDING:
            raise EmbeddingError("wrong use", code="rights_use_unexpected")
        if not processor_id:
            raise EmbeddingError("no processor", code="processor_not_named")
        granted = self._grants.get(source_id)
        if granted is None:
            raise EmbeddingError("no decision", code="rights_blocked")
        if granted != processor_id:
            raise EmbeddingError("wrong processor", code="processor_not_authorized")
        return type("Evaluation", (), {"decision_id": f"decision.{source_id}"})()


class TraceCorpus:
    def __init__(self, trace: list[str] | None = None) -> None:
        self.trace = trace if trace is not None else []
        self.reads: list[str] = []

    def read(self, source_id: str) -> bytes:
        self.trace.append(f"read:{source_id}")
        self.reads.append(source_id)
        return TEXTS[source_id].encode("utf-8")


class TraceGateway(ScriptedEmbeddingGateway):
    def __init__(self, trace: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(
            provider="openai", model_identifier=MODEL,
            vectors=kwargs.pop("vectors", VECTORS),
            input_tokens={"alpha-doc": 11, "beta-doc": 13},
        )
        self.trace = trace if trace is not None else []

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.trace.append(f"embed:{request.document_id}:{request.processor_id}")
        return super().embed(request)


def configuration(
    *, processor_id: str = PROCESSOR, provider: str = "openai",
    normalization: str = "round_half_even_scale_2p30", dimension: int = 4,
    max_calls: int = 8, max_input_tokens: int = 4_096,
    max_cost_microusd: int = 1_000_000, per_call_input_token_reserve: int = 512,
) -> Any:
    return create_embedding_run_configuration(
        configuration_id="config.embedding.test.v1",
        provider=provider, model_identifier=MODEL, dimension=dimension,
        normalization=normalization, processor_id=processor_id,
        pricing_snapshot_id=PRICING.snapshot_id.value,
        call_timeout_milliseconds=30_000,
        per_call_input_token_reserve=per_call_input_token_reserve,
        budget=EmbeddingBudget(
            max_calls=max_calls, max_input_tokens=max_input_tokens,
            max_cost_microusd=max_cost_microusd,
        ),
    )


class TemporaryRootMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="adaivy-ingestion-test.")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)

    def ingest(self, **kwargs: Any) -> Any:
        arguments: dict[str, Any] = {
            "root": self.root,
            "configuration": configuration(),
            "pricing": PRICING,
            "gateway": TraceGateway(),
            "rights": TraceGate({"source.alpha": PROCESSOR, "source.beta": PROCESSOR}),
            "corpus": TraceCorpus(),
            "documents": DOCUMENTS,
            "run_id": "run.embedding.test.v1",
            "recorded_at": "2026-08-22T00:00:00Z",
            "execute": True,
            "acknowledgement": LIVE_EMBEDDING_ACKNOWLEDGEMENT,
        }
        arguments.update(kwargs)
        return ingest_partition(**arguments)


class PortShapeTests(unittest.TestCase):
    def test_output_tokens_are_a_stated_constant(self) -> None:
        self.assertEqual(OUTPUT_TOKENS_CONSTANT, 0)
        self.assertEqual(EmbeddingUsage(input_tokens=5).output_tokens, 0)

    def test_a_result_claiming_output_tokens_is_refused(self) -> None:
        with self.assertRaises(OutputTokensNotZeroError):
            EmbeddingUsage(input_tokens=5, output_tokens=1)

    def test_result_requires_an_adapter_backed_provider(self) -> None:
        with self.assertRaises(EmbeddingError):
            EmbeddingResult(
                provider="bedrock", model_identifier=MODEL,
                provider_coordinates=(0.5,),
                usage=EmbeddingUsage(input_tokens=1, usage_source="fixture"),
            )

    def test_request_requires_a_named_processor(self) -> None:
        with self.assertRaises(EmbeddingError):
            EmbeddingRequest(
                document_id="alpha-doc", source_id="source.alpha",
                source_content_hash="sha256:" + "0" * 64, text="x",
                processor_id="", max_input_tokens=1, timeout_milliseconds=1,
            )

    def test_only_the_two_credentialed_providers_have_an_adapter(self) -> None:
        self.assertEqual(
            sorted(SUPPORTED_EMBEDDING_PROVIDERS), ["azure_openai", "openai"],
        )

    def test_gateway_provenance_is_fail_closed(self) -> None:
        self.assertEqual(
            gateway_corpus_provenance(OpenAIEmbeddingGateway(
                openai_embedding_config(model_identifier=MODEL, dimension=4),
            )),
            CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
        )
        for gateway in (
            TraceGateway(), ForbiddingEmbeddingGateway(), object(),
        ):
            with self.subTest(gateway=type(gateway).__name__):
                self.assertEqual(
                    gateway_corpus_provenance(gateway),
                    CORPUS_PROVENANCE_PROJECT_AUTHORED,
                )

    def test_azure_config_reuses_the_phase2_secret_declaration(self) -> None:
        gateway = OpenAIEmbeddingGateway(
            azure_openai_embedding_config(model_identifier=MODEL, dimension=4),
        )
        self.assertEqual(gateway.secret_variables(), ("AZURE_OPENAI_API_KEY",))
        self.assertEqual(
            OpenAIEmbeddingGateway(
                openai_embedding_config(model_identifier=MODEL, dimension=4),
            ).secret_variables(),
            ("OPENAI_API_KEY",),
        )


class RunConfigurationTests(unittest.TestCase):
    def test_round_trip_preserves_the_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).joinpath("config.json")
            original = configuration()
            write_embedding_run_configuration(original, path)
            self.assertEqual(load_embedding_run_configuration(path), original)

    def test_schema_version_is_explicit(self) -> None:
        self.assertEqual(
            configuration().schema_version, EMBEDDING_RUN_CONFIG_SCHEMA_VERSION,
        )

    def test_an_output_token_budget_field_is_refused(self) -> None:
        payload = embedding_run_configuration_payload(configuration())
        payload["per_call_output_token_reserve"] = 256
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).joinpath("config.json")
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EmbeddingRunConfigurationError) as caught:
                load_embedding_run_configuration(path)
        self.assertIn("output-token budget", str(caught.exception))

    def test_unknown_field_is_refused(self) -> None:
        payload = embedding_run_configuration_payload(configuration())
        payload["temperature"] = 0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).joinpath("config.json")
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EmbeddingRunConfigurationError):
                load_embedding_run_configuration(path)

    def test_tampered_content_hash_is_refused(self) -> None:
        payload = embedding_run_configuration_payload(configuration())
        payload["dimension"] = 8
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).joinpath("config.json")
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EmbeddingRunConfigurationError):
                load_embedding_run_configuration(path)

    def test_fixture_synthetic_can_never_be_configured_for_a_run(self) -> None:
        with self.assertRaises(FixtureProviderNotIngestibleError):
            configuration(provider=FIXTURE_SYNTHETIC_PROVIDER)

    def test_a_provider_without_an_embedding_adapter_is_refused(self) -> None:
        with self.assertRaises(EmbeddingRunConfigurationError):
            configuration(provider="bedrock")


class IngestionOrderingTests(TemporaryRootMixin):
    def test_rights_precede_the_read_which_precedes_the_provider(self) -> None:
        trace: list[str] = []
        self.ingest(
            gateway=TraceGateway(trace),
            rights=TraceGate(
                {"source.alpha": PROCESSOR, "source.beta": PROCESSOR}, trace,
            ),
            corpus=TraceCorpus(trace),
        )
        self.assertEqual(trace, [
            f"rights:source.alpha:{PROCESSOR}",
            "read:source.alpha",
            f"embed:alpha-doc:{PROCESSOR}",
            f"rights:source.beta:{PROCESSOR}",
            "read:source.beta",
            f"embed:beta-doc:{PROCESSOR}",
        ])

    def test_no_rights_means_no_read_and_no_call(self) -> None:
        trace: list[str] = []
        corpus = TraceCorpus(trace)
        gateway = TraceGateway(trace)
        with self.assertRaises(EmbeddingError) as caught:
            self.ingest(
                gateway=gateway, corpus=corpus,
                rights=TraceGate({}, trace),
            )
        self.assertEqual(caught.exception.code, "rights_blocked")
        self.assertEqual(corpus.reads, [])
        self.assertEqual(gateway.call_count, 0)
        self.assertFalse(any(item.startswith("read:") for item in trace))

    def test_a_decision_for_another_processor_does_not_authorize(self) -> None:
        corpus = TraceCorpus()
        with self.assertRaises(EmbeddingError) as caught:
            self.ingest(
                configuration=configuration(processor_id=OTHER_PROCESSOR),
                corpus=corpus,
            )
        self.assertEqual(caught.exception.code, "processor_not_authorized")
        self.assertEqual(corpus.reads, [])

    def test_documents_are_processed_in_sorted_order(self) -> None:
        trace: list[str] = []
        self.ingest(
            gateway=TraceGateway(trace),
            rights=TraceGate(
                {"source.alpha": PROCESSOR, "source.beta": PROCESSOR}, trace,
            ),
            corpus=TraceCorpus(trace),
            documents=tuple(reversed(DOCUMENTS)),
        )
        self.assertEqual(trace[0], f"rights:source.alpha:{PROCESSOR}")


class IngestionRecordTests(TemporaryRootMixin):
    def test_record_closes_usage_cost_and_vector_bytes(self) -> None:
        record = self.ingest()
        partition = load_partition(self.root, PartitionKey(
            provider="openai", model_identifier=MODEL, dimension=4,
            normalization="round_half_even_scale_2p30",
        ))
        self.assertEqual(record.manifest_hash, partition.manifest_hash)
        self.assertEqual(record.total_input_tokens, 24)
        self.assertEqual(record.output_tokens, 0)
        self.assertEqual(record.provider_calls, 2)
        self.assertEqual(record.estimated_cost_microusd, 1)
        self.assertEqual(
            [item.document_id for item in record.documents],
            ["alpha-doc", "beta-doc"],
        )
        self.assertEqual(
            [item.rights_decision_id for item in record.documents],
            ["decision.source.alpha", "decision.source.beta"],
        )

    def test_a_scripted_gateway_yields_a_project_authored_manifest(self) -> None:
        record = self.ingest()
        self.assertEqual(record.corpus_provenance, CORPUS_PROVENANCE_PROJECT_AUTHORED)

    def test_record_is_byte_reproducible(self) -> None:
        first = self.ingest()
        second_root = self.root.joinpath("second")
        second = self.ingest(root=second_root)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(
            json.dumps(ingestion_record_payload(first), sort_keys=True),
            json.dumps(ingestion_record_payload(second), sort_keys=True),
        )

    def test_record_asserts_no_epistemic_effect(self) -> None:
        payload = ingestion_record_payload(self.ingest())
        self.assertFalse(payload["creates_epistemic_warrant"])
        self.assertFalse(payload["asserts_source_applicability"])
        self.assertFalse(payload["creates_graph_admission"])
        self.assertEqual(payload["novelty_status"], "not_assessed")
        self.assertEqual(payload["significance_status"], "not_assessed")

    def test_record_claiming_nonzero_output_tokens_is_refused(self) -> None:
        payload = ingestion_record_payload(self.ingest())
        payload["output_tokens"] = 1
        with self.assertRaises(OutputTokensNotZeroError):
            load_ingestion_record(payload)

    def test_record_claiming_a_warrant_is_refused(self) -> None:
        payload = ingestion_record_payload(self.ingest())
        payload["creates_epistemic_warrant"] = True
        with self.assertRaises(EmbeddingIngestionError):
            load_ingestion_record(payload)

    def test_record_naming_the_fixture_provider_is_refused(self) -> None:
        payload = ingestion_record_payload(self.ingest())
        payload["partition_key"]["provider"] = FIXTURE_SYNTHETIC_PROVIDER
        with self.assertRaises(FixtureProviderNotIngestibleError):
            load_ingestion_record(payload)

    def test_record_write_refuses_a_differing_overwrite(self) -> None:
        record = self.ingest()
        path = self.root.joinpath("record.json")
        write_ingestion_record(record, path)
        write_ingestion_record(record, path)
        payload = ingestion_record_payload(record)
        payload["run_id"] = "run.other"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(EmbeddingIngestionError):
            write_ingestion_record(record, path)


class IngestionRefusalTests(TemporaryRootMixin):
    def test_execute_is_required(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(execute=False)

    def test_the_exact_acknowledgement_is_required(self) -> None:
        for candidate in ("", "yes", LIVE_EMBEDDING_ACKNOWLEDGEMENT.lower()):
            with self.subTest(candidate=candidate):
                with self.assertRaises(EmbeddingIngestionError):
                    self.ingest(acknowledgement=candidate)

    def test_a_provider_declaring_an_output_rate_is_refused(self) -> None:
        with self.assertRaises(EmbeddingIngestionError) as caught:
            self.ingest(pricing=OUTPUT_PRICING)
        self.assertIn("zero output rate", str(caught.exception))

    def test_unconfirmed_pricing_is_refused(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(pricing=UNCONFIRMED_PRICING)

    def test_call_budget_is_enforced(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(configuration=configuration(max_calls=1))

    def test_input_token_budget_is_enforced(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(configuration=configuration(max_input_tokens=12))

    def test_cost_budget_is_enforced(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(configuration=configuration(max_cost_microusd=0))

    def test_per_call_reserve_is_enforced(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(configuration=configuration(per_call_input_token_reserve=5))

    def test_provider_dimension_must_match_the_partition_key(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(configuration=configuration(dimension=8))

    def test_a_saturating_coordinate_halts_and_writes_no_manifest(self) -> None:
        key = PartitionKey(
            provider="openai", model_identifier=MODEL, dimension=4,
            normalization="round_half_even_scale_2p30",
        )
        with self.assertRaises(CoordinateSaturatedError):
            self.ingest(gateway=TraceGateway(vectors={
                "alpha-doc": (1.5, 0.25, -0.125, 0.0),
                "beta-doc": (0.25, 0.5, 0.125, 0.0),
            }))
        self.assertFalse(
            key.directory(self.root).joinpath(MANIFEST_FILENAME).exists()
        )

    def test_boundary_coordinate_is_accepted(self) -> None:
        record = self.ingest(gateway=TraceGateway(vectors={
            "alpha-doc": (1.0, -1.0, 0.5, 0.0),
            "beta-doc": (0.25, 0.5, 0.125, 0.0),
        }))
        partition = load_partition(self.root, record.partition_key)
        self.assertEqual(
            partition.vector("alpha-doc").coordinates,
            (1 << 30, -(1 << 30), 1 << 29, 0),
        )

    def test_duplicate_document_ids_are_refused(self) -> None:
        with self.assertRaises(EmbeddingIngestionError):
            self.ingest(documents=(DOCUMENTS[0], DOCUMENTS[0]))

    def test_a_forbidding_gateway_makes_ingestion_loud(self) -> None:
        with self.assertRaises(ProviderCallForbiddenError):
            self.ingest(gateway=ForbiddingEmbeddingGateway())


class ReplayMakesNoProviderCallTests(TemporaryRootMixin):
    def test_replay_reproduces_the_manifest_hash_with_a_forbidding_gateway(self) -> None:
        record = self.ingest()
        gateway = ForbiddingEmbeddingGateway()
        partition, report = replay_partition(
            self.root, record.partition_key, gateway=gateway,
            expected_manifest_hash=record.manifest_hash,
        )
        self.assertEqual(gateway.attempts, 0)
        self.assertEqual(report["provider_calls"], 0)
        self.assertEqual(partition.manifest_hash, record.manifest_hash)


class RightsSeamTests(unittest.TestCase):
    """The ADR-0064 seam. Fails closed until slice A lands."""

    class _Unbound:
        def require_rights(self, source_id: str, intended_use: Any, *, at: str) -> str:
            return "granted-without-a-processor"

    class _Bound:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def require_rights(
            self, source_id: str, intended_use: Any, *, at: str,
            processor_id: str | None = None,
        ) -> str:
            self.calls.append((source_id, processor_id))
            return "granted"

    def test_embedding_use_is_already_in_the_closed_vocabulary(self) -> None:
        self.assertIs(EMBEDDING_RIGHTS_USE, RightsUse.EMBEDDING)

    def test_an_unbound_service_is_detected(self) -> None:
        self.assertFalse(processor_bound_rights_supported(self._Unbound()))
        self.assertTrue(processor_bound_rights_supported(self._Bound()))

    def test_the_seam_refuses_rather_than_checking_an_unbound_decision(self) -> None:
        gate = Phase4ProcessorRightsGate(self._Unbound())
        with self.assertRaises(RightsSeamUnavailableError):
            gate.require_rights(
                "source.alpha", RightsUse.EMBEDDING,
                at="2026-08-22T00:00:00Z", processor_id=PROCESSOR,
            )

    def test_the_seam_forwards_once_the_parameter_exists(self) -> None:
        service = self._Bound()
        gate = Phase4ProcessorRightsGate(service)
        self.assertEqual(
            gate.require_rights(
                "source.alpha", RightsUse.EMBEDDING,
                at="2026-08-22T00:00:00Z", processor_id=PROCESSOR,
            ),
            "granted",
        )
        self.assertEqual(service.calls, [("source.alpha", PROCESSOR)])

    def test_an_unnamed_processor_is_refused_before_the_service_is_consulted(self) -> None:
        service = self._Bound()
        gate = Phase4ProcessorRightsGate(service)
        with self.assertRaises(ProcessorNotNamedError):
            gate.require_rights(
                "source.alpha", RightsUse.EMBEDDING, at="2026-08-22T00:00:00Z",
            )
        self.assertEqual(service.calls, [])

    def test_the_seam_agrees_with_whatever_phase4a_currently_supports(self) -> None:
        """Passes before AND after ADR-0064 slice A, asserting the seam either way.

        Before slice A the gate must refuse; after it, the gate must forward.
        A test asserting only the present state would fail at integration and
        would therefore be deleted rather than read.
        """

        from math_research.phase4a.service import Phase4Service

        supported = processor_bound_rights_supported(Phase4Service)
        gate = Phase4ProcessorRightsGate(self._Unbound())
        if supported:
            self.assertTrue(
                processor_bound_rights_supported(self._Bound()),
                "the detector must still recognise a bound signature",
            )
        else:
            with self.assertRaises(RightsSeamUnavailableError):
                gate.require_rights(
                    "source.alpha", RightsUse.EMBEDDING,
                    at="2026-08-22T00:00:00Z", processor_id=PROCESSOR,
                )


class SourceReaderTests(unittest.TestCase):
    def test_reads_a_bounded_utf8_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("source.alpha.txt").write_text("hello", encoding="utf-8")
            reader = DirectorySourceTextReader(root)
            self.assertEqual(reader.read("source.alpha"), b"hello")
            self.assertEqual(reader.reads, ["source.alpha"])

    def test_refuses_traversal_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("big.txt").write_text("x" * 32, encoding="utf-8")
            with self.assertRaises(EmbeddingError):
                DirectorySourceTextReader(root).read("../escape")
            with self.assertRaises(EmbeddingError):
                DirectorySourceTextReader(root, max_bytes=4).read("big")


class PlanTests(unittest.TestCase):
    def test_the_dry_plan_calls_nothing(self) -> None:
        plan = plan_ingestion(
            configuration=configuration(), pricing=PRICING, documents=DOCUMENTS,
        )
        self.assertEqual(plan["execution_status"], "not_executed")
        self.assertEqual(plan["provider_calls"], 0)
        self.assertEqual(plan["network_requests"], 0)
        self.assertEqual(plan["output_tokens"], 0)
        self.assertEqual(plan["document_ids"], ["alpha-doc", "beta-doc"])
        self.assertEqual(
            plan["required_acknowledgement"], LIVE_EMBEDDING_ACKNOWLEDGEMENT,
        )


if __name__ == "__main__":
    unittest.main()
