"""Exploratory multi-result research synthesis (ADR-0025 / ADR-0027).

Implements the contract in `docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md`.
The package name is deliberately not `phase7`: the blueprint has no Phase 7, and
this slice is the separately gated Phase 5 exploratory expansion rather than a
new roadmap phase.

Boundaries this package does not cross, per the contract's Section 13: no
crawler, network access, remote-source adapter, HTML/TeX/PDF/OCR/archive parser,
embedding model, vector database, theorem prover, model call, or autonomous
multi-agent runtime. Retrieval reuses the existing Phase 3A FTS5/BM25 index.
"""

from __future__ import annotations

SCHEMA_VERSION = "adaivy.synthesis-record.v1"
EXPORT_VERSION = "adaivy.synthesis-workspace.v1"
POLICY_ID = "policy.synthesis-exploratory-v1"
POLICY_VERSION = "synthesis-exploratory-v1"
CANONICALIZATION_VERSION = "synthesis-canonical-json-v1"
ADMISSION_POLICY_VERSION = "synthesis-admission-v1"
COMPARISON_RULE_VERSION = "synthesis-composition-comparison-v2"
DUPLICATE_KEY_VERSION = "synthesis-duplicate-attempt-key-v1"

MAX_RECORDS = 8192
MAX_INPUT_BYTES = 2_097_152
MAX_EXPORT_BYTES = 67_108_864

__all__ = [
    "ADMISSION_POLICY_VERSION",
    "CANONICALIZATION_VERSION",
    "COMPARISON_RULE_VERSION",
    "DUPLICATE_KEY_VERSION",
    "EXPORT_VERSION",
    "MAX_EXPORT_BYTES",
    "MAX_INPUT_BYTES",
    "MAX_RECORDS",
    "POLICY_ID",
    "POLICY_VERSION",
    "SCHEMA_VERSION",
]
