"""Bounded Phase 4C hybrid retrieval over the frozen benchmark fixtures.

Three deterministic offline signals, fused in score space: an FTS5/BM25 lexical
baseline, a demotion-only hedging-scope discrimination signal, and a
content-keyed alias expansion signal. Standard library only. No network, no
model call, no embedding, no vector, no third-party dependency.

Scope per ADR-0031: this package reads the project-authored Phase 4C benchmark
fixtures and nothing else. It consumes no Phase 4B parse projection, reads no
Phase 4A rights decision, touches no deletable content or protected evidence
manifest, and does not extend `RightsUse`.

Retrieval is candidate generation. Nothing here creates an `EpistemicWarrant`,
approves semantic alignment, asserts source applicability, or sets novelty or
significance.
"""

from __future__ import annotations

from .benchmark import evaluate_hybrid, verify_report
from .bounds import BOUNDS, HybridRetrievalBounds, Phase4CValidationError, SCHEMA_VERSION
from .fixtures import AliasEntry, Document, GoldQuery, load_aliases, load_corpus, load_gold
from .hedging import OBJECT_LEVEL_CUES, SELF_DISCLAIMING_CUES

__all__ = [
    "AliasEntry",
    "BOUNDS",
    "Document",
    "GoldQuery",
    "HybridRetrievalBounds",
    "OBJECT_LEVEL_CUES",
    "Phase4CValidationError",
    "SCHEMA_VERSION",
    "SELF_DISCLAIMING_CUES",
    "evaluate_hybrid",
    "load_aliases",
    "load_corpus",
    "load_gold",
    "verify_report",
]
