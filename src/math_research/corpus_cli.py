"""CLI for the bounded ADR-0067 arXiv metadata corpus slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus.acquisition import STATUS_ACQUIRED, STATUS_FAILED, acquire_tranche, dry_run
from .corpus.activation import load_production_activation, require_active
from .corpus.constants import (
    ARXIV_API_ORIGIN,
    CAPABILITY_ID,
    LIVE_ACKNOWLEDGEMENT,
    MAX_REQUESTS_PER_RUN,
)
from .corpus.pacing import RequestPacer, SystemMonotonicClock, SystemSleeper
from .corpus.probes import run_probes
from .corpus.projection import build_projection, verify_projection
from .corpus.replay import ForbiddingMetadataTransport, replay_tranche
from .corpus.report import STATUS_REPLAYED, build_report, verify_report
from .corpus.rights import Phase4CorpusRightsWriter
from .corpus.serialization import canonical_bytes
from .corpus.tranche import load_plan, request_budget


def _write(payload: object, output: Path | None) -> None:
    data = canonical_bytes(payload) + b"\n"
    if output is None:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


def _load_inputs(activation_path: Path, plan_path: Path) -> tuple[dict, dict]:
    return (
        load_production_activation(activation_path.read_bytes()),
        load_plan(plan_path.read_bytes()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus",
        description="Bounded arXiv metadata corpus acquisition and offline replay",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    acquire = commands.add_parser(
        "acquire", help="plan without network by default; --execute opts in",
    )
    acquire.add_argument("activation", type=Path)
    acquire.add_argument("plan", type=Path)
    acquire.add_argument("--store-root", type=Path, required=True)
    acquire.add_argument("--observed-at-epoch", type=int, required=True)
    acquire.add_argument("--output", type=Path)
    acquire.add_argument("--execute", action="store_true")
    acquire.add_argument("--operator-id")
    acquire.add_argument("--confirm-live-network")
    acquire.add_argument("--confirm-plan-hash")

    replay = commands.add_parser(
        "replay", help="derive records, report and projection from stored bytes",
    )
    replay.add_argument("activation", type=Path)
    replay.add_argument("plan", type=Path)
    replay.add_argument("--store-root", type=Path, required=True)
    replay.add_argument("--workspace", type=Path, required=True)
    replay.add_argument("--recorded-at", required=True)
    replay.add_argument("--expect-manifest-hash")
    replay.add_argument("--output-dir", type=Path, required=True)

    probes = commands.add_parser(
        "probes", help="run the ADR-0067 falsifiability probes offline",
    )
    probes.add_argument("--output", type=Path)

    inspect = commands.add_parser(
        "inspect", help="verify a replay report against its corpus records",
    )
    inspect.add_argument("report", type=Path)
    inspect.add_argument("ingestion", type=Path)

    args = parser.parse_args(argv)

    if args.command == "probes":
        result = run_probes()
        _write(result, args.output)
        return 0 if result["probes_flipped"] == result["probes_total"] else 1

    if args.command == "inspect":
        report = json.loads(args.report.read_text(encoding="utf-8"))
        ingestion = json.loads(args.ingestion.read_text(encoding="utf-8"))
        verified = verify_report(report, records=ingestion["records"])
        print(json.dumps({
            "content_hash": verified["content_hash"],
            "record_count": verified["record_count"],
            "records_with_applicability_record": verified[
                "records_with_applicability_record"
            ],
            "status": verified["status"],
            "verified": True,
        }, indent=2, sort_keys=True))
        return 0

    activation, plan = _load_inputs(args.activation, args.plan)

    if args.command == "acquire":
        if not args.execute:
            if any(value is not None for value in (
                args.operator_id,
                args.confirm_live_network,
                args.confirm_plan_hash,
            )):
                parser.error("live identity and confirmations require --execute")
            result = dry_run(
                activation, plan, observed_at_epoch=args.observed_at_epoch,
            )
        else:
            if not args.operator_id or not args.operator_id.strip():
                parser.error("--execute requires a nonempty --operator-id")
            if args.confirm_live_network != LIVE_ACKNOWLEDGEMENT:
                parser.error(
                    "--execute requires --confirm-live-network "
                    + LIVE_ACKNOWLEDGEMENT
                )
            if args.confirm_plan_hash != plan["content_hash"]:
                parser.error(
                    "--execute requires --confirm-plan-hash equal to the plan hash"
                )
            # Refuse before constructing any resolver or transport.  The
            # shipped production record is deliberately pending.
            require_active(activation)
            from .corpus.live import build_live_transport
            from .phase4b.live_transport import LiveNetworkPermit

            permit = LiveNetworkPermit(
                "run.corpus." + plan["content_hash"].removeprefix("sha256:")[:24],
                args.operator_id.strip(),
                "human",
                "human_final",
                CAPABILITY_ID,
                (ARXIV_API_ORIGIN,),
                True,
            )
            transport = build_live_transport(permit)
            pacer = RequestPacer(
                SystemMonotonicClock(),
                SystemSleeper(),
                max_requests=min(request_budget(plan), MAX_REQUESTS_PER_RUN),
            )
            result = acquire_tranche(
                activation,
                plan,
                store_root=args.store_root,
                transport=transport,
                pacer=pacer,
                acknowledgement=args.confirm_live_network,
                confirmed_plan_hash=args.confirm_plan_hash,
                observed_at_epoch=args.observed_at_epoch,
                operator_id=args.operator_id,
            )
            if result["status"] not in {STATUS_ACQUIRED, STATUS_FAILED}:
                raise RuntimeError("live corpus acquisition returned an unknown status")
        _write(result, args.output)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    writer = Phase4CorpusRightsWriter(args.workspace, plan["rights_declaration"])
    transport = ForbiddingMetadataTransport()
    ingestion = replay_tranche(
        args.store_root,
        plan,
        rights_writer=writer,
        recorded_at=args.recorded_at,
        transport=transport,
        expected_manifest_hash=args.expect_manifest_hash,
    )
    report = verify_report(build_report(
        status=STATUS_REPLAYED,
        activation=activation,
        plan=plan,
        ingestion=ingestion,
        network_requests=0,
        transport_calls=transport.attempts,
        manifest_hash=ingestion["manifest_hash"],
    ), records=ingestion["records"])
    projection = verify_projection(
        build_projection(ingestion["records"]), records=ingestion["records"],
    )
    _write(ingestion, args.output_dir / "ingestion.json")
    _write(report, args.output_dir / "report.json")
    _write(projection, args.output_dir / "projection.json")
    _write({
        "ingestion_hash": ingestion["content_hash"],
        "manifest_hash": ingestion["manifest_hash"],
        "network_requests": 0,
        "projection_hash": projection["content_hash"],
        "record_count": ingestion["record_count"],
        "report_hash": report["content_hash"],
        "rights_records_written": ingestion["rights_records_written"],
        "status": STATUS_REPLAYED,
    }, args.output_dir / "summary.json")
    print(json.dumps({
        "manifest_hash": ingestion["manifest_hash"],
        "network_requests": 0,
        "record_count": ingestion["record_count"],
        "records_with_applicability_record": ingestion[
            "records_with_applicability_record"
        ],
        "rights_records_written": ingestion["rights_records_written"],
        "status": STATUS_REPLAYED,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
