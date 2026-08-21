"""CLI for Phase 6 frozen confirmatory evaluation, replay ingest, and verification.

`replay` and `verify` are deliberately separate. `replay` INGESTS an export into
a workspace and checks only that the envelope is self-consistent. `verify` runs
the read-only clean-room re-derivation in `phase6.replay` and touches no
workspace at all. Collapsing them would hide that distinction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase5.service import Phase5Service
from .phase5.workspace import decode_json
from .phase6.replay import Phase6ReplayError, verify_release_bundle
from .phase6.service import Phase6Service
from .phase6.workspace import Phase6Workspace


def _write_outputs(output_dir: Path, result: dict[str, object], workspace: Phase6Workspace) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    release = dict(result)
    report = str(release.pop("report"))
    (output_dir / "release.json").write_text(
        json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "confirmatory-report.md").write_text(report, encoding="utf-8")
    data = workspace.export_bytes()
    workspace.save_verified_export(data)
    (output_dir / "phase6-export.json").write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 confirmatory evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="confirm an existing Phase 5 run")
    run.add_argument("workspace", type=Path)
    run.add_argument("protocol", type=Path)
    run.add_argument("phase5_fixture", type=Path)
    run.add_argument("phase5_run_id")
    run.add_argument("recorded_at")
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--generality-suite", type=Path, default=None)
    demo = commands.add_parser("demo", help="run the complete Phase 5 to Phase 6 workflow")
    demo.add_argument("workspace", type=Path)
    demo.add_argument("protocol", type=Path)
    demo.add_argument("phase5_fixture", type=Path)
    demo.add_argument("phase5_recorded_at")
    demo.add_argument("phase6_recorded_at")
    demo.add_argument("--output-dir", type=Path, required=True)
    demo.add_argument("--generality-suite", type=Path, default=None)
    export = commands.add_parser("export")
    export.add_argument("workspace", type=Path)
    export.add_argument("output", type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    replay = commands.add_parser(
        "replay", help="ingest an export into a workspace (envelope self-consistency only)"
    )
    replay.add_argument("workspace", type=Path)
    replay.add_argument("path", type=Path)
    verify = commands.add_parser(
        "verify",
        help="clean-room re-derivation of a release bundle; read-only, no workspace",
    )
    verify.add_argument("phase6_export", type=Path)
    verify.add_argument("phase5_export", type=Path)
    verify.add_argument("phase5_fixture", type=Path)
    args = parser.parse_args(argv)

    if args.command == "verify":
        try:
            verdict = verify_release_bundle(
                args.phase6_export.read_bytes(),
                args.phase5_export.read_bytes(),
                args.phase5_fixture.read_bytes(),
            )
        except Phase6ReplayError as error:
            # A rejection is preserved as machine-readable output, never a
            # silent pass and never a bare traceback.
            print(json.dumps(
                {"verified": False, "rejection": str(error)}, indent=2, sort_keys=True
            ))
            return 1
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return 0

    if args.command == "inspect":
        value = decode_json(args.path.read_bytes(), max_bytes=67_108_864)
        print(json.dumps({
            "schema_version": value.get("schema_version"),
            "content_hash": value.get("content_hash") or value.get("release_hash"),
            "record_count": len(value.get("records", [])),
            "status": value.get("confirmatory_result", {}).get("status") if isinstance(value.get("confirmatory_result"), dict) else None,
        }, indent=2, sort_keys=True))
        return 0

    with Phase6Workspace(args.workspace) as workspace:
        if args.command == "replay":
            value = workspace.save_verified_export(args.path.read_bytes())
            print(json.dumps({"content_hash": value["content_hash"], "records": len(value["records"])}, indent=2, sort_keys=True))
            return 0
        if args.command == "export":
            data = workspace.export_bytes()
            workspace.save_verified_export(data)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            print(json.dumps({"bytes": len(data), "content_hash": decode_json(data, max_bytes=67_108_864)["content_hash"]}, indent=2, sort_keys=True))
            return 0

        protocol = decode_json(args.protocol.read_bytes())
        fixture = decode_json(args.phase5_fixture.read_bytes())
        if args.command == "demo":
            phase5 = Phase5Service(workspace.phase5)
            phase5_result = phase5.run_quantum_fixture(fixture, recorded_at=args.phase5_recorded_at)
            phase5_run_id = phase5_result["run_id"]
            recorded_at = args.phase6_recorded_at
        else:
            phase5_run_id = args.phase5_run_id
            recorded_at = args.recorded_at
        result = Phase6Service(
            workspace, generality_suite_path=args.generality_suite,
        ).confirm(
            protocol=protocol, phase5_fixture=fixture,
            phase5_run_id=phase5_run_id, recorded_at=recorded_at,
        )
        _write_outputs(args.output_dir, result, workspace)
        summary = {
            "confirmatory_run_id": result["confirmatory_run_id"],
            "phase5_run_id": result["phase5_run_id"],
            "release_hash": result["release_hash"],
            "status": result["confirmatory_result"]["status"],
            "controls": f"{result['controls_passed']}/{result['controls_total']}",
            "probes_flipped": f"{result['probes_flipped']}/{result['probes_total']}",
            "generality_suite_hash": result["generality_suite_hash"],
            "positive_control_admitted": result["positive_control_admitted"],
            "control_corpus_provenance": result["control_corpus_provenance"],
            "heldout_accesses": result["heldout_accesses"],
            "material_result_count": result["material_result_count"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
