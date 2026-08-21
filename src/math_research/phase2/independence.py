"""Measured, not declared, verifier independence (ADR-0041).

Before this module the run path accepted a `VerifierIndependence` value from
whoever started the run. An operator could assert ``different_provider=True``
on a run whose proposer and verifier were the same gateway object, and the
durable manifest would repeat the assertion. That is the failure mode ADR-0035
rules out for the Phase 5 radicand: a trust-bearing claim must be derived from
what the run actually did.

Four of the seven dimensions are now derived here:

``different_provider`` / ``different_model``
    From the two resolved gateway configurations. Unresolvable identity is
    ``False``: an unmeasurable independence claim is refused, not assumed.
``separate_model_call``
    Structurally true of this loop -- the verifier is always its own call
    against its own request artifact -- so it is asserted by construction
    rather than by the caller.
``context_isolated``
    From the verifier context that was actually serialized: the proposer's
    model call must be excluded and the proposer's narrative must be absent.

Three dimensions remain operator-declared because nothing the loop can observe
settles them: ``deterministic_checker``, ``independently_implemented_checker``
and ``formal_kernel`` are facts about how a checker was built, not about how it
was called. ADR-0041 records that gap rather than hiding it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from .records import VerifierIndependence
from .serialization import canonical_json


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayIdentity:
    """Provider and model a gateway will actually call."""

    provider: str
    model_identifier: str


def gateway_identity(gateway: object) -> GatewayIdentity | None:
    """Resolve ``(provider, model)`` for a gateway, or ``None`` if unknowable.

    ``None`` is not an error. A scripted or fixture gateway has no provider
    identity, and the caller must then refuse the independence claim rather
    than guess one.
    """
    config = getattr(gateway, "config", None)
    if config is None:
        return None
    model_identifier = getattr(config, "model_identifier", None)
    if not isinstance(model_identifier, str) or not model_identifier:
        return None
    provider = getattr(config, "provider", None)
    if not isinstance(provider, str) or not provider:
        # Imported lazily: provider_registry pulls in every adapter module, and
        # records/serialization must stay importable without them.
        from .provider_registry import gateway_provider

        provider = gateway_provider(gateway)
    if not isinstance(provider, str) or not provider:
        return None
    return GatewayIdentity(provider=provider, model_identifier=model_identifier)


def measure_role_independence(
    declared: VerifierIndependence, *, proposer: object, verifier: object,
) -> VerifierIndependence:
    """Overwrite the two role axes with what the two gateways actually are."""
    if proposer is verifier:
        # One object cannot be two providers, whatever was declared.
        return replace(declared, different_provider=False, different_model=False, separate_model_call=True)
    proposer_identity = gateway_identity(proposer)
    verifier_identity = gateway_identity(verifier)
    if proposer_identity is None or verifier_identity is None:
        return replace(declared, different_provider=False, different_model=False, separate_model_call=True)
    return replace(
        declared,
        different_provider=proposer_identity.provider != verifier_identity.provider,
        different_model=proposer_identity.model_identifier != verifier_identity.model_identifier,
        separate_model_call=True,
    )


def measure_context_isolation(
    independence: VerifierIndependence,
    *,
    serialized_context: str,
    excluded_entity_ids: tuple[str, ...],
    proposer_call_id: str,
) -> VerifierIndependence:
    """Derive ``context_isolated`` from the bytes the verifier was handed."""
    isolated = (
        proposer_call_id in set(excluded_entity_ids)
        and "declared_rationale" not in _candidate_keys(serialized_context)
    )
    return replace(independence, context_isolated=isolated)


def _candidate_keys(serialized_context: str) -> frozenset[str]:
    try:
        value = json.loads(serialized_context)
    except json.JSONDecodeError:
        return frozenset({"declared_rationale"})
    candidate = value.get("candidate") if isinstance(value, dict) else None
    if not isinstance(candidate, dict):
        return frozenset({"declared_rationale"})
    return frozenset(candidate)


def independence_evidence(
    independence: VerifierIndependence, *, proposer: object, verifier: object,
) -> dict[str, object]:
    """Auditable record of what the two roles resolved to.

    Provider and model identifiers are non-secret configuration. No credential
    is read here and no network call is made.
    """
    proposer_identity = gateway_identity(proposer)
    verifier_identity = gateway_identity(verifier)
    return {
        "schema_version": independence.schema_version,
        "proposer": None if proposer_identity is None else {
            "provider": proposer_identity.provider,
            "model_identifier": proposer_identity.model_identifier,
        },
        "verifier": None if verifier_identity is None else {
            "provider": verifier_identity.provider,
            "model_identifier": verifier_identity.model_identifier,
        },
        "same_gateway_object": proposer is verifier,
        "independence": canonical_json(independence),
    }
