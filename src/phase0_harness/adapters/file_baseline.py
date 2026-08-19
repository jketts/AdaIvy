from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..canonical import canonical_bytes, dossier_hash
from ..validation import validate_dossier


def evaluate(dossier: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / "research-dossier.json"
    first = canonical_bytes(dossier)
    export_path.write_bytes(first + b"\n")
    replayed = json.loads(export_path.read_text(encoding="utf-8"))
    second = canonical_bytes(replayed)
    issues = validate_dossier(replayed)
    replay_match = first == second and dossier_hash(replayed) == dossier["content_hash"]
    scores = {
        "target_fidelity": 2,
        "applicability_separation": 2,
        "obligations_and_failures": 2,
        "evidence_warrant_typing": 2,
        "exportability": 2,
        "replay_determinism": 2 if replay_match else 0,
        "verifier_reconstruction": 2,
        "local_offline": 2,
        "license_clarity": 0,
        "maintenance_evidence": 1,
        "security_boundary": 2,
        "setup_review_cost": 2,
    }
    return {
        "status": "succeeded" if not issues and replay_match else "failed",
        "summary": "Lossless canonical JSON round-trip; provides storage and replay, not mathematical verification.",
        "scores": scores,
        "hard_gates": ["repository_license_unresolved"],
        "evidence": {
            "export": str(export_path),
            "input_hash": dossier["content_hash"],
            "replay_hash": dossier_hash(replayed),
            "byte_stable": first == second,
            "validation_issues": [issue.as_dict() for issue in issues],
        },
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }

