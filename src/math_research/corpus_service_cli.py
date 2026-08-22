"""CLI for the ADR-0072 Slice 3 persistent corpus service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus_service.activation import load_production_activation, require_active
from .corpus_service.constants import LIVE_SNAPSHOT_ACKNOWLEDGEMENT
from .corpus_service.dataroot import initialize_data_root, open_data_root, ordinary_cleanup
from .corpus_service.generation import (
    latest_generation_id,
    record_takedown,
    require_active_generation,
)
from .corpus_service.policy import load_policy
from .corpus_service.ports import DirectoryArchiveSource
from .corpus_service.rightsstore import PolicyDerivedRightsWriter
from .corpus_service.serialization import canonical_bytes
from .corpus_service.service import ingest_tranche
from .corpus_service.snapshot import load_tranche_config


def _write(payload: object, output: Path | None) -> None:
    data = canonical_bytes(payload) + b"\n"
    if output is None:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus-service",
        description="Persistent multi-run corpus store (ADR-0072 Slice 3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a data root outside Git")
    init.add_argument("--data-root", type=Path, required=True)
    init.add_argument("--data-root-id", required=True)
    init.add_argument("--initialized-at", required=True)
    init.add_argument("--output", type=Path)

    ingest = commands.add_parser(
        "ingest", help="ingest one bounded tranche from a local archive",
    )
    ingest.add_argument("--data-root", type=Path, required=True)
    ingest.add_argument("--policy", type=Path, required=True)
    ingest.add_argument("--archive-root", type=Path, required=True)
    ingest.add_argument("--tranche-config", type=Path, required=True)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--recorded-at", required=True)
    ingest.add_argument("--output", type=Path)

    acquire = commands.add_parser(
        "acquire", help="live snapshot acquisition gate (shipped pending)",
    )
    acquire.add_argument("activation", type=Path)
    acquire.add_argument("--confirm-live-network")

    takedown = commands.add_parser(
        "takedown", help="remove one document from active use, tombstoned",
    )
    takedown.add_argument("--data-root", type=Path, required=True)
    takedown.add_argument("--document-id", required=True)
    takedown.add_argument("--actor-id", required=True)
    takedown.add_argument("--reason", required=True)
    takedown.add_argument("--recorded-at", required=True)
    takedown.add_argument("--output", type=Path)

    show = commands.add_parser("show", help="latest active generation summary")
    show.add_argument("--data-root", type=Path, required=True)

    cleanup = commands.add_parser(
        "cleanup", help="ordinary cleanup: scratch only, never corpus artifacts",
    )
    cleanup.add_argument("--data-root", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.command == "init":
        marker = initialize_data_root(
            args.data_root, data_root_id=args.data_root_id,
            initialized_at=args.initialized_at,
        )
        _write(marker, args.output)
        return 0

    if args.command == "ingest":
        report = ingest_tranche(
            args.data_root,
            policy=load_policy(args.policy.read_bytes()),
            archive=DirectoryArchiveSource(args.archive_root),
            tranche_config=load_tranche_config(args.tranche_config.read_bytes()),
            run_id=args.run_id,
            recorded_at=args.recorded_at,
        )
        _write(report, args.output)
        return 0

    if args.command == "acquire":
        activation = load_production_activation(args.activation.read_bytes())
        # Refuses while the shipped record is pending; no archive fetcher
        # exists in this package, so an ACTIVE record still acquires nothing.
        require_active(activation, acknowledgement=args.confirm_live_network)
        print(json.dumps({
            "status": "no_snapshot_fetcher_implemented",
            "detail": (
                "the activation record is active, but this slice ships no "
                "network fetcher for snapshot archives; acquisition of the "
                "archive is a separately gated capability"
            ),
            "acknowledgement_required": LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
        }, indent=2, sort_keys=True))
        return 1

    if args.command == "takedown":
        writer_root = open_data_root(args.data_root)
        del writer_root
        writer = PolicyDerivedRightsWriter(
            args.data_root, actor_id=args.actor_id,
            valid_from=args.recorded_at, valid_until=None,
        )
        tombstone = record_takedown(
            args.data_root, document_id=args.document_id,
            reason_detail=args.reason, actor_id=args.actor_id,
            recorded_at=args.recorded_at, rights_writer=writer,
        )
        _write(tombstone, args.output)
        return 0

    if args.command == "cleanup":
        removed = ordinary_cleanup(args.data_root)
        print(json.dumps({
            "removed": list(removed),
            "corpus_artifacts_touched": False,
        }, indent=2, sort_keys=True))
        return 0

    # show
    open_data_root(args.data_root)
    generation_id = latest_generation_id(args.data_root)
    if generation_id is None:
        print(json.dumps({"generation_id": None, "entry_count": 0}, indent=2, sort_keys=True))
        return 0
    manifest = require_active_generation(args.data_root, generation_id)
    print(json.dumps({
        "generation_id": manifest["generation_id"],
        "generation_hash": manifest["content_hash"],
        "entry_count": manifest["entry_count"],
        "quarantined_count": manifest["quarantined_count"],
        "tombstoned_count": len(manifest["tombstoned_document_ids"]),
        "retrieval_indexed": manifest["retrieval_indexed"],
        "applicability_ceiling": manifest["applicability_ceiling"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
