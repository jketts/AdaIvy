"""Bounded Phase 4C hybrid retrieval over the frozen benchmark fixtures.

Four deterministic offline signals, fused in score space: an FTS5/BM25 lexical
baseline, an exclusion-only evidentiary self-disclaimer signal, a content-keyed
alias expansion signal, and (ADR-0070) an exact-integer-cosine semantic signal
over one declared ADR-0065 vector partition. Standard library only, plus the
in-repo `embedding` read path. No network, no model call, no provider call, no
third-party dependency.

ADR-0070 adds the second of `TECHNICAL_BLUEPRINT.md` Section 7.3's seven
candidate-generation signals. Five remain unbuilt. The corpus, not the signal,
is the binding limit: nineteen documents with project-authored synthetic vectors
is a better-measured benchmark and never a literature search.

Scope per ADR-0031, ADR-0032 and ADR-0070: this package reads the
project-authored Phase 4C benchmark fixtures and one project-authored vector
partition replayed from bytes, and nothing else. It consumes no Phase 4B parse
projection, reads no Phase 4A rights decision, touches no deletable content or
protected evidence manifest, does not extend `RightsUse`, and computes no vector
of its own.

Retrieval is candidate generation. Nothing here creates an `EpistemicWarrant`,
approves semantic alignment, asserts source applicability, or sets novelty or
significance. Exclusion is not an applicability judgement: it removes a
candidate from one result list, and the excluded document stays in the report.
"""

from __future__ import annotations

from .benchmark import evaluate_hybrid, verify_report
from .bounds import BOUNDS, HybridRetrievalBounds, Phase4CValidationError, SCHEMA_VERSION
from .disclaimer import ABSENCE_OPERATORS, EVIDENCE_NOUNS, OBJECT_LEVEL_CUES
from .fixtures import AliasEntry, Document, GoldQuery, load_aliases, load_corpus, load_gold
from .probes import PROBE_REPORT_SCHEMA_VERSION, run_probes
from .semantic import (
    DisabledSemanticSignal,
    SemanticPartitionSignal,
    load_semantic_partition,
)

__all__ = [
    "ABSENCE_OPERATORS",
    "AliasEntry",
    "BOUNDS",
    "DisabledSemanticSignal",
    "Document",
    "EVIDENCE_NOUNS",
    "GoldQuery",
    "HybridRetrievalBounds",
    "OBJECT_LEVEL_CUES",
    "PROBE_REPORT_SCHEMA_VERSION",
    "Phase4CValidationError",
    "SCHEMA_VERSION",
    "SemanticPartitionSignal",
    "evaluate_hybrid",
    "load_aliases",
    "load_corpus",
    "load_gold",
    "load_semantic_partition",
    "run_probes",
    "verify_report",
]
