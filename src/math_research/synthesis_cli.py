"""Bounded exploratory synthesis commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthesis.budget import BudgetPolicy, allocate_with_reserve
from .synthesis.workspace import SynthesisWorkspace, decode_json, verify_export_bytes


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _read(path: Path) -> dict:
    return decode_json(path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded exploratory multi-result synthesis (ADR-0025 / ADR-0027)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate-budget", help="validate a budget policy and print its reserve equation"
    )
    validate.add_argument("policy", type=Path)

    reserve = commands.add_parser(
        "check-reserve", help="validate a branch-generation allocation against the reserve"
    )
    reserve.add_argument("policy", type=Path)
    reserve.add_argument("allocation", type=Path)

    inspect = commands.add_parser("inspect", help="verify and inspect a canonical export")
    inspect.add_argument("path", type=Path)

    export = commands.add_parser("export", help="export a canonical synthesis workspace")
    export.add_argument("workspace", type=Path)
    export.add_argument("output", type=Path)

    records = commands.add_parser("list-records", help="list records in a synthesis workspace")
    records.add_argument("workspace", type=Path)
    records.add_argument("--record-type", default=None)

    admission = commands.add_parser(
        "list-admissions", help="list the rebuilt current admission view"
    )
    admission.add_argument("workspace", type=Path)

    args = parser.parse_args(argv)

    # Commands that only read a file need no workspace.
    if args.command == "validate-budget":
        policy = BudgetPolicy.from_value(_read(args.policy))
        _json(
            {
                "policy_version": policy.policy_version,
                "branch_generation_attempts": policy.branch_generation_attempts,
                "exploration_reserve": (
                    f"ceil({policy.branch_generation_attempts} * "
                    f"{policy.exploration_reserve_numerator} / "
                    f"{policy.exploration_reserve_denominator})"
                ),
                "reserved_attempts": policy.reserved_attempts(),
                "valid": True,
            }
        )
        return 0

    if args.command == "check-reserve":
        policy = BudgetPolicy.from_value(_read(args.policy))
        spec = _read(args.allocation)
        allocation = allocate_with_reserve(
            policy,
            incumbent_family=spec["incumbent_family"],
            eligible_families=spec["eligible_families"],
            allocations=spec["allocations"],
            waivers=spec.get("reserve_unavailable", ()),
        )
        _json(allocation.value())
        return 0

    if args.command == "inspect":
        value = verify_export_bytes(args.path.read_bytes())
        _json(
            {
                "schema_version": value["schema_version"],
                "content_hash": value["content_hash"],
                "operational_hash": value["operational_hash"],
                "record_count": len(value["records"]),
                "admitted_subjects": sorted(
                    row["subject_id"]
                    for row in value["admission_projection"]
                    if row["current_admission"] == "admitted_under_policy"
                ),
            }
        )
        return 0

    with SynthesisWorkspace(args.workspace) as workspace:
        if args.command == "export":
            data = workspace.export_bytes()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name("." + args.output.name + ".tmp")
            temporary.write_bytes(data)
            workspace.save_verified_export(data)
            temporary.replace(args.output)
            _json({"bytes": len(data), "content_hash": json.loads(data)["content_hash"]})
        elif args.command == "list-records":
            _json(
                [
                    {
                        "record_id": row["record_id"],
                        "record_type": row["record_type"],
                        "subject_id": row["subject_id"],
                        "sequence": row["sequence"],
                    }
                    for row in workspace.records(args.record_type)
                ]
            )
        else:
            _json([dict(row) for row in workspace.admission_projection()])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
