"""Immutable request/result values for the sibling embedding port.

`ModelRequest`/`ModelResult` are chat-completion-shaped end to end:
``response_schema`` is mandatory (`records.py:165-179`), ``structured_output`` is
a JSON string that cannot hold a vector, and `validate_structured_output`
recognises only ``proposer``/``verifier`` (`model_gateway.py:83`). Rather than
lie to four validators, ADR-0065 adds these values alongside them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import (
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    OUTPUT_TOKENS_CONSTANT,
    SUPPORTED_EMBEDDING_PROVIDERS,
)
from .errors import EmbeddingError, OutputTokensNotZeroError


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingRequest:
    """One text, the processor that will see it, and a token bound.

    ``text`` is the disclosure. ``processor_id`` names the processor an ADR-0064
    rights decision must have authorized; it is carried on the request so a
    gateway cannot be handed a text without one.
    """

    document_id: str
    source_id: str
    source_content_hash: str
    text: str
    processor_id: str
    max_input_tokens: int
    timeout_milliseconds: int

    def __post_init__(self) -> None:
        if IDENTIFIER_PATTERN.fullmatch(self.document_id) is None:
            raise EmbeddingError(f"document_id is not path-safe: {self.document_id!r}",
                                 code="document_id_invalid")
        for name in ("source_id", "processor_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise EmbeddingError(f"{name} must be a non-empty string",
                                     code="embedding_request_invalid")
        if HASH_PATTERN.fullmatch(self.source_content_hash) is None:
            raise EmbeddingError("source_content_hash is not a sha256 content hash",
                                 code="embedding_request_invalid")
        if not isinstance(self.text, str) or not self.text:
            raise EmbeddingError("text must be a non-empty string",
                                 code="embedding_request_invalid")
        for name in ("max_input_tokens", "timeout_milliseconds"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise EmbeddingError(f"{name} must be a positive integer",
                                     code="embedding_request_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingUsage:
    """Input-only usage. ``output_tokens`` is a stated constant, not a reading."""

    input_tokens: int
    output_tokens: int = OUTPUT_TOKENS_CONSTANT
    usage_source: str = "api_reported"

    def __post_init__(self) -> None:
        if not isinstance(self.input_tokens, int) or isinstance(self.input_tokens, bool):
            raise EmbeddingError("input_tokens must be an integer",
                                 code="embedding_usage_invalid")
        if self.input_tokens < 0:
            raise EmbeddingError("input_tokens must be non-negative",
                                 code="embedding_usage_invalid")
        if self.output_tokens != OUTPUT_TOKENS_CONSTANT:
            raise OutputTokensNotZeroError(
                "an embeddings call produces no output tokens; "
                f"a result claiming {self.output_tokens!r} is refused"
            )
        if self.usage_source not in {"api_reported", "unavailable", "fixture"}:
            raise EmbeddingError(f"unknown usage_source: {self.usage_source!r}",
                                 code="embedding_usage_invalid")

    def payload(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usage_source": self.usage_source,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingResult:
    """A provider's answer, before quantization. Raw coordinates, once."""

    provider: str
    model_identifier: str
    provider_coordinates: tuple[float, ...]
    usage: EmbeddingUsage
    provider_request_id: str | None = None
    capabilities: tuple[str, ...] = field(default=("embeddings", "input_only"))

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            raise EmbeddingError(
                f"no embedding adapter for provider {self.provider!r}",
                code="embedding_provider_unsupported",
            )
        if not isinstance(self.model_identifier, str) or not self.model_identifier:
            raise EmbeddingError("model_identifier must be a non-empty string",
                                 code="embedding_result_invalid")
        if not isinstance(self.provider_coordinates, tuple) or not self.provider_coordinates:
            raise EmbeddingError("provider_coordinates must be a non-empty tuple",
                                 code="embedding_result_invalid")
        if self.provider_request_id is not None and not isinstance(self.provider_request_id, str):
            raise EmbeddingError("provider_request_id must be a string or None",
                                 code="embedding_result_invalid")

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens

    @property
    def dimension(self) -> int:
        return len(self.provider_coordinates)


__all__ = [
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingUsage",
]
