#!/usr/bin/env python3
"""Deterministic generator for the ``fixture_synthetic`` Phase 4C vector partition.

These are PROJECT-AUTHORED SYNTHETIC VECTORS. No embedding provider produced
them, they contain no third-party text, and they prove nothing whatever about
the quality of any real embedding model. They exist so the ADR-0066
semantic-signal slice has an offline partition to read, and so ADR-0065's
replay-from-bytes contract can be exercised with no credential, no socket and no
spend.

Licence of the produced fixtures: ``LicenseRef-AdaIvy-Synthetic-Fixture``.
Corpus provenance: ``project_authored`` (``fixtures/phase4c``, frozen at 19
documents and 17 gold queries).


The construction, stated in full
================================

The scheme is a **corpus co-occurrence projection onto deterministically chosen
anchor terms**. It is a distributional-semantics construction, which is the
honest low-dimensional analogue of an embedding: two texts are near each other
when their vocabulary keeps the same company across the corpus, not merely when
their surface tokens coincide.

Everything is exact rational arithmetic until a single half-to-even rounding at
the end. No float is constructed anywhere, and no float literal appears in this
file or in any file it writes.

1. **Tokenization.** Exactly the frozen Phase 4C tokenizer, mirrored here so the
   generator needs nothing but the standard library: Unicode NFC, whitespace runs
   collapsed to a single space, the token regex ``[^\\W_]+``, then
   ``str.casefold()``. ``--check-tokenizer`` re-derives every token sequence
   through ``math_research.phase4c.text.tokens`` and refuses on any
   disagreement, so the mirror cannot drift silently.

2. **Features.** Over the token sequence ``t[0..n-1]``:

   * a unigram feature ``"u\\x1f" + t[i]`` for every position ``i``;
   * a bigram feature ``"b\\x1f" + t[i] + "\\x1f" + t[i+1]`` for every adjacent
     pair.

   Occurrences are counted; duplicates are not collapsed.

3. **Document frequency and rational IDF.** ``df(f)`` is counted over the 19
   frozen corpus documents only. Gold queries are the read side and never
   contribute to it, so adding or removing a query cannot perturb a document
   vector. The term weight multiplier is the exact rational

       idf(f) = Fraction(DOCUMENT_COUNT + 1, df(f) + 1) = Fraction(20, df(f) + 1)

   a monotone-decreasing rational surrogate for a logarithmic IDF. A logarithm
   would be irrational and this repository does not put an irrational on a trust
   path. Features present in every document (``project``, ``authored``, ``the``)
   are damped to ``20/20 == 1``; a feature in one document carries ``20/2 == 10``;
   a query feature absent from the corpus carries ``20/1 == 20``.

4. **Anchor selection: the coordinate axes.** Each of the ``DIMENSION``
   coordinates is one *anchor term*, chosen from the corpus by a stated rule with
   no reference to any gold label, relevance judgement or gate metric:

   * the pool is every **unigram** feature with
     ``df(f) >= ANCHOR_MIN_DOCUMENT_FREQUENCY`` (that is, ``>= 2``). A ``df == 1``
     term co-occurs with nothing outside its single document, so its association
     column would be an indicator of that one document rather than a probe; two
     observations is the stated minimum for the association below to be
     estimated from more than a single document.
   * the pool is ordered by ``(df ascending, blake2b digest of the seeded
     feature, feature)`` and the first ``DIMENSION`` entries become coordinates
     ``0 .. DIMENSION - 1`` in that order. Lowest ``df`` first because a rare
     anchor draws the sharpest contrast between the documents that contain it and
     those that do not. BLAKE2b breaks ties rather than ``hash()``, which is
     salted per process by ``PYTHONHASHSEED`` and would destroy reproducibility.

   On the frozen corpus the pool holds 88 terms and all 32 selected anchors have
   ``df == 2``, so the selection is insensitive to any upper ``df`` bound; none is
   declared, and there is therefore no band parameter to tune.

5. **Signed rational association.** For a feature ``f`` and an anchor ``a``, let
   ``cooc(f, a)`` be the number of corpus documents containing both. The
   association is the observed conditional rate minus the anchor's marginal rate:

       assoc(f, a) = Fraction(cooc(f, a), df(f) + 1)
                   - Fraction(df(a), DOCUMENT_COUNT + 1)

   an exact signed rational surrogate for pointwise mutual information: positive
   when ``f`` keeps company with ``a`` more often than chance, negative when it
   avoids it. The same ``+1`` smoothing as the IDF denominator is used so a
   feature the corpus has never seen is well defined rather than a division by
   zero. Because the term is signed, vectors are not confined to the positive
   orthant and cosine retains its discriminating power.

6. **Projection.** For a text with feature counts ``count(f, text)``:

       accumulator[i] = sum over f of count(f, text) * idf(f) * assoc(f, anchor[i])

   accumulated as ``Fraction``, so the pre-rounding vector is exact.

7. **L-infinity normalization to the declared scale.** With
   ``m = max |accumulator[i]|``,

       coordinate[i] = round_half_even(accumulator[i] * 2**30 / m)

   evaluated in exact rational arithmetic and rounded half-to-even exactly once.
   L-infinity rather than L2 because an L2 norm needs a square root, which is not
   rational. Cosine similarity is invariant under independent positive rescaling
   of each vector, so this choice does not perturb the ranking the pre-rounding
   vectors induce; it only fixes the magnitude. The argmax coordinate lands on
   exactly +/- 2**30, the declared saturation bound. Anything beyond it halts,
   per ADR-0065's "a saturating coordinate is a fault, not a rounding detail".

8. **Partition key.** ``(provider, model_identifier, dimension, normalization)``
   exactly as ``TECHNICAL_BLUEPRINT.md:1661-1663`` requires. The quantization
   scale lives in ``normalization``, so changing ``2**30`` is a partition change
   and therefore a rebuild, which is the property ADR-0065 asks for. The
   construction lives in ``model_identifier``, so changing step 4, 5 or 6 is also
   a partition change.


A rejected first construction, recorded so it is not re-derived
==============================================================

The first authored construction was textbook **signed feature hashing**: place
each feature in one of ``DIMENSION`` buckets by BLAKE2b, sign it by a digest bit,
and accumulate ``sign * count * idf``. It was implemented, run, and measured, and
it FAILED the vocabulary-locality property that makes a fixture a plausible
stand-in for an embedding at all: measured property-1 AUC ``517/962 == 0.5374``,
against ``0.5`` for a coin flip.

The cause is structural rather than a bug. Corpus documents carry 40 to 74
distinct features and ``DIMENSION`` is 32, so every bucket holds roughly two
colliding features and the collision noise is the same order as the three-to-five
shared features that carry the signal. Signed hashing is unbiased but its
variance scales with ``||u||^2 ||v||^2 / DIMENSION``, and at ``DIMENSION == 32``
over a 700-feature space that variance simply swamps the inner product. No choice
of seed, sign rule or weighting repairs it; the construction was replaced rather
than retuned.

The replacement was selected on the label-blind property-1 and property-2
instruments below and on nothing else. No gold relevance judgement and no Phase
4C gate metric took any part in choosing it, and the vectors have not been
adjusted after any gate was read.


Hash convention
===============

``content_hash`` is computed over the canonical body with the hash field **set to
``None``** (serialized as ``null``), not popped. This differs deliberately from
``src/math_research/phase4c/serialization.py``, which pops. ADR-0065 artifacts
are a new record family; the rule is stated once here and applied uniformly to
the manifest and to every artifact, because mixing the two conventions changes
every hash. It is also recorded in the manifest as ``hash_rule``.
Canonicalization is otherwise identical to ``phase4c/serialization.py``:
``sort_keys=True``, ``separators=(",", ":")``, ``ensure_ascii=False``,
``allow_nan=False``, UTF-8, digest prefixed ``sha256:``. Each file on disk is the
canonical bytes plus one trailing newline; the newline is outside every preimage.


Artifact shape
==============

Every artifact carries ``schema_version``, ``artifact_kind``, ``document_id``,
``source_content_hash``, ``coordinates`` and ``content_hash``.

``artifact_kind`` is ``"document"`` for the 19 corpus artifacts and ``"query"``
for the 17 gold-query artifacts. It is **additive to** ``document_id``, not a
rename of it: a strict fail-closed loader must be able to establish that a gold
query is not a corpus document from the artifact bytes alone, without inferring
it from which manifest list the entry appeared in or from the directory the file
happened to sit in. ``document_id`` therefore still holds the corpus document id
or the gold query id as before.

``source_content_hash`` is ``sha256_bytes`` of the exact source bytes: the corpus
file bytes for a ``document`` (identical to what
``math_research.phase4c.fixtures.load_corpus`` computes for
``Document.source_hash``), and the UTF-8 encoding of the ``query`` string from
``gold-queries.json`` for a ``query``.


Usage
=====

    .venv/bin/python fixtures/phase4c-semantic/generate_fixture_vectors.py \\
        --write --check-tokenizer

    .venv/bin/python fixtures/phase4c-semantic/generate_fixture_vectors.py \\
        --verify --measure --check-tokenizer
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Declared constants. Every one is part of the partition identity or the stated
# construction. None is a tunable.
# --------------------------------------------------------------------------

PROVIDER = "fixture_synthetic"
MODEL_IDENTIFIER = "adaivy-cooccurrence-anchor-v1"
DIMENSION = 32
SCALE_EXPONENT = 30
SCALE = 2**SCALE_EXPONENT
NORMALIZATION = "round_half_even_scale_2p30"

ANCHOR_MIN_DOCUMENT_FREQUENCY = 2
HASH_SEED = "adaivy.phase4c-semantic.fixture_synthetic.v1"
FEATURE_SEPARATOR = "\x1f"
SEED_SEPARATOR = "\x1e"
UNIGRAM_PREFIX = "u" + FEATURE_SEPARATOR
BIGRAM_PREFIX = "b" + FEATURE_SEPARATOR

MANIFEST_SCHEMA_VERSION = "adaivy.vector-partition-manifest.v1"
ARTIFACT_SCHEMA_VERSION = "adaivy.vector-artifact.v1"
ARTIFACT_KINDS = ("document", "query")
FIXTURE_LICENSE = "LicenseRef-AdaIvy-Synthetic-Fixture"
CORPUS_PROVENANCE = "project_authored"
HASH_RULE = "content_hash_over_canonical_body_with_hash_field_set_to_null"

DOCUMENT_COUNT = 19
QUERY_COUNT = 17

MANIFEST_NAME = "manifest.json"
DOCUMENT_ARTIFACT_DIRECTORY = "artifacts/documents"
QUERY_ARTIFACT_DIRECTORY = "artifacts/queries"

TOKEN_PATTERN = r"[^\W_]+"
NORMALIZATION_FORM = "NFC"

HALF = Fraction(1, 2)


class GeneratorError(RuntimeError):
    """The single rejection type. Every check fails closed."""


# --------------------------------------------------------------------------
# Tokenizer: a mirror of src/math_research/phase4c/text.py, cross-checked by
# --check-tokenizer.
# --------------------------------------------------------------------------

_TOKEN = re.compile(TOKEN_PATTERN, re.UNICODE)


def normalize(text: str) -> str:
    return unicodedata.normalize(NORMALIZATION_FORM, " ".join(text.split()))


def tokens(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN.findall(normalize(text)))


# --------------------------------------------------------------------------
# Canonical serialization, mirroring phase4c/serialization.py except for the
# documented set-to-None hash rule.
# --------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def content_hash_of(body: dict[str, Any]) -> str:
    """Hash the body with ``content_hash`` set to ``None``, per ``HASH_RULE``."""

    preimage = dict(body)
    preimage["content_hash"] = None
    return sha256_bytes(canonical_bytes(preimage))


def sealed(body: dict[str, Any]) -> dict[str, Any]:
    result = dict(body)
    result["content_hash"] = content_hash_of(body)
    return result


def render(body: dict[str, Any]) -> bytes:
    return canonical_bytes(body) + b"\n"


# --------------------------------------------------------------------------
# Exact arithmetic.
# --------------------------------------------------------------------------


def round_half_even(value: Fraction) -> int:
    """Round an exact rational to the nearest integer, ties to even.

    Correct for negatives: ``-5/2`` floors to ``-3`` with remainder ``1/2``;
    ``-3`` is odd, so the result is ``-2``, which is even.

    The ``Fraction`` guard is load-bearing rather than decorative: it is the one
    place a float could enter the pipeline, and ``int / int`` in Python yields a
    float, so an accidental unwrapped division upstream would arrive here.
    """

    if not isinstance(value, Fraction):
        raise GeneratorError(
            f"round_half_even requires an exact Fraction, got "
            f"{type(value).__name__}; a float reached the quantization step"
        )
    floor = value.numerator // value.denominator
    remainder = value - floor
    if remainder < HALF:
        return floor
    if remainder > HALF:
        return floor + 1
    return floor if floor % 2 == 0 else floor + 1


def features(token_sequence: tuple[str, ...]) -> Counter[str]:
    counted: Counter[str] = Counter()
    for token in token_sequence:
        counted[UNIGRAM_PREFIX + token] += 1
    for left, right in zip(token_sequence, token_sequence[1:]):
        counted[BIGRAM_PREFIX + left + FEATURE_SEPARATOR + right] += 1
    return counted


def seeded_digest(feature: str) -> str:
    return hashlib.blake2b(
        (HASH_SEED + SEED_SEPARATOR + feature).encode("utf-8"), digest_size=16
    ).hexdigest()


def inverse_document_frequency(
    feature: str, document_frequency: Counter[str]
) -> Fraction:
    return Fraction(DOCUMENT_COUNT + 1, document_frequency[feature] + 1)


def select_anchors(
    document_frequency: Counter[str], feature_sets: dict[str, frozenset[str]]
) -> tuple[str, ...]:
    """The declared coordinate axes. See step 4 of the module docstring."""

    del feature_sets  # selection depends on document frequency alone
    pool = [
        feature
        for feature in document_frequency
        if feature.startswith(UNIGRAM_PREFIX)
        and document_frequency[feature] >= ANCHOR_MIN_DOCUMENT_FREQUENCY
    ]
    pool.sort(key=lambda f: (document_frequency[f], seeded_digest(f), f))
    if len(pool) < DIMENSION:
        raise GeneratorError(
            f"anchor pool holds {len(pool)} terms, fewer than the declared "
            f"dimension {DIMENSION}; the corpus cannot support this partition"
        )
    return tuple(pool[:DIMENSION])


def association_table(
    anchors: tuple[str, ...],
    document_frequency: Counter[str],
    feature_sets: dict[str, frozenset[str]],
) -> dict[tuple[str, str], Fraction]:
    """``assoc(f, a)`` for every feature and anchor. See step 5."""

    ordered_documents = sorted(feature_sets)
    anchor_documents = {
        anchor: frozenset(
            document
            for document in ordered_documents
            if anchor in feature_sets[document]
        )
        for anchor in anchors
    }
    table: dict[tuple[str, str], Fraction] = {}
    for feature in sorted(document_frequency):
        holders = frozenset(
            document
            for document in ordered_documents
            if feature in feature_sets[document]
        )
        for anchor in anchors:
            cooccurrence = len(holders & anchor_documents[anchor])
            table[(feature, anchor)] = Fraction(
                cooccurrence, document_frequency[feature] + 1
            ) - Fraction(document_frequency[anchor], DOCUMENT_COUNT + 1)
    return table


def project(
    counted: Counter[str],
    anchors: tuple[str, ...],
    document_frequency: Counter[str],
    table: dict[tuple[str, str], Fraction],
) -> tuple[Fraction, ...]:
    """Step 6. Unseen features fall back to the stated ``cooc == 0`` case."""

    marginal = {
        anchor: Fraction(document_frequency[anchor], DOCUMENT_COUNT + 1)
        for anchor in anchors
    }
    accumulator: list[Fraction] = []
    for anchor in anchors:
        total = Fraction(0)
        for feature in sorted(counted):
            association = table.get((feature, anchor))
            if association is None:
                association = -marginal[anchor]
            if association:
                total += (
                    Fraction(counted[feature])
                    * inverse_document_frequency(feature, document_frequency)
                    * association
                )
        accumulator.append(total)
    return tuple(accumulator)


def quantize(accumulator: tuple[Fraction, ...], label: str) -> tuple[int, ...]:
    """Step 7."""

    peak = max(abs(entry) for entry in accumulator)
    if peak == 0:
        raise GeneratorError(
            f"{label}: projects to the zero vector; there is nothing to embed"
        )
    coordinates = tuple(round_half_even(entry * SCALE / peak) for entry in accumulator)
    for offset, coordinate in enumerate(coordinates):
        if abs(coordinate) > SCALE:
            raise GeneratorError(
                f"{label}: coordinate {offset} saturated at {coordinate}, "
                f"declared bound is {SCALE}"
            )
    return coordinates


# --------------------------------------------------------------------------
# Exact integer similarity, as ADR-0065 specifies it: no sqrt, no division on
# the decision, no epsilon. Used for measurement only; never written to a file.
# --------------------------------------------------------------------------


def dot(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    if len(left) != len(right):
        raise GeneratorError("dimension mismatch in a similarity comparison")
    return sum(a * b for a, b in zip(left, right))


def cosine_squared_signed(left: tuple[int, ...], right: tuple[int, ...]) -> Fraction:
    """``sign(u.v) * (u.v)^2 / (|u|^2 |v|^2)``: exact and monotone in cosine."""

    product = dot(left, right)
    denominator = dot(left, left) * dot(right, right)
    if denominator == 0:
        raise GeneratorError("zero-norm vector in a similarity comparison")
    magnitude = Fraction(product * product, denominator)
    return magnitude if product >= 0 else -magnitude


# --------------------------------------------------------------------------
# Fixture inputs.
# --------------------------------------------------------------------------


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise GeneratorError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_bytes().decode("utf-8", "strict"),
        object_pairs_hook=reject_duplicate_keys,
    )


def load_inputs(
    corpus_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corpus = load_json(corpus_root / "corpus-manifest.json")
    gold = load_json(corpus_root / "gold-queries.json")

    documents: list[dict[str, Any]] = []
    for entry in corpus["documents"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise GeneratorError(f"{entry['id']}: fixture path escape")
        raw = (corpus_root / relative).read_bytes()
        documents.append(
            {
                "id": entry["id"],
                "duplicate_group": entry["duplicate_group"],
                "text": raw.decode("utf-8", "strict"),
                "tokens": tokens(raw.decode("utf-8", "strict")),
                "source_content_hash": sha256_bytes(raw),
            }
        )

    queries: list[dict[str, Any]] = []
    for entry in gold["queries"]:
        raw = entry["query"].encode("utf-8")
        queries.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "relevant_ids": tuple(entry["relevant_ids"]),
                "top_k": entry["top_k"],
                "text": entry["query"],
                "tokens": tokens(entry["query"]),
                "source_content_hash": sha256_bytes(raw),
            }
        )

    if len(documents) != DOCUMENT_COUNT:
        raise GeneratorError(
            f"corpus cardinality mismatch: {len(documents)} documents, "
            f"expected {DOCUMENT_COUNT}"
        )
    if len(queries) != QUERY_COUNT:
        raise GeneratorError(
            f"gold cardinality mismatch: {len(queries)} queries, "
            f"expected {QUERY_COUNT}"
        )
    if len({record["id"] for record in documents}) != DOCUMENT_COUNT:
        raise GeneratorError("duplicate document id")
    if len({record["id"] for record in queries}) != QUERY_COUNT:
        raise GeneratorError("duplicate query id")
    return documents, queries


def check_tokenizer(records: Iterable[dict[str, Any]]) -> None:
    try:
        from math_research.phase4c.text import tokens as reference_tokens
    except ImportError as error:  # pragma: no cover - environment dependent
        raise GeneratorError(
            "--check-tokenizer needs math_research importable; run with "
            "PYTHONPATH=src or from the installed venv"
        ) from error
    for record in records:
        if reference_tokens(record["text"]) != record["tokens"]:
            raise GeneratorError(
                f"{record['id']}: the mirrored tokenizer disagrees with "
                "math_research.phase4c.text.tokens"
            )


# --------------------------------------------------------------------------
# Build.
# --------------------------------------------------------------------------


def build(corpus_root: Path, check: bool) -> dict[str, Any]:
    documents, queries = load_inputs(corpus_root)
    if check:
        check_tokenizer(list(documents) + list(queries))

    document_features = {record["id"]: features(record["tokens"]) for record in documents}
    query_features = {record["id"]: features(record["tokens"]) for record in queries}
    feature_sets = {
        identifier: frozenset(bag) for identifier, bag in document_features.items()
    }

    document_frequency: Counter[str] = Counter()
    for bag in feature_sets.values():
        for feature in bag:
            document_frequency[feature] += 1

    anchors = select_anchors(document_frequency, feature_sets)
    table = association_table(anchors, document_frequency, feature_sets)

    document_vectors = {
        identifier: quantize(
            project(bag, anchors, document_frequency, table), identifier
        )
        for identifier, bag in sorted(document_features.items())
    }
    query_vectors = {
        identifier: quantize(
            project(bag, anchors, document_frequency, table), identifier
        )
        for identifier, bag in sorted(query_features.items())
    }
    return {
        "anchors": anchors,
        "documents": documents,
        "document_features": document_features,
        "document_frequency": document_frequency,
        "document_vectors": document_vectors,
        "queries": queries,
        "query_features": query_features,
        "query_vectors": query_vectors,
    }


def artifact_body(
    identifier: str,
    kind: str,
    source_content_hash: str,
    coordinates: tuple[int, ...],
) -> dict[str, Any]:
    """One vector artifact.

    ``artifact_kind`` is ``"document"`` or ``"query"``. It is additive to, not a
    rename of, ``document_id``: a strict loader must be able to tell that a gold
    query is not a corpus document without inferring it from which manifest list
    the entry appeared in, or from the artifact's directory.
    """

    if kind not in ARTIFACT_KINDS:
        raise GeneratorError(
            f"{identifier}: artifact_kind {kind!r} is not one of "
            f"{list(ARTIFACT_KINDS)}"
        )
    return sealed(
        {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_kind": kind,
            "document_id": identifier,
            "source_content_hash": source_content_hash,
            "coordinates": list(coordinates),
        }
    )


def plan(built: dict[str, Any]) -> dict[str, bytes]:
    """Relative path -> exact file bytes for the whole partition."""

    files: dict[str, bytes] = {}
    entries: dict[str, list[dict[str, Any]]] = {"documents": [], "queries": []}

    # `bucket` names the manifest list; `kind` is the artifact's own
    # `artifact_kind`. They are deliberately separate: the artifact must be
    # self-describing rather than relying on which list it was found in.
    for bucket, kind, directory, records, vectors in (
        (
            "documents",
            "document",
            DOCUMENT_ARTIFACT_DIRECTORY,
            built["documents"],
            built["document_vectors"],
        ),
        (
            "queries",
            "query",
            QUERY_ARTIFACT_DIRECTORY,
            built["queries"],
            built["query_vectors"],
        ),
    ):
        for record in sorted(records, key=lambda item: item["id"]):
            identifier = record["id"]
            body = artifact_body(
                identifier, kind, record["source_content_hash"], vectors[identifier]
            )
            relative = f"{directory}/{identifier}.json"
            payload = render(body)
            files[relative] = payload
            entries[bucket].append(
                {
                    "artifact_path": relative,
                    "artifact_sha256": sha256_bytes(payload),
                    "byte_length": len(payload),
                    "content_hash": body["content_hash"],
                    "document_id": identifier,
                    "source_content_hash": record["source_content_hash"],
                }
            )

    manifest = sealed(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "fixture_license": FIXTURE_LICENSE,
            "corpus_provenance": CORPUS_PROVENANCE,
            "corpus_fixture_root": "fixtures/phase4c",
            "generator": "fixtures/phase4c-semantic/generate_fixture_vectors.py",
            "hash_rule": HASH_RULE,
            "partition_key": {
                "dimension": DIMENSION,
                "model_identifier": MODEL_IDENTIFIER,
                "normalization": NORMALIZATION,
                "provider": PROVIDER,
            },
            "expected_counts": {
                "artifact_count": DOCUMENT_COUNT + QUERY_COUNT,
                "coordinate_bound_absolute": SCALE,
                "coordinates_per_artifact": DIMENSION,
                "document_count": DOCUMENT_COUNT,
                "query_count": QUERY_COUNT,
            },
            "documents": entries["documents"],
            "queries": entries["queries"],
        }
    )
    files[MANIFEST_NAME] = render(manifest)
    return files


# --------------------------------------------------------------------------
# Measurement. Reported, never fed back into the construction.
# --------------------------------------------------------------------------


def sparse_cosine_squared(
    left: Counter[str], right: Counter[str], document_frequency: Counter[str]
) -> Fraction:
    """Exact cosine^2 of the *unprojected* rational IDF feature vectors.

    This is the vocabulary-overlap ground truth the projection is meant to
    preserve. It reads no gold label. It is a measurement instrument only and no
    fixture byte depends on it.
    """

    def weight(bag: Counter[str], feature: str) -> Fraction:
        return Fraction(bag[feature]) * inverse_document_frequency(
            feature, document_frequency
        )

    numerator = sum(
        (
            weight(left, feature) * weight(right, feature)
            for feature in sorted(left)
            if feature in right
        ),
        Fraction(0),
    )
    left_norm = sum((weight(left, f) ** 2 for f in sorted(left)), Fraction(0))
    right_norm = sum((weight(right, f) ** 2 for f in sorted(right)), Fraction(0))
    if left_norm == 0 or right_norm == 0:
        return Fraction(0)
    return numerator * numerator / (left_norm * right_norm)


def approximately(value: Fraction, places: int = 4) -> str:
    """Decimal rendering via exact integer arithmetic. No float is constructed."""

    negative = value < 0
    value = -value if negative else value
    unit = 10**places
    scaled = round_half_even(value * unit)
    whole, part = divmod(scaled, unit)
    return f"{'-' if negative else ''}{whole}.{str(part).rjust(places, '0')}"


def measure(built: dict[str, Any]) -> None:
    document_frequency = built["document_frequency"]
    document_vectors = built["document_vectors"]
    query_vectors = built["query_vectors"]
    document_features = built["document_features"]
    query_features = built["query_features"]
    document_ids = sorted(document_features)
    queries = sorted(built["queries"], key=lambda item: item["id"])

    print("=" * 78)
    print("CONSTRUCTION")
    print("=" * 78)
    counts = [len(document_features[d]) for d in document_ids]
    print(f"  dimension                {DIMENSION}")
    print(f"  distinct corpus features {len(document_frequency)}")
    print(
        f"  features per document    min {min(counts)} max {max(counts)} "
        f"mean {sum(counts) // len(counts)}"
    )
    anchor_df = sorted({document_frequency[a] for a in built['anchors']})
    print(f"  anchor document frequencies present: {anchor_df}")
    print(
        "  anchors: "
        + ", ".join(a[len(UNIGRAM_PREFIX):] for a in built["anchors"][:8])
        + ", ..."
    )

    print()
    print("=" * 78)
    print("PROPERTY 1 -- is a query nearer to documents sharing its vocabulary")
    print("than to unrelated ones?")
    print("Instrument: for every query, every (sharing, unrelated) document pair,")
    print("where 'sharing' means nonzero unprojected IDF-feature overlap. No gold")
    print("label is read. 0.5000 is a coin flip.")
    print("=" * 78)

    auc_hits = 0
    auc_pairs = 0
    top1_agreements = 0
    for record in queries:
        identifier = record["id"]
        bag = query_features[identifier]
        truth = {
            document_id: sparse_cosine_squared(
                bag, document_features[document_id], document_frequency
            )
            for document_id in document_ids
        }
        projected = {
            document_id: cosine_squared_signed(
                query_vectors[identifier], document_vectors[document_id]
            )
            for document_id in document_ids
        }
        sharing = [d for d in document_ids if truth[d] > 0]
        unrelated = [d for d in document_ids if truth[d] == 0]
        hits = sum(
            1 for a in sharing for b in unrelated if projected[a] > projected[b]
        )
        pairs = len(sharing) * len(unrelated)
        auc_hits += hits
        auc_pairs += pairs
        truth_top = min(document_ids, key=lambda d: (-truth[d], d))
        projected_top = min(document_ids, key=lambda d: (-projected[d], d))
        if truth_top == projected_top:
            top1_agreements += 1
        print(
            f"  {identifier:<28} sharing={len(sharing):>2} unrelated="
            f"{len(unrelated):>2}  separated {hits:>3}/{pairs:<3} "
            f"({approximately(Fraction(hits, pairs))})"
        )
    print()
    print(
        f"  PROPERTY 1 AUC: {auc_hits}/{auc_pairs} = "
        f"{approximately(Fraction(auc_hits, auc_pairs))}   (coin flip 0.5000)"
    )
    print(f"  unprojected/projected top-1 agreement: {top1_agreements}/{QUERY_COUNT}")

    print()
    print("=" * 78)
    print("PROPERTY 2 -- do near-duplicate documents get near-identical vectors?")
    print("=" * 78)
    pairs_all = [
        (left, right)
        for index, left in enumerate(document_ids)
        for right in document_ids[index + 1 :]
    ]
    similarity = {
        pair: cosine_squared_signed(
            document_vectors[pair[0]], document_vectors[pair[1]]
        )
        for pair in pairs_all
    }
    ranked = sorted(pairs_all, key=lambda pair: (-similarity[pair], pair))
    groups: dict[str, list[str]] = {}
    for record in built["documents"]:
        if record["duplicate_group"] is not None:
            groups.setdefault(record["duplicate_group"], []).append(record["id"])
    for group, members in sorted(groups.items()):
        for index, left in enumerate(sorted(members)):
            for right in sorted(members)[index + 1 :]:
                pair = (left, right)
                print(f"  declared duplicate_group {group!r}: {left} / {right}")
                print(
                    f"    signed cosine^2 = {approximately(similarity[pair], 6)}, "
                    f"rank {ranked.index(pair) + 1} of {len(pairs_all)} document pairs"
                )
    print("  five most similar document pairs:")
    for pair in ranked[:5]:
        print(f"    {approximately(similarity[pair], 6)}  {pair[0]} :: {pair[1]}")

    print()
    print("=" * 78)
    print("SEMANTIC-SIGNAL-ONLY recall, reported UNADJUSTED. NOT a Phase 4C gate.")
    print("phase4c/semantic.py and the ADR-0066 fusion term do not exist yet; this")
    print("is the standalone behaviour of this partition and nothing here has been")
    print("tuned against it.")
    print("=" * 78)
    by_category: dict[str, list[int]] = {}
    for record in queries:
        projected = {
            document_id: cosine_squared_signed(
                query_vectors[record["id"]], document_vectors[document_id]
            )
            for document_id in document_ids
        }
        window = sorted(document_ids, key=lambda d: (-projected[d], d))[
            : record["top_k"]
        ]
        hits = sum(1 for gold in record["relevant_ids"] if gold in window)
        bucket = by_category.setdefault(record["category"], [0, 0])
        bucket[0] += hits
        bucket[1] += len(record["relevant_ids"])
        print(
            f"  {record['id']:<28} {record['category']:<22} "
            f"gold@{record['top_k']} = {hits}/{len(record['relevant_ids'])}"
        )
    print()
    for category in sorted(by_category):
        hits, total = by_category[category]
        print(
            f"  {category:<24} {hits}/{total} "
            f"({approximately(Fraction(hits, total))})"
        )


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate the fixture_synthetic Phase 4C vector partition."
    )
    parser.add_argument("--write", action="store_true", help="write the fixture files")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="regenerate in memory and refuse if any on-disk byte differs",
    )
    parser.add_argument(
        "--measure", action="store_true", help="print the property measurements"
    )
    parser.add_argument(
        "--check-tokenizer",
        action="store_true",
        help="cross-check the mirrored tokenizer against math_research.phase4c.text",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=here.parent / "phase4c",
        help="the frozen Phase 4C fixture directory",
    )
    parser.add_argument("--out", type=Path, default=here)
    arguments = parser.parse_args(argv)

    if not (arguments.write or arguments.verify or arguments.measure):
        parser.error("nothing to do: pass --write, --verify, or --measure")

    built = build(arguments.corpus_root.resolve(), arguments.check_tokenizer)
    files = plan(built)

    if arguments.write:
        for relative, payload in sorted(files.items()):
            target = arguments.out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        print(f"wrote {len(files)} files under {arguments.out}")

    if arguments.verify:
        problems: list[str] = []
        for relative, payload in sorted(files.items()):
            target = arguments.out / relative
            if not target.is_file():
                problems.append(f"missing: {relative}")
            elif target.read_bytes() != payload:
                problems.append(f"byte mismatch: {relative}")
        expected = {(arguments.out / relative).resolve() for relative in files}
        for existing in sorted((arguments.out / "artifacts").rglob("*.json")):
            if existing.resolve() not in expected:
                problems.append(f"unexpected artifact: {existing}")
        if problems:
            for problem in problems:
                print(f"FAIL {problem}", file=sys.stderr)
            return 1
        manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
        print(
            f"verified {len(files)} files byte-identical; "
            f"manifest content_hash={manifest['content_hash']}"
        )

    if arguments.measure:
        measure(built)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
