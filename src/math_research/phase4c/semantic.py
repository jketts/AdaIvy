"""Signal 4: exact-cosine semantic tiering over one replayed vector partition.

ADR-0070. This module is the second of `TECHNICAL_BLUEPRINT.md` Section 7.3's
seven candidate-generation signals. Five remain unbuilt, and that is the honest
measure of how far this architecture is from "wide".

ONE READER FOR THE PARTITION, AND IT IS NOT THIS MODULE. Everything here goes
through `embedding.partition.load_partition` and the accessors it returns:
`corpus_document_ids()`, `query_ids()`, `vector()`, `partitioned_vector()`. This
module opens no manifest, parses no artifact, and recomputes no artifact or
manifest hash. That is deliberate and it is the correction of a real defect: a
second parser for the same bytes diverges from the first, and the divergence
shows up as a partition that one reader accepts and the other refuses. So
ADR-0065 owns the schema, the hash rule, the fail-closed refusals and the
partition-isolation guarantee, and this module owns only the ranking.

Consequently NO HASH IS HARD-CODED anywhere in this slice. The manifest hash is
read off the loaded partition and carried into report identity; it is never
compared against a literal, because an ADR-0065 schema change legitimately moves
every artifact hash and the manifest hash with it.

WHAT IT READS. One declared partition, replayed from bytes on disk. It holds no
credential, opens no connection, and makes no provider call. The provider call
happened once, at ingestion, in a different process; retrieval replays the
integers it produced. `TECHNICAL_BLUEPRINT.md:1667-1671` requires exactly that,
and the Phase 4C zero-spend gate independently forbids the live call, so the two
constraints agree.

WHY THE QUERY VECTOR IS READ AND NEVER COMPUTED. Computing a query vector inside
`evaluate_hybrid` would need a provider, which is the rejected option in
ADR-0070's table. So a query is addressed by the identifier under which its
vector was frozen, and a query the partition does not carry is a refusal rather
than a query scored against a fallback.

WHAT IT CONTRIBUTES. Documents are ordered by EXACT integer cosine -- carried as
`(dot, |q|^2 * |d|^2)` and compared by cross-multiplying integers, so there is no
square root, no division, no epsilon, and a tie is decidable rather than machine
noise. Every comparison goes through `cosine_terms_within_partition`, which
refuses two operands from different partitions before it computes anything, so
partition isolation is enforced on each comparison and not merely at load time.
The top `BOUNDS.semantic_candidate_limit` ranks earn the frozen tier credit in
`bounds.SEMANTIC_TIERS`, and fusion adds `semantic_tier_points * tier_credit`.
The credit is a function of the RANK, so this signal cannot hand fusion a
magnitude of its own choosing, and its maximum contribution of three points sits
below ADR-0031's smallest measured BM25 gold margin.

EXACTNESS. No float is constructed here and nothing is divided, including path
composition: paths are built with `Path.joinpath` because a static sweep cannot
distinguish `pathlib`'s `/` from arithmetic, and an exception list is exactly
where a real division would eventually hide. `pr.semantic-no-float-constructed`
asserts the property over this module's own source text.

FAIL CLOSED. Every ADR-0065 refusal -- absent partition, unknown or missing
manifest field, duplicate JSON key, a decimal anywhere in the bytes, a manifest
or artifact hash mismatch, a missing artifact, a coordinate outside the declared
scale -- reaches a caller as `Phase4CValidationError` and nothing else. On top of
those this module refuses a partition whose cardinality is not the frozen Phase
4C corpus, one that claims provider provenance, and one that carries no query
vector for a gold query. There is no fallback partition and no degraded
three-signal mode.

WHAT THIS IS NOT. A vector is not evidence. A high cosine records that two texts
project near each other under one declared construction; it creates no
applicability record, no premise, no graph admission, and no warrant, and the
19-document corpus this reads is not a literature search.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..embedding.errors import EmbeddingError
from ..embedding.flat_fixture import load_flat_fixture_partition
from ..embedding.partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    Partition,
    PartitionKey,
)
from ..embedding.similarity import compare_cosine, cosine_terms_within_partition
from .bounds import (
    BOUNDS,
    MAXIMUM_SEMANTIC_TIER_CREDIT,
    Phase4CValidationError,
    SEMANTIC_PARTITION_DIMENSION,
    SEMANTIC_PARTITION_DIRNAME,
    SEMANTIC_PARTITION_MODEL_IDENTIFIER,
    SEMANTIC_PARTITION_NORMALIZATION,
    SEMANTIC_PARTITION_PROVIDER,
    semantic_tier_credit,
    semantic_tier_rule,
)
from .ports import SemanticCredit, SemanticPartitionIdentity

METHOD = "exact-integer-cosine-rank-tiering"
RANKING_RULE = "exact_cosine_desc_then_document_id_asc"
COMPARISON_RULE = "cross-multiplied-integers-no-sqrt-no-division-no-epsilon"
QUERY_VECTOR_RULE = "replayed-from-the-frozen-partition-never-computed-at-retrieval"
#: The single reader, named in the declared method so a reviewer can see that
#: this slice added no second parser for the artifact bytes.
PARTITION_READER = "math_research.embedding.flat_fixture.load_flat_fixture_partition"


@dataclass(frozen=True, slots=True)
class LoadedPartition:
    """The replayed partition and the identity observed from its bytes.

    The wrapper keeps the manifest identity explicit at the Phase 4C boundary
    without introducing a second parser.  Both fields originate in ADR-0065's
    single ``load_partition`` call.
    """

    partition: Partition
    manifest_hash: str


def declared_partition_key() -> PartitionKey:
    """The one declared partition. There is no default and no fallback."""

    try:
        return PartitionKey(
            provider=SEMANTIC_PARTITION_PROVIDER,
            model_identifier=SEMANTIC_PARTITION_MODEL_IDENTIFIER,
            dimension=SEMANTIC_PARTITION_DIMENSION,
            normalization=SEMANTIC_PARTITION_NORMALIZATION,
        )
    except EmbeddingError as error:
        raise Phase4CValidationError(
            f"the declared semantic partition key is invalid: {error}"
        ) from error


def default_partition_root(fixtures: Path) -> Path:
    """The partition ROOT for a Phase 4C fixture root: its sibling directory.

    A root, not a partition directory: ADR-0065 places a partition at
    `<root>/<partition_key_string>/`, and that layout is its rule rather than a
    choice made here. Derived from the fixture root rather than from the working
    directory, so a benchmark launched from anywhere reads the same partition or
    refuses.
    """

    return fixtures.parent.joinpath(SEMANTIC_PARTITION_DIRNAME)


def declared_method(
    identity: SemanticPartitionIdentity, *, semantic_tier_points: int
) -> dict[str, Any]:
    """Provenance built from the same constants that build the ranking."""

    return {
        "method": METHOD,
        "ranking": RANKING_RULE,
        "comparison": COMPARISON_RULE,
        "query_vector": QUERY_VECTOR_RULE,
        "partition_reader": PARTITION_READER,
        "parses_artifact_bytes": False,
        "recomputes_artifact_hashes": False,
        "constructs_float": False,
        "divides": False,
        "opens_a_connection": False,
        "calls_a_provider": False,
        "may_introduce_a_document": True,
        "exclusion_effect": "none",
        "candidate_limit": BOUNDS.semantic_candidate_limit,
        "semantic_tier_points": semantic_tier_points,
        "tiers": semantic_tier_rule(),
        "maximum_contribution": (
            semantic_tier_points * MAXIMUM_SEMANTIC_TIER_CREDIT
        ),
        "partition_key_string": identity.partition_key_string,
        "manifest_hash": identity.manifest_hash,
        "corpus_provenance": identity.corpus_provenance,
        "vector_count": identity.vector_count,
        "corpus_document_count": identity.corpus_document_count,
        "query_vector_count": identity.query_count,
        "is_evidence": False,
        "creates_applicability_record": False,
        "creates_epistemic_warrant": False,
    }


def load_semantic_partition(
    root: Path, *, declared_key: PartitionKey | None = None
) -> LoadedPartition:
    """Replay the declared partition through the ADR-0065 reader.

    This adds NO parsing. It selects the key, delegates every schema, hash and
    scale decision to `load_partition`, translates ADR-0065's coded refusals
    into the single Phase 4C rejection type, and then applies the checks that
    belong to Phase 4C rather than to the vector store: the frozen corpus
    cardinality and the project-authored provenance.

    `declared_key` exists so the mismatch branch is reachable from either side.
    Which of the manifest and the caller moved is not something this function
    can or should decide; it refuses either way.
    """

    key = declared_key or declared_partition_key()
    try:
        partition = load_flat_fixture_partition(root, key)
    except EmbeddingError as error:
        raise Phase4CValidationError(
            f"the semantic vector partition {key.key_string()} under {root} was "
            f"refused: {error}. A partition that cannot be replayed is a "
            "refusal, not a degradation to three signals, and there is no "
            "fallback partition"
        ) from error
    if not partition.is_project_authored:
        raise Phase4CValidationError(
            "the Phase 4C semantic partition must be project_authored; "
            f"{partition.corpus_provenance!r} would let synthetic vectors be "
            "read as provider evidence"
        )
    documents = partition.corpus_document_ids()
    queries = partition.query_ids()
    # Cardinality is part of the frozen Phase 4C contract, not a default: a
    # partition over a different number of documents is a partition over a
    # different corpus, and no gate measured on it is comparable.
    if len(documents) != BOUNDS.document_count:
        raise Phase4CValidationError(
            f"semantic partition has {len(documents)} corpus documents, the "
            f"frozen Phase 4C corpus has {BOUNDS.document_count}"
        )
    if len(queries) != BOUNDS.query_count:
        raise Phase4CValidationError(
            f"semantic partition has {len(queries)} query vectors, the frozen "
            f"Phase 4C gold set has {BOUNDS.query_count}"
        )
    return LoadedPartition(
        partition=partition,
        manifest_hash=partition.manifest_hash,
    )


class SemanticPartitionSignal:
    """A `SemanticSignal` over one replayed ADR-0065 partition."""

    signal_id = METHOD

    def __init__(self, loaded: LoadedPartition) -> None:
        self._partition = loaded.partition
        self._manifest_hash = loaded.manifest_hash
        # `document_ids()` is a SUPERSET that includes the query vectors. The
        # candidate pool is the corpus documents only: ranking a query against
        # the other queries would make a gold query id a retrieval feature.
        self._candidates = self._partition.corpus_document_ids()
        self._queries = frozenset(self._partition.query_ids())
        if len(self._candidates) > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError(
                f"semantic candidate pool {len(self._candidates)} exceeds "
                f"{BOUNDS.max_candidates_per_signal}"
            )
        for artifact_kind, expected in (
            (ARTIFACT_KIND_DOCUMENT, set(self._candidates)),
            (ARTIFACT_KIND_QUERY, set(self._queries)),
        ):
            if set(self._partition.ids_of_kind(artifact_kind)) != expected:
                raise Phase4CValidationError(
                    f"the partition's {artifact_kind} artifacts do not agree "
                    "with its own accessor"
                )

    def partition_identity(self) -> SemanticPartitionIdentity:
        return SemanticPartitionIdentity(
            partition_key_string=self._partition.key.key_string(),
            manifest_hash=self._manifest_hash,
            corpus_provenance=self._partition.corpus_provenance,
            vector_count=self._partition.vector_count,
            corpus_document_count=len(self._candidates),
            query_count=len(self._queries),
        )

    def _vector(self, identifier: str) -> Any:
        try:
            return self._partition.partitioned_vector(identifier)
        except EmbeddingError as error:
            raise Phase4CValidationError(
                f"{identifier} is not in partition "
                f"{self._partition.key.key_string()}: {error}"
            ) from error

    def ranked(self, query_id: str) -> tuple[tuple[str, tuple[int, int]], ...]:
        """Every candidate, exact cosine descending then `document_id` ascending.

        Ordered by insertion against `compare_cosine`, walking a list that is
        already in `document_id` ascending order and moving a candidate up only
        on a STRICTLY greater cosine. So an exact tie keeps `document_id`
        ascending, and the result depends on no set iteration order, no
        dictionary order, and no salted hash.
        """

        if query_id not in self._queries:
            raise Phase4CValidationError(
                f"no query vector for {query_id!r} in partition "
                f"{self._partition.key.key_string()}; a query vector is replayed "
                "and never computed inside the retrieval path"
            )
        query_vector = self._vector(query_id)
        ordered: list[tuple[str, tuple[int, int]]] = []
        for document_id in sorted(self._candidates):
            try:
                terms = cosine_terms_within_partition(
                    query_vector, self._vector(document_id)
                )
            except EmbeddingError as error:
                raise Phase4CValidationError(
                    f"exact cosine refused for {query_id!r} against "
                    f"{document_id!r}: {error}"
                ) from error
            position = len(ordered)
            while position > 0 and compare_cosine(terms, ordered[position - 1][1]) > 0:
                position -= 1
            ordered.insert(position, (document_id, terms))
        return tuple(ordered)

    def credits(self, query_id: str, *, limit: int) -> tuple[SemanticCredit, ...]:
        if limit < 1 or limit > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError(
                f"semantic candidate limit {limit} is outside "
                f"1..{BOUNDS.max_candidates_per_signal}"
            )
        ordered = self.ranked(query_id)
        credits: list[SemanticCredit] = []
        for index, (document_id, terms) in enumerate(ordered[:limit]):
            rank = index + 1
            credit = semantic_tier_credit(rank)
            if credit == 0:
                # Beyond the last tier the signal contributes nothing, so it
                # names nothing: a zero-credit candidate would enlarge the
                # candidate set without changing any score.
                break
            credits.append(
                SemanticCredit(
                    document_id=document_id,
                    rank=rank,
                    tier_credit=credit,
                    cosine_dot=terms[0],
                    cosine_norm_squared_product=terms[1],
                )
            )
        if len(credits) > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError("semantic candidate bound exceeded")
        return tuple(credits)


class DisabledSemanticSignal:
    """A `SemanticSignal` that reads no partition and credits nothing.

    This is the ADR-0070 "signal disabled" case, and it is recorded as a
    substituted signal rather than presented as an empty partition. With it
    installed every fused score equals the ADR-0032 three-signal value exactly,
    which `pr.semantic-disabled-is-a-true-noop` asserts.
    """

    signal_id = "disabled-semantic-signal"

    def partition_identity(self) -> SemanticPartitionIdentity:
        return SemanticPartitionIdentity(
            partition_key_string="none",
            manifest_hash=None,
            corpus_provenance="project_authored",
            vector_count=0,
            corpus_document_count=0,
            query_count=0,
        )

    def credits(self, query_id: str, *, limit: int) -> tuple[SemanticCredit, ...]:
        return ()


__all__ = [
    "COMPARISON_RULE",
    "DisabledSemanticSignal",
    "LoadedPartition",
    "METHOD",
    "PARTITION_READER",
    "QUERY_VECTOR_RULE",
    "RANKING_RULE",
    "SemanticPartitionSignal",
    "declared_method",
    "declared_partition_key",
    "default_partition_root",
    "load_semantic_partition",
]
