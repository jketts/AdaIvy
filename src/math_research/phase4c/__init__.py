"""Bounded Phase 4C hybrid retrieval over the frozen benchmark fixtures.

Three deterministic offline signals, fused in score space: an FTS5/BM25 lexical
baseline, an exclusion-only evidentiary self-disclaimer signal, and a
content-keyed alias expansion signal. Standard library only. No network, no
model call, no embedding, no vector, no third-party dependency.

Scope per ADR-0031 and ADR-0032: this package reads the project-authored
Phase 4C benchmark fixtures and nothing else. It consumes no Phase 4B parse projection, reads no
Phase 4A rights decision, touches no deletable content or protected evidence
manifest, and does not extend `RightsUse`.

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

__all__ = [
    "ABSENCE_OPERATORS",
    "AliasEntry",
    "BOUNDS",
    "Document",
    "EVIDENCE_NOUNS",
    "GoldQuery",
    "HybridRetrievalBounds",
    "OBJECT_LEVEL_CUES",
    "Phase4CValidationError",
    "SCHEMA_VERSION",
    "evaluate_hybrid",
    "load_aliases",
    "load_corpus",
    "load_gold",
    "verify_report",
]
