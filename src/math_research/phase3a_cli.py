"""Minimal offline CLI for the bounded Phase 3A slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase3a.demonstration import run_acceptance
from .phase3a.interchange import import_trusted_replay
from .phase3a.reporting import render_report
from .phase3a.serialization import canonical_bytes, sha256_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3A local research-memory CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the project-authored offline acceptance corpus")
    demo.add_argument("workspace", type=Path)
    demo.add_argument("--output-dir", type=Path, required=True)
    inspect = commands.add_parser("inspect", help="validate a canonical ResearchMemoryExport")
    inspect.add_argument("export", type=Path)
    report = commands.add_parser("report", help="regenerate a report from acceptance evidence")
    report.add_argument("acceptance", type=Path)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "demo":
        result = run_acceptance(args.workspace, args.output_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    if args.command == "inspect":
        replay = import_trusted_replay(args.export.read_bytes())
        summary = {
            "schema_version": "1.0.0", "id": replay.payload["id"], "content_hash": replay.content_hash,
            "record_count": len(replay.records), "canonical_bytes": len(replay.canonical_bytes),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    evidence = json.loads(args.acceptance.read_text(encoding="utf-8"))
    rendered = render_report(evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"schema_version": "1.0.0", "report_hash": sha256_bytes(rendered.encode("utf-8"))}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
