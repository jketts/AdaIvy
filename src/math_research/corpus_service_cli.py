"""CLI for the ADR-0072 Slice 3 persistent corpus service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus_service.activation import load_production_activation
from .corpus_service.bridge import import_arxiv_metadata
from .corpus_service.dataroot import initialize_data_root, open_data_root, ordinary_cleanup
from .corpus_service.extraction import (
    ExtractorRegistry,
    IdentityTextExtractor,
    LatexSourceExtractor,
    PinnedBinaryExtractor,
)
from .corpus_service.fetcher import UrllibSnapshotTransport, fetch_snapshot
from .corpus_service.generation import (
    latest_generation_id,
    record_takedown,
    require_active_generation,
)
from .corpus_service.policy import load_policy
from .corpus_service.ports import DirectoryArchiveSource
from .corpus_service.rightsstore import PolicyDerivedRightsWriter
from .corpus_service.serialization import canonical_bytes, strict_canonical_object
from .corpus_service.service import ingest_tranche
from .corpus_service.snapshot import load_archive_manifest, load_tranche_config


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
    # ADR-0080: the pinned external PDF extractor is an explicit opt-in trio;
    # supplying any of the three requires all three, and the exact pinned
    # binary or a refusal.
    ingest.add_argument("--pdf-extractor-binary", type=Path)
    ingest.add_argument("--pdf-extractor-sha256")
    ingest.add_argument("--pdf-extractor-version")

    acquire = commands.add_parser(
        "acquire", help="live snapshot fetch (gated; shipped record is pending)",
    )
    acquire.add_argument("activation", type=Path)
    acquire.add_argument("--confirm-live-network")
    acquire.add_argument("--data-root", type=Path, required=True)
    acquire.add_argument("--archive-manifest", type=Path, required=True)
    acquire.add_argument("--origin", required=True)
    acquire.add_argument("--run-id", required=True)
    acquire.add_argument("--recorded-at", required=True)
    acquire.add_argument("--operator-id", required=True)
    acquire.add_argument("--output", type=Path)

    bridge = commands.add_parser(
        "bridge-arxiv",
        help="import ADR-0067 arXiv metadata records as descriptive documents",
    )
    bridge.add_argument("--data-root", type=Path, required=True)
    bridge.add_argument(
        "--records", type=Path, required=True,
        help="JSON file: a list of verified arXiv corpus records, or an "
        "object with a 'records' list",
    )
    bridge.add_argument("--policy", type=Path, required=True)
    bridge.add_argument("--tranche-id", required=True)
    bridge.add_argument("--archive-version", required=True)
    bridge.add_argument("--run-id", required=True)
    bridge.add_argument("--recorded-at", required=True)
    bridge.add_argument("--output", type=Path)

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
        extractors = None
        pdf_pins = (
            args.pdf_extractor_binary, args.pdf_extractor_sha256,
            args.pdf_extractor_version,
        )
        if any(item is not None for item in pdf_pins):
            if any(item is None for item in pdf_pins):
                parser.error(
                    "--pdf-extractor-binary, --pdf-extractor-sha256, and "
                    "--pdf-extractor-version are one opt-in and travel together"
                )
            extractors = ExtractorRegistry((
                IdentityTextExtractor(),
                LatexSourceExtractor(),
                PinnedBinaryExtractor(
                    binary_path=args.pdf_extractor_binary,
                    expected_sha256=args.pdf_extractor_sha256,
                    expected_version=args.pdf_extractor_version,
                ),
            ))
        report = ingest_tranche(
            args.data_root,
            policy=load_policy(args.policy.read_bytes()),
            archive=DirectoryArchiveSource(args.archive_root),
            tranche_config=load_tranche_config(args.tranche_config.read_bytes()),
            run_id=args.run_id,
            recorded_at=args.recorded_at,
            extractors=extractors,
        )
        _write(report, args.output)
        return 0

    if args.command == "acquire":
        # ADR-0080: the snapshot fetcher exists but stays behind the named
        # gate.  ``fetch_snapshot`` refuses while the shipped record is
        # pending or the exact acknowledgement string is absent; the live
        # transport is constructed only for this call and only after the
        # arguments are on the table.
        activation = load_production_activation(args.activation.read_bytes())
        report = fetch_snapshot(
            args.data_root,
            manifest=load_archive_manifest(args.archive_manifest.read_bytes()),
            origin=args.origin,
            activation=activation,
            acknowledgement=args.confirm_live_network,
            transport=UrllibSnapshotTransport(),
            operator_id=args.operator_id,
            run_id=args.run_id,
            recorded_at=args.recorded_at,
        )
        _write(report, args.output)
        return 0

    if args.command == "bridge-arxiv":
        raw = args.records.read_bytes()
        if raw.lstrip().startswith(b"{"):
            payload = strict_canonical_object(
                raw, maximum=67_108_864, label="arxiv bridge records",
                code="bridge_record_invalid",
            )
            records = payload["records"]
        else:
            def _refuse_duplicates(pairs):
                keys = [key for key, _ in pairs]
                if len(keys) != len(set(keys)):
                    raise ValueError("bridge_record_invalid: duplicate keys")
                return dict(pairs)
            records = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_refuse_duplicates,
            )
        report = import_arxiv_metadata(
            args.data_root,
            records=records,
            policy=load_policy(args.policy.read_bytes()),
            tranche_id=args.tranche_id,
            archive_version=args.archive_version,
            run_id=args.run_id,
            recorded_at=args.recorded_at,
        )
        _write(report, args.output)
        return 0

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
