"""The deliverable is a bundle. The PDF is its readable face.

A third party rebuilds ``paper.pdf`` from ``paper.tex`` plus the pinned
toolchain, re-runs Lean from ``lean/`` plus the pinned commits, and re-derives
``paper.tex`` from ``records/``. Any of the three failing is detectable from
``MANIFEST.json`` alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import CANONICALIZATION_VERSION, POLICY_ID, POLICY_VERSION, SCHEMA_VERSION, SOURCE_DATE_EPOCH
from .bibliography import render_bibliography
from .errors import PublicationValidationError
from .manuscript import Manuscript
from .probes import run_probes
from .render import RenderedDocument, lean_artifact_filename, ledger_payload, render_manuscript
from .serialization import canonical_bytes, canonical_hash, sha256_bytes
from ..novelty import load_recheck

BUNDLE_SCHEMA_VERSION = "1.0.0"

README = """# AdaIvy publication bundle

The records in `records/` are the artifact of record. `paper.tex` is a
projection of them and `paper.pdf` is a build product of `paper.tex`. Nothing
flows back.

- `records/manuscript.json` is the canonical record set the projection read.
- `records/ledger.json` names every content block in `paper.tex` and the records
  backing it. `paper.tex` is exactly the frozen template plus these blocks.
- `records/evidence.json` records the computed evidence class of every claim and
  why. No input field selects an environment.
- `records/prior-art.json` records the derived prior-result/report
  classification, read from the manuscript's own prior-art engagement record and
  only then from an approval. An identified matching proof or refutation cannot be
  hidden behind the broader `novelty: not_assessed` status, and an unapproved
  draft carrying a real classification no longer reports `not_assessed`.
- `records/probes.json` records the falsifiability probes: single-field
  mutations of the manuscript, each of which must produce a named refusal or a
  named demotion.
- AI-authored builds also carry `records/campaign.json` and
  `records/publication-campaign-link.json`, the verified operational ledger and
  the exact claim/certificate join used to derive attribution and disclosure.
- `lean/` holds the content-hashed Lean source for every solved claim. Each
  paper claim links to its file and states whether checking is pending, failed,
  or kernel-checked.
- `build.json` pins the typesetting invocation. `typeset_status` is
  `not_typeset` until a compile has actually run; its absence is never a pass.
- `MANIFEST.json` hashes every file above, plus the manuscript, template and
  document hashes.

To re-derive the document:

    python3 -m math_research.cli publication render <manuscript.json> --output-dir <dir>

`document_hash` in `MANIFEST.json` must match. To typeset, see `build.json`.
"""


@dataclass(frozen=True, slots=True)
class PublicationBundle:
    manuscript_id: str
    document: RenderedDocument
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]

    @property
    def bundle_hash(self) -> str:
        return str(self.manifest["bundle_hash"])


def build_bundle(
    manuscript: Manuscript,
    *,
    toolchain: Mapping[str, Any] | None = None,
    record_files: Mapping[str, bytes] | None = None,
) -> PublicationBundle:
    document = render_manuscript(manuscript)
    probes = run_probes(manuscript)
    if probes["probes_flipped"] != probes["probes_total"]:
        unflipped = [item["probe_id"] for item in probes["probes"] if not item["flipped"]]
        raise PublicationValidationError(
            "probe_did_not_flip",
            f"{len(unflipped)} of {probes['probes_total']} probes did not flip: {unflipped}; a "
            "render rule with no reachable failure is a suite failure",
        )

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "claims": [
            {
                "claim_id": item.claim_id,
                "evidence_class": item.evidence_class,
                "environment": item.environment,
                "heading": item.heading,
                "reason": item.reason,
                "record_refs": list(item.record_refs),
                "approved_axioms": list(item.approved_axioms),
                "unapproved_assumptions": list(item.unapproved_assumptions),
            }
            for item in document.classifications
        ],
        "evidence_class_counts": dict(document.statistics["evidence_class_counts"]),
    }

    # ADR-0059 and amendment B7. The classification is keyed off the manuscript's
    # own prior-art engagement record, and only then off an approval. Keying it
    # off `publication_approval` left `records/prior-art.json` reading
    # `not_assessed` on every draft even when the manuscript carried a real
    # classification -- and a draft is exactly the artifact that circulates.
    approval = manuscript.value["publication_approval"]
    recheck = manuscript.prior_art_recheck()
    source = "prior_art_engagement"
    if recheck is None and approval is not None:
        recheck = load_recheck(approval["novelty_rechecks"][1])
        source = "publication_approval"
    if recheck is None:
        prior_art = {
            "status": "not_assessed",
            "source": "absent",
            "outcome": "not_assessed",
            "relationship": "not_assessed",
            "resolution": "not_assessed",
            "verification_status": "not_assessed",
            "report_classification": "not_assessed",
            "target_resolution_status": "not_assessed",
            "novelty_status": "not_assessed",
            "creates_mathematical_warrant": False,
            "recheck_id": None,
            "recheck_hash": None,
            "subject_id": None,
            "subject_hash": None,
        }
    else:
        prior_art = {
            "status": "recorded",
            "source": source,
            "outcome": recheck.outcome,
            "relationship": recheck.prior_art_relationship,
            "resolution": recheck.prior_resolution,
            "verification_status": recheck.prior_resolution_verification,
            **recheck.classification().payload(),
            "recheck_id": recheck.recheck_id,
            "recheck_hash": recheck.content_hash,
            "subject_id": recheck.subject_id,
            "subject_hash": recheck.subject_hash,
        }

    build = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "force_source_date": 1,
        "tex_entrypoint": "paper.tex",
        "typeset_status": "not_typeset",
        "pdf_sha256": None,
        "reproducibility_check": "two compiles must hash identically",
        "refusal_conditions": [
            "undefined reference",
            "undefined citation",
            "nonzero engine exit status",
            "differing hashes across the two compiles",
        ],
        "toolchain": dict(toolchain) if toolchain else None,
        "note": (
            "A skipped typeset step is never a pass. Until an engine has run, "
            "typeset_status stays not_typeset and pdf_sha256 stays null."
        ),
    }

    files: dict[str, bytes] = {
        "paper.tex": document.tex.encode("utf-8"),
        "refs.bib": render_bibliography(document.bibliography).encode("utf-8")
        if document.bibliography
        else b"% No acquisition record backs any citation in this document.\n",
        "records/manuscript.json": canonical_bytes(manuscript.value) + b"\n",
        "records/ledger.json": canonical_bytes(ledger_payload(document)) + b"\n",
        "records/evidence.json": canonical_bytes(evidence) + b"\n",
        "records/prior-art.json": canonical_bytes(prior_art) + b"\n",
        "records/probes.json": canonical_bytes(probes) + b"\n",
        "build.json": canonical_bytes(build) + b"\n",
        "README.md": README.encode("utf-8"),
    }
    for claim_id in sorted(manuscript.claims):
        claim = manuscript.claims[claim_id]
        artifact = claim["lean_artifact"]
        if artifact is None:
            continue
        path = f"lean/{lean_artifact_filename(claim)}"
        if path in files:
            raise PublicationValidationError(
                "lean_artifact_path_collision", f"more than one claim resolves to {path}"
            )
        files[path] = str(artifact["source"]).encode("utf-8")
    for path, data in sorted((record_files or {}).items()):
        if (
            not isinstance(path, str)
            or not path.startswith("records/")
            or path in files
            or ".." in Path(path).parts
            or not isinstance(data, bytes)
        ):
            raise PublicationValidationError(
                "publication_record_file_invalid", f"refused additional record {path!r}",
            )
        files[path] = data

    manifest: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "manuscript_id": manuscript.manuscript_id,
        "manuscript_hash": manuscript.hash,
        "template_hash": document.template_hash,
        "document_hash": document.document_hash,
        "headline": {
            "title_stem": document.headline.title_stem,
            "displayed_title": document.headline.displayed_title,
            "qualifiers": list(document.headline.qualifiers),
            "record_refs": list(document.headline.record_refs),
            "creates_mathematical_warrant": False,
        },
        "publication_approval": manuscript.value["publication_approval"],
        "run_disclosure": dict(manuscript.value["run_disclosure"]),
        "corpus_provenance": manuscript.value["corpus_provenance"],
        "novelty": dict(manuscript.value["novelty"]),
        "significance": dict(manuscript.value["significance"]),
        "prior_art": prior_art,
        "toolchain": dict(manuscript.value["toolchain"]),
        "statistics": dict(document.statistics),
        "evidence_class_counts": dict(document.statistics["evidence_class_counts"]),
        "probes_total": probes["probes_total"],
        "probes_flipped": probes["probes_flipped"],
        "typeset_status": build["typeset_status"],
        "pdf_sha256": build["pdf_sha256"],
        "files": [
            {"path": path, "sha256": sha256_bytes(files[path]), "bytes": len(files[path])}
            for path in sorted(files)
        ],
    }
    manifest["bundle_hash"] = canonical_hash(manifest)
    return PublicationBundle(
        manuscript_id=manuscript.manuscript_id, document=document, files=files, manifest=manifest,
    )


def write_bundle(bundle: PublicationBundle, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(bundle.files):
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bundle.files[path])
    manifest_bytes = json.dumps(bundle.manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (output_dir / "MANIFEST.json").write_bytes(manifest_bytes)
    return dict(bundle.manifest)


def verify_bundle(output_dir: Path) -> dict[str, Any]:
    """Recompute every file hash in a written bundle and refuse a mismatch."""

    manifest = json.loads((output_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    recorded = dict(manifest)
    bundle_hash = recorded.pop("bundle_hash")
    if canonical_hash(recorded) != bundle_hash:
        raise PublicationValidationError(
            "bundle_hash_mismatch", "MANIFEST.json does not hash to its own bundle_hash"
        )
    for entry in manifest["files"]:
        path = output_dir / str(entry["path"])
        if not path.exists():
            raise PublicationValidationError("bundle_file_missing", str(entry["path"]))
        data = path.read_bytes()
        if sha256_bytes(data) != entry["sha256"] or len(data) != entry["bytes"]:
            raise PublicationValidationError("bundle_file_hash_mismatch", str(entry["path"]))
    return manifest
