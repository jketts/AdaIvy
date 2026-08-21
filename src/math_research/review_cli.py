"""CLI for the ADR-0042 review decision journal and warrant-granting surface.

Every command is offline and deterministic. Instants arrive as explicit
arguments, following `PHASE5_INSTANT`/`PHASE6_INSTANT` and the ADR-0039 intake
instant: a moving clock would break byte reproducibility, and a review decision
must be reproducible from its inputs.

Exit codes: 0 accepted, 2 refused. A refusal prints structured JSON naming the
single unmet precondition. No command grants a weaker warrant kind as a
consolation prize, and no command derives a verdict from a model recommendation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .domain.entities import WarrantKind
from .domain.policies import TrustPolicy
from .domain.repositories import InMemoryTrustStore
from .interchange import export_dossier_dict, import_trusted_replay, write_dossier
from .phase2.artifacts import FileArtifactStore
from .review import EXPORT_VERSION, SCHEMA_VERSION
from .review.decisions import (
    build_alignment_decision,
    build_human_review_warrant,
    build_kernel_warrant,
    build_obligation_discharge,
    build_review_verdict,
)
from .review.journal import ReviewJournal
from .review.projection import build_successor, parse_instant
from .review.records import (
    AlignmentDecision,
    ReviewRefused,
    ReviewVerdict,
    ReviewerIdentity,
    ReviewerKind,
    require_identifier,
)

CLI_SCHEMA_VERSION = "1.0.0"


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _reviewer(args: argparse.Namespace) -> ReviewerIdentity:
    return ReviewerIdentity(
        id=require_identifier(args.reviewer, field="--reviewer"),
        kind=ReviewerKind(args.reviewer_kind),
        attestation=args.attestation,
    )


def _measured_trust(dossier: Any) -> dict[str, Any]:
    """Measured by Phase 1 TrustPolicy, never declared by this surface."""

    policy = TrustPolicy(dossier)
    target = policy.target_resolution()
    claim = policy.project_claim(dossier.formalization.target_claim_id)
    return {
        "target_resolution": {
            "blockers": list(target.blockers),
            "logical_status": target.logical_status,
            "semantic_alignment_status": target.semantic_alignment_status,
            "warrant_kinds": list(target.warrant_kinds),
        },
        "target_claim_projection": {
            "blockers": list(claim.blockers),
            "logical_status": claim.logical_status,
            "novelty_status": claim.novelty_status,
            "significance_status": claim.significance_status,
            "warrant_kinds": list(claim.warrant_kinds),
        },
    }


def _reviewer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reviewer", required=True, help="named human reviewer identity")
    parser.add_argument(
        "--reviewer-kind",
        required=True,
        choices=sorted(item.value for item in ReviewerKind),
        help=(
            "must be 'human'; 'model' and 'automated_tool' exist so that a non-human reviewer is "
            "a named refusal rather than an unrepresentable state"
        ),
    )
    parser.add_argument(
        "--attestation", required=True, help="what the reviewer personally checked"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Human review verdicts, semantic approvals, and warrant granting"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    verdict = commands.add_parser(
        "record-verdict", help="record a human verdict over a run awaiting review"
    )
    verdict.add_argument("workspace", type=Path)
    verdict.add_argument("run_id")
    verdict.add_argument("recorded_at", help="explicit UTC instant, e.g. 2026-08-21T12:00:00Z")
    _reviewer_arguments(verdict)
    verdict.add_argument(
        "--verdict", required=True, choices=sorted(item.value for item in ReviewVerdict)
    )
    verdict.add_argument("--rationale", required=True)
    verdict.add_argument(
        "--independently-checked",
        action="store_true",
        help=(
            "the reviewer attests an independent check of the candidate; required to accept, "
            "because the verifier's own recommendation is an input and never a verdict"
        ),
    )

    alignment = commands.add_parser(
        "decide-alignment", help="approve or dispute a semantic alignment record"
    )
    alignment.add_argument("workspace", type=Path)
    alignment.add_argument("run_id")
    alignment.add_argument("alignment_id")
    alignment.add_argument("recorded_at")
    _reviewer_arguments(alignment)
    alignment.add_argument(
        "--decision", required=True, choices=sorted(item.value for item in AlignmentDecision)
    )
    alignment.add_argument("--rationale", required=True)

    grant = commands.add_parser(
        "grant-warrant", help="grant an epistemic warrant from a recorded human review"
    )
    grant.add_argument("workspace", type=Path)
    grant.add_argument("run_id")
    grant.add_argument("claim_id")
    grant.add_argument("recorded_at")
    _reviewer_arguments(grant)
    grant.add_argument(
        "--kind", required=True, choices=sorted(item.value for item in WarrantKind)
    )
    grant.add_argument("--scope", required=True, help="exactly what the warrant covers")

    kernel = commands.add_parser(
        "grant-warrant-from-formal-check",
        help="grant a warrant from a Phase 3B kernel-checked formal-check finding",
    )
    kernel.add_argument("workspace", type=Path)
    kernel.add_argument("run_id")
    kernel.add_argument("finding", type=Path)
    kernel.add_argument("recorded_at")
    _reviewer_arguments(kernel)
    kernel.add_argument(
        "--kind", required=True, choices=sorted(item.value for item in WarrantKind)
    )
    kernel.add_argument("--scope", required=True)

    discharge = commands.add_parser(
        "discharge-obligation", help="discharge a proof obligation against a granted warrant"
    )
    discharge.add_argument("workspace", type=Path)
    discharge.add_argument("run_id")
    discharge.add_argument("obligation_id")
    discharge.add_argument("recorded_at")
    _reviewer_arguments(discharge)
    discharge.add_argument("--warrant-id", required=True)
    discharge.add_argument("--rationale", required=True)

    project = commands.add_parser(
        "project", help="project the journal into a successor dossier"
    )
    project.add_argument("workspace", type=Path)
    project.add_argument("run_id")
    project.add_argument("projected_at")
    project.add_argument("output", type=Path)
    project.add_argument("--projected-by", required=True)

    journal = commands.add_parser("journal", help="print the canonical journal export")
    journal.add_argument("workspace", type=Path)
    journal.add_argument("--output", type=Path)

    inspect = commands.add_parser(
        "inspect", help="re-verify a written successor dossier and report measured trust"
    )
    inspect.add_argument("dossier", type=Path)
    return parser


def _appended(record: dict[str, Any], appended: bool, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": True,
        "appended": appended,
        "decision": record,
        "replayed_without_change": not appended,
        "review_decision_schema_version": SCHEMA_VERSION,
        "schema_version": CLI_SCHEMA_VERSION,
        **extra,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "inspect":
        data = args.dossier.read_bytes()
        dossier = import_trusted_replay(data)
        payload = export_dossier_dict(dossier)
        _print(
            {
                "schema_version": CLI_SCHEMA_VERSION,
                "dossier_id": dossier.id.value,
                "dossier_content_hash": payload["content_hash"],
                "round_trip_bytes_identical": data.rstrip(b"\n")
                == json.dumps(
                    payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
                "counts": {
                    "evidence": len(dossier.evidence),
                    "obligations_open": sum(
                        1 for item in dossier.obligations if item.status.value == "open"
                    ),
                    "verification_records": len(dossier.verification_records),
                    "warrants": len(dossier.warrants),
                },
                "measured_trust": _measured_trust(dossier),
            }
        )
        return 0

    journal = ReviewJournal(args.workspace)
    try:
        if args.command == "journal":
            export = journal.export()
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            _print(export)
            return 0

        runs = journal.durable
        try:
            if args.command == "project":
                return _project(args, journal, runs)
            run_id = require_identifier(args.run_id, field="run_id")
            reviewer = _reviewer(args)
            recorded_at = parse_instant(args.recorded_at).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z")
            if args.command == "record-verdict":
                proposal, loaded = build_review_verdict(
                    runs=runs,
                    artifacts=FileArtifactStore(args.workspace / "artifacts"),
                    run_id=run_id,
                    reviewer=reviewer,
                    verdict=ReviewVerdict(args.verdict),
                    independently_checked=bool(args.independently_checked),
                    rationale=args.rationale,
                )
                record, appended = journal.append_once(proposal, recorded_at=recorded_at)
                _print(
                    _appended(
                        record,
                        appended,
                        {
                            "reviewed_verifier_finding": {
                                "artifact_hash": loaded["artifact_hash"],
                                "recommendation": loaded["finding"].get("recommendation"),
                                "recommendation_is_an_input_not_a_verdict": True,
                                "source_id": loaded["source_id"],
                                "source_kind": loaded["source_kind"],
                            }
                        },
                    )
                )
                return 0
            if args.command == "decide-alignment":
                proposal = build_alignment_decision(
                    runs=runs,
                    run_id=run_id,
                    alignment_id=require_identifier(args.alignment_id, field="alignment_id"),
                    approver=reviewer,
                    decision=AlignmentDecision(args.decision),
                    rationale=args.rationale,
                )
                record, appended = journal.append_once(proposal, recorded_at=recorded_at)
                _print(_appended(record, appended, {}))
                return 0
            if args.command == "grant-warrant":
                proposal = build_human_review_warrant(
                    runs=runs,
                    journal_decisions=journal.decisions(),
                    run_id=run_id,
                    claim_id=require_identifier(args.claim_id, field="claim_id"),
                    kind=WarrantKind(args.kind),
                    scope=args.scope,
                    grantor=reviewer,
                )
                record, appended = journal.append_once(proposal, recorded_at=recorded_at)
                _print(
                    _appended(
                        record, appended, {"warrant_id": record["payload"]["warrant_id"]}
                    )
                )
                return 0
            if args.command == "grant-warrant-from-formal-check":
                proposal = build_kernel_warrant(
                    runs=runs,
                    journal_decisions=journal.decisions(),
                    run_id=run_id,
                    finding_bytes=args.finding.read_bytes(),
                    kind=WarrantKind(args.kind),
                    scope=args.scope,
                    grantor=reviewer,
                )
                record, appended = journal.append_once(proposal, recorded_at=recorded_at)
                _print(
                    _appended(
                        record, appended, {"warrant_id": record["payload"]["warrant_id"]}
                    )
                )
                return 0
            proposal = build_obligation_discharge(
                runs=runs,
                journal_decisions=journal.decisions(),
                run_id=run_id,
                obligation_id=require_identifier(args.obligation_id, field="obligation_id"),
                warrant_id=args.warrant_id,
                reviewer=reviewer,
                rationale=args.rationale,
            )
            record, appended = journal.append_once(proposal, recorded_at=recorded_at)
            _print(_appended(record, appended, {}))
            return 0
        except ReviewRefused as refusal:
            stored = [
                journal.record_refusal(item, recorded_at=_refusal_instant(args))
                for item in refusal.refusals
            ]
            _print(
                {
                    "schema_version": CLI_SCHEMA_VERSION,
                    "command": args.command,
                    "accepted": False,
                    "refusals": [item.value() for item in refusal.refusals],
                    "refusal_record_ids": [item["refusal_id"] for item in stored],
                }
            )
            return 2
    finally:
        journal.close()


def _refusal_instant(args: argparse.Namespace) -> str:
    """Refusals are retained with the instant the caller supplied, when valid."""

    raw = getattr(args, "recorded_at", None) or getattr(args, "projected_at", None)
    try:
        return parse_instant(str(raw)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except ReviewRefused:
        return "unspecified"


def _project(args: argparse.Namespace, journal: ReviewJournal, runs: Any) -> int:
    run_id = require_identifier(args.run_id, field="run_id")
    projection = build_successor(
        runs=runs,
        run_id=run_id,
        journal_export=journal.export(),
        projected_at=parse_instant(args.projected_at),
        projected_by=require_identifier(args.projected_by, field="--projected-by"),
    )
    # Append-only store admission: the successor must satisfy the same Phase 1
    # invariants as any other dossier.
    admitted = InMemoryTrustStore().append_dossier(projection.successor)
    written = write_dossier(admitted, args.output)
    replayed = import_trusted_replay(args.output.read_bytes())
    replay_hash = export_dossier_dict(replayed)["content_hash"]
    if written != projection.successor_hash or replay_hash != written or replayed != admitted:
        raise RuntimeError("successor dossier does not round-trip byte-identically")
    _print(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "review_journal_schema_version": EXPORT_VERSION,
            "accepted": True,
            "applied_decision_ids": list(projection.applied_decision_ids),
            "derived_counts": dict(sorted(projection.derived_counts.items())),
            "journal_semantic_hash": projection.journal_hash,
            "prior_dossier_hash": projection.prior_dossier_hash,
            "prior_dossier_id": projection.prior_dossier_id,
            "reviewers": list(projection.reviewers),
            "round_trip_hash_preserved": True,
            "successor_dossier_hash": projection.successor_hash,
            "successor_dossier_id": projection.successor.id.value,
            "successor_path": str(args.output),
            "measured_trust": _measured_trust(projection.successor),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
