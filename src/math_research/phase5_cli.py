"""CLI for adaptive exact quantum-discrimination research and steering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase5.service import Phase5Service
from .phase5.workspace import Phase5Workspace, decode_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 adaptive quantum benchmark")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run the exact deterministic QD-FS-01 fixture")
    run.add_argument("workspace", type=Path)
    run.add_argument("fixture", type=Path)
    run.add_argument("recorded_at")
    run.add_argument("--output", type=Path)
    run.add_argument("--run-id")
    export = commands.add_parser("export", help="export the canonical Phase 5 workspace")
    export.add_argument("workspace", type=Path)
    export.add_argument("output", type=Path)
    inspect = commands.add_parser("inspect", help="inspect a record or canonical export")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--record-id")
    listed = commands.add_parser("list-results", help="list projected material partial results")
    listed.add_argument("workspace", type=Path)
    listed.add_argument("--run-id")
    steer = commands.add_parser("steer", help="append a human steering action")
    steer.add_argument("workspace", type=Path)
    steer.add_argument("event_id")
    steer.add_argument("action")
    steer.add_argument("idempotency_key")
    steer.add_argument("recorded_at")
    steer.add_argument("--target-objective-id")
    steer.add_argument("--target-branch-id")
    args = parser.parse_args(argv)

    if args.command == "inspect" and args.record_id is None:
        value = decode_json(args.path.read_bytes(), max_bytes=67_108_864)
        print(json.dumps({
            "schema_version": value.get("schema_version"),
            "content_hash": value.get("content_hash"),
            "record_count": len(value.get("records", [])),
            "material_result_count": len(value.get("material_results", [])),
        }, indent=2, sort_keys=True))
        return 0

    workspace_path = args.path if args.command == "inspect" else args.workspace
    with Phase5Workspace(workspace_path) as workspace:
        service = Phase5Service(workspace)
        if args.command == "run":
            fixture = decode_json(args.fixture.read_bytes())
            result = service.run_quantum_fixture(
                fixture, recorded_at=args.recorded_at, run_id=args.run_id,
            )
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "export":
            data = workspace.export_bytes()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name("." + args.output.name + ".tmp")
            temporary.write_bytes(data)
            workspace.save_verified_export(data)
            temporary.replace(args.output)
            print(json.dumps({"bytes": len(data), "content_hash": decode_json(data, max_bytes=67_108_864)["content_hash"]}, indent=2, sort_keys=True))
        elif args.command == "inspect":
            print(json.dumps(workspace.record(args.record_id), indent=2, sort_keys=True))
        elif args.command == "list-results":
            print(json.dumps(list(workspace.material_results(args.run_id)), indent=2, sort_keys=True))
        else:
            record = service.steer(
                event_id=args.event_id, action=args.action,
                principal_id="principal.phase5.owner", capability_id="capability.phase5.steer",
                idempotency_key=args.idempotency_key, recorded_at=args.recorded_at,
                target_objective_id=args.target_objective_id,
                target_branch_id=args.target_branch_id,
            )
            print(json.dumps({"record_id": record["record_id"], "content_hash": record["content_hash"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
