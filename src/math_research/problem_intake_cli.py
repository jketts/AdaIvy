"""CLI for the declarative problem intake (ADR-0039).

Every command is offline, deterministic, and free of clock reads: the intake
instant is an explicit argument, exactly as `PHASE5_INSTANT`/`PHASE6_INSTANT`
are explicit inputs in the Makefile.

Trust status is never taken from the problem file. It is MEASURED here by
running the Phase 1 `TrustPolicy` over the constructed dossier and recorded in
the printed summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .application.problem_intake import (
    PROBLEM_DEFINITION_SCHEMA_VERSION,
    ProblemDefinitionError,
    ProblemIntakeResult,
    load_problem_definition_file,
    parse_instant,
    parse_problem_definition,
    problem_definition_schema_text,
)
from .domain.entities import ObligationStatus, ResearchDossier
from .domain.policies import TrustPolicy
from .domain.repositories import InMemoryTrustStore
from .interchange import export_dossier_dict, import_trusted_replay, write_dossier

SUMMARY_SCHEMA_VERSION = "1.0.0"


def _render_intake_report(result: ProblemIntakeResult, dossier_hash: str) -> str:
    """An intake report states what was declared and what was measured.

    `reporting.render_traceable_report` is deliberately not reused: its lines
    assert that target evidence was independently checked, which is never true
    of an intake dossier.
    """
    dossier = result.dossier
    definition = result.definition
    trust = _measured_trust(dossier)
    target = next(item for item in dossier.claims if item.id.value == trust["target_claim_id"])
    open_obligations = ", ".join(
        sorted(item.id.value for item in dossier.obligations if item.status is ObligationStatus.OPEN)
    )
    return "\n".join([
        "# Declarative Problem Intake Report",
        "",
        f"- Problem definition `{definition.problem_definition_id}` has canonical hash "
        f"`{definition.canonical_document_hash}` and source bytes hash "
        f"`{definition.source_bytes_hash}`. [refs: {dossier.audit_events[0].id}]",
        f"- Dossier `{dossier.id}` has canonical content hash `{dossier_hash}` and binds the "
        f"canonical problem-definition hash into its own identity. [refs: {dossier.id}]",
        f"- Declared domain is `{definition.declared_domain}`; originating principal is "
        f"`{definition.originating_principal}`. [refs: {dossier.problem.id}]",
        f"- Declared target: {target.statement} [refs: {target.id}, {dossier.formalization.id}]",
        f"- MEASURED by Phase 1 TrustPolicy: logical status `{trust['logical_status']}`, semantic "
        f"alignment `{trust['semantic_alignment_status']}`, warrant kinds "
        f"`{trust['warrant_kinds']}`. Declared prose in the problem file did not change this. "
        f"[refs: {target.id}, {dossier.semantic_alignment.id}]",
        f"- The intake created no warrant, evidence, verification record, source applicability "
        f"record, or representation map: counts are "
        f"{len(dossier.warrants)}, {len(dossier.evidence)}, "
        f"{len(dossier.verification_records)}, {len(dossier.source_applicability)}, "
        f"{len(dossier.representation_maps)}. [refs: {dossier.id}]",
        f"- Open obligations recorded by the intake: {open_obligations}. "
        f"[refs: {open_obligations}]",
        f"- Novelty is `{trust['novelty_status']}`, significance is "
        f"`{trust['significance_status']}`, contribution is `{trust['contribution_status']}`; the "
        f"problem file cannot set any of them. [refs: {target.id}]",
        "",
    ])


def _measured_trust(dossier: ResearchDossier) -> dict[str, Any]:
    """Measured, never declared: the projection is computed by TrustPolicy."""
    projection = TrustPolicy(dossier).target_resolution()
    return {
        "blockers": list(projection.blockers),
        "contribution_status": projection.contribution_status,
        "logical_status": projection.logical_status,
        "novelty_status": projection.novelty_status,
        "semantic_alignment_status": projection.semantic_alignment_status,
        "significance_status": projection.significance_status,
        "target_claim_id": projection.claim_id.value,
        "warrant_kinds": list(projection.warrant_kinds),
    }


def _summary(result: ProblemIntakeResult) -> dict[str, Any]:
    dossier = result.dossier
    definition = result.definition
    payload = export_dossier_dict(dossier)
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "problem_definition_schema_version": PROBLEM_DEFINITION_SCHEMA_VERSION,
        "problem_definition_id": definition.problem_definition_id,
        "problem_definition_canonical_hash": definition.canonical_document_hash,
        "problem_definition_source_bytes_hash": definition.source_bytes_hash,
        "declared_domain": definition.declared_domain,
        "originating_principal": definition.originating_principal.value,
        "intake_instant": result.instant.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "dossier_id": dossier.id.value,
        "dossier_content_hash": payload["content_hash"],
        "formalization_id": dossier.formalization.id.value,
        "semantic_alignment_id": dossier.semantic_alignment.id.value,
        "counts": {
            "claims": len(dossier.claims),
            "evidence": len(dossier.evidence),
            "obligations_open": sum(
                1 for item in dossier.obligations if item.status is ObligationStatus.OPEN
            ),
            "representation_maps": len(dossier.representation_maps),
            "source_applicability": len(dossier.source_applicability),
            "verification_records": len(dossier.verification_records),
            "warrants": len(dossier.warrants),
        },
        "measured_trust": _measured_trust(dossier),
    }


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _rejection(error: ProblemDefinitionError, path: Path) -> dict[str, Any]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "problem_definition_schema_version": PROBLEM_DEFINITION_SCHEMA_VERSION,
        "accepted": False,
        "source": path.name,
        "codes": list(error.codes),
        "issues": [
            {"path": item.path, "code": item.code, "message": item.message}
            for item in error.issues
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Declarative research problem intake")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a problem definition without building a dossier")
    validate.add_argument("definition", type=Path)
    create = commands.add_parser("create", help="build a canonical dossier from a problem definition")
    create.add_argument("definition", type=Path)
    create.add_argument("instant", help="explicit UTC intake instant, for example 2026-08-21T00:00:00Z")
    create.add_argument("output", type=Path)
    demo = commands.add_parser("demo", help="create, replay, re-derive, and report one problem definition")
    demo.add_argument("definition", type=Path)
    demo.add_argument("instant")
    demo.add_argument("--output-dir", type=Path, required=True)
    schema = commands.add_parser("schema", help="print the schema derived from the Phase 1 enums")
    schema.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.command == "schema":
        text = problem_definition_schema_text()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0

    if args.command == "validate":
        try:
            definition = parse_problem_definition(args.definition.read_bytes())
        except ProblemDefinitionError as error:
            _print(_rejection(error, args.definition))
            return 2
        _print({
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "problem_definition_schema_version": PROBLEM_DEFINITION_SCHEMA_VERSION,
            "accepted": True,
            "problem_definition_id": definition.problem_definition_id,
            "declared_domain": definition.declared_domain,
            "originating_principal": definition.originating_principal.value,
            "problem_definition_canonical_hash": definition.canonical_document_hash,
            "problem_definition_source_bytes_hash": definition.source_bytes_hash,
            "assumption_claims": len(definition.assumption_claims),
            "target_claim_local_id": definition.target_claim.local_id,
            "target_claim_scope": definition.target_claim.scope.value,
        })
        return 0

    try:
        instant = parse_instant(args.instant)
        result = load_problem_definition_file(args.definition, instant=instant)
    except ProblemDefinitionError as error:
        _print(_rejection(error, args.definition))
        return 2

    # Append-only store admission: the builder output must satisfy the same
    # Phase 1 invariants as any other dossier.
    dossier = InMemoryTrustStore().append_dossier(result.dossier)

    if args.command == "create":
        write_dossier(dossier, args.output)
        summary = _summary(result)
        summary["dossier_path"] = str(args.output)
        _print(summary)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dossier_path = args.output_dir / "intake-dossier.json"
    report_path = args.output_dir / "intake-report.md"
    summary_path = args.output_dir / "intake-summary.json"
    original_hash = write_dossier(dossier, dossier_path)
    replayed = import_trusted_replay(dossier_path.read_bytes())
    replay_hash = export_dossier_dict(replayed)["content_hash"]
    if original_hash != replay_hash or replayed != dossier:
        raise RuntimeError("canonical replay changed dossier identity or meaning")
    rederived = load_problem_definition_file(args.definition, instant=instant).dossier
    if export_dossier_dict(rederived)["content_hash"] != original_hash:
        raise RuntimeError("re-deriving the dossier from the same problem file changed its identity")
    report_path.write_text(_render_intake_report(result, original_hash), encoding="utf-8")
    summary = _summary(result)
    summary.update({
        "round_trip_hash_preserved": True,
        "rederived_hash_identical": True,
        "dossier_path": str(dossier_path),
        "report_path": str(report_path),
        "summary_path": str(summary_path),
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
