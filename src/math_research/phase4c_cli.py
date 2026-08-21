"""Offline CLI for the bounded Phase 4C hybrid-retrieval benchmark.

Standard library only. No network, no model call, no process spawning, no
embedding, no vector.

Exit status:

* `0` -- the command succeeded and every gate passed;
* `1` -- a measured failure: a gate reported `fail` or `undetermined`, or a
  report failed hash verification. The report is still emitted, because hiding
  a failed query or a failed gate is a forbidden outcome;
* `2` -- missing or invalid input: a fixture, bound, or schema rejection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .phase4c.benchmark import evaluate_hybrid, verify_report
from .phase4c.bounds import BOUNDS, Phase4CValidationError
from .phase4c.fixtures import reject_duplicate_keys
from .phase4c.serialization import canonical_bytes

DEFAULT_FIXTURES = Path("fixtures/phase4c")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    """A projection, not a full dump."""

    results = report["results"]
    gates = report["gate_evaluation"]
    return {
        "schema_version": report["schema_version"],
        "method": report["method"],
        "content_hash": report["content_hash"],
        "operational_hash": report["operational_hash"],
        "corpus_manifest_hash": report["corpus_manifest_hash"],
        "gold_queries_hash": report["gold_queries_hash"],
        "name_aliases_hash": report["name_aliases_hash"],
        "resource_policy_sha256": report["resource_bounds"]["policy_sha256"],
        "queries": len(results),
        "zero_hit_query_ids": report["zero_hit_query_ids"],
        "queries_with_missed_relevant_ids": sorted(
            item["id"] for item in results if item["missed_relevant_ids"]
        ),
        "queries_with_duplicate_hits": sorted(
            item["id"] for item in results if item["duplicate_ids_at_5"]
        ),
        "queries_with_inapplicable_hits": sorted(
            item["id"] for item in results if item["inapplicable_retrieved_ids"]
        ),
        "queries_with_suppressions": sorted(
            item["id"] for item in results if item["suppressed_ids"]
        ),
        "suppressed_inapplicable_ids": sorted(
            {
                identifier
                for item in results
                for identifier in item["suppressed_inapplicable_ids"]
            }
        ),
        "alias_entries_exercised_by_no_query": sorted(
            item["entry_id"]
            for item in report["alias_table_coverage"]
            if item["exercised_by_no_query"]
        ),
        "metrics": report["metrics"],
        "metric_support": report["metric_support"],
        "gate_status": {key: value["status"] for key, value in gates.items()},
        "failing_gates": sorted(key for key, value in gates.items() if value["status"] == "fail"),
        "undetermined_gates": sorted(
            key for key, value in gates.items() if value["status"] == "undetermined"
        ),
        "gate_summary": report["gate_summary"],
    }


def _emit(value: Any, output: Path | None) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))
    if output is not None:
        output.write_bytes(canonical_bytes(value))


def _read_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise Phase4CValidationError(f"{path} is not readable: {error}") from error
    if len(raw) > BOUNDS.max_report_bytes:
        raise Phase4CValidationError(
            f"{path}: {len(raw)} bytes exceeds the {BOUNDS.max_report_bytes}-byte bound"
        )
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Phase4CValidationError(f"{path} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise Phase4CValidationError(f"{path} must contain an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded offline Phase 4C hybrid-retrieval benchmark"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    benchmark = subparsers.add_parser(
        "benchmark", help="run the hybrid benchmark and emit a canonical report"
    )
    benchmark.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    benchmark.add_argument("--output", type=Path, default=None)
    benchmark.add_argument(
        "--reverse-insertion",
        action="store_true",
        help="build the index in reverse document order (rebuild-determinism check)",
    )

    inspect = subparsers.add_parser(
        "inspect", help="verify the canonical hashes of an emitted report"
    )
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--output", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "benchmark":
        try:
            report = evaluate_hybrid(
                args.fixtures, reverse_insertion=args.reverse_insertion
            )
        except Phase4CValidationError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 2
        if args.output is not None:
            args.output.write_bytes(canonical_bytes(report))
        print(json.dumps(_summary(report), indent=2, sort_keys=True))
        return 0 if report["gate_summary"]["overall"] == "pass" else 1

    if args.command == "inspect":
        try:
            report = _read_report(args.path)
        except Phase4CValidationError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 2
        try:
            verification = verify_report(report)
        except Phase4CValidationError as error:
            print(
                json.dumps(
                    {"verified": False, "error": str(error)}, indent=2, sort_keys=True
                )
            )
            return 1
        _emit({**verification, **_summary(report)}, args.output)
        return 0 if report["gate_summary"]["overall"] == "pass" else 1

    raise Phase4CValidationError(f"unsupported command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
