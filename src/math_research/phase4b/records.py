"""Closed, candidate-only record vocabulary for durable Phase 4B metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = "adaivy.phase4b-record.v1"
LEGACY_EXPORT_VERSION = "adaivy.phase4b-export.v1"
LEGACY_EXPORT_PROFILE = "phase4b-candidate-audit-v1"
EXPORT_VERSION = "adaivy.phase4b-export.v2"
EXPORT_PROFILE = "phase4b-candidate-audit-v2"
MAX_INPUT_BYTES = 8_388_608
MAX_EXPORT_BYTES = 8_388_608
MAX_RECORDS = 4_096


class RecordType(str, Enum):
    ACQUISITION_CANDIDATE = "acquisition_candidate"
    PARSE_CANDIDATE = "parse_candidate"
    FAILURE = "failure"
    INVALIDATION = "invalidation"


class CandidateState(str, Enum):
    ACTIVE = "active_candidate"
    INVALIDATED = "invalidated_candidate"


@dataclass(frozen=True, slots=True)
class Phase4BRecord:
    schema_version: str
    record_id: str
    record_type: RecordType
    subject_id: str
    sequence: int
    recorded_at: str
    payload: Mapping[str, Any]
    operational: Mapping[str, Any]
    content_hash: str
    operational_hash: str

    def value(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "record_type": self.record_type.value,
            "subject_id": self.subject_id,
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "payload": dict(self.payload),
            "operational": dict(self.operational),
            "content_hash": self.content_hash,
            "operational_hash": self.operational_hash,
        }


__all__ = [
    "CandidateState",
    "EXPORT_PROFILE",
    "EXPORT_VERSION",
    "LEGACY_EXPORT_PROFILE",
    "LEGACY_EXPORT_VERSION",
    "MAX_EXPORT_BYTES",
    "MAX_INPUT_BYTES",
    "MAX_RECORDS",
    "Phase4BRecord",
    "RecordType",
    "SCHEMA_VERSION",
]
