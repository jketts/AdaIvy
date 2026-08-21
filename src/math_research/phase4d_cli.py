"""CLI for grounded, bounded, public scholarly discovery (ADR-0051)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .phase4a.content_store import read_interchange_file, read_local_text
from .phase4b.live_transport import (
    LiveNetworkPermit, OptInHttpsTransport, OptInSystemResolver,
)
from .phase4b.serialization import canonical_bytes
from .phase4d.discovery import (
    CAPABILITY_ID, LIVE_ACKNOWLEDGEMENT, MAX_CONFIG_BYTES, MAX_REPORT_BYTES,
    MAX_SOURCE_BYTES, GroundedQuery, dry_run, load_config, search, verify_report,
)


def _strict_report(data: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ValueError("discovery report contains a duplicate key")
            value[key] = item
        return value

    if not data or len(data) > MAX_REPORT_BYTES:
        raise ValueError("discovery report byte bound differs")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value forbidden: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("discovery report JSON is invalid") from error
    if not isinstance(value, dict) or data not in {
        canonical_bytes(value), canonical_bytes(value) + b"\n",
    }:
        raise ValueError("discovery report is not canonical")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grounded public scholarly discovery; results are inspiration only"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser(
        "search", help="prepare a query without network access; --execute opts in"
    )
    discover.add_argument("source", type=Path, help="local UTF-8 terminology source")
    discover.add_argument("--term", action="append", required=True)
    discover.add_argument("--config", type=Path, required=True)
    discover.add_argument("--output", type=Path)
    discover.add_argument("--observed-at-epoch", type=int, default=0)
    discover.add_argument("--execute", action="store_true")
    discover.add_argument("--actor-id")
    discover.add_argument("--confirm-live-network")
    discover.add_argument("--confirm-query-hash")
    inspect = commands.add_parser("inspect", help="verify a canonical discovery report")
    inspect.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    if args.command == "inspect":
        value = verify_report(_strict_report(
            read_interchange_file(args.path, max_bytes=MAX_REPORT_BYTES)
        ))
        print(json.dumps({
            "status": value["status"], "content_hash": value["content_hash"],
            "query_hash": value["query"]["query_hash"],
            "candidate_count": value["candidate_count"],
            "inspiration_only": value["inspiration_only"],
        }, indent=2, sort_keys=True))
        return 0

    config = load_config(read_interchange_file(args.config, max_bytes=MAX_CONFIG_BYTES))
    query = GroundedQuery.create(
        args.term, read_local_text(args.source, max_bytes=MAX_SOURCE_BYTES),
        max_terms=config["max_query_terms"], max_query_bytes=config["max_query_bytes"],
    )
    if args.execute:
        if args.actor_id is None or not args.actor_id.strip():
            parser.error("--execute requires a nonempty --actor-id")
        if args.confirm_live_network != LIVE_ACKNOWLEDGEMENT:
            parser.error(
                "--execute requires --confirm-live-network " + LIVE_ACKNOWLEDGEMENT
            )
        if args.confirm_query_hash != query.query_hash:
            parser.error(
                "--execute requires --confirm-query-hash equal to the displayed query hash"
            )
        observed_at = int(time.time())
        permit = LiveNetworkPermit(
            "run.phase4d." + query.query_hash.removeprefix("sha256:")[:24],
            args.actor_id.strip(), "human", "human_final", CAPABILITY_ID,
            (config["origin"],), True,
        )
        value = search(
            config, query, permit=permit, resolver=OptInSystemResolver(permit),
            transport=OptInHttpsTransport(permit), observed_at_epoch=observed_at,
            acknowledgement=args.confirm_live_network,
            confirmed_query_hash=args.confirm_query_hash,
        )
    else:
        if any(item is not None for item in (
            args.actor_id, args.confirm_live_network, args.confirm_query_hash,
        )):
            parser.error("live-network identity and confirmations are valid only with --execute")
        if args.observed_at_epoch < 0:
            parser.error("--observed-at-epoch must be nonnegative")
        value = dry_run(config, query, args.observed_at_epoch)
    verify_report(value)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_bytes(value))
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
