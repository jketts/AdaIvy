from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluator import load_json, run_evaluation
from .scorecard import write_correction
from .validation import validate_dossier


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 capability evaluation harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a ResearchDossier")
    validate_parser.add_argument("path", type=Path)
    evaluate_parser = subparsers.add_parser("evaluate", help="run all bounded component evaluations")
    evaluate_parser.add_argument("--report-dir", type=Path)
    subparsers.add_parser("scorecard", help="derive the corrected scorecard from immutable raw observations")
    subparsers.add_parser("check", help="validate the reference dossier and immutable Phase 0 evidence")
    args = parser.parse_args()

    if args.command == "validate":
        issues = validate_dossier(load_json(args.path))
        print(json.dumps([issue.as_dict() for issue in issues], indent=2))
        return 1 if issues else 0

    root = repository_root()
    if args.command in {"check", "scorecard"}:
        reference = root / "fixtures" / "phase0" / "reference-dossier.json"
        issues = validate_dossier(load_json(reference))
        if issues:
            print(json.dumps([issue.as_dict() for issue in issues], indent=2))
            return 1
        raw_path = root / "reports" / "phase-0" / "results.json"
        correction = write_correction(
            raw_path,
            root / "reports" / "phase-0" / "evaluation-correction.json",
            root / "reports" / "phase-0" / "scorecard.md",
        )
        print(json.dumps({"checks_passed": True, "components": len(correction["components"])}, indent=2))
        return 0
    else:
        payload = run_evaluation(root, args.report_dir)
    print(json.dumps({"checks_passed": payload["checks_passed"], "components": len(payload["components"])}, indent=2))
    return 0 if payload["checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
