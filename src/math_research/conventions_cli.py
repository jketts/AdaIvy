"""CLI helpers for definitional-reading records and derived claim scope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .conventions import (
    POLICY_ID,
    SCHEMA_VERSION,
    ConventionError,
    read_convention,
    read_verdict_matrix,
    reading_coupling_index,
    require_convention_binding,
    weakest_reading_status,
)


def _inspect(convention_path: Path, matrix_path: Path | None) -> dict[str, object]:
    convention = read_convention(convention_path)
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "convention_id": convention.convention_id,
        "content_hash": convention.content_hash,
        "subject_ids": list(convention.subject_ids),
        "coupled_subject_ids": list(convention.coupled_subject_ids),
        "contested_terms": [
            {
                "term_id": term.term_id,
                "term": term.term,
                "readings": [
                    {
                        "reading_id": reading.reading_id,
                        "reading_status": reading.reading_status,
                        "source_passage_ref": reading.source_passage_ref,
                        "attributed_to": reading.attributed_to,
                    }
                    for reading in term.readings
                ],
            }
            for term in convention.terms
        ],
        "reading_tuples": [
            {
                "reading_tuple": list(item),
                "weakest_reading_status": weakest_reading_status(convention, item),
            }
            for item in convention.reading_tuples()
        ],
        "verdict_matrix": None,
        "derived_scope": None,
        "creates_mathematical_warrant": False,
        "resolves_contested_reading": False,
    }
    if matrix_path is not None:
        matrix = read_verdict_matrix(matrix_path)
        require_convention_binding(matrix, convention)
        report["verdict_matrix"] = {
            "matrix_id": matrix.matrix_id,
            "claim_id": matrix.claim_id,
            "content_hash": matrix.content_hash,
            "verdicts": [
                {
                    "reading_tuple": list(item.reading_tuple),
                    "verdict": item.verdict,
                    "evidence_ref": item.evidence_ref,
                    "weakest_reading_status": weakest_reading_status(
                        convention, item.reading_tuple
                    ),
                }
                for item in matrix.verdicts
            ],
        }
        report["derived_scope"] = matrix.scope(convention=convention)
    return report


def _couplings(paths: list[Path]) -> dict[str, object]:
    conventions = [read_convention(path) for path in paths]
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "conventions": [
            {
                "convention_id": convention.convention_id,
                "content_hash": convention.content_hash,
                "subject_ids": list(convention.subject_ids),
                "coupled_subject_ids": list(convention.coupled_subject_ids),
                "governed_subject_ids": list(convention.governed_subject_ids()),
            }
            for convention in conventions
        ],
        "coupled_by_reading": [
            {"reading_id": reading_id, "subject_ids": list(subjects)}
            for reading_id, subjects in reading_coupling_index(conventions).items()
        ],
        "creates_mathematical_warrant": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect convention-reading records and derived claim scope"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("convention", type=Path)
    inspect.add_argument("--matrix", type=Path)
    couplings = commands.add_parser("couplings")
    couplings.add_argument("convention", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            report = _inspect(args.convention, args.matrix)
        else:
            report = _couplings(list(args.convention))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ConventionError, OSError) as error:
        print(json.dumps({"accepted": False, "reason": str(error)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
