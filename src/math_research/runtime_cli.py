"""Command line surface for the bounded iterative research runtime (ADR-0047).

`run` defaults to `--provider fixture`, which calls nothing and needs no key,
so the offline acceptance path is the default and spending money is the
explicit choice. A live provider additionally requires `--execute`, a
content-hashed session configuration, and a confirmed pricing snapshot; the
Phase 2 preflight is reused unchanged rather than reimplemented, so a live
session cannot start on an unverified rate or an unpinned SDK.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .application.problem_intake import load_problem_definition_file
from .domain.entities import OpaqueId, ResearchDossier
from .interchange import export_dossier_dict
from .novelty import NoveltyRecheckError, read_recheck, require_checkpoint
from .phase2.live_config import load_live_run_configuration
from .phase2.live_gate import preflight_live_gate
from .phase2.pricing import load_pricing_snapshot
from .phase2.provider_registry import build_gateway
from .phase2.records import BudgetLimits
from .phase2.sqlite_workspace import SQLiteWorkspace
from .runtime.fixtures import RehearsalGateway
from .runtime.lead import ResearchLeadRuntime, freeze_target
from .runtime.records import LeadSession
from .runtime.reporting import render_session_report, session_facts
from .runtime.serialization import canonical_json
from .runtime.session_config import (
    SessionConfigurationError,
    create_session_configuration,
    load_session_configuration,
    session_configuration_payload,
    write_session_configuration,
)


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _dossier(args: argparse.Namespace) -> ResearchDossier:
    if args.problem is not None:
        instant = datetime.fromisoformat(args.instant) if args.instant else datetime(
            2026, 8, 21, tzinfo=timezone.utc
        )
        result = load_problem_definition_file(args.problem, instant=instant)
        return result.dossier
    from .phase2.fixtures import build_open_theorem_dossier

    return build_open_theorem_dossier()


def _session_config_create(args: argparse.Namespace) -> int:
    try:
        configuration = create_session_configuration(
            session_configuration_id=OpaqueId(args.session_configuration_id),
            max_iterations=args.max_iterations,
            max_model_calls=args.max_model_calls,
            max_cost_microusd=args.max_cost_microusd,
            max_wall_milliseconds=args.max_wall_milliseconds,
            stagnation_window=args.stagnation_window,
            per_iteration_budget=BudgetLimits(
                max_input_tokens=args.iteration_max_input_tokens,
                max_output_tokens=args.iteration_max_output_tokens,
                max_cost_microusd=args.iteration_max_cost_microusd,
                max_wall_milliseconds=args.iteration_max_wall_milliseconds,
                max_attempts=args.iteration_max_attempts,
            ),
        )
    except SessionConfigurationError as error:
        _print({"status": "rejected", "reason": str(error)})
        return 2
    write_session_configuration(configuration, args.output)
    _print({"status": "written", "path": str(args.output), **session_configuration_payload(configuration)})
    return 0


def _run(args: argparse.Namespace) -> int:
    configuration = load_session_configuration(args.config)
    dossier = _dossier(args)
    target = freeze_target(dossier)
    if args.novelty_recheck is None:
        _print({"status": "refused", "reason": "fresh_novelty_recheck_required_before_research"})
        return 2
    try:
        recheck = read_recheck(args.novelty_recheck)
        require_checkpoint(
            recheck, checkpoint="before_research",
            subject_id=dossier.problem.id.value,
            subject_hash=str(export_dossier_dict(dossier)["content_hash"]),
            next_action_id=args.session_id,
        )
    except (NoveltyRecheckError, OSError) as error:
        _print({"status": "refused", "reason": str(error)})
        return 2
    pricing = load_pricing_snapshot(args.pricing_snapshot) if args.pricing_snapshot else None

    if args.provider == "fixture":
        referenced = tuple(sorted({
            target.target_claim_id.value,
            dossier.formalization.id.value,
            dossier.semantic_alignment.id.value,
            *(item.value for item in dossier.formalization.assumption_claim_ids),
        }))
        gateway: Any = RehearsalGateway(
            target_claim_id=target.target_claim_id.value,
            referenced_entity_ids=referenced,
            distinct_attempts=args.fixture_distinct_attempts,
            verdict=args.fixture_verdict,
            final_verdict=args.fixture_final_verdict,
            final_after=args.fixture_final_after,
        )
    else:
        if not args.execute:
            _print({
                "status": "refused",
                "reason": "a live provider session requires --execute",
                "provider": args.provider,
            })
            return 2
        if args.live_config is None or pricing is None:
            _print({
                "status": "refused",
                "reason": "a live provider session requires --live-config and --pricing-snapshot",
            })
            return 2
        live = load_live_run_configuration(args.live_config)
        if live.provider != args.provider:
            _print({
                "status": "refused",
                "reason": "the named provider differs from the content-hashed live configuration",
                "requested": args.provider,
                "configured": live.provider,
            })
            return 2
        preflight = preflight_live_gate(live, pricing)
        if not preflight.passed:
            _print({
                "status": "refused",
                "reason": "the Phase 2 live preflight did not pass",
                "missing_variables": list(preflight.missing_variables),
                "failed_checks": list(preflight.failed_checks),
            })
            return 2
        gateway = build_gateway(live.provider, live.model_identifier)

    runtime = ResearchLeadRuntime(
        root=args.root,
        configuration=configuration,
        proposer=gateway,
        verifier=gateway,
        pricing_snapshot=pricing,
    )
    session = runtime.run(
        session_id=OpaqueId(args.session_id), dossier=dossier, novelty_recheck=recheck,
    )
    with SQLiteWorkspace(args.root / "workspace.sqlite3") as workspace:
        facts = session_facts(session, workspace)
        report = render_session_report(session, workspace)
    (args.root / "session-report.md").write_text(report, encoding="utf-8")
    (args.root / "session-facts.json").write_text(canonical_json(facts) + "\n", encoding="utf-8")
    _print(facts)
    return 0


def _inspect(args: argparse.Namespace) -> int:
    session = _load_session(args.root / "session.json")
    with SQLiteWorkspace(args.root / "workspace.sqlite3") as workspace:
        _print(session_facts(session, workspace))
    return 0


def _report(args: argparse.Namespace) -> int:
    session = _load_session(args.root / "session.json")
    with SQLiteWorkspace(args.root / "workspace.sqlite3") as workspace:
        report = render_session_report(session, workspace)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


def _load_session(path: Path) -> LeadSession:
    """Rebuild a session record from its canonical bytes.

    Deliberately strict: the stored `content_hash` is recomputed and compared,
    so a hand-edited session record is a load failure rather than a report.
    """
    from .runtime.records import (
        IterationOutcome,
        IterationRecord,
        IterationUsage,
        SessionUsage,
        TargetIdentity,
        TerminalReason,
        VerifierFinding,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    target = TargetIdentity(
        target_claim_id=OpaqueId(payload["target"]["target_claim_id"]),
        target_statement_hash=payload["target"]["target_statement_hash"],
        formalization_statement_hash=payload["target"]["formalization_statement_hash"],
        assumption_manifest_hash=payload["target"]["assumption_manifest_hash"],
        semantic_alignment_hash=payload["target"]["semantic_alignment_hash"],
        dossier_hash=payload["target"]["dossier_hash"],
    )
    iterations = tuple(
        IterationRecord(
            iteration_index=item["iteration_index"],
            run_id=OpaqueId(item["run_id"]),
            branch_id=item["branch_id"],
            hypothesis_digest=item["hypothesis_digest"],
            duplicate_of_iteration=item["duplicate_of_iteration"],
            proposal_id=OpaqueId(item["proposal_id"]) if item["proposal_id"] else None,
            proposal_kind=item["proposal_kind"],
            proposal_artifact_hash=item["proposal_artifact_hash"],
            verifier_manifest_hash=item["verifier_manifest_hash"],
            verifier_recommendation=item["verifier_recommendation"],
            findings=tuple(
                VerifierFinding(code=finding["code"], outcome=finding["outcome"])
                for finding in item["findings"]
            ),
            outcome=IterationOutcome(item["outcome"]),
            phase2_run_status=item["phase2_run_status"],
            usage=IterationUsage(**item["usage"]),
            productive=item["productive"],
            content_hash=item["content_hash"],
            operational_hash=item["operational_hash"],
        )
        for item in payload["iterations"]
    )
    for item, stored in zip(iterations, payload["iterations"]):
        expected = item.with_content_hash()
        if expected.content_hash != stored["content_hash"]:
            raise ValueError(f"iteration {item.iteration_index} content_hash mismatch")
        if expected.operational_hash != stored["operational_hash"]:
            raise ValueError(f"iteration {item.iteration_index} operational_hash mismatch")
    session = LeadSession(
        session_id=OpaqueId(payload["session_id"]),
        dossier_id=OpaqueId(payload["dossier_id"]),
        target=target,
        session_configuration_id=OpaqueId(payload["session_configuration_id"]),
        session_configuration_hash=payload["session_configuration_hash"],
        iterations=iterations,
        terminal_reason=TerminalReason(payload["terminal_reason"]),
        exhausted_bound=payload["exhausted_bound"],
        usage=SessionUsage(**payload["usage"]),
        distinct_hypotheses=payload["distinct_hypotheses"],
        started_at=payload["started_at"],
        ended_at=payload["ended_at"],
        novelty_recheck_id=payload["novelty_recheck_id"],
        novelty_recheck_hash=payload["novelty_recheck_hash"],
        prior_art_outcome=payload["prior_art_outcome"],
        prior_art_relationship=payload["prior_art_relationship"],
        prior_resolution=payload["prior_resolution"],
        prior_resolution_verification=payload["prior_resolution_verification"],
        report_classification=payload["report_classification"],
        target_resolution_status=payload["target_resolution_status"],
        content_hash=payload["content_hash"],
        operational_hash=payload["operational_hash"],
    )
    expected_session = session.with_content_hash()
    if expected_session.content_hash != payload["content_hash"]:
        raise ValueError("session content_hash mismatch")
    if expected_session.operational_hash != payload["operational_hash"]:
        raise ValueError("session operational_hash mismatch")
    try:
        recheck = read_recheck(path.parent / "novelty-recheck.json")
    except (NoveltyRecheckError, OSError) as error:
        raise ValueError(f"session novelty re-check unavailable: {error}") from error
    if (
        recheck.recheck_id != session.novelty_recheck_id
        or recheck.content_hash != session.novelty_recheck_hash
    ):
        raise ValueError("session novelty re-check identity mismatch")
    return session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runtime", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "session-config-create", help="write a content-hashed session bounds artifact"
    )
    create.add_argument("output", type=Path)
    create.add_argument("--session-configuration-id", required=True)
    create.add_argument("--max-iterations", type=int, required=True)
    create.add_argument("--max-model-calls", type=int, required=True)
    create.add_argument("--max-cost-microusd", type=int, required=True)
    create.add_argument("--max-wall-milliseconds", type=int, required=True)
    create.add_argument("--stagnation-window", type=int, required=True)
    create.add_argument("--iteration-max-input-tokens", type=int, required=True)
    create.add_argument("--iteration-max-output-tokens", type=int, required=True)
    create.add_argument("--iteration-max-cost-microusd", type=int, required=True)
    create.add_argument("--iteration-max-wall-milliseconds", type=int, required=True)
    create.add_argument("--iteration-max-attempts", type=int, default=2)

    run = commands.add_parser("run", help="run one bounded iterative session")
    run.add_argument("root", type=Path)
    run.add_argument("session_id")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--problem", type=Path)
    run.add_argument("--instant")
    run.add_argument("--novelty-recheck", type=Path)
    run.add_argument("--provider", default="fixture")
    run.add_argument("--live-config", type=Path)
    run.add_argument("--pricing-snapshot", type=Path)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--fixture-distinct-attempts", type=int, default=3)
    run.add_argument("--fixture-verdict", default="unresolved")
    run.add_argument("--fixture-final-verdict")
    run.add_argument("--fixture-final-after", type=int)

    inspect = commands.add_parser("inspect", help="verify and inspect a persisted session")
    inspect.add_argument("root", type=Path)

    report = commands.add_parser("report", help="render the durable session report")
    report.add_argument("root", type=Path)
    report.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    if args.command == "session-config-create":
        return _session_config_create(args)
    if args.command == "run":
        return _run(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "report":
        return _report(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
