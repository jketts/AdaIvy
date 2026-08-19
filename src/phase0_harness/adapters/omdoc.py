from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..canonical import canonical_bytes, dossier_hash
from ..validation import validate_dossier

OMDOC = "http://omdoc.org/ns"
XML = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("", OMDOC)


def _project(dossier: dict[str, Any]) -> ET.Element:
    root = ET.Element(f"{{{OMDOC}}}omdoc", {f"{{{XML}}}id": dossier["dossier_id"], "version": "1.2"})
    theory = ET.SubElement(root, f"{{{OMDOC}}}theory", {f"{{{XML}}}id": dossier["formalization"]["id"]})
    target_id = dossier["formalization"]["target_claim_id"]
    for claim in dossier["claims"]:
        assertion = ET.SubElement(
            theory,
            f"{{{OMDOC}}}assertion",
            {f"{{{XML}}}id": claim["id"], "type": claim["kind"], "status": claim["truth_status"]},
        )
        cmp_element = ET.SubElement(assertion, f"{{{OMDOC}}}CMP")
        cmp_element.text = claim["statement"]
        if claim["id"] == target_id:
            assertion.set("role", "target")
    for obligation in dossier["open_obligations"]:
        note = ET.SubElement(theory, f"{{{OMDOC}}}omtext", {f"{{{XML}}}id": obligation["id"], "type": "proof-obligation"})
        cmp_element = ET.SubElement(note, f"{{{OMDOC}}}CMP")
        cmp_element.text = obligation["description"]
    return root


def evaluate(dossier: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    xml_path = output_dir / "research-dossier.omdoc.xml"
    sidecar_path = output_dir / "research-dossier.sidecar.json"
    tree = ET.ElementTree(_project(dossier))
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    sidecar_path.write_bytes(canonical_bytes(dossier) + b"\n")

    parsed = ET.parse(xml_path).getroot()
    replayed = json.loads(sidecar_path.read_text(encoding="utf-8"))
    target = dossier["formalization"]["target_claim_id"]
    xml_target = parsed.find(f".//{{{OMDOC}}}assertion[@role='target']")
    xml_target_id = None if xml_target is None else xml_target.get(f"{{{XML}}}id")
    issues = validate_dossier(replayed)
    replay_match = dossier_hash(replayed) == dossier["content_hash"] and xml_target_id == target
    scores = {
        "target_fidelity": 2 if xml_target_id == target else 0,
        "applicability_separation": 1,
        "obligations_and_failures": 1,
        "evidence_warrant_typing": 1,
        "exportability": 2,
        "replay_determinism": 2 if replay_match else 0,
        "verifier_reconstruction": 1,
        "local_offline": 2,
        "license_clarity": 0,
        "maintenance_evidence": 1,
        "security_boundary": 2,
        "setup_review_cost": 2,
    }
    return {
        "status": "partial" if not issues and replay_match else "failed",
        "summary": "Statements and obligations project to OMDoc-shaped XML; full trust metadata requires the lossless JSON sidecar, so this is not claimed as complete OMDoc/MMT conformance.",
        "scores": scores,
        "hard_gates": ["format_license_unresolved", "xml_projection_is_lossy_without_sidecar"],
        "evidence": {
            "xml_export": str(xml_path),
            "sidecar_export": str(sidecar_path),
            "target_id_round_trip": xml_target_id,
            "sidecar_hash": dossier_hash(replayed),
            "validation_issues": [issue.as_dict() for issue in issues],
        },
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }
