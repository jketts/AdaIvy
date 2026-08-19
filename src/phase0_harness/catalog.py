"""Frozen Phase 0 candidate catalog and score rubric."""

from __future__ import annotations

from typing import Any

WEIGHTS = {
    "target_fidelity": 3,
    "applicability_separation": 3,
    "obligations_and_failures": 3,
    "evidence_warrant_typing": 3,
    "exportability": 2,
    "replay_determinism": 2,
    "verifier_reconstruction": 2,
    "local_offline": 1,
    "license_clarity": 2,
    "maintenance_evidence": 1,
    "security_boundary": 2,
    "setup_review_cost": 1,
}


def empty_scores(*, license_clarity: int = 0, maintenance_evidence: int = 0) -> dict[str, int]:
    scores = {criterion: 0 for criterion in WEIGHTS}
    scores["license_clarity"] = license_clarity
    scores["maintenance_evidence"] = maintenance_evidence
    return scores


CANDIDATES: tuple[dict[str, Any], ...] = (
    {"id": "file-baseline", "name": "File baseline", "category": "baseline", "adapter": "file", "recommendation": "build", "license": "UNLICENSED repository"},
    {"id": "omdoc-projection", "name": "OMDoc concept projection", "category": "representation", "adapter": "omdoc", "recommendation": "interoperate", "license": "format artifact licensing unresolved"},
    {"id": "albilich", "name": "Albilich", "category": "proof_state", "adapter": "albilich", "recommendation": "interoperate", "license": "Apache-2.0", "license_score": 2, "maintenance_score": 2},
    {"id": "mathgraph", "name": "MathGraph", "category": "proof_state", "recommendation": "defer", "license": "NOASSERTION", "maintenance_score": 2, "hard_gates": ["license_absent"]},
    {"id": "mmt", "name": "MMT", "category": "representation", "recommendation": "interoperate", "license": "custom-no-modification", "license_score": 2, "maintenance_score": 2, "hard_gates": ["modification_not_permitted"]},
    {"id": "why3", "name": "Why3", "category": "obligation_dispatch", "adapter": "why3", "recommendation": "wrap", "license": "LGPL-2.1", "license_score": 2, "maintenance_score": 2},
    {"id": "lean", "name": "Lean 4", "category": "formal_tool", "adapter": "lean", "recommendation": "wrap", "license": "Apache-2.0", "license_score": 2, "maintenance_score": 2},
    {"id": "leandojo", "name": "LeanDojo", "category": "lean_retrieval", "recommendation": "defer", "license": "MIT", "license_score": 2, "maintenance_score": 1, "hard_gates": ["host_python_unsupported", "deprecated_generation"]},
    {"id": "leansearch-v2", "name": "LeanSearch v2", "category": "lean_retrieval", "recommendation": "defer", "license": "Apache-2.0", "license_score": 2, "maintenance_score": 2, "hard_gates": ["gpu_and_model_prerequisites_unavailable"]},
    {"id": "paperqa2", "name": "PaperQA2", "category": "literature", "adapter": "paperqa", "recommendation": "wrap", "license": "Apache-2.0", "license_score": 2, "maintenance_score": 2},
    {"id": "eigenius", "name": "Eigenius", "category": "typed_provenance", "recommendation": "interoperate", "license": "Apache-2.0", "license_score": 2, "maintenance_score": 2, "hard_gates": ["local_toolchain_unavailable"]},
    {"id": "astra", "name": "ASTRA", "category": "research_system", "recommendation": "defer", "license": "NOASSERTION", "maintenance_score": 2, "hard_gates": ["license_absent", "host_python_unsupported"]},
    {"id": "rma", "name": "RMA", "category": "research_system", "recommendation": "defer", "license": "no_public_code", "maintenance_score": 1, "hard_gates": ["implementation_unavailable"]},
    {"id": "aletheia", "name": "Aletheia", "category": "research_system", "recommendation": "defer", "license": "no_public_code", "maintenance_score": 1, "hard_gates": ["implementation_unavailable"]},
    {"id": "alphaproof-nexus", "name": "AlphaProof Nexus", "category": "lean_agent", "recommendation": "defer", "license": "no_public_code", "maintenance_score": 1, "hard_gates": ["implementation_unavailable"]},
    {"id": "proofatlas", "name": "ProofAtlas", "category": "proof_state", "recommendation": "defer", "license": "no_reusable_code_identified", "maintenance_score": 1, "hard_gates": ["implementation_unavailable"]},
    {"id": "funsearch", "name": "FunSearch", "category": "executable_discovery", "recommendation": "defer", "license": "Apache-2.0/CC-BY-4.0", "license_score": 2, "maintenance_score": 1, "hard_gates": ["omits_model_and_sandbox"]},
    {"id": "alphaevolve", "name": "AlphaEvolve", "category": "executable_discovery", "recommendation": "defer", "license": "no_public_official_code", "maintenance_score": 1, "hard_gates": ["implementation_unavailable"]},
    {"id": "agentic-researcher", "name": "The Agentic Researcher", "category": "file_workflow", "recommendation": "reference", "license": "method/paper", "maintenance_score": 1, "hard_gates": ["not_a_component"]},
)


def weighted_score(scores: dict[str, int]) -> float:
    numerator = sum(scores[criterion] * weight for criterion, weight in WEIGHTS.items())
    denominator = 2 * sum(WEIGHTS.values())
    return round(numerator / denominator * 100, 1)

