"""One resumable central campaign over explicit literature/runtime actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .checkpoint import ActionCheckpointStore, AmbiguousEffectError
from .records import ActionType, canonical_bytes, canonical_hash

END_TO_END_SCHEMA_VERSION = "adaivy.end-to-end-campaign.v1"


@dataclass(frozen=True, slots=True)
class RuntimeAction:
    action_type: ActionType
    request: Mapping[str, Any] | Callable[[], Mapping[str, Any]]
    effect: Callable[[str], Mapping[str, Any]]
    paid_or_irreversible: bool = False


class EndToEndRuntimeError(ValueError):
    pass


_LITERATURE_ACTIONS = frozenset({
    ActionType.SEARCH_LITERATURE,
    ActionType.FOLLOW_DISCOVERY_RESULTS,
    ActionType.ACQUIRE_SOURCE,
    ActionType.PARSE_SOURCE,
    ActionType.EMBED_SOURCES,
    ActionType.REFRESH_RETRIEVAL_INDEX,
    ActionType.RETRIEVE_EVIDENCE,
})


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
            if item in {ActionType.DERIVE, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM}
        ), len(types))
        if types.index(ActionType.SEARCH_LITERATURE) > first_research:
            raise EndToEndRuntimeError("literature search must precede substantive research")
        if ActionType.FOLLOW_DISCOVERY_RESULTS in types:
            follow_request = actions[types.index(ActionType.FOLLOW_DISCOVERY_RESULTS)].request
            follow = follow_request() if callable(follow_request) else follow_request
            if follow.get("max_depth") != 1:
                raise EndToEndRuntimeError("result following is pinned to depth one")

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
            if terminal["status"] != "completed":
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
    "END_TO_END_SCHEMA_VERSION", "EndToEndCampaignRunner",
    "EndToEndRuntimeError", "RuntimeAction",
]
