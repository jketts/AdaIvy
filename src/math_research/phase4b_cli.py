"""Offline CLI for bounded Phase 4B candidate metadata.

Network acquisition remains behind a separately authorized, content-hashed
human-final plan and an explicit execution acknowledgement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase4a.content_store import read_interchange_file
from .phase4b.interchange import verify_export_bytes
from .phase4b.records import MAX_EXPORT_BYTES
from .phase4b.workspace import Phase4BWorkspace


def _summary(value: dict[str, object]) -> dict[str, object]:
    records = value["records"]
    projection = value["candidate_projection"]
    if not isinstance(records, list) or not isinstance(projection, list):
        raise ValueError("verified Phase 4B export collections are invalid")
    return {
        "profile": value["profile"],
        "content_hash": value["content_hash"],
        "operational_hash": value["operational_hash"],
        "records": len(records),
        "active_candidates": sum(
            item.get("current_state") == "active_candidate"
            for item in projection
            if isinstance(item, dict)
        ),
        "invalidated_candidates": sum(
            item.get("current_state") == "invalidated_candidate"
            for item in projection
            if isinstance(item, dict)
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 4B offline acquisition/parsing candidate metadata"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize and verify the local workspace")
    init.add_argument("workspace", type=Path)
    export = commands.add_parser("export", help="write a canonical candidate-metadata export")
    export.add_argument("workspace", type=Path)
    export.add_argument("output", type=Path)
    inspect = commands.add_parser("inspect", help="strictly verify and summarize an export")
    inspect.add_argument("path", type=Path)
    replay = commands.add_parser("replay", help="verify and import candidate metadata")
    replay.add_argument("workspace", type=Path)
    replay.add_argument("path", type=Path)
    rebuild = commands.add_parser("rebuild", help="rebuild and verify the derived projection")
    rebuild.add_argument("workspace", type=Path)
    gate = commands.add_parser(
        "gate", help="run feasible offline controls and report blocked activation controls"
    )
    gate.add_argument("repository", type=Path)
    gate.add_argument("workdir", type=Path)
    gate.add_argument("--output", type=Path)
    live_gate = commands.add_parser(
        "live-gate", help="verify a live-network plan without executing it by default"
    )
    live_gate.add_argument("plan", type=Path)
    live_gate.add_argument("--output", type=Path)
    live_gate.add_argument("--execute", action="store_true")
    live_gate.add_argument("--confirm-live-network")
    args = parser.parse_args(argv)

    if args.command == "inspect":
        data = read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES)
        print(json.dumps(_summary(verify_export_bytes(data)), indent=2, sort_keys=True))
        return 0

    if args.command == "gate":
        from .phase4b.gate import run_feasible_gate

        value = run_feasible_gate(args.repository, args.workdir)
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(data, encoding="utf-8")
        print(data, end="")
        return 0

    if args.command == "live-gate":
        from .phase4b.live_gate import (
            load_live_gate_plan, not_executed_report, run_live_gate,
        )
        from .phase4b.live_transport import (
            OptInHttpsTransport, OptInSystemResolver, SystemMonotonicClock,
        )

        plan = load_live_gate_plan(args.plan.read_bytes())
        if args.execute:
            if args.confirm_live_network != "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK":
                parser.error(
                    "--execute requires --confirm-live-network "
                    "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK"
                )
            value = run_live_gate(
                plan,
                resolver=OptInSystemResolver(plan.permit),
                transport=OptInHttpsTransport(plan.permit),
                start_clock=SystemMonotonicClock(),
            )
        else:
            if args.confirm_live_network is not None:
                parser.error("--confirm-live-network is valid only with --execute")
            value = not_executed_report(plan)
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(data, encoding="utf-8")
        print(data, end="")
        return 0

    with Phase4BWorkspace(args.workspace) as workspace:
        if args.command == "init":
            value = workspace.export_value()
        elif args.command == "export":
            data = workspace.export_bytes()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            value = verify_export_bytes(data)
        elif args.command == "replay":
            data = read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES)
            value = workspace.import_bytes(data)
        else:
            workspace.rebuild_projection()
            workspace.verify_integrity()
            value = workspace.export_value()
        print(json.dumps(_summary(value), indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
