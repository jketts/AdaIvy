"""CLI helpers for ADR-0055 novelty re-check records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .novelty import (
    PRIOR_ART_RELATIONSHIPS,
    PRIOR_RESOLUTIONS,
    PRIOR_RESOLUTION_VERIFICATIONS,
    NoveltyRecheck,
    NoveltyRecheckError,
    read_recheck,
    write_recheck,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify a novelty re-check record")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("checkpoint", choices=("before_research", "before_announcement"))
    create.add_argument("subject_id")
    create.add_argument("subject_hash")
    create.add_argument("next_action_id")
    create.add_argument("performed_by")
    create.add_argument("performed_at")
    create.add_argument("output", type=Path)
    create.add_argument("--recheck-id", required=True)
    create.add_argument("--protocol-id", required=True)
    create.add_argument("--query-term", action="append", required=True)
    create.add_argument("--searched-source", action="append", required=True)
    create.add_argument("--equivalence-check", action="append", required=True)
    create.add_argument("--evidence-ref", action="append", nargs=2, metavar=("ID", "SHA256"), required=True)
    create.add_argument("--outcome", choices=("prior_art_found", "not_found_under_protocol", "inconclusive"), required=True)
    create.add_argument("--prior-art-relationship", choices=sorted(PRIOR_ART_RELATIONSHIPS), required=True)
    create.add_argument("--prior-resolution", choices=sorted(PRIOR_RESOLUTIONS), required=True)
    create.add_argument(
        "--prior-resolution-verification",
        choices=sorted(PRIOR_RESOLUTION_VERIFICATIONS), required=True,
    )
    create.add_argument("--limitation", action="append", required=True)
    create.add_argument("--previous-recheck-id")
    create.add_argument("--previous-recheck-hash")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            record = read_recheck(args.path)
        else:
            record = NoveltyRecheck(
                recheck_id=args.recheck_id, checkpoint=args.checkpoint,
                subject_id=args.subject_id, subject_hash=args.subject_hash,
                next_action_id=args.next_action_id, performed_by=args.performed_by,
                performed_at=args.performed_at, protocol_id=args.protocol_id,
                query_terms=tuple(args.query_term), searched_sources=tuple(args.searched_source),
                equivalence_checks=tuple(args.equivalence_check),
                evidence_refs=tuple((item[0], item[1]) for item in args.evidence_ref),
                outcome=args.outcome, limitations=tuple(args.limitation),
                prior_art_relationship=args.prior_art_relationship,
                prior_resolution=args.prior_resolution,
                prior_resolution_verification=args.prior_resolution_verification,
                previous_recheck_id=args.previous_recheck_id,
                previous_recheck_hash=args.previous_recheck_hash,
            ).finalized()
            # Run the same closed validator used by consumers before writing.
            from .novelty import load_recheck
            record = load_recheck(record.payload())
            write_recheck(record, args.output)
        print(json.dumps(record.payload(), indent=2, sort_keys=True))
        return 0
    except (NoveltyRecheckError, OSError) as error:
        print(json.dumps({"accepted": False, "reason": str(error)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
