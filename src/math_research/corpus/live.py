"""The opt-in live adapter for the corpus `MetadataTransport` port.

Constructed only on the ``--execute`` branch of ``corpus acquire``.  The
offline acceptance path never imports this module's outward machinery: it wraps
the already-reviewed ADR-0028/ADR-0050 opt-in HTTPS transport rather than adding
a second network implementation, and it narrows that transport further.

Narrowing, not widening:

* the request is always ``GET`` with NO caller-supplied headers;
* the URL must pass :func:`math_research.corpus.tranche.assert_metadata_target`,
  which admits exactly the arXiv metadata query endpoint;
* the resolved addresses must be globally routable;
* every attempt is counted, so the replay path can assert zero.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from ..phase4b.acquisition import AcquisitionPolicyError, Resolution, TransportRequest
from .constants import ARXIV_API_HOSTNAME, ARXIV_API_ORIGIN, CAPABILITY_ID
from .errors import CorpusError, OriginNotAuthorizedError
from .ports import MetadataRequest, MetadataResponse
from .tranche import assert_metadata_target

MAX_HEADER_BYTES = 65_536


def public_addresses(resolution: Resolution, hostname: str) -> tuple[str, ...]:
    if resolution.hostname != hostname or not 1 <= len(resolution.addresses) <= 16:
        raise OriginNotAuthorizedError("corpus resolver identity is invalid")
    result: list[str] = []
    for raw in resolution.addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise OriginNotAuthorizedError(f"resolved address is invalid: {raw!r}") from error
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise OriginNotAuthorizedError(f"resolved address is not public: {raw!r}")
        if address.compressed not in result:
            result.append(address.compressed)
    if not result:
        raise OriginNotAuthorizedError("resolver returned no public address")
    return tuple(sorted(result))


class OptInArxivMetadataTransport:
    """Adapt the reviewed Phase 4B HTTPS transport onto `MetadataTransport`."""

    def __init__(self, permit: Any, resolver: Any, transport: Any) -> None:
        if getattr(permit, "capability_id", None) != CAPABILITY_ID:
            raise CorpusError(
                "the live permit must name the corpus capability",
                code="corpus_permit_invalid",
            )
        if tuple(getattr(permit, "approved_origins", ())) != (ARXIV_API_ORIGIN,):
            raise OriginNotAuthorizedError(
                f"the live permit must approve exactly {ARXIV_API_ORIGIN}"
            )
        if getattr(resolver, "permit", None) is not permit or getattr(
            transport, "permit", None
        ) is not permit:
            raise CorpusError(
                "resolver and transport must be bound to the same permit",
                code="corpus_permit_invalid",
            )
        self.permit = permit
        self.resolver = resolver
        self.transport = transport
        self.attempts = 0

    def fetch(self, request: MetadataRequest) -> MetadataResponse:
        url = assert_metadata_target(request.url)
        self.attempts += 1
        resolution = self.resolver.resolve(ARXIV_API_HOSTNAME)
        addresses = public_addresses(resolution, ARXIV_API_HOSTNAME)
        try:
            response = self.transport.fetch(TransportRequest(
                method="GET",
                url=url,
                headers=(),
                connect_addresses=addresses,
                timeout_milliseconds=request.timeout_milliseconds,
                max_header_bytes=MAX_HEADER_BYTES,
                max_body_bytes=request.max_response_bytes,
            ))
        except AcquisitionPolicyError as error:
            raise CorpusError(str(error), code="corpus_transport_policy_refusal") from error
        headers = {
            str(name).casefold(): str(value) for name, value in response.headers
        }
        return MetadataResponse(
            status=int(response.status),
            media_type=headers.get("content-type", ""),
            body=bytes(response.body),
        )


def build_live_transport(permit: Any) -> OptInArxivMetadataTransport:
    """Construct the reviewed opt-in resolver and transport for this permit."""

    from ..phase4b.live_transport import OptInHttpsTransport, OptInSystemResolver

    return OptInArxivMetadataTransport(
        permit, OptInSystemResolver(permit), OptInHttpsTransport(permit),
    )


__all__ = [
    "MAX_HEADER_BYTES",
    "OptInArxivMetadataTransport",
    "build_live_transport",
    "public_addresses",
]
