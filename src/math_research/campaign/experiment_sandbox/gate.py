"""Command-line entry point for the separate, container-requiring ADR-0066 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...phase4b.oci_parser_sandbox import OciRuntimeIdentity
from ..records import canonical_bytes
from .activation import run_campaign_experiment_activation


def _runtime(path: Path) -> OciRuntimeIdentity:
    value = json.loads(path.read_text("utf-8"))["environment"]
    value["image_layers"] = tuple(value["image_layers"])
    return OciRuntimeIdentity(**value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("--phase4b-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = run_campaign_experiment_activation(
        args.repository_root, _runtime(args.phase4b_evidence),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    print(json.dumps({
        "content_hash": report["content_hash"],
        "output": str(args.output),
        "probes_flipped": report["probes_flipped"],
        "probes_total": report["probes_total"],
        "status": report["status"],
    }, sort_keys=True))
    return 0 if report["status"] == "activated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
