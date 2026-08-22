"""One resumable central campaign over explicit literature/runtime actions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from .checkpoint import ActionCheckpointStore, AmbiguousEffectError
from .records import ActionType, canonical_bytes, canonical_hash

END_TO_END_SCHEMA_VERSION = "adaivy.end-to-end-campaign.v1"
ACTION_SCHEMA_VERSION = "2.0.0"
ACTION_SCHEMA_PATH = Path("schemas/model-campaign-action-v2.schema.json")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_V2_SUPPORTED_ACTIONS = frozenset({
    ActionType.SEARCH_LITERATURE, ActionType.FOLLOW_DISCOVERY_RESULTS,
    ActionType.ACQUIRE_SOURCE, ActionType.PARSE_SOURCE, ActionType.EMBED_SOURCES,
    ActionType.REFRESH_RETRIEVAL_INDEX, ActionType.RETRIEVE_EVIDENCE,
    ActionType.EXPERIMENT, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM,
    ActionType.INSPECT_RESULT, ActionType.DERIVE, ActionType.FALSIFY,
    ActionType.VERIFY, ActionType.FORMAL_CHECK, ActionType.SUSPEND_BRANCH,
    ActionType.REPORT,
})


@dataclass(frozen=True, slots=True)
class RuntimeAction:
    action_type: ActionType
    request: Mapping[str, Any] | Callable[[], Mapping[str, Any]]
    effect: Callable[[str], Mapping[str, Any]]
    paid_or_irreversible: bool = False


class EndToEndRuntimeError(ValueError):
    pass


def parse_planned_action(
    raw: bytes | str, effect: Callable[[str], Mapping[str, Any]], *,
    paid_or_irreversible: bool = False,
) -> RuntimeAction:
    """Consume the closed v2 planner contract at the campaign boundary."""

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            decoded: dict[str, Any] = {}
            for key, item in pairs:
                if key in decoded:
                    raise EndToEndRuntimeError(f"duplicate planned-action field: {key}")
                decoded[key] = item
            return decoded

        value = json.loads(text, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EndToEndRuntimeError("planned action is not valid UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "action_type", "branch_id", "rationale",
        "operation_request",
    }:
        raise EndToEndRuntimeError("planned action fields differ from v2")
    if value["schema_version"] != ACTION_SCHEMA_VERSION:
        raise EndToEndRuntimeError("planned action schema version differs")
    try:
        action_type = ActionType(value["action_type"])
    except (TypeError, ValueError) as error:
        raise EndToEndRuntimeError("planned action type differs") from error
    if action_type not in _V2_SUPPORTED_ACTIONS:
        raise EndToEndRuntimeError("planned action is outside the v2 campaign contract")
    if not isinstance(value["branch_id"], str) or not _IDENTIFIER.fullmatch(value["branch_id"]):
        raise EndToEndRuntimeError("planned action branch differs")
    rationale = value["rationale"]
    if not isinstance(rationale, str) or not rationale or len(rationale.encode()) > 2_000:
        raise EndToEndRuntimeError("planned action rationale differs")
    request = value["operation_request"]
    if not isinstance(request, dict) or len(request) > 32:
        raise EndToEndRuntimeError("planned operation request differs")
    return RuntimeAction(
        action_type=action_type, request=request, effect=effect,
        paid_or_irreversible=paid_or_irreversible,
    )


class EndToEndCampaignRunner:
    """Sequential, single-writer orchestrator; no agent spawning or hidden I/O."""

    def __init__(
        self, root: Path, *, campaign_id: str, recorded_at: str,
        max_actions: int,
    ) -> None:
        if max_actions < 1:
            raise EndToEndRuntimeError("max_actions must be positive")
        self.root = root
        self.campaign_id = campaign_id
        self.recorded_at = recorded_at
        self.max_actions = max_actions
        self.checkpoints = ActionCheckpointStore(root, campaign_id)

    def run(self, actions: Sequence[RuntimeAction]) -> dict[str, Any]:
        if len(actions) > self.max_actions:
            raise EndToEndRuntimeError("end-to-end action bound exceeded")
        types = [item.action_type for item in actions]
        if ActionType.SEARCH_LITERATURE not in types:
            raise EndToEndRuntimeError("recorded literature search is mandatory")
        first_research = next((
            index for index, item in enumerate(types)
            if item in {
                ActionType.DERIVE, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM,
                ActionType.EXPERIMENT, ActionType.FALSIFY, ActionType.VERIFY,
                ActionType.FORMAL_CHECK,
            }
        ), len(types))
        if types.index(ActionType.SEARCH_LITERATURE) > first_research:
            raise EndToEndRuntimeError("literature search must precede substantive research")
        stages = {
            ActionType.SEARCH_LITERATURE: 1,
            ActionType.FOLLOW_DISCOVERY_RESULTS: 2,
            ActionType.ACQUIRE_SOURCE: 3,
            ActionType.PARSE_SOURCE: 4,
            ActionType.EMBED_SOURCES: 5,
            ActionType.REFRESH_RETRIEVAL_INDEX: 6,
            ActionType.RETRIEVE_EVIDENCE: 7,
        }
        stage = 0
        research = {
            ActionType.DERIVE, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM,
            ActionType.EXPERIMENT, ActionType.FALSIFY, ActionType.VERIFY,
            ActionType.FORMAL_CHECK,
        }
        for action in actions:
            expected = stages.get(action.action_type)
            if expected is not None:
                if expected == 1:
                    stage = 1
                elif stage != expected - 1:
                    predecessor = next(key for key, value in stages.items() if value == expected - 1)
                    raise EndToEndRuntimeError(
                        f"{action.action_type.value} requires the prior "
                        f"literature stage {predecessor.value}"
                    )
                else:
                    stage = expected
            elif action.action_type in research and stage < 7:
                raise EndToEndRuntimeError("retrieval must precede substantive research")
            if action.action_type is not ActionType.FOLLOW_DISCOVERY_RESULTS:
                continue
            follow_request = action.request
            follow = follow_request() if callable(follow_request) else follow_request
            allowed = follow.get("allowed_origins")
            if (
                follow.get("max_depth") != 1
                or not isinstance(allowed, list) or not allowed
                or any(not isinstance(item, str) or not item for item in allowed)
                or follow.get("origin") not in allowed
            ):
                raise EndToEndRuntimeError(
                    "result following requires depth one and a pinned origin allowlist"
                )

        terminal_records: list[dict[str, Any]] = []
        unresolved: dict[str, Any] | None = None
        for sequence, action in enumerate(actions, start=1):
            request = action.request() if callable(action.request) else action.request
            try:
                terminal = self.checkpoints.execute(
                    sequence=sequence, action_type=action.action_type.value,
                    request=request,
                    paid_or_irreversible=action.paid_or_irreversible,
                    recorded_at=self.recorded_at, effect=action.effect,
                )
            except AmbiguousEffectError:
                unresolved = {
                    "sequence": sequence,
                    "action_type": action.action_type.value,
                    "reason": "effect_intent_has_no_terminal_record",
                    "paid_work_repeated": False,
                }
                break
            terminal_records.append(terminal)
            nonterminal_candidate_failure = (
                terminal["status"] != "completed"
                and action.action_type in {ActionType.VERIFY, ActionType.FORMAL_CHECK}
                and sequence < len(actions)
            )
            if terminal["status"] != "completed" and not nonterminal_candidate_failure:
                unresolved = {
                    "sequence": sequence,
                    "action_type": action.action_type.value,
                    "reason": terminal["result"].get("error_class", "action_failed"),
                    "paid_work_repeated": False,
                }
                break
        summary = {
            "schema_version": END_TO_END_SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "status": "completed" if unresolved is None else "unresolved",
            "completed_action_count": len(terminal_records),
            "failed_action_count": sum(
                item["status"] != "completed" for item in terminal_records
            ),
            "candidate_failure_continued": any(
                item["status"] != "completed"
                and item["action_type"] in {
                    ActionType.VERIFY.value, ActionType.FORMAL_CHECK.value,
                }
                and index < len(terminal_records) - 1
                for index, item in enumerate(terminal_records)
            ),
            "action_types": [item["action_type"] for item in terminal_records],
            "literature_search_recorded": any(
                item["action_type"] == ActionType.SEARCH_LITERATURE.value
                for item in terminal_records
            ),
            "before_research_human_checkpoint_required": False,
            "before_announcement_human_checkpoint_required": True,
            "unresolved": unresolved,
            "recorded_at": self.recorded_at,
            "epistemic_warrant_created": False,
        }
        summary["content_hash"] = canonical_hash(summary)
        path = self.root.joinpath("end-to-end-summary.json")
        rendered = canonical_bytes(summary) + b"\n"
        if path.exists() and path.read_bytes() != rendered:
            # A resumed run may legitimately advance from unresolved to
            # completed; preserve the former summary by hash before replacing
            # the current projection.
            history = self.root.joinpath("summary-history")
            history.mkdir(parents=True, exist_ok=True)
            old = path.read_bytes()
            old_hash = canonical_hash({"bytes_sha256": canonical_hash(old)})
            historical = history.joinpath(old_hash.removeprefix("sha256:") + ".json")
            if not historical.exists():
                historical.write_bytes(old)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(rendered)
        temporary.replace(path)
        return summary


__all__ = [
    "ACTION_SCHEMA_PATH", "ACTION_SCHEMA_VERSION", "parse_planned_action",
    "END_TO_END_SCHEMA_VERSION", "EndToEndCampaignRunner",
    "EndToEndRuntimeError", "RuntimeAction",
]
