"""Offline CLI for bounded Phase 4B candidate metadata.

Network acquisition remains behind a separately authorized, content-hashed
human-final plan and an explicit execution acknowledgement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase4a.content_store import read_interchange_file
from .phase4b.interchange import verify_export_bytes
from .phase4b.records import MAX_EXPORT_BYTES
from .phase4b.serialization import canonical_bytes
from .phase4b.workspace import Phase4BWorkspace


def _summary(value: dict[str, object]) -> dict[str, object]:
    records = value["records"]
    projection = value["candidate_projection"]
    if not isinstance(records, list) or not isinstance(projection, list):
        raise ValueError("verified Phase 4B export collections are invalid")
    return {
        "profile": value["profile"],
        "content_hash": value["content_hash"],
        "operational_hash": value["operational_hash"],
        "records": len(records),
        "active_candidates": sum(
            item.get("current_state") == "active_candidate"
            for item in projection
            if isinstance(item, dict)
        ),
        "invalidated_candidates": sum(
            item.get("current_state") == "invalidated_candidate"
            for item in projection
            if isinstance(item, dict)
        ),
    }


def _strict_canonical_json(data: bytes, label: str) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"{label} contains a duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise ValueError(f"{label} is not canonical")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 4B offline acquisition/parsing candidate metadata"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize and verify the local workspace")
    init.add_argument("workspace", type=Path)
    export = commands.add_parser("export", help="write a canonical candidate-metadata export")
    export.add_argument("workspace", type=Path)
    export.add_argument("output", type=Path)
    inspect = commands.add_parser("inspect", help="strictly verify and summarize an export")
    inspect.add_argument("path", type=Path)
    replay = commands.add_parser("replay", help="verify and import candidate metadata")
    replay.add_argument("workspace", type=Path)
    replay.add_argument("path", type=Path)
    rebuild = commands.add_parser("rebuild", help="rebuild and verify the derived projection")
    rebuild.add_argument("workspace", type=Path)
    gate = commands.add_parser(
        "gate", help="run feasible offline controls and report blocked activation controls"
    )
    gate.add_argument("repository", type=Path)
    gate.add_argument("workdir", type=Path)
    gate.add_argument("--output", type=Path)
    live_gate = commands.add_parser(
        "live-gate", help="verify a live-network plan without executing it by default"
    )
    live_gate.add_argument("plan", type=Path)
    live_gate.add_argument("--output", type=Path)
    live_gate.add_argument("--execute", action="store_true")
    live_gate.add_argument("--confirm-live-network")
    live_gate.add_argument("--confirm-plan-hash")
    public_acquire = commands.add_parser(
        "public-acquire",
        help="acquire one public unauthenticated exact URL; dry-run by default",
    )
    public_acquire.add_argument("workspace", type=Path)
    public_acquire.add_argument("source_id")
    public_acquire.add_argument("plan", type=Path)
    public_acquire.add_argument("--activation", type=Path, required=True)
    public_acquire.add_argument("--activation-evidence", type=Path, required=True)
    public_acquire.add_argument("--output", type=Path)
    public_acquire.add_argument("--execute", action="store_true")
    public_acquire.add_argument("--confirm-live-network")
    public_acquire.add_argument("--confirm-plan-hash")
    oci_gate = commands.add_parser(
        "oci-gate", help="run the strict exact-image parser activation gate"
    )
    oci_gate.add_argument("repository", type=Path)
    oci_gate.add_argument("feasible_report", type=Path)
    oci_gate.add_argument("--docker", type=Path, required=True)
    oci_gate.add_argument("--daemon-host", required=True)
    oci_gate.add_argument("--image", required=True)
    oci_gate.add_argument("--platform", default="linux/arm64")
    oci_gate.add_argument("--output", type=Path, required=True)
    combine = commands.add_parser(
        "combine-activation-evidence",
        help="strictly combine two offline gates, one live gate, and the OCI gate",
    )
    combine.add_argument("repository", type=Path)
    combine.add_argument("first_feasible_report", type=Path)
    combine.add_argument("second_feasible_report", type=Path)
    combine.add_argument("live_report", type=Path)
    combine.add_argument("oci_report", type=Path)
    combine.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    if args.command == "inspect":
        data = read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES)
        print(json.dumps(_summary(verify_export_bytes(data)), indent=2, sort_keys=True))
        return 0

    if args.command == "gate":
        from .phase4b.gate import run_feasible_gate

        value = run_feasible_gate(args.repository, args.workdir)
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_bytes(value))
        print(data, end="")
        return 0

    if args.command == "live-gate":
        from .phase4b.live_gate import (
            MAX_PLAN_BYTES, live_gate_plan_hash, load_live_gate_plan,
            not_executed_report, run_live_gate,
        )
        from .phase4b.live_transport import (
            OptInHttpsTransport, OptInSystemResolver, SystemMonotonicClock,
        )

        plan = load_live_gate_plan(
            read_interchange_file(args.plan, max_bytes=MAX_PLAN_BYTES)
        )
        if args.execute:
            if args.confirm_live_network != "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK":
                parser.error(
                    "--execute requires --confirm-live-network "
                    "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK"
                )
            if args.confirm_plan_hash != live_gate_plan_hash(plan):
                parser.error(
                    "--execute requires --confirm-plan-hash equal to the exact "
                    "verified plan content_hash"
                )
            value = run_live_gate(
                plan,
                resolver=OptInSystemResolver(plan.permit),
                transport=OptInHttpsTransport(plan.permit),
                start_clock=SystemMonotonicClock(),
            )
        else:
            if (
                args.confirm_live_network is not None
                or args.confirm_plan_hash is not None
            ):
                parser.error("live-network confirmations are valid only with --execute")
            value = not_executed_report(plan)
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_bytes(value))
        print(data, end="")
        return 0

    if args.command == "public-acquire":
        from .phase4b.live_gate import MAX_PLAN_BYTES, live_gate_plan_hash, load_live_gate_plan
        from .phase4b.public_acquisition import (
            LIVE_NETWORK_ACKNOWLEDGEMENT, MAX_ACTIVATION_BYTES, MAX_EVIDENCE_BYTES,
            acquire_public_plan, load_public_activation, validate_public_plan,
        )

        plan = load_live_gate_plan(
            read_interchange_file(args.plan, max_bytes=MAX_PLAN_BYTES)
        )
        activation_data = read_interchange_file(
            args.activation, max_bytes=MAX_ACTIVATION_BYTES
        )
        evidence_data = read_interchange_file(
            args.activation_evidence, max_bytes=MAX_EVIDENCE_BYTES
        )
        activation = load_public_activation(activation_data, evidence_data)
        validate_public_plan(plan)
        if args.execute:
            if args.confirm_live_network != LIVE_NETWORK_ACKNOWLEDGEMENT:
                parser.error(
                    "--execute requires --confirm-live-network "
                    "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK"
                )
            if args.confirm_plan_hash != live_gate_plan_hash(plan):
                parser.error(
                    "--execute requires --confirm-plan-hash equal to the exact "
                    "verified plan content_hash"
                )
            from .phase4b.live_transport import (
                OptInHttpsTransport, OptInSystemResolver, SystemMonotonicClock,
            )
            from .phase4b.service import Phase4BService
            import time

            with Phase4BWorkspace(args.workspace) as workspace:
                with Phase4BService(workspace) as service:
                    stored = acquire_public_plan(
                        service, args.source_id, plan,
                        activation_data=activation_data,
                        activation_evidence_data=evidence_data,
                        execution_epoch=int(time.time()),
                        resolver=OptInSystemResolver(plan.permit),
                        transport=OptInHttpsTransport(plan.permit),
                        start_clock=SystemMonotonicClock(),
                        network_acknowledgement=args.confirm_live_network,
                        confirmed_plan_hash=args.confirm_plan_hash,
                    )
            value = {
                "schema_version": "adaivy.phase4b-public-acquisition-result.v1",
                "execution_status": "executed",
                "activation_hash": activation["content_hash"],
                "plan_hash": live_gate_plan_hash(plan),
                "semantic_hash": "sha256:" + stored.result.semantic_hash,
                "operational_hash": "sha256:" + stored.result.operational_hash,
                "candidate_count": len(stored.result.candidates),
                "record_ids": [item["record_id"] for item in stored.records],
            }
        else:
            if args.confirm_live_network is not None or args.confirm_plan_hash is not None:
                parser.error("live-network confirmations are valid only with --execute")
            value = {
                "schema_version": "adaivy.phase4b-public-acquisition-result.v1",
                "execution_status": "not_executed",
                "activation_hash": activation["content_hash"],
                "plan_hash": live_gate_plan_hash(plan),
                "source_id": args.source_id,
                "candidate_count": 0,
                "record_ids": [],
            }
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_bytes(value))
        print(data, end="")
        return 0

    if args.command == "oci-gate":
        from .phase4b.gate import MAX_REPORT_BYTES, load_feasible_gate_report
        from .phase4b.oci_parser_sandbox import OciRuntimeIdentity
        from .phase4b.oci_sandbox_activation import (
            run_oci_sandbox_activation_evidence,
        )

        feasible = load_feasible_gate_report(
            read_interchange_file(args.feasible_report, max_bytes=MAX_REPORT_BYTES),
            args.repository,
        )
        runtime = OciRuntimeIdentity.measure(
            docker_executable=args.docker,
            daemon_host=args.daemon_host,
            image_reference=args.image,
            platform=args.platform,
        )
        value = run_oci_sandbox_activation_evidence(
            args.repository, feasible["parser_corpus_authorization"], runtime,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_bytes(value))
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0

    if args.command == "combine-activation-evidence":
        from .phase4b.activation import create_activation_evidence
        from .phase4b.gate import MAX_REPORT_BYTES, load_feasible_gate_report
        from .phase4b.live_gate import verify_live_gate_report
        from .phase4b.oci_sandbox_activation import (
            MAX_EVIDENCE_BYTES, load_oci_sandbox_activation_evidence,
            verify_oci_sandbox_activation_evidence,
        )

        feasible = tuple(
            load_feasible_gate_report(
                read_interchange_file(path, max_bytes=MAX_REPORT_BYTES),
                args.repository,
            )
            for path in (args.first_feasible_report, args.second_feasible_report)
        )
        live = _strict_canonical_json(
            read_interchange_file(args.live_report, max_bytes=262_144),
            "live gate report",
        )
        verify_live_gate_report(live)
        oci = load_oci_sandbox_activation_evidence(
            read_interchange_file(args.oci_report, max_bytes=MAX_EVIDENCE_BYTES)
        )
        value = create_activation_evidence(
            feasible, live, oci, repository_root=args.repository,
            sandbox_verifier=verify_oci_sandbox_activation_evidence,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_bytes(value))
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0

    with Phase4BWorkspace(args.workspace) as workspace:
        if args.command == "init":
            value = workspace.export_value()
        elif args.command == "export":
            data = workspace.export_bytes()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            value = verify_export_bytes(data)
        elif args.command == "replay":
            data = read_interchange_file(args.path, max_bytes=MAX_EXPORT_BYTES)
            value = workspace.import_bytes(data)
        else:
            workspace.rebuild_projection()
            workspace.verify_integrity()
            value = workspace.export_value()
        print(json.dumps(_summary(value), indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
