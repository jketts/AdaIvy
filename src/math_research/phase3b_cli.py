"""CLI for the bounded Phase 3B formal-checking slice.

Two families of command live here and the separation is deliberate. The four
`bridge-*` commands (ADR-0043) are fully offline and never need the sealed
ADR-0016 image: constructing a request is not executing one. `check` and `demo`
execute, and they require the image.

Every ADR-0043 command name is prefixed `bridge-` and every ADR-0043 symbol
lives in `phase3b/bridge.py`, so this slice adds nothing to an existing module
in the `phase3b` package and reserves no generic verb.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .phase3b.adapter import DockerLeanAdapter
from .phase3b.bridge import (
    BridgeInputs, BridgeRefusal, BridgedRequestRecord, BridgeStore, bridge_from_paths,
    build_correspondence_attestation, parse_bridged_record, trace_finding,
)
from .phase3b.demonstration import run_acceptance
from .phase3b.interchange import export_workspace, import_trusted_replay
from .phase3b.records import SourceKind
from .phase3b.serialization import canonical_bytes, public_value
from .phase3b.service import FormalCheckingService
from .phase3b.validation import RequestValidationError
from .phase3b.workspace import FormalCheckWorkspace


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _refusal(error: BridgeRefusal | RequestValidationError) -> dict[str, Any]:
    return {
        "status": "refused",
        "codes": sorted({item.code for item in error.rejections}),
        "rejections": [
            {"code": item.code, "field": item.field, "detail": item.detail}
            for item in error.rejections
        ],
    }


def _write_canonical(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def _bridge(args: argparse.Namespace) -> int:
    inputs = BridgeInputs(
        phase2_workspace=args.phase2_workspace,
        artifact_root=args.artifacts,
        run_id=args.run_id,
        proposal_id=args.proposal_id,
        target_statement_path=args.target_statement,
        proof_fragment_path=args.proof_fragment,
        lean_source_kind=SourceKind(args.lean_source_kind),
        created_at=args.created_at,
        lean_authored_by=args.lean_authored_by,
        declaration_name=args.declaration_name,
        imports=tuple(args.imports or ()),
        assumptions_path=args.assumptions,
        meaning_tests_path=args.meaning_tests,
    )
    try:
        result = bridge_from_paths(inputs)
    except (BridgeRefusal, RequestValidationError) as error:
        _print(_refusal(error))
        return 2
    record = result.record
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result.request_bytes)
    with BridgeStore(args.workspace) as store:
        store.save_bridged_request(record, request_bytes=result.request_bytes)
        correspondence = store.correspondence_state(record.bridge_id.value)
    if args.record is not None:
        _write_canonical(args.record, record)
    _print({
        "status": "bridged",
        "bridge_id": record.bridge_id.value,
        "request_id": record.request.request_id.value,
        "claim_id": record.request.claim_id.value,
        "claim_id_source": record.claim_identity.claim_id_source,
        "claim_id_derived_from_lean": record.claim_identity.claim_id_derived_from_lean,
        "semantic_alignment_id": record.semantic_alignment.semantic_alignment_id.value,
        "semantic_alignment_status": record.semantic_alignment.status,
        "declaration_name": record.request.declaration_name,
        "lean_source_kind": record.lean_source.source_kind.value,
        "lean_authored_by": record.lean_source.authored_by,
        "phase2_provenance": public_value(record.phase2_proposal),
        "request_path": str(args.output),
        "record_path": None if args.record is None else str(args.record),
        "request_bytes_hash": record.request_bytes_hash,
        "request_canonical_hash": record.request_canonical_hash,
        "content_hash": record.content_hash,
        "operational_hash": record.operational_hash,
        "correspondence": correspondence,
        "trust_grants": public_value(record.trust_grants),
    })
    return 0


def _attest(args: argparse.Namespace) -> int:
    statement = args.statement
    if statement is None and args.statement_file is not None:
        statement = args.statement_file.read_text(encoding="utf-8")
    with BridgeStore(args.workspace) as store:
        record: BridgedRequestRecord = parse_bridged_record(store.bridged_request(args.bridge_id))
        try:
            attestation = build_correspondence_attestation(
                record, attester_id=args.attester, statement=statement or "",
                attested_at=args.attested_at,
            )
        except BridgeRefusal as error:
            _print(_refusal(error))
            return 2
        store.save_correspondence_attestation(attestation)
        correspondence = store.correspondence_state(args.bridge_id)
    if args.output is not None:
        _write_canonical(args.output, attestation)
    _print({
        "status": "attested",
        "attestation_id": attestation.attestation_id.value,
        "bridge_id": attestation.bridge_id.value,
        "claim_id": attestation.claim_id.value,
        "attester_id": attestation.attester_id,
        "attester_role": attestation.attester_role,
        "basis": attestation.basis,
        "attested_at": attestation.attested_at,
        "content_hash": attestation.content_hash,
        "bridge_correspondence_check": attestation.bridge_correspondence_check,
        "correspondence": correspondence,
        "output_path": None if args.output is None else str(args.output),
    })
    return 0


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

    bridge = commands.add_parser(
        "bridge-request",
        help="build a provenance-linked request from a committed Phase 2 proposal (offline; ADR-0043)",
        description=(
            "Builds the request envelope. The Lean target statement and proof fragment are "
            "INPUTS: this command never derives Lean from the Phase 2 payload and never checks "
            "that the two say the same thing."
        ),
    )
    bridge.add_argument("--phase2-workspace", type=Path, required=True)
    bridge.add_argument("--artifacts", type=Path, required=True)
    bridge.add_argument("--run-id", required=True)
    bridge.add_argument("--proposal-id", required=True)
    bridge.add_argument("--target-statement", type=Path, required=True, help="file holding the Lean target statement")
    bridge.add_argument("--proof-fragment", type=Path, required=True, help="file holding the Lean proof fragment")
    bridge.add_argument(
        "--lean-source-kind", required=True, choices=[item.value for item in (SourceKind.OPERATOR, SourceKind.MODEL)],
        help="who authored the Lean; there is no default",
    )
    bridge.add_argument("--created-at", required=True, help="explicit UTC instant, for example 2026-08-21T00:00:00Z")
    bridge.add_argument("--workspace", type=Path, required=True, help="Phase 3B workspace for durable provenance")
    bridge.add_argument("--output", type=Path, required=True, help="path for the canonical FormalCheckRequest")
    bridge.add_argument("--record", type=Path, help="optional path for the canonical bridged-request record")
    bridge.add_argument("--lean-authored-by", help="named principal who authored the Lean")
    bridge.add_argument("--declaration-name", help="Lean declaration name; derived deterministically when omitted")
    bridge.add_argument("--import", dest="imports", action="append", help="allowed Lean import; repeatable")
    bridge.add_argument("--assumptions", type=Path, help="JSON array of declared assumptions")
    bridge.add_argument("--meaning-tests", type=Path, help="JSON array of diagnostic meaning tests")

    attest = commands.add_parser(
        "bridge-attest",
        help="record one named operator's assertion that the payload and the Lean correspond",
        description=(
            "An attestation is a human assertion, not a verification. Nothing in this slice "
            "machine-checks the correspondence it asserts."
        ),
    )
    attest.add_argument("bridge_id")
    attest.add_argument("--workspace", type=Path, required=True)
    attest.add_argument("--attester", required=True, help="named attesting principal")
    attest.add_argument("--attested-at", required=True, help="explicit UTC instant")
    attest.add_argument("--statement", help="what the attester read and asserts")
    attest.add_argument("--statement-file", type=Path)
    attest.add_argument("--output", type=Path)

    status = commands.add_parser("bridge-status", help="resolve the recorded correspondence state of a bridged request")
    status.add_argument("workspace", type=Path)
    status.add_argument("bridge_id")

    trace = commands.add_parser(
        "bridge-trace", help="trace one finding back to the Phase 2 proposal it formalizes",
    )
    trace.add_argument("workspace", type=Path)
    trace.add_argument("finding_id")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        value = import_trusted_replay(args.path.read_bytes())
        _print({"content_hash": value["content_hash"], "findings": len(value["findings"]), "outcomes": sorted(item["outcome"] for item in value["findings"])})
        return 0
    if args.command == "finding":
        with FormalCheckWorkspace(args.workspace) as workspace:
            _print(workspace.finding(args.finding_id))
        return 0
    if args.command == "demo":
        summary = run_acceptance(args.workspace, args.output_dir)
        _print(summary)
        return 0 if summary["status"] == "passed" else 1
    if args.command == "bridge-request":
        return _bridge(args)
    if args.command == "bridge-attest":
        return _attest(args)
    if args.command == "bridge-status":
        with BridgeStore(args.workspace) as store:
            record = store.bridged_request(args.bridge_id)
            state = store.correspondence_state(args.bridge_id)
        _print({
            "bridge_id": args.bridge_id,
            "claim_id": record["request"]["claim_id"],
            "request_canonical_hash": record["request_canonical_hash"],
            "request_bytes_hash": record["request_bytes_hash"],
            "phase2_provenance": record["phase2_proposal"],
            "correspondence": state,
        })
        return 0
    if args.command == "bridge-trace":
        with FormalCheckWorkspace(args.workspace) as findings, BridgeStore(args.workspace) as store:
            _print(trace_finding(findings=findings, store=store, finding_id=args.finding_id))
        return 0
    source = args.request.read_bytes()
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = FormalCheckingService(DockerLeanAdapter()).check(source, created_at=created_at)
    with FormalCheckWorkspace(args.workspace) as workspace:
        workspace.save_attempt(source, result)
        if args.export:
            export_workspace(workspace, args.export)
    _print(public_value(result))
    return 0 if result.outcome.value.startswith("kernel_checked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
