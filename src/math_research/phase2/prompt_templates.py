"""Versioned, hash-recorded prompt templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import PHASE2_SCHEMA_VERSION
from .serialization import sha256_bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptTemplate:
    schema_version: str = PHASE2_SCHEMA_VERSION
    template_id: str
    version: str
    text: str
    content_hash: str


class PromptCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "prompts" / "phase-2"

    def load(self, purpose: str) -> PromptTemplate:
        names = {
            "proposer": "proposer-v1.txt",
            # ADR-0041. Rounds after the first get their own versioned, hashed
            # template so a refinement request is never mistaken in the durable
            # record for a first attempt.
            "proposer_refinement": "proposer-refinement-v1.txt",
            "verifier": "verifier-v1.txt",
        }
        try:
            filename = names[purpose]
        except KeyError as error:
            raise ValueError(f"unknown prompt purpose: {purpose}") from error
        data = (self.root / filename).read_bytes()
        return PromptTemplate(
            template_id=f"phase2.{purpose}", version="1.0.0",
            text=data.decode("utf-8"), content_hash=sha256_bytes(data),
        )

