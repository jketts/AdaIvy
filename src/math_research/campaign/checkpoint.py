"""Crash-safe, append-only action checkpoints for end-to-end campaigns.

An intent is durable before an effect begins.  A terminal record is durable
after it finishes. Replaying a completed action returns its recorded result.
An orphaned paid or irreversible intent is ambiguous and is never executed
again automatically; an explicitly local, idempotent action may retry with the
same key.
"""

from __future__ import annotations

import fcntl
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .records import ActionType, canonical_bytes, canonical_hash
from ..corpus_service.serialization import strict_canonical_object

CHECKPOINT_SCHEMA_VERSION = "adaivy.campaign-action-checkpoint.v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_INTENT_FIELDS = frozenset({
    "schema_version", "record_type", "campaign_id", "sequence", "action_type",
    "request", "request_hash", "idempotency_key", "paid_or_irreversible",
    "recorded_at", "content_hash",
})
_TERMINAL_FIELDS = frozenset({
    "schema_version", "record_type", "campaign_id", "sequence", "action_type",
    "intent_hash", "idempotency_key", "status", "result", "result_hash",
    "recorded_at", "content_hash",
})


class CheckpointError(ValueError):
    pass


class AmbiguousEffectError(CheckpointError):
    pass


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    rendered = canonical_bytes(value) + b"\n"
    if path.exists():
        if path.read_bytes() != rendered:
            raise CheckpointError(f"checkpoint overwrite refused: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, rendered)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)


@dataclass(slots=True)
class ActionCheckpointStore:
    root: Path
    campaign_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_id, str) or not _IDENTIFIER.fullmatch(self.campaign_id):
            raise CheckpointError("campaign_id must be a valid identifier")

    @property
    def directory(self) -> Path:
        return self.root.joinpath("action-checkpoints")

    def _path(self, sequence: int, suffix: str) -> Path:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise CheckpointError("checkpoint sequence must be positive")
        return self.directory.joinpath(f"{sequence:06d}.{suffix}.json")

    def _lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = self.directory.joinpath("writer.lock").open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def intent(
        self, *, sequence: int, action_type: str, request: Mapping[str, Any],
        paid_or_irreversible: bool, recorded_at: str,
    ) -> dict[str, Any]:
        return self._ensure_intent(
            sequence=sequence, action_type=action_type, request=request,
            paid_or_irreversible=paid_or_irreversible, recorded_at=recorded_at,
        )[0]

    def _ensure_intent(
        self, *, sequence: int, action_type: str, request: Mapping[str, Any],
        paid_or_irreversible: bool, recorded_at: str,
    ) -> tuple[dict[str, Any], bool]:
        request_hash = canonical_hash(request)
        value = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "record_type": "action_intent",
            "campaign_id": self.campaign_id,
            "sequence": sequence,
            "action_type": action_type,
            "request": dict(request),
            "request_hash": request_hash,
            "idempotency_key": canonical_hash({
                "campaign_id": self.campaign_id, "sequence": sequence,
                "action_type": action_type, "request_hash": request_hash,
            }),
            "paid_or_irreversible": paid_or_irreversible,
            "recorded_at": recorded_at,
        }
        value["content_hash"] = canonical_hash(value)
        lock = self._lock()
        try:
            existing = self.load(sequence, "intent")
            if existing is not None and existing != value:
                raise CheckpointError("sequence already has a different action intent")
            if existing is not None:
                return existing, False
            _write_once(self._path(sequence, "intent"), value)
            return value, True
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        return value

    def complete(
        self, *, sequence: int, intent: Mapping[str, Any], status: str,
        result: Mapping[str, Any], recorded_at: str,
    ) -> dict[str, Any]:
        if status not in {"completed", "failed", "incomplete"}:
            raise CheckpointError("terminal checkpoint status differs")
        stored_intent = self.load(sequence, "intent")
        if stored_intent is None or dict(intent) != stored_intent:
            raise CheckpointError("terminal completion does not bind the stored intent")
        value = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "record_type": "action_terminal",
            "campaign_id": self.campaign_id,
            "sequence": sequence,
            "action_type": intent["action_type"],
            "intent_hash": intent["content_hash"],
            "idempotency_key": intent["idempotency_key"],
            "status": status,
            "result": dict(result),
            "result_hash": canonical_hash(result),
            "recorded_at": recorded_at,
        }
        value["content_hash"] = canonical_hash(value)
        lock = self._lock()
        try:
            _write_once(self._path(sequence, "terminal"), value)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        return value

    def load(self, sequence: int, kind: str) -> dict[str, Any] | None:
        if kind not in {"intent", "terminal"}:
            raise CheckpointError("checkpoint kind differs")
        path = self._path(sequence, kind)
        if not path.exists():
            return None
        value = strict_canonical_object(
            path.read_bytes(), maximum=16_777_216, label="campaign checkpoint",
            code="campaign_checkpoint_invalid",
        )
        supplied = value.get("content_hash")
        core = {key: item for key, item in value.items() if key != "content_hash"}
        if supplied != canonical_hash(core):
            raise CheckpointError("campaign checkpoint content hash differs")
        expected = _INTENT_FIELDS if kind == "intent" else _TERMINAL_FIELDS
        if set(value) != expected:
            raise CheckpointError("campaign checkpoint fields differ")
        if value["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointError("campaign checkpoint schema differs")
        if value["record_type"] != f"action_{kind}":
            raise CheckpointError("campaign checkpoint record type differs")
        if value["campaign_id"] != self.campaign_id or value["sequence"] != sequence:
            raise CheckpointError("campaign checkpoint identity differs")
        try:
            ActionType(value["action_type"])
        except (TypeError, ValueError) as error:
            raise CheckpointError("campaign checkpoint action type differs") from error
        if not isinstance(value["recorded_at"], str) or not value["recorded_at"]:
            raise CheckpointError("campaign checkpoint recorded_at differs")
        if kind == "intent":
            if not isinstance(value["request"], dict):
                raise CheckpointError("action intent request differs")
            if value["request_hash"] != canonical_hash(value["request"]):
                raise CheckpointError("action intent request hash differs")
            expected_key = canonical_hash({
                "campaign_id": self.campaign_id, "sequence": sequence,
                "action_type": value["action_type"],
                "request_hash": value["request_hash"],
            })
            if value["idempotency_key"] != expected_key:
                raise CheckpointError("action intent idempotency key differs")
            if not isinstance(value["paid_or_irreversible"], bool):
                raise CheckpointError("action intent effect classification differs")
        else:
            if value["status"] not in {"completed", "failed", "incomplete"}:
                raise CheckpointError("action terminal status differs")
            if not isinstance(value["result"], dict):
                raise CheckpointError("action terminal result differs")
            if value["result_hash"] != canonical_hash(value["result"]):
                raise CheckpointError("action terminal result hash differs")
            intent = self.load(sequence, "intent")
            if intent is None:
                raise CheckpointError("action terminal has no intent")
            if (
                value["intent_hash"] != intent["content_hash"]
                or value["idempotency_key"] != intent["idempotency_key"]
                or value["action_type"] != intent["action_type"]
            ):
                raise CheckpointError("action terminal binding differs")
        return value

    def execute(
        self, *, sequence: int, action_type: str, request: Mapping[str, Any],
        paid_or_irreversible: bool, recorded_at: str,
        effect: Callable[[str], Mapping[str, Any]],
    ) -> dict[str, Any]:
        prior_terminal = self.load(sequence, "terminal")
        intent, created = self._ensure_intent(
            sequence=sequence, action_type=action_type, request=request,
            paid_or_irreversible=paid_or_irreversible, recorded_at=recorded_at,
        )
        terminal = prior_terminal or self.load(sequence, "terminal")
        if terminal is not None:
            if terminal["intent_hash"] != intent["content_hash"]:
                raise CheckpointError("terminal checkpoint binds another intent")
            return terminal
        # A prior paid/irreversible intent proves the process may already have
        # crossed an effect boundary. Never repeat that class automatically;
        # local idempotent projections retry under the same key.
        if not created and intent["paid_or_irreversible"]:
            raise AmbiguousEffectError("an action intent exists without a terminal record")
        try:
            result = effect(intent["idempotency_key"])
        except Exception as error:
            return self.complete(
                sequence=sequence, intent=intent, status="failed",
                result={"error_class": type(error).__name__}, recorded_at=recorded_at,
            )
        return self.complete(
            sequence=sequence, intent=intent, status="completed",
            result=result, recorded_at=recorded_at,
        )

    def completed(self) -> tuple[dict[str, Any], ...]:
        if not self.directory.exists():
            return ()
        return tuple(
            self.load(int(path.name.split(".", 1)[0]), "terminal")
            for path in sorted(self.directory.glob("*.terminal.json"))
        )


__all__ = [
    "ActionCheckpointStore", "AmbiguousEffectError", "CheckpointError",
    "CHECKPOINT_SCHEMA_VERSION",
]
