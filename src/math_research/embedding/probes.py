"""The thirteen ADR-0069 falsifiability probes.

ADR-0034 established the standard and ADR-0069 restates it: ``probes_flipped ==
probes_total`` gates the slice, because a rule that cannot be made to fail proves
nothing.

Each probe has two legs and a named expected code. The BASELINE leg exercises the
accepted path and must NOT produce the code; the MUTATED leg makes one named
change and must produce exactly that code. A probe flips only when both hold, so
a probe passes neither by always failing nor by never firing.

Ten probes mutate an INPUT to the production path. Three -- the two
no-provider-call/read-path-purity probes and the tie-order probe -- state a
positive property, so their mutated leg fires the instrument against a
deliberately wrong subject instead. That distinction is recorded on each probe as
``mutation_target`` rather than left to a reader.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..phase2.pricing import create_pricing_snapshot
from ..phase2.serialization import sha256_bytes
from ..domain.entities import OpaqueId
from .constants import (
    DEFAULT_NORMALIZATION,
    FIXTURE_SYNTHETIC_PROVIDER,
    LIVE_EMBEDDING_ACKNOWLEDGEMENT,
)
from .errors import (
    EmbeddingError,
    ProviderCallForbiddenError,
    ReadPathPurityError,
    TieOrderError,
)
from .gateways import ForbiddingEmbeddingGateway, ScriptedEmbeddingGateway
from .ingestion import (
    DocumentRequest,
    ingest_partition,
    ingestion_record_payload,
    load_ingestion_record,
)
from .partition import (
    MANIFEST_FILENAME,
    PartitionKey,
    PartitionedVector,
    artifact_relative_path,
    create_vector_artifact,
    load_partition,
    write_partition,
    write_vector_artifact,
)
from .readpath import READ_PATH_MODULES, sweep_read_path, sweep_source
from .records import EmbeddingUsage
from .replay import replay_partition
from .rights import EMBEDDING_RIGHTS_USE
from .run_config import EmbeddingBudget, create_embedding_run_configuration
from .similarity import cosine_terms_within_partition, rank_exact_cosine

PROBE_REPORT_SCHEMA_VERSION = "adaivy.embedding-probe-report.v1"

#: Not a rights authority. A probe fixture, constructed only inside this module,
#: that mimics the ADR-0064 decision shape closely enough to order the ingestion
#: path. Production callers inject `Phase4ProcessorRightsGate` onto Phase 4A.
_PROBE_PROCESSOR = "processor.openai.embeddings.v1"
_OTHER_PROCESSOR = "processor.azure-openai.embeddings.v1"


@dataclass(frozen=True, slots=True, kw_only=True)
class _ProbeRightsEvaluation:
    decision_id: str


class _ProbeFixtureRightsGate:
    """Grants exactly the (source_id, processor_id) pairs it was handed."""

    def __init__(self, grants: Mapping[str, str]) -> None:
        self._grants = dict(sorted(grants.items()))
        self.checks: list[tuple[str, str | None]] = []

    def require_rights(
        self, source_id: str, intended_use: Any, *, at: str,
        processor_id: str | None = None,
    ) -> _ProbeRightsEvaluation:
        self.checks.append((source_id, processor_id))
        if intended_use is not EMBEDDING_RIGHTS_USE:
            raise EmbeddingError(f"unexpected rights use {intended_use!r}",
                                 code="rights_use_unexpected")
        if not processor_id:
            raise EmbeddingError("no processor named", code="processor_not_named")
        granted = self._grants.get(source_id)
        if granted is None:
            raise EmbeddingError(
                f"no live embedding decision for {source_id}", code="rights_blocked",
            )
        if granted != processor_id:
            raise EmbeddingError(
                f"decision for {source_id} names {granted}, not {processor_id}",
                code="processor_not_authorized",
            )
        return _ProbeRightsEvaluation(decision_id=f"decision.{source_id}")


class _RecordingCorpus:
    """Counts reads so a probe can assert the text was never opened."""

    def __init__(self, texts: Mapping[str, str]) -> None:
        self._texts = dict(sorted(texts.items()))
        self.reads: list[str] = []

    def read(self, source_id: str) -> bytes:
        self.reads.append(source_id)
        return self._texts[source_id].encode("utf-8")


_PRICING = create_pricing_snapshot(
    snapshot_id=OpaqueId("pricing.embedding.probe.v1"),
    provider="openai",
    model_identifier="text-embedding-probe",
    source="ADR-0069 probe fixture; project-authored, not a quoted rate",
    captured_at="2026-08-22T00:00:00Z",
    currency="USD",
    input_microusd_per_million_tokens=20_000,
    output_microusd_per_million_tokens=0,
)

_LIVE_KEY_DIMENSION = 4
_LIVE_MODEL = "text-embedding-probe"


def _live_configuration(
    *, processor_id: str = _PROBE_PROCESSOR, normalization: str = DEFAULT_NORMALIZATION,
) -> Any:
    return create_embedding_run_configuration(
        configuration_id="config.embedding.probe.v1",
        provider="openai",
        model_identifier=_LIVE_MODEL,
        dimension=_LIVE_KEY_DIMENSION,
        normalization=normalization,
        processor_id=processor_id,
        pricing_snapshot_id=_PRICING.snapshot_id.value,
        call_timeout_milliseconds=30_000,
        per_call_input_token_reserve=512,
        budget=EmbeddingBudget(
            max_calls=8, max_input_tokens=4_096, max_cost_microusd=1_000_000,
        ),
    )


_PROBE_TEXTS = {
    "source.alpha": "alpha source text for the ADR-0069 probe suite",
    "source.beta": "beta source text for the ADR-0069 probe suite",
}
_PROBE_VECTORS = {
    "alpha-doc": (0.5, 0.25, -0.125, 0.0),
    "beta-doc": (0.25, 0.5, 0.125, 0.0),
}


def _scripted_gateway(
    vectors: Mapping[str, Sequence[float]] | None = None,
) -> ScriptedEmbeddingGateway:
    return ScriptedEmbeddingGateway(
        provider="openai", model_identifier=_LIVE_MODEL,
        vectors=vectors if vectors is not None else _PROBE_VECTORS,
        input_tokens={"alpha-doc": 11, "beta-doc": 13},
    )


def _ingest(
    root: Path, *, gateway: Any | None = None, rights: Any | None = None,
    corpus: Any | None = None, configuration: Any | None = None,
    documents: Sequence[DocumentRequest] | None = None,
) -> Any:
    return ingest_partition(
        root=root,
        configuration=configuration or _live_configuration(),
        pricing=_PRICING,
        gateway=gateway or _scripted_gateway(),
        rights=rights or _ProbeFixtureRightsGate({
            "source.alpha": _PROBE_PROCESSOR, "source.beta": _PROBE_PROCESSOR,
        }),
        corpus=corpus or _RecordingCorpus(_PROBE_TEXTS),
        documents=documents or (
            DocumentRequest(document_id="alpha-doc", source_id="source.alpha"),
            DocumentRequest(document_id="beta-doc", source_id="source.beta"),
        ),
        run_id="run.embedding.probe.v1",
        recorded_at="2026-08-22T00:00:00Z",
        execute=True,
        acknowledgement=LIVE_EMBEDDING_ACKNOWLEDGEMENT,
    )


def _live_key(normalization: str = DEFAULT_NORMALIZATION) -> PartitionKey:
    return PartitionKey(
        provider="openai", model_identifier=_LIVE_MODEL,
        dimension=_LIVE_KEY_DIMENSION, normalization=normalization,
    )


def _fixture_key(
    *, model_identifier: str = "project-authored-v1", dimension: int = 3,
    normalization: str = DEFAULT_NORMALIZATION,
) -> PartitionKey:
    return PartitionKey(
        provider=FIXTURE_SYNTHETIC_PROVIDER, model_identifier=model_identifier,
        dimension=dimension, normalization=normalization,
    )


def _authored_vector(key: PartitionKey, document_id: str, coordinates: Sequence[int]) -> Any:
    return create_vector_artifact(
        key, document_id=document_id,
        source_content_hash=sha256_bytes(document_id.encode("utf-8")),
        coordinates=coordinates,
    )


def _partitioned(key: PartitionKey, document_id: str, coordinates: Sequence[int]) -> PartitionedVector:
    return PartitionedVector(
        partition_key=key, document_id=document_id, coordinates=tuple(coordinates),
    )


def _observe(action: Callable[[Path], None], workspace: Path) -> str:
    """Run a leg and report the refusal code it produced, or ``""``."""

    try:
        action(workspace)
    except EmbeddingError as error:
        return error.code
    return ""


# --------------------------------------------------------------------------
# probe legs
# --------------------------------------------------------------------------


def _similarity_pair(left_key: PartitionKey, right_key: PartitionKey) -> Callable[[Path], None]:
    def leg(_: Path) -> None:
        left = _partitioned(left_key, "alpha-doc", (1, 2, 3)[: left_key.dimension])
        right = _partitioned(right_key, "beta-doc", (3, 2, 1)[: right_key.dimension])
        cosine_terms_within_partition(left, right)

    return leg


def _no_fallback_baseline(workspace: Path) -> None:
    key = _fixture_key()
    write_partition(workspace, key, [_authored_vector(key, "alpha-doc", (1, 2, 3))])
    load_partition(workspace, key)


def _no_fallback_mutated(workspace: Path) -> None:
    key = _fixture_key()
    write_partition(workspace, key, [_authored_vector(key, "alpha-doc", (1, 2, 3))])
    # One component changed, nothing else. There is no fallback partition, so
    # this must fail closed rather than serve the neighbouring geometry.
    load_partition(workspace, _fixture_key(model_identifier="project-authored-v2"))


def _replay_no_call_baseline(workspace: Path) -> None:
    record = _ingest(workspace)
    gateway = ForbiddingEmbeddingGateway()
    _, report = replay_partition(
        workspace, _live_key(), gateway=gateway,
        expected_manifest_hash=record.manifest_hash,
    )
    if gateway.attempts != 0 or report["provider_calls"] != 0:
        raise EmbeddingError("replay touched a provider",
                             code="provider_call_forbidden")


def _replay_no_call_mutated(workspace: Path) -> None:
    # Fire the instrument: an ingestion against the forbidding gateway must be
    # loud. That is what makes the silent baseline meaningful.
    _ingest(workspace, gateway=ForbiddingEmbeddingGateway())


def _missing_artifact_baseline(workspace: Path) -> None:
    record = _ingest(workspace)
    replay_partition(workspace, _live_key(), expected_manifest_hash=record.manifest_hash)


def _missing_artifact_mutated(workspace: Path) -> None:
    _ingest(workspace)
    key = _live_key()
    (key.directory(workspace) / artifact_relative_path("beta-doc")).unlink()
    replay_partition(workspace, key)


def _overwrite_baseline(workspace: Path) -> None:
    key = _fixture_key()
    artifact = _authored_vector(key, "alpha-doc", (1, 2, 3))
    write_vector_artifact(workspace, key, artifact)
    # Identical bytes twice is idempotent, not a violation.
    write_vector_artifact(workspace, key, artifact)


def _overwrite_mutated(workspace: Path) -> None:
    key = _fixture_key()
    write_vector_artifact(workspace, key, _authored_vector(key, "alpha-doc", (1, 2, 3)))
    write_vector_artifact(workspace, key, _authored_vector(key, "alpha-doc", (1, 2, 4)))


def _rights_baseline(workspace: Path) -> None:
    corpus = _RecordingCorpus(_PROBE_TEXTS)
    _ingest(workspace, corpus=corpus)
    if len(corpus.reads) != 2:
        raise EmbeddingError("baseline did not read its sources", code="rights_blocked")


def _rights_mutated(workspace: Path) -> None:
    corpus = _RecordingCorpus(_PROBE_TEXTS)
    try:
        _ingest(workspace, corpus=corpus, rights=_ProbeFixtureRightsGate({}))
    finally:
        if corpus.reads:
            raise EmbeddingError(
                "the source was opened before the rights check",
                code="source_read_before_rights",
            )


def _processor_baseline(workspace: Path) -> None:
    _ingest(workspace, rights=_ProbeFixtureRightsGate({
        "source.alpha": _PROBE_PROCESSOR, "source.beta": _PROBE_PROCESSOR,
    }))


def _processor_mutated(workspace: Path) -> None:
    # The decision names processor A; the run is configured for processor B.
    _ingest(
        workspace,
        configuration=_live_configuration(processor_id=_OTHER_PROCESSOR),
        rights=_ProbeFixtureRightsGate({
            "source.alpha": _PROBE_PROCESSOR, "source.beta": _PROBE_PROCESSOR,
        }),
    )


_IMPURE_MODULE = (
    "def score(dot, norm):\n"
    "    scale = 1.0\n"
    "    return float(dot) / norm * scale\n"
)


def _read_path_baseline(_: Path) -> None:
    findings = sweep_read_path()
    if findings:
        raise ReadPathPurityError("; ".join(item.render() for item in findings))


def _read_path_mutated(_: Path) -> None:
    findings = sweep_source(_IMPURE_MODULE, module="deliberately_impure.py")
    if findings:
        raise ReadPathPurityError("; ".join(item.render() for item in findings))


def _saturation_baseline(workspace: Path) -> None:
    _ingest(workspace, gateway=_scripted_gateway({
        "alpha-doc": (1.0, -1.0, 0.5, 0.0), "beta-doc": (0.25, 0.5, 0.125, 0.0),
    }))


def _saturation_mutated(workspace: Path) -> None:
    root = workspace / "vectors"
    try:
        _ingest(root, gateway=_scripted_gateway({
            # One coordinate outside the declared scale. A fault, not a clamp.
            "alpha-doc": (1.5, 0.25, -0.125, 0.0),
            "beta-doc": (0.25, 0.5, 0.125, 0.0),
        }))
    finally:
        if (_live_key().directory(root) / MANIFEST_FILENAME).exists():
            raise EmbeddingError("a saturating run still wrote a manifest",
                                 code="saturated_run_persisted")


def _tie_order(descending_input: bool) -> tuple[str, ...]:
    key = _fixture_key(dimension=2)
    # Two DISTINCT vectors with exactly equal cosine against the query: the
    # query is (1, 1) and both candidates are unit-scaled reflections, so the
    # exact cosines coincide and only the tie-break can order them.
    candidates = [
        _partitioned(key, "aaa-doc", (3, 1)),
        _partitioned(key, "zzz-doc", (1, 3)),
    ]
    if descending_input:
        candidates.reverse()
    query = _partitioned(key, "query", (1, 1))
    return tuple(item[0] for item in rank_exact_cosine(query, candidates))


def _tie_baseline(_: Path) -> None:
    for descending in (False, True):
        ordering = _tie_order(descending)
        if ordering != tuple(sorted(ordering)):
            raise TieOrderError(
                f"tie ordering {ordering} is not document_id ascending"
            )


def _tie_mutated(_: Path) -> None:
    # Fire the instrument against the failure mode it exists to catch: an
    # insertion-ordered result over descending document ids.
    ordering = ("zzz-doc", "aaa-doc")
    if ordering != tuple(sorted(ordering)):
        raise TieOrderError(
            f"tie ordering {ordering} is not document_id ascending"
        )


def _output_tokens_baseline(workspace: Path) -> None:
    record = _ingest(workspace)
    payload = ingestion_record_payload(record)
    if payload["output_tokens"] != 0:
        raise EmbeddingError("baseline record claims output tokens",
                             code="output_tokens_not_zero")
    load_ingestion_record(json.loads(json.dumps(payload)))
    EmbeddingUsage(input_tokens=7)


def _output_tokens_mutated(workspace: Path) -> None:
    record = _ingest(workspace)
    payload = ingestion_record_payload(record)
    payload["output_tokens"] = 1
    load_ingestion_record(payload)


@dataclass(frozen=True, slots=True, kw_only=True)
class Probe:
    probe_id: str
    expected_code: str
    mutation_target: str
    detail: str
    baseline: Callable[[Path], None]
    mutated: Callable[[Path], None]


PROBES: tuple[Probe, ...] = (
    Probe(
        probe_id="pr.cross-partition-similarity-refused",
        expected_code="partition_mismatch:model_identifier",
        mutation_target="input",
        detail="a different embedding model is a different geometry",
        baseline=_similarity_pair(_fixture_key(), _fixture_key()),
        mutated=_similarity_pair(
            _fixture_key(), _fixture_key(model_identifier="project-authored-v2"),
        ),
    ),
    Probe(
        probe_id="pr.dimension-mismatch-refused",
        expected_code="partition_mismatch:dimension",
        mutation_target="input",
        detail="same provider and model, different dimension",
        baseline=_similarity_pair(_fixture_key(), _fixture_key()),
        mutated=_similarity_pair(_fixture_key(), _fixture_key(dimension=2)),
    ),
    Probe(
        probe_id="pr.normalization-mismatch-refused",
        expected_code="partition_mismatch:normalization",
        mutation_target="input",
        detail="proves the quantization scale is really in the partition key",
        baseline=_similarity_pair(_fixture_key(), _fixture_key()),
        mutated=_similarity_pair(
            _fixture_key(),
            _fixture_key(normalization="round_half_even_scale_2p20"),
        ),
    ),
    Probe(
        probe_id="pr.no-fallback-partition",
        expected_code="partition_absent",
        mutation_target="input",
        detail="an absent partition fails closed and never serves another one",
        baseline=_no_fallback_baseline,
        mutated=_no_fallback_mutated,
    ),
    Probe(
        probe_id="pr.rebuild-makes-no-provider-call",
        expected_code="provider_call_forbidden",
        mutation_target="instrument",
        detail="replay reproduces the manifest hash with a gateway that raises",
        baseline=_replay_no_call_baseline,
        mutated=_replay_no_call_mutated,
    ),
    Probe(
        probe_id="pr.missing-artifact-fails-closed",
        expected_code="artifact_missing",
        mutation_target="input",
        detail="a rebuild with one artifact removed fails, never re-embeds",
        baseline=_missing_artifact_baseline,
        mutated=_missing_artifact_mutated,
    ),
    Probe(
        probe_id="pr.artifact-overwrite-refused",
        expected_code="artifact_overwrite_refused",
        mutation_target="input",
        detail="identical bytes are idempotent; different bytes are refused",
        baseline=_overwrite_baseline,
        mutated=_overwrite_mutated,
    ),
    Probe(
        probe_id="pr.embedding-without-rights-refused",
        expected_code="rights_blocked",
        mutation_target="input",
        detail="refused before the source file is opened",
        baseline=_rights_baseline,
        mutated=_rights_mutated,
    ),
    Probe(
        probe_id="pr.embedding-wrong-processor-refused",
        expected_code="processor_not_authorized",
        mutation_target="input",
        detail="a decision naming processor A does not authorize processor B",
        baseline=_processor_baseline,
        mutated=_processor_mutated,
    ),
    Probe(
        probe_id="pr.no-float-in-retrieval-path",
        expected_code="float_on_read_path",
        mutation_target="instrument",
        detail=f"AST sweep of {', '.join(READ_PATH_MODULES)}",
        baseline=_read_path_baseline,
        mutated=_read_path_mutated,
    ),
    Probe(
        probe_id="pr.saturating-coordinate-halts",
        expected_code="coordinate_saturated",
        mutation_target="input",
        detail="a coordinate outside the declared scale halts, never clamps",
        baseline=_saturation_baseline,
        mutated=_saturation_mutated,
    ),
    Probe(
        probe_id="pr.tie-broken-by-document-id",
        expected_code="tie_order_not_document_id_ascending",
        mutation_target="instrument",
        detail="equal exact cosines order by document_id ascending",
        baseline=_tie_baseline,
        mutated=_tie_mutated,
    ),
    Probe(
        probe_id="pr.output-tokens-are-zero",
        expected_code="output_tokens_not_zero",
        mutation_target="input",
        detail="an ingestion record claiming nonzero output tokens is refused",
        baseline=_output_tokens_baseline,
        mutated=_output_tokens_mutated,
    ),
)


def run_probes() -> dict[str, Any]:
    """Run every probe in its own temporary workspace. Deterministic order."""

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for probe in PROBES:
        if probe.probe_id in seen:
            raise EmbeddingError(f"duplicate probe id {probe.probe_id}",
                                 code="probe_id_duplicated")
        seen.add(probe.probe_id)
        baseline_code = _run_leg(probe.baseline)
        mutated_code = _run_leg(probe.mutated)
        flipped = mutated_code == probe.expected_code and baseline_code != probe.expected_code
        results.append({
            "probe_id": probe.probe_id,
            "expected_code": probe.expected_code,
            "mutation_target": probe.mutation_target,
            "detail": probe.detail,
            "baseline_observed": baseline_code,
            "mutated_observed": mutated_code,
            "flipped": flipped,
        })
    results.sort(key=lambda item: item["probe_id"])
    return {
        "schema_version": PROBE_REPORT_SCHEMA_VERSION,
        "probes_total": len(results),
        "probes_flipped": sum(1 for item in results if item["flipped"]),
        "unflipped_probe_ids": sorted(
            item["probe_id"] for item in results if not item["flipped"]
        ),
        "read_path_modules": list(READ_PATH_MODULES),
        "probes": results,
        "creates_epistemic_warrant": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
    }


def _run_leg(leg: Callable[[Path], None]) -> str:
    workspace = Path(tempfile.mkdtemp(prefix="adaivy-embedding-probe."))
    try:
        return _observe(leg, workspace)
    except ProviderCallForbiddenError as error:  # pragma: no cover - subclass of EmbeddingError
        return error.code
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


__all__ = ["PROBES", "PROBE_REPORT_SCHEMA_VERSION", "Probe", "run_probes"]
