"""Minimal manual CLI for the Phase 1 in-memory vertical slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .application.manual_slice import build_known_valid_theorem_dossier
from .domain.entities import ResearchDossier
from .domain.policies import TrustPolicy
from .domain.repositories import InMemoryTrustStore
from .interchange import export_dossier_dict, import_trusted_replay, write_dossier
from .reporting import render_traceable_report


def _summary(dossier: ResearchDossier) -> dict[str, object]:
    projection = TrustPolicy(dossier).target_resolution()
    payload = export_dossier_dict(dossier)
    return {
        "schema_version": "1.0.0",
        "dossier_id": dossier.id.value,
        "content_hash": payload["content_hash"],
        "target_claim_id": projection.claim_id.value,
        "logical_status": projection.logical_status,
        "semantic_alignment_status": projection.semantic_alignment_status,
        "blockers": list(projection.blockers),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual trust-core and durable baseline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="create the deterministic complete manual dossier")
    create.add_argument("output", type=Path)
    inspect = subparsers.add_parser("inspect", help="validate and inspect a canonical dossier")
    inspect.add_argument("path", type=Path)
    demo = subparsers.add_parser("demo", help="create, replay, and report the manual vertical slice")
    demo.add_argument("--output-dir", type=Path, required=True)
    phase2 = subparsers.add_parser("phase2", help="Phase 2 durable workspace commands")
    phase2.add_argument("phase2_args", nargs=argparse.REMAINDER)
    phase3a = subparsers.add_parser("phase3a", help="bounded Phase 3A research-memory commands")
    phase3a.add_argument("phase3a_args", nargs=argparse.REMAINDER)
    phase3b = subparsers.add_parser("phase3b", help="bounded Phase 3B Lean formal-checking commands")
    phase3b.add_argument("phase3b_args", nargs=argparse.REMAINDER)
    phase4a = subparsers.add_parser("phase4a", help="bounded Phase 4A local rights/review commands")
    phase4a.add_argument("phase4a_args", nargs=argparse.REMAINDER)
    phase5 = subparsers.add_parser("phase5", help="adaptive quantum benchmark and steering commands")
    phase5.add_argument("phase5_args", nargs=argparse.REMAINDER)
    phase6 = subparsers.add_parser("phase6", help="confirmatory evaluation and release commands")
    phase6.add_argument("phase6_args", nargs=argparse.REMAINDER)
    synthesis = subparsers.add_parser("synthesis", help="bounded exploratory synthesis commands")
    synthesis.add_argument("synthesis_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if args.command == "phase2":
        from .phase2_cli import main as phase2_main
        return phase2_main(args.phase2_args)
    if args.command == "phase3a":
        from .phase3a_cli import main as phase3a_main
        return phase3a_main(args.phase3a_args)
    if args.command == "phase3b":
        from .phase3b_cli import main as phase3b_main
        return phase3b_main(args.phase3b_args)
    if args.command == "phase4a":
        from .phase4a_cli import main as phase4a_main
        return phase4a_main(args.phase4a_args)
    if args.command == "phase5":
        from .phase5_cli import main as phase5_main
        return phase5_main(args.phase5_args)
    if args.command == "phase6":
        from .phase6_cli import main as phase6_main
        return phase6_main(args.phase6_args)
    if args.command == "synthesis":
        from .synthesis_cli import main as synthesis_main
        return synthesis_main(args.synthesis_args)

    if args.command == "create":
        dossier = InMemoryTrustStore().append_dossier(build_known_valid_theorem_dossier())
        write_dossier(dossier, args.output)
        print(json.dumps(_summary(dossier), indent=2, sort_keys=True))
        return 0
    if args.command == "inspect":
        dossier = import_trusted_replay(args.path.read_bytes())
        print(json.dumps(_summary(dossier), indent=2, sort_keys=True))
        return 0

    dossier = InMemoryTrustStore().append_dossier(build_known_valid_theorem_dossier())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dossier_path = args.output_dir / "manual-dossier.json"
    report_path = args.output_dir / "traceable-report.md"
    original_hash = write_dossier(dossier, dossier_path)
    replayed = import_trusted_replay(dossier_path.read_bytes())
    replay_hash = export_dossier_dict(replayed)["content_hash"]
    if original_hash != replay_hash or replayed != dossier:
        raise RuntimeError("canonical replay changed dossier identity or meaning")
    report_path.write_text(render_traceable_report(replayed), encoding="utf-8")
    summary = _summary(replayed)
    summary_path = args.output_dir / "demo-summary.json"
    summary.update({"round_trip_hash_preserved": True, "dossier_path": str(dossier_path), "report_path": str(report_path), "summary_path": str(summary_path)})
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
