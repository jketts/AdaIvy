"""One resumable central campaign over explicit literature/runtime actions."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from .checkpoint import ActionCheckpointStore, AmbiguousEffectError
from .records import ActionType, RecordStatus, UsageSource, canonical_bytes, canonical_hash
from .runner import PlannerContext, PlannerResponse

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
    ActionType.ASK_USER, ActionType.READ_ARTIFACT, ActionType.NOTE,
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


@dataclass(frozen=True, slots=True)
class RuntimeEffect:
    effect: Callable[[Mapping[str, Any], str], Mapping[str, Any]]
    paid_or_irreversible: bool = False


class RuntimeEffectRegistry:
    """Closed action-to-effect boundary for model-selected v2 operations."""

    def __init__(self, effects: Mapping[ActionType, RuntimeEffect]) -> None:
        if any(not isinstance(key, ActionType) for key in effects):
            raise EndToEndRuntimeError("effect registry keys must be action types")
        self._effects = dict(effects)

    def resolve(self, action_type: ActionType) -> RuntimeEffect:
        try:
            return self._effects[action_type]
        except KeyError as error:
            raise EndToEndRuntimeError(
                f"no effect is registered for {action_type.value}"
            ) from error


def _hashes(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        found.add(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            found.update(_hashes(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_hashes(item))
    return found


def _advance_literature_state(
    action_type: ActionType, request: Mapping[str, Any], *, stage: int,
    search_seen: bool, published_generations: set[str],
    require_published_binding: bool = False,
) -> tuple[int, bool]:
    """Enforce repeatable literature cycles without a one-pass ladder."""

    if action_type is ActionType.SEARCH_LITERATURE:
        return 1, True
    if action_type is ActionType.FOLLOW_DISCOVERY_RESULTS:
        allowed = request.get("allowed_origins")
        if (
            stage < 1 or request.get("max_depth") != 1
            or not isinstance(allowed, list) or not allowed
            or any(not isinstance(item, str) or not item for item in allowed)
            or request.get("origin") not in allowed
        ):
            raise EndToEndRuntimeError(
                "result following requires a prior search, depth one, and a pinned origin allowlist"
            )
        return stage, search_seen
    minimum = {
        ActionType.ACQUIRE_SOURCE: 1,
        ActionType.PARSE_SOURCE: 2,
        ActionType.EMBED_SOURCES: 3,
        ActionType.REFRESH_RETRIEVAL_INDEX: 4,
        ActionType.RETRIEVE_EVIDENCE: 5,
    }.get(action_type)
    if minimum is not None:
        if stage < minimum:
            raise EndToEndRuntimeError(
                f"{action_type.value} is out of order in the current literature cycle"
            )
        if action_type is ActionType.RETRIEVE_EVIDENCE and require_published_binding:
            generation = request.get("generation_hash", request.get("projection_id"))
            if generation not in published_generations:
                raise EndToEndRuntimeError(
                    "retrieval evidence must name a published generation"
                )
        return minimum + 1, search_seen
    if action_type in {
        ActionType.DERIVE, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM,
        ActionType.EXPERIMENT, ActionType.FALSIFY, ActionType.VERIFY,
        ActionType.FORMAL_CHECK,
    } and not search_seen:
        raise EndToEndRuntimeError(
            "a recorded literature search must precede substantive research"
        )
    return stage, search_seen


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
        terminal_records: list[dict[str, Any]] = []
        unresolved: dict[str, Any] | None = None
        stage = 0
        search_seen = False
        published_generations: set[str] = set()
        for sequence, action in enumerate(actions, start=1):
            request = action.request() if callable(action.request) else action.request
            stage, search_seen = _advance_literature_state(
                action.action_type, request, stage=stage,
                search_seen=search_seen,
                published_generations=published_generations,
            )
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
            if (
                terminal["status"] == "completed"
                and action.action_type is ActionType.REFRESH_RETRIEVAL_INDEX
            ):
                for key in ("published_generation_hash", "generation_hash", "projection_id"):
                    value = terminal["result"].get(key)
                    if isinstance(value, str) and value:
                        published_generations.add(value)
            nonterminal_candidate_failure = (
                terminal["status"] != "completed"
                and action.action_type in {
                    ActionType.EXPERIMENT, ActionType.RUN_PROGRAM,
                    ActionType.VERIFY, ActionType.FORMAL_CHECK,
                }
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


class ModelDrivenEndToEndCampaignRunner:
    """Drive the v2 action protocol one model-selected action at a time.

    Planner calls and operation effects use separate checkpoint stores. This
    keeps an interrupted paid model call distinguishable from an interrupted
    acquisition or embedding effect while preserving one visible action
    sequence.
    """

    def __init__(
        self, root: Path, *, campaign_id: str, target_hash: str,
        configuration_hash: str, recorded_at: str, max_actions: int,
        planner: Callable[[PlannerContext], PlannerResponse],
        effects: RuntimeEffectRegistry, planner_is_paid: bool = True,
        target_statement: str | None = None,
    ) -> None:
        if max_actions < 1:
            raise EndToEndRuntimeError("max_actions must be positive")
        if not _IDENTIFIER.fullmatch(campaign_id):
            raise EndToEndRuntimeError("campaign_id differs")
        self.root = root
        self.campaign_id = campaign_id
        self.target_hash = target_hash
        self.configuration_hash = configuration_hash
        self.recorded_at = recorded_at
        self.max_actions = max_actions
        self.planner = planner
        self.effects = effects
        self.planner_is_paid = planner_is_paid
        self.target_statement = target_statement
        self.planner_checkpoints = ActionCheckpointStore(root / "planner", campaign_id)
        self.action_checkpoints = ActionCheckpointStore(root, campaign_id)
        self.answer_checkpoints = ActionCheckpointStore(root / "human", campaign_id)

    @staticmethod
    def _planner_result(response: PlannerResponse) -> dict[str, Any]:
        return {
            "action_json_base64": base64.b64encode(response.action_json).decode("ascii"),
            "provider": response.provider,
            "model_identifier": response.model_identifier,
            "status": response.status.value,
            "usage_source": response.usage_source.value,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "estimated_cost_microusd": response.estimated_cost_microusd,
            "provider_request_id": response.provider_request_id,
        }

    @staticmethod
    def _response_from_result(value: Mapping[str, Any]) -> PlannerResponse:
        try:
            return PlannerResponse(
                action_json=base64.b64decode(value["action_json_base64"], validate=True),
                provider=value["provider"], model_identifier=value["model_identifier"],
                status=RecordStatus(value["status"]),
                usage_source=UsageSource(value["usage_source"]),
                input_tokens=value["input_tokens"], output_tokens=value["output_tokens"],
                estimated_cost_microusd=value["estimated_cost_microusd"],
                provider_request_id=value["provider_request_id"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EndToEndRuntimeError("planner checkpoint result differs") from error

    def _record_answer(
        self, sequence: int, *, question: str, answer: str, operator_id: str,
    ) -> dict[str, Any]:
        if not _IDENTIFIER.fullmatch(operator_id):
            raise EndToEndRuntimeError("answer operator_id differs")
        if not isinstance(answer, str) or not answer or len(answer.encode("utf-8")) > 65_536:
            raise EndToEndRuntimeError("human answer differs")
        return self.answer_checkpoints.execute(
            sequence=sequence, action_type=ActionType.IMPORT.value,
            request={
                "ask_action_sequence": sequence, "question": question,
                "answer": answer, "operator_id": operator_id,
                "origin": "human",
            }, paid_or_irreversible=False, recorded_at=self.recorded_at,
            effect=lambda key: {
                "answer": answer, "operator_id": operator_id,
                "origin": "human", "idempotency_key": key,
            },
        )

    def run(
        self, *, answer: str | None = None, operator_id: str | None = None,
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        available: set[str] = {self.target_hash, self.configuration_hash}
        published_generations: set[str] = set()
        stage = 0
        search_seen = False
        latest: bytes | None = None
        latest_hash: str | None = None
        status = "unresolved"
        unresolved: dict[str, Any] | None = None

        for sequence in range(1, self.max_actions + 1):
            context = PlannerContext(
                campaign_id=self.campaign_id, target_hash=self.target_hash,
                configuration_hash=self.configuration_hash, sequence=sequence,
                previous_action_id=(None if not records else f"action.{sequence - 1}"),
                available_artifact_hashes=tuple(sorted(available)),
                recorded_program_hashes=(), selected_candidate_hash=None,
                selected_tool_artifact_hashes=(),
                latest_tool_result_hash=latest_hash, latest_tool_result=latest,
                actions_remaining=self.max_actions - sequence + 1,
                tool_runs_remaining=self.max_actions - sequence + 1,
                target_statement=self.target_statement,
                target_statement_hash=(self.target_hash if self.target_statement else None),
                frozen_artifact_hashes=(self.target_hash,),
            )
            planner_request = {
                "campaign_id": self.campaign_id, "sequence": sequence,
                "target_hash": self.target_hash,
                "configuration_hash": self.configuration_hash,
                "available_artifact_hashes": list(context.available_artifact_hashes),
                "latest_result_hash": latest_hash,
            }
            prior_plan = self.planner_checkpoints.load(sequence, "terminal")
            try:
                planned = self.planner_checkpoints.execute(
                    sequence=sequence, action_type=ActionType.PLAN.value,
                    request=planner_request,
                    paid_or_irreversible=self.planner_is_paid,
                    recorded_at=self.recorded_at,
                    effect=lambda key: self._planner_result(self.planner(context)),
                )
            except AmbiguousEffectError:
                unresolved = {
                    "sequence": sequence, "action_type": "plan",
                    "reason": "effect_intent_has_no_terminal_record",
                    "paid_work_repeated": False,
                }
                break
            if planned["status"] != "completed":
                unresolved = {
                    "sequence": sequence, "action_type": "plan",
                    "reason": planned["result"].get("error_class", "planner_failed"),
                    "paid_work_repeated": False,
                }
                break
            response = self._response_from_result(planned["result"])
            if prior_plan is not None and hasattr(self.planner, "restore_checkpoint"):
                self.planner.restore_checkpoint(sequence, planned["result"])
            if response.status is not RecordStatus.COMPLETED:
                unresolved = {
                    "sequence": sequence, "action_type": "plan",
                    "reason": "planner_" + response.status.value,
                    "paid_work_repeated": False,
                }
                break
            try:
                parsed = parse_planned_action(response.action_json, lambda key: {})
                request = parsed.request
                assert isinstance(request, Mapping)
                stage, search_seen = _advance_literature_state(
                    parsed.action_type, request, stage=stage,
                    search_seen=search_seen,
                    published_generations=published_generations,
                    require_published_binding=True,
                )
                if parsed.action_type is ActionType.ASK_USER:
                    question = request.get("question")
                    if not isinstance(question, str) or not question:
                        raise EndToEndRuntimeError("ask_user requires a question")
                    binding = RuntimeEffect(
                        lambda operation, key: {
                            "question": operation["question"],
                            "idempotency_key": key,
                        }
                    )
                elif parsed.action_type is ActionType.REPORT:
                    binding = RuntimeEffect(
                        lambda operation, key: {
                            "report": dict(operation), "idempotency_key": key,
                        }
                    )
                else:
                    binding = self.effects.resolve(parsed.action_type)
                terminal = self.action_checkpoints.execute(
                    sequence=sequence, action_type=parsed.action_type.value,
                    request=request,
                    paid_or_irreversible=binding.paid_or_irreversible,
                    recorded_at=self.recorded_at,
                    effect=lambda key: binding.effect(request, key),
                )
            except AmbiguousEffectError:
                unresolved = {
                    "sequence": sequence,
                    "action_type": parsed.action_type.value,
                    "reason": "effect_intent_has_no_terminal_record",
                    "paid_work_repeated": False,
                }
                break
            except EndToEndRuntimeError as error:
                unresolved = {
                    "sequence": sequence, "action_type": "plan",
                    "reason": str(error), "paid_work_repeated": False,
                }
                break

            records.append(terminal)
            latest = canonical_bytes(terminal["result"])
            latest_hash = canonical_hash(terminal["result"])
            available.update(_hashes(terminal["result"]))
            if (
                terminal["status"] == "completed"
                and parsed.action_type is ActionType.REFRESH_RETRIEVAL_INDEX
            ):
                for key in ("published_generation_hash", "generation_hash", "projection_id"):
                    value = terminal["result"].get(key)
                    if isinstance(value, str) and value:
                        published_generations.add(value)
            if parsed.action_type is ActionType.ASK_USER:
                if answer is None or operator_id is None:
                    status = "awaiting_user"
                    unresolved = {
                        "sequence": sequence, "action_type": "ask_user",
                        "reason": "human_answer_required", "paid_work_repeated": False,
                    }
                    break
                human = self._record_answer(
                    sequence, question=request["question"], answer=answer,
                    operator_id=operator_id,
                )
                latest = canonical_bytes(human["result"])
                latest_hash = canonical_hash(human["result"])
                answer = None
                operator_id = None
                continue
            if terminal["status"] != "completed" and parsed.action_type not in {
                ActionType.EXPERIMENT, ActionType.RUN_PROGRAM,
                ActionType.VERIFY, ActionType.FORMAL_CHECK,
            }:
                unresolved = {
                    "sequence": sequence, "action_type": parsed.action_type.value,
                    "reason": terminal["result"].get("error_class", "action_failed"),
                    "paid_work_repeated": False,
                }
                break
            if parsed.action_type is ActionType.REPORT:
                status = "completed"
                unresolved = None
                break
        else:
            unresolved = {
                "sequence": self.max_actions, "action_type": "plan",
                "reason": "action_bound_exhausted", "paid_work_repeated": False,
            }

        summary = {
            "schema_version": "adaivy.model-driven-end-to-end-campaign.v1",
            "campaign_id": self.campaign_id, "status": status,
            "completed_action_count": len(records),
            "action_types": [item["action_type"] for item in records],
            "literature_search_recorded": search_seen,
            "before_announcement_human_checkpoint_required": True,
            "unresolved": unresolved, "recorded_at": self.recorded_at,
            "epistemic_warrant_created": False,
        }
        summary["content_hash"] = canonical_hash(summary)
        path = self.root / "model-driven-end-to-end-summary.json"
        rendered = canonical_bytes(summary) + b"\n"
        if path.exists() and path.read_bytes() != rendered:
            history = self.root / "model-driven-summary-history"
            history.mkdir(parents=True, exist_ok=True)
            old = path.read_bytes()
            old_name = canonical_hash({"bytes": base64.b64encode(old).decode("ascii")})
            historical = history / (old_name.removeprefix("sha256:") + ".json")
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
    "EndToEndRuntimeError", "ModelDrivenEndToEndCampaignRunner",
    "RuntimeAction", "RuntimeEffect", "RuntimeEffectRegistry",
]
