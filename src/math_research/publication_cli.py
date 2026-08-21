"""CLI for the ADR-0036 publication projection.

``build`` is the supported solved-result path: it writes the bundle and compiles
the reproducible PDF in one fail-closed operation. ``render`` writes an
uncompiled diagnostic bundle. ``inspect`` reports a written bundle's manifest
after recomputing every file hash. ``probe`` runs the falsifiability suite
alone. ``typeset`` compiles a written bundle with the pinned toolchain and
refuses anything that is not byte-reproducible; without the toolchain it exits
non-zero and reports what is missing, because a skipped typeset step is never a
pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .publication import PublicationValidationError
from .publication.bundle import build_bundle, verify_bundle, write_bundle
from .publication.manuscript import read_manuscript
from .publication.production import produce_publication
from .publication.probes import run_probes
from .publication.typeset import load_toolchain, toolchain_status, typeset_bundle

DEFAULT_TOOLCHAIN = Path("config/publication-typeset-toolchain-v1.json")


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publication projection commands")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="project a manuscript into a publication bundle")
    render.add_argument("manuscript", type=Path)
    render.add_argument("--output-dir", type=Path, required=True)
    render.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    inspect = commands.add_parser("inspect", help="verify and report a written bundle")
    inspect.add_argument("bundle_dir", type=Path)
    probe = commands.add_parser("probe", help="run the falsifiability probe suite")
    probe.add_argument("manuscript", type=Path)
    typeset = commands.add_parser("typeset", help="compile a written bundle to a reproducible PDF")
    typeset.add_argument("bundle_dir", type=Path)
    typeset.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    build = commands.add_parser(
        "build", help="automatically project records, emit Lean, and compile the final PDF"
    )
    build.add_argument("manuscript", type=Path)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    build.add_argument("--campaign-export", type=Path)
    build.add_argument("--campaign-link", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "render":
            toolchain = load_toolchain(args.toolchain) if args.toolchain.exists() else None
            manuscript = read_manuscript(args.manuscript)
            bundle = build_bundle(manuscript, toolchain=toolchain)
            manifest = write_bundle(bundle, args.output_dir)
            _print({
                "manuscript_id": manifest["manuscript_id"],
                "manuscript_hash": manifest["manuscript_hash"],
                "document_hash": manifest["document_hash"],
                "bundle_hash": manifest["bundle_hash"],
                "evidence_class_counts": manifest["evidence_class_counts"],
                "probes_flipped": manifest["probes_flipped"],
                "probes_total": manifest["probes_total"],
                "typeset_status": manifest["typeset_status"],
                "files": len(manifest["files"]),
                "output_dir": str(args.output_dir),
            })
            return 0
        if args.command == "inspect":
            manifest = verify_bundle(args.bundle_dir)
            _print({
                "manuscript_id": manifest["manuscript_id"],
                "document_hash": manifest["document_hash"],
                "bundle_hash": manifest["bundle_hash"],
                "evidence_class_counts": manifest["evidence_class_counts"],
                "probes_flipped": manifest["probes_flipped"],
                "probes_total": manifest["probes_total"],
                "typeset_status": manifest["typeset_status"],
                "pdf_sha256": manifest["pdf_sha256"],
                "verified": True,
            })
            return 0
        if args.command == "probe":
            _print(run_probes(read_manuscript(args.manuscript)))
            return 0
        if args.command == "build":
            toolchain = load_toolchain(args.toolchain)
            campaign_value = (
                None if args.campaign_export is None
                else args.campaign_export.read_bytes()
            )
            campaign_link = (
                None if args.campaign_link is None
                else json.loads(args.campaign_link.read_text(encoding="utf-8"))
            )
            manifest = produce_publication(
                read_manuscript(args.manuscript), args.output_dir, toolchain,
                campaign_value=campaign_value, campaign_link=campaign_link,
            )
            _print({
                "manuscript_id": manifest["manuscript_id"],
                "bundle_hash": manifest["bundle_hash"],
                "document_hash": manifest["document_hash"],
                "typeset_status": manifest["typeset_status"],
                "pdf_sha256": manifest["pdf_sha256"],
                "output_dir": str(args.output_dir),
            })
            return 0
        toolchain = load_toolchain(args.toolchain)
        status = toolchain_status(toolchain)
        if not status.available:
            _print({
                "typeset_status": "not_typeset",
                "engine": status.engine,
                "reason": status.reason,
                "distribution_required": toolchain["distribution"],
                "packages_required": list(toolchain["packages_required"]),
                "note": "A skipped typeset step is never a pass.",
            })
            return 1
        _print(typeset_bundle(args.bundle_dir, toolchain))
        return 0
    except PublicationValidationError as error:
        _print({"refused": True, "code": error.code, "detail": error.detail})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
