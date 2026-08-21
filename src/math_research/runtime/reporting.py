"""Durable, replayable reporting for one iterative session.

The report is rendered from the session record and the Phase 2 workspace, and
from nothing else. It never calls a model, and it is required to state what did
*not* happen: a report that lists four iterations and stays silent about the
absence of a warrant reads like progress.

`providers_called` is read out of the durable `model_calls` rows rather than
declared, so an offline rehearsal cannot be reported as a live run and a live
run cannot be reported as a rehearsal.
"""

from __future__ import annotations

from typing import Any

from ..phase2.sqlite_workspace import SQLiteWorkspace
from .records import LeadSession, TerminalReason
from .serialization import canonical_hash

_TERMINAL_PROSE: dict[str, str] = {
    TerminalReason.AWAITING_HUMAN_REVIEW.value: (
        "an isolated verifier declined to fault one proposal, and a person now "
        "has to read it. This is the strongest outcome the runtime can reach "
        "and it is not an acceptance"
    ),
    TerminalReason.STAGNATED.value: (
        "consecutive iterations stopped contributing a new hypothesis or a new "
        "finding signature. This is a stop rule, not a verdict on the problem"
    ),
    TerminalReason.ITERATIONS_EXHAUSTED.value: "the session used every iteration it was allowed",
    TerminalReason.BUDGET_EXHAUSTED.value: "a named bound forbade another iteration",
    TerminalReason.ITERATION_FAILED.value: (
        "a model call did not return validated structured output, and the "
        "runtime does not retry above the Phase 2 attempt bound"
    ),
    TerminalReason.NO_LIVE_BRANCH.value: "no branch remained to explore",
}


def session_facts(session: LeadSession, workspace: SQLiteWorkspace) -> dict[str, Any]:
    """Machine-readable gate values. Every one is measured, none is declared."""
    calls: list[dict[str, Any]] = []
    for record in session.iterations:
        calls.extend(dict(row) for row in workspace.list_model_calls(record.run_id))
    providers = sorted({str(row["provider"]) for row in calls})
    return {
        "schema_version": session.schema_version,
        "session_id": session.session_id.value,
        "content_hash": session.content_hash,
        "session_configuration_id": session.session_configuration_id.value,
        "session_configuration_hash": session.session_configuration_hash,
        "target_claim_id": session.target.target_claim_id.value,
        "target_frozen_hash": session.target.frozen_hash(),
        "terminal_reason": session.terminal_reason.value,
        "exhausted_bound": session.exhausted_bound,
        "iterations": len(session.iterations),
        "distinct_hypotheses": session.distinct_hypotheses,
        "duplicate_iterations": sum(
            1 for item in session.iterations if item.duplicate_of_iteration is not None
        ),
        "productive_iterations": sum(1 for item in session.iterations if item.productive),
        "model_calls": session.usage.model_calls,
        "recorded_model_calls": len(calls),
        "input_tokens": session.usage.input_tokens,
        "output_tokens": session.usage.output_tokens,
        "cost_microusd": session.usage.cost_microusd,
        "providers_called": providers,
        "live_model_calls": [item for item in providers if item not in {"fixture", "scripted", "none"}],
        "verifier_manifest_hashes": [
            item.verifier_manifest_hash for item in session.iterations
            if item.verifier_manifest_hash is not None
        ],
        "epistemic_warrant_created": session.epistemic_warrant_created,
        "obligations_discharged": session.obligations_discharged,
        "novelty_assessment": session.novelty_assessment,
        "significance_assessment": session.significance_assessment,
        "retention_gain_measured": session.retention_gain_measured,
        "iteration_hashes": [item.content_hash for item in session.iterations],
        "timeline_replay_hash": canonical_hash([
            workspace.timeline(item.run_id) for item in session.iterations
        ]),
    }


def render_session_report(session: LeadSession, workspace: SQLiteWorkspace) -> str:
    facts = session_facts(session, workspace)
    lines: list[str] = []
    lines.append(f"# Iterative research session `{session.session_id.value}`")
    lines.append("")
    lines.append(f"- Target claim: `{facts['target_claim_id']}`")
    lines.append(f"- Frozen target hash: `{facts['target_frozen_hash']}`")
    lines.append(f"- Session bounds: `{facts['session_configuration_id']}` (`{facts['session_configuration_hash']}`)")
    lines.append(f"- Session record hash: `{facts['content_hash']}`")
    live = facts["live_model_calls"]
    lines.append(
        "- Model calls: "
        + (
            f"{facts['recorded_model_calls']} to {', '.join(live)}"
            if live
            else f"{facts['recorded_model_calls']} offline, providers {facts['providers_called'] or ['none']} -- NO live model was called"
        )
    )
    lines.append("")
    reason = facts["terminal_reason"]
    prose = _TERMINAL_PROSE.get(reason, "an unrecognized terminal reason")
    bound = f" (bound: `{facts['exhausted_bound']}`)" if facts["exhausted_bound"] else ""
    lines.append(f"## Why it stopped: `{reason}`{bound}")
    lines.append("")
    lines.append(f"The session stopped because {prose}.")
    lines.append("")
    lines.append("## Iterations")
    lines.append("")
    lines.append("| # | outcome | hypothesis | duplicate of | verifier | findings | productive | calls |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for item in session.iterations:
        digest = item.hypothesis_digest[7:19] if item.hypothesis_digest else "--"
        duplicate = str(item.duplicate_of_iteration) if item.duplicate_of_iteration else "--"
        codes = ", ".join(finding.code for finding in item.findings) or "--"
        lines.append(
            f"| {item.iteration_index} | {item.outcome.value} | `{digest}` | {duplicate} "
            f"| {item.verifier_recommendation or '--'} | {codes} "
            f"| {'yes' if item.productive else 'no'} | {item.usage.model_calls} |"
        )
    lines.append("")
    lines.append(
        f"{facts['iterations']} iterations, {facts['distinct_hypotheses']} distinct hypotheses, "
        f"{facts['duplicate_iterations']} discarded as repeats, "
        f"{facts['productive_iterations']} productive."
    )
    lines.append("")
    lines.append("## What this session did not do")
    lines.append("")
    lines.append(
        "- It created **no epistemic warrant**. "
        f"`epistemic_warrant_created` is `{facts['epistemic_warrant_created']}`, unconditionally, "
        "including on the path that ends in review."
    )
    lines.append(
        "- It discharged **no proof obligation**. "
        f"`obligations_discharged` is `{facts['obligations_discharged']}`. Every obligation the "
        "dossier opened is still open."
    )
    lines.append(
        "- It changed **no trust state**: no warrant, evidence disposition, applicability "
        "record, semantic-alignment approval, or graph admission was written."
    )
    lines.append(
        f"- Novelty is `{facts['novelty_assessment']}` and significance is "
        f"`{facts['significance_assessment']}`. Neither was assessed, and the iteration "
        "count is not evidence about either."
    )
    lines.append(
        "- It did **not** measure whether iterating helped. "
        f"`retention_gain_measured` is `{facts['retention_gain_measured']}`; the ADR-0029 "
        "retention question is untouched by this run."
    )
    lines.append(
        "- It activated **no search tier**: one lead, one centralized verifier, no "
        "specialists, no parallel workers, no evolutionary selection."
    )
    lines.append("")
    lines.append(
        "The verifier context for every iteration excluded the proposer's narrative and "
        "the session history; that isolation is enforced in code and its manifest hashes "
        f"are recorded ({len(facts['verifier_manifest_hashes'])} manifests)."
    )
    lines.append("")
    return "\n".join(lines)


def replay_session_report(session: LeadSession, database_root: Any) -> str:
    """Re-render from the durable workspace alone, with no gateway in reach."""
    from pathlib import Path

    with SQLiteWorkspace(Path(database_root) / "workspace.sqlite3") as workspace:
        return render_session_report(session, workspace)
