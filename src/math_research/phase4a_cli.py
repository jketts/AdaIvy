"""Local-only CLI for the bounded Phase 4A production slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .phase4a import MAX_EXPORT_BYTES
from .phase4a.content_store import read_interchange_file
from .phase4a.interchange import export_workspace, import_into_workspace, import_replay
from .phase4a.records import (
    ActorKind, ApplicabilityOutcome, ApplicabilityReason, ApplicabilityStatus,
    Authority, LifecycleType, RecordType, RightsReason, RightsUse, RightsValue,
)
from .phase4a.service import Phase4Service
from .phase4a.workspace import Phase4Workspace


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError(f"duplicate Phase 4A command-spec key: {key}")
        value[key] = item
    return value


def _spec(path: Path, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    value = json.loads(read_interchange_file(path, max_bytes=MAX_EXPORT_BYTES), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("Phase 4A command spec must be an object")
    allowed = required | (optional or set())
    if not required.issubset(value) or not set(value).issubset(allowed):
        raise ValueError("Phase 4A command spec has missing or unknown fields")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4A local rights and applicability review")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "rights", "lifecycle", "card", "review"):
        item = commands.add_parser(name)
        item.add_argument("workspace", type=Path)
        item.add_argument("spec", type=Path)
    intake = commands.add_parser("intake")
    intake.add_argument("workspace", type=Path); intake.add_argument("path", type=Path)
    intake.add_argument("source_id"); intake.add_argument("actor_id"); intake.add_argument("recorded_at")
    export = commands.add_parser("export")
    export.add_argument("workspace", type=Path); export.add_argument("output", type=Path); export.add_argument("exported_at")
    inspect = commands.add_parser("inspect", help="strictly verify and summarize an export envelope")
    inspect.add_argument("path", type=Path)
    replay = commands.add_parser("replay")
    replay.add_argument("workspace", type=Path); replay.add_argument("path", type=Path)
    rebuild = commands.add_parser("rebuild")
    rebuild.add_argument("workspace", type=Path)
    inspect_rights = commands.add_parser("inspect-rights", help="inspect one rights decision by record ID")
    inspect_rights.add_argument("workspace", type=Path); inspect_rights.add_argument("record_id")
    inspect_lifecycle = commands.add_parser("inspect-lifecycle", help="inspect one lifecycle action or a source lifecycle chain")
    inspect_lifecycle.add_argument("workspace", type=Path)
    lifecycle_selector = inspect_lifecycle.add_mutually_exclusive_group(required=True)
    lifecycle_selector.add_argument("--record-id"); lifecycle_selector.add_argument("--source-id")
    inspect_card = commands.add_parser("inspect-card", help="inspect one evidence card and authorized local content")
    inspect_card.add_argument("workspace", type=Path); inspect_card.add_argument("card_id"); inspect_card.add_argument("at")
    args = parser.parse_args(argv)

    if args.command == "inspect":
        value = import_replay(read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES))
        print(json.dumps({"content_hash": value["content_hash"], "records": len(value["records"]), "profile": value["profile"]}, indent=2, sort_keys=True))
        return 0
    with Phase4Workspace(args.workspace) as workspace:
        service = Phase4Service(workspace)
        if args.command == "inspect-rights":
            value = workspace.record(args.record_id)
            if value["record_type"] != RecordType.RIGHTS_DECISION.value:
                raise ValueError("record is not a rights decision")
            print(json.dumps(value, indent=2, sort_keys=True))
            return 0
        elif args.command == "inspect-lifecycle":
            if args.record_id is not None:
                value = workspace.record(args.record_id)
                if value["record_type"] != RecordType.LIFECYCLE_ACTION.value:
                    raise ValueError("record is not a lifecycle action")
                output: Any = value
            else:
                output = [
                    value for value in workspace.records()
                    if value["record_type"] == RecordType.LIFECYCLE_ACTION.value and value["subject_id"] == args.source_id
                ]
                if not output:
                    raise KeyError(args.source_id)
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0
        elif args.command == "inspect-card":
            record = workspace.record(args.card_id)
            if record["record_type"] != "evidence_card":
                raise ValueError("record is not an evidence card")
            output = {"content": service.inspect_evidence_card(args.card_id, at=args.at), "record": record}
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0
        elif args.command == "init":
            spec = _spec(args.spec, {"actor_id", "recorded_at"})
            record = service.initialize_policy(actor_id=spec["actor_id"], recorded_at=spec["recorded_at"])
        elif args.command == "intake":
            record = service.intake_local(args.path, source_id=args.source_id, actor_id=args.actor_id, recorded_at=args.recorded_at)
        elif args.command == "rights":
            spec = _spec(
                args.spec,
                {"source_id", "intended_use", "value", "reason_code", "reason_detail", "evidence_refs", "actor_id", "valid_from", "recorded_at", "lifecycle_id"},
                {"valid_until", "predecessor_id"},
            )
            record = service.append_rights(
                source_id=spec["source_id"], intended_use=RightsUse(spec["intended_use"]), value=RightsValue(spec["value"]),
                reason_code=RightsReason(spec["reason_code"]), reason_detail=spec["reason_detail"], evidence_refs=spec["evidence_refs"],
                actor_id=spec["actor_id"], valid_from=spec["valid_from"], valid_until=spec.get("valid_until"),
                recorded_at=spec["recorded_at"], lifecycle_id=spec["lifecycle_id"], predecessor_id=spec.get("predecessor_id"),
            )
        elif args.command == "lifecycle":
            spec = _spec(
                args.spec,
                {"source_id", "action", "target_record_id", "actor_id", "actor_kind", "authority", "reason_code", "reason_detail", "evidence_refs", "recorded_at"},
                {"legal_hold"},
            )
            if LifecycleType(spec["action"]) is LifecycleType.DELETION_COMPLETION:
                value = service.complete_deletion(spec["source_id"])
                print(json.dumps({"id": value["id"], "content_hash": value["content_hash"], "sequence": value["sequence"]}, indent=2, sort_keys=True))
                return 0
            record = service.append_lifecycle(
                source_id=spec["source_id"], action=LifecycleType(spec["action"]), target_record_id=spec["target_record_id"],
                actor_id=spec["actor_id"], actor_kind=ActorKind(spec["actor_kind"]), authority=Authority(spec["authority"]),
                reason_code=spec["reason_code"], reason_detail=spec["reason_detail"], evidence_refs=spec["evidence_refs"],
                recorded_at=spec["recorded_at"], legal_hold=spec.get("legal_hold", False),
            )
        elif args.command == "card":
            spec = _spec(
                args.spec,
                {"source_id", "span_byte_ranges", "bibliographic_identity", "imported_statement", "hypotheses", "definitions", "scope", "exceptions", "actor_id", "actor_kind", "reason_detail", "recorded_at"},
            )
            record = service.create_evidence_card(
                source_id=spec["source_id"], span_byte_ranges=tuple(tuple(item) for item in spec["span_byte_ranges"]),
                bibliographic_identity=spec["bibliographic_identity"], imported_statement=spec["imported_statement"], hypotheses=spec["hypotheses"],
                definitions=spec["definitions"], scope=spec["scope"], exceptions=spec["exceptions"], actor_id=spec["actor_id"],
                actor_kind=ActorKind(spec["actor_kind"]), reason_detail=spec["reason_detail"], recorded_at=spec["recorded_at"],
            )
        elif args.command == "review":
            spec = _spec(
                args.spec,
                {"source_id", "evidence_card_id", "status", "outcome", "reason_code", "reason_detail", "evidence_refs", "actor_id", "actor_kind", "recorded_at", "checks"},
                {"predecessor_id"},
            )
            record = service.review_applicability(
                source_id=spec["source_id"], evidence_card_id=spec["evidence_card_id"], status=ApplicabilityStatus(spec["status"]),
                outcome=ApplicabilityOutcome(spec["outcome"]), reason_code=ApplicabilityReason(spec["reason_code"]), reason_detail=spec["reason_detail"],
                evidence_refs=spec["evidence_refs"], actor_id=spec["actor_id"], actor_kind=ActorKind(spec["actor_kind"]),
                recorded_at=spec["recorded_at"], checks=spec["checks"], predecessor_id=spec.get("predecessor_id"),
            )
        elif args.command == "export":
            semantic, operational, byte_length = export_workspace(workspace, args.output, exported_at=args.exported_at)
            print(json.dumps({"content_hash": semantic, "operational_hash": operational, "bytes": byte_length}, indent=2, sort_keys=True))
            return 0
        elif args.command == "replay":
            value = import_into_workspace(read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES), workspace)
            print(json.dumps({"content_hash": value["content_hash"], "records": len(value["records"])}, indent=2, sort_keys=True))
            return 0
        else:
            print(json.dumps(workspace.rebuild_projections(), indent=2, sort_keys=True))
            return 0
        print(json.dumps({"id": record.id, "content_hash": record.content_hash, "sequence": record.sequence}, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
