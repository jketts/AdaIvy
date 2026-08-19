"""CLI for the bounded Phase 3B formal-checking slice."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .phase3b.adapter import DockerLeanAdapter
from .phase3b.demonstration import run_acceptance
from .phase3b.interchange import export_workspace, import_trusted_replay
from .phase3b.serialization import public_value
from .phase3b.service import FormalCheckingService
from .phase3b.workspace import FormalCheckWorkspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bounded Phase 3B Lean formal-checking commands")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate and check one restricted request")
    check.add_argument("request", type=Path)
    check.add_argument("--workspace", type=Path, required=True)
    check.add_argument("--export", type=Path)
    inspect = commands.add_parser("inspect", help="validate and summarize a canonical findings export")
    inspect.add_argument("path", type=Path)
    finding = commands.add_parser("finding", help="inspect one persisted proposal finding")
    finding.add_argument("workspace", type=Path)
    finding.add_argument("finding_id")
    demo = commands.add_parser("demo", help="run the bounded production acceptance cases")
    demo.add_argument("workspace", type=Path)
    demo.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "inspect":
        value = import_trusted_replay(args.path.read_bytes())
        print(json.dumps({"content_hash": value["content_hash"], "findings": len(value["findings"]), "outcomes": sorted(item["outcome"] for item in value["findings"])}, indent=2, sort_keys=True))
        return 0
    if args.command == "finding":
        with FormalCheckWorkspace(args.workspace) as workspace:
            print(json.dumps(workspace.finding(args.finding_id), indent=2, sort_keys=True))
        return 0
    if args.command == "demo":
        summary = run_acceptance(args.workspace, args.output_dir)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["status"] == "passed" else 1
    source = args.request.read_bytes()
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = FormalCheckingService(DockerLeanAdapter()).check(source, created_at=created_at)
    with FormalCheckWorkspace(args.workspace) as workspace:
        workspace.save_attempt(source, result)
        if args.export:
            export_workspace(workspace, args.export)
    print(json.dumps(public_value(result), indent=2, sort_keys=True))
    return 0 if result.outcome.value.startswith("kernel_checked") else 2


if __name__ == "__main__":
    raise SystemExit(main())

