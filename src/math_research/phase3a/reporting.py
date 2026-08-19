"""Deterministic traceable Phase 3A report rendering."""

from __future__ import annotations

import json
from typing import Mapping


def render_report(evidence: Mapping[str, object]) -> str:
    metrics = evidence["retrieval_metrics"]
    hashes = evidence["hashes"]
    quarantine = evidence["quarantine"]
    assert isinstance(metrics, Mapping) and isinstance(hashes, Mapping) and isinstance(quarantine, Mapping)
    lines = [
        "# Phase 3A Traceable Research-Memory Report",
        "",
        f"Schema version: `{evidence['schema_version']}`",
        f"Aggregate ID: `{evidence['aggregate_id']}`",
        "",
        "## Acceptance result",
        "",
        f"Status: **{evidence['status']}**",
        f"Network/model/external API calls: **{evidence['api_call_count']}**",
        f"Recall@5: `{metrics['recall_at_5']}` (required `1.0`)",
        f"MRR: `{metrics['mrr']}` (required `>= 0.75`)",
        f"Citation resolution precision: `{metrics['citation_resolution_precision']}` (required `1.0`)",
        f"Quarantined evidence retrieved: `{metrics['quarantined_evidence_retrieved']}` (required `0`)",
        f"Repeated/restart ordering stable: `{str(metrics['repeat_restart_stable']).lower()}`",
        "",
        "## Canonical hashes",
        "",
    ]
    for name in sorted(
        name for name in hashes
        if name not in {"traceable_report_hash", "acceptance_evidence_preimage_hash"}
    ):
        lines.append(f"- `{name}`: `{hashes[name]}`")
    lines.extend(["", "## Quarantine and licensing", ""])
    for name in sorted(quarantine):
        lines.append(
            f"- `{name}`: `{json.dumps(quarantine[name], ensure_ascii=False, separators=(',', ':'), sort_keys=True)}`"
        )
    lines.extend(
        [
            "",
            "The indexed corpus consists only of project-authored synthetic UTF-8 plain-text fixtures with explicit local retrieval and evidence-pack rights.",
            "The malformed PDF-shaped fixture and prompt-injection fixture remain immutable quarantined artifacts and produced no evidence units.",
            "The quantum-state-discrimination paper is an unresolved metadata-only locator with a null content hash; no paper bytes or extracted text are present.",
            "",
            "## Trust boundary",
            "",
            "Parser-derived evidence and scripted model-shaped claims remain proposals. Citation validation establishes exact pack membership only; it creates no warrant, closes no obligation, and does not establish applicability.",
            "",
            "## Scope stop",
            "",
            "No crawler, DNS/HTTP operation, embeddings, PDF extraction, model provider, external API, formal tool, Phase 3B feature, Phase 4 feature, or quantum convergence solver was invoked.",
            "",
        ]
    )
    return "\n".join(lines)
