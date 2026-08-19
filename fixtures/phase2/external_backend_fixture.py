"""Small deterministic executable fixture for the Phase 2 process adapter."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "success"
    root = Path(os.environ["ADAIVY_BACKEND_RUN_DIR"])
    dossier_bytes = (root / "input" / "dossier.json").read_bytes()
    dossier = json.loads(dossier_bytes)
    manifest_bytes = (root / "input" / "manifest.json").read_bytes()
    output = root / "output"
    artifacts = output / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    proposal = json.dumps(
        {
            "schema_version": "2.0.0",
            "kind": "proof_attempt",
            "statement": "External fixture proposes the standard even-sum derivation.",
            "disposition": "proposal"
        },
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    proposal_path = artifacts / "proposal.json"
    proposal_path.write_bytes(proposal)
    relative = "artifacts/proposal.json"
    observed_hash = digest(proposal)
    schema_version = "2.0.0"
    if mode == "bad-hash":
        observed_hash = "sha256:" + "0" * 64
    elif mode == "traversal":
        relative = "../escape.json"
    elif mode == "schema-mismatch":
        schema_version = "0.0.0"
    package = {
        "schema_version": schema_version,
        "input_dossier_hash": dossier["content_hash"],
        "input_manifest_hash": digest(manifest_bytes),
        "artifacts": [{
            "path": relative,
            "sha256": observed_hash,
            "kind": "proof_attempt",
            "target_claim_id": dossier["formalization"]["target_claim_id"],
        }],
    }
    (output / "package.json").write_text(
        json.dumps(package, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    if mode == "unexpected":
        (output / "unexpected.txt").write_text("not declared", encoding="utf-8")
    print(f"fixture mode={mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
