# `fixture_synthetic` vector partition for the ADR-0066 Phase 4C semantic signal

**These are project-authored synthetic vectors. No embedding provider produced
them. They prove nothing whatever about the quality of any real embedding model,
and no number measured on them may be reported as an embedding-quality result.**

They exist for one purpose: to give the ADR-0066 semantic-signal slice a
partition it can read entirely offline, so that ADR-0065's replay-from-bytes
contract, the exact-integer similarity path, and the Phase 4C zero-network and
zero-spend gates can all be exercised with no credential, no socket and no spend.

- Licence: `LicenseRef-AdaIvy-Synthetic-Fixture`
- Corpus provenance: `project_authored`
- Source corpus: `fixtures/phase4c`, frozen at 19 documents and 17 gold queries
  (`src/math_research/phase4c/fixtures.py` enforces `document_count == 19`
  exactly)

## Partition key

The blueprint's four-component tuple (`TECHNICAL_BLUEPRINT.md:1661-1663`),
verbatim:

| component | value |
|---|---|
| `provider` | `fixture_synthetic` |
| `model_identifier` | `adaivy-cooccurrence-anchor-v1` |
| `dimension` | `32` |
| `normalization` | `round_half_even_scale_2p30` |

`normalization` carries the quantization scale, so changing `2**30` is a
partition change and therefore a full rebuild. `model_identifier` carries the
construction, so changing the anchor rule, the association measure or the
projection is also a partition change. Neither can be altered quietly.

## Contents

```
manifest.json                          15117 bytes
artifacts/documents/<document_id>.json  19 files,  649-692 bytes each
artifacts/queries/<query_id>.json       17 files
generate_fixture_vectors.py            the generator
README.md                              this file
```

Manifest `content_hash`:

```
sha256:0011f3288f2429571528842b276b01a340254e5138e2ebb188a59a0cb2fbbb94
```

Declared counts, which are what a test should assert on
(`manifest.expected_counts`):

| key | value |
|---|---|
| `document_count` | 19 |
| `query_count` | 17 |
| `artifact_count` | 36 |
| `coordinates_per_artifact` | 32 |
| `coordinate_bound_absolute` | 1073741824 (`2**30`) |

Every coordinate is a JSON integer. There is no float, no `NaN` and no
`Infinity` anywhere in any fixture file, which is checked with a
`json.loads(..., parse_float=...)` hook rather than by eye.

## Artifact shape

Every artifact carries exactly six keys: `schema_version`, `artifact_kind`,
`document_id`, `source_content_hash`, `coordinates`, `content_hash`.

`artifact_kind` is `"document"` for the 19 corpus artifacts and `"query"` for the
17 gold-query artifacts. It is **additive to** `document_id`, not a rename of it:
a strict fail-closed loader must be able to establish that a gold query is not a
corpus document from the artifact bytes alone, without inferring it from which
manifest list the entry appeared in or from the directory the file happens to sit
in. `document_id` still holds the corpus document id or the gold query id.

`source_content_hash` is `sha256_bytes` of the exact source bytes: for a
`document`, the corpus file bytes, identical to what
`math_research.phase4c.fixtures.load_corpus` computes for `Document.source_hash`;
for a `query`, the UTF-8 encoding of the `query` string in `gold-queries.json`.

## Regenerating

Byte-identical regeneration, from the repository root:

```
PYTHONPATH=src .venv/bin/python \
    fixtures/phase4c-semantic/generate_fixture_vectors.py --write --check-tokenizer
```

Verifying the tree on disk without writing, and printing the property
measurements:

```
PYTHONPATH=src .venv/bin/python \
    fixtures/phase4c-semantic/generate_fixture_vectors.py \
    --verify --measure --check-tokenizer
```

`--verify` refuses on any byte difference, any missing artifact, and any
artifact present on disk that the generator did not plan. `--check-tokenizer`
re-derives every token sequence through `math_research.phase4c.text.tokens` and
refuses if the tokenizer mirrored inside the generator has drifted from the
frozen Phase 4C one; it is the only flag that needs `math_research` importable.
Without it the generator is standard-library-only.

Output is byte-identical under `PYTHONHASHSEED` in `{0, 1, 4242, random}` and
across fresh processes, because feature ordering is explicit and the only hash
used is BLAKE2b, never the salted built-in `hash()`.

## The construction

Stated in full, with its justification, in the module docstring of
`generate_fixture_vectors.py`. In brief: a **corpus co-occurrence projection onto
deterministically chosen anchor terms**, computed in exact `fractions.Fraction`
arithmetic and rounded half-to-even exactly once at the end.

1. Tokenize with the frozen Phase 4C tokenizer (NFC, `[^\W_]+`, `casefold`).
2. Features are unigrams and adjacent bigrams, counted.
3. `idf(f) = Fraction(20, df(f) + 1)` over the 19 corpus documents. Queries never
   contribute to `df`, so adding a query cannot perturb a document vector.
4. The 32 coordinate axes are *anchor terms*: unigrams with `df >= 2`, ordered by
   `(df ascending, seeded BLAKE2b digest, feature)`, first 32 taken.
5. Coordinate `i` accumulates `count(f) * idf(f) * assoc(f, anchor[i])`, where
   `assoc(f, a) = Fraction(cooc(f, a), df(f) + 1) - Fraction(df(a), 20)` is an
   exact signed rational surrogate for pointwise mutual information.
6. L-infinity normalize to `2**30` and round half-to-even. L-infinity rather than
   L2 because an L2 norm needs a square root, which is not rational.

Similarity for measurement is exact integer signed `cosine^2`, matching
ADR-0065: no square root, no epsilon, ties broken by `document_id` ascending.

### A first construction that was authored, measured and rejected

The first construction was textbook **signed feature hashing**. It was
implemented, run, and it failed the vocabulary-locality property outright:
property-1 AUC `517/962 = 0.5374`, against `0.5000` for a coin flip. The cause is
structural, not a bug: corpus documents carry 40-74 distinct features and the
dimension is 32, so collision noise is the same order as the three-to-five shared
features carrying the signal. It was **replaced, not retuned**, and the
replacement was chosen on the two label-blind property instruments below and on
nothing else. The failed attempt is recorded here so nobody re-derives it.

## Measured properties

Both are measured, not assumed. Reproduce with `--measure`.

**Property 1 — a query is nearer to documents sharing its vocabulary than to
unrelated ones.** Instrument: for every query, every ordered
`(sharing, unrelated)` document pair, where *sharing* means nonzero overlap in
the *unprojected* rational IDF feature space. This reads no gold label and no
gate metric; it asks only whether the projection preserves its own input
geometry.

```
PROPERTY 1 AUC: 748/962 = 0.7775   (coin flip 0.5000)
unprojected/projected top-1 agreement: 12/17
```

Property 1 **holds**. It is not perfect: per-query separation ranges from
`0.4167` (`renamed-known`) to `1.0000` (`applicability-spectral`), and the four
weakest queries are all renamed-known-result or notation cases, which is
consistent with the honest reading that a 19-document co-occurrence statistic is
thin evidence for bridging a name the corpus never uses.

**Property 2 — near-duplicate documents get near-identical vectors.**

```
duplicate_group 'dual-certificate'
  duplicate-certificate-a :: duplicate-certificate-b
  signed cosine^2 = 0.995698, rank 1 of 171 document pairs
next-most-similar pair: 0.533532  compactness-lemma :: separation-lemma
```

Property 2 **holds, emphatically**. The declared duplicate pair is the single
most similar pair in the corpus by a factor of nearly two over the runner-up.
This is not a nice result; it is precisely the `duplicate_rate_at_5` risk
ADR-0066 predicted, now made measurable.

## Unadjusted findings, recorded before anyone builds `semantic.py`

`src/math_research/phase4c/semantic.py`, `src/math_research/embedding/` and the
ADR-0066 fusion term do **not exist yet**. The numbers below are the standalone
behaviour of this partition ranked by exact cosine alone. They are **not** the
seven Phase 4C gates, which are measured on the fused four-signal score. Nothing
in the construction was adjusted after reading them.

Semantic-signal-only recall inside each query's own `top_k`:

| gold category | recall | note |
|---|---|---|
| `necessary_lemma` | 3/3 | |
| `applicability` | 14/14 | |
| `contradiction` | 2/2 | |
| `notation_variant` | 2/2 | |
| `renamed_known_result` | **2/4** | `renamed-known` and `renamed-container-count` both miss at `top_k = 10` |

Semantic-signal-only `duplicate_rate_at_5` analogue, computed with
`benchmark.py`'s own rule (a second member of a `duplicate_group` inside a
five-document window, over all windowed hits): **1/85 = 0.0118**, against the
declared maximum of `0.05`.

The `renamed_known_result` result is the finding worth carrying forward, because
it lands squarely on ADR-0066's recorded prediction that
`renamed_known_result_recall_at_10` would "improve or hold". On this partition,
standing alone, it does not: it reaches 0.5.

The reason is a genuine property of the frozen corpus, measured rather than
assumed. **All four** renamed controls have *exactly zero* direct vocabulary
overlap with their own gold document — unprojected IDF-feature cosine `0.0000`,
empty shared-feature set:

| query | gold document | overlap | rank of gold | inside `top_k = 10` |
|---|---|---|---|---|
| `renamed-maximal-chain` (`Kuratowski Zorn lemma`) | `renamed-maximal-chain-result` | 0.0000 | 7/19 | yes |
| `renamed-uniform-bound` (`Banach Steinhaus theorem`) | `renamed-uniform-bound-result` | 0.0000 | 10/19 | yes |
| `renamed-known` (`Borel Lebesgue theorem`) | `renamed-cover-result` | 0.0000 | 12/19 | **no** |
| `renamed-container-count` (`Dirichlet drawer principle`) | `renamed-container-count-result` | 0.0000 | 14/19 | **no** |

So these four are not merely hard, they are *lexically unreachable by
construction*: no shared token, no shared bigram, nothing for a term-overlap
signal to grip. The only route is second-order co-occurrence, and across 19
documents there is not enough co-occurrence evidence to carry two of the four.
That is a fact about a 19-document corpus, which is precisely the limit ADR-0066
names as binding, and it is why `name-aliases.json` and the ADR-0032 alias signal
exist for exactly these four cases. It is reported, not repaired: the
construction has not been touched since these numbers were read.

By contrast every one of the other 13 queries has nonzero overlap with each of
its gold documents (`0.0003` to `0.1212`) and every one of those golds lands
inside its `top_k`.

## What this partition does not license

It is not evidence. An artifact records that a text was projected by a declared
synthetic construction; it creates no applicability record, no premise, no graph
admission and no warrant. `NOVELTY_LANDSCAPE.md:62-64` governs. It does not widen
the corpus, and a benchmark measured on 19 synthetic documents with synthetic
vectors is a better-measured benchmark, never a literature search.
