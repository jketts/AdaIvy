"""Offline CLI for the Phase 5 noncommuting-SDP comparison experiment.

Standard library only. No network, no model call, no subprocess. The two SDP
engines are loaded lazily through the gated boundary in ``engines.py`` and are
absent by default; when they are absent every engine result is a recorded
missing-tool record and the experiment reports itself INCOMPLETE rather than
passing.

Exit status:

* ``0`` -- the report was emitted, every case carries an exact certificate, and
  the two-engine clause of the spec was satisfied;
* ``1`` -- a measured shortfall: a case has no exact certificate, or fewer than
  two independent engines ran, or a hash failed to verify. The report is still
  emitted, because discarding a failed or missing result is a forbidden outcome;
* ``2`` -- missing or invalid input.

A ``1`` exit with ``experiment_status = incomplete_engines_absent_or_refused``
is the expected offline outcome and must never be read as a pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison import (
    Summary,
    canonical_report_bytes,
    read_report,
    run_comparison,
    verify_report,
)
from .engines import AbsentModuleResolver, default_engines
from .validator import CertificateInputError

DEFAULT_FIXTURE = Path("fixtures/phase5-noncommuting-sdp/exact-small-cases.json")


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _exit_code(report: dict[str, Any]) -> int:
    ok = report["all_cases_exactly_certified"] and report["spec_clauses"][
        "two_independent_engines_run"
    ]
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 5 noncommuting-SDP engine-comparison experiment (spike only)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run the experiment and emit a canonical report")
    run.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    run.add_argument("--output", type=Path, default=None)
    run.add_argument(
        "--no-engines",
        action="store_true",
        help="force the fail-closed path: no engine is loaded, every result is a missing tool",
    )
    run.add_argument(
        "--full",
        action="store_true",
        help="print the whole report instead of the summary projection",
    )

    inspect = subparsers.add_parser("inspect", help="verify the hashes of an emitted report")
    inspect.add_argument("path", type=Path)

    args = parser.parse_args(argv)

    if args.command == "run":
        engines = default_engines(AbsentModuleResolver()) if args.no_engines else None
        try:
            report = run_comparison(args.fixture, engines=engines)
        except (CertificateInputError, OSError) as error:
            _emit({"error": str(error)})
            return 2
        if args.output is not None:
            args.output.write_bytes(canonical_report_bytes(report))
        _emit(report if args.full else Summary(report).public())
        return _exit_code(report)

    if args.command == "inspect":
        try:
            report = read_report(args.path)
            verification = verify_report(report)
        except (CertificateInputError, OSError) as error:
            _emit({"verified": False, "error": str(error)})
            return 2
        _emit({**verification, **Summary(report).public()})
        if not verification["verified"]:
            return 1
        return _exit_code(report)

    raise CertificateInputError(f"unsupported command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
