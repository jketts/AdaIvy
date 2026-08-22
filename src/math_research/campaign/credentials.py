"""Explicit named credential profiles for a campaign (runtime-plan Slice 2).

A campaign selects a profile by identifier; the profile resolves the provider,
the endpoint/deployment identity, and the model identifiers.  Ambient process
credentials never take precedence over the selected profile on a campaign
path, and there is no silent fallback to a host Codex/Claude credential or to
another provider: resolution consults ONLY the explicitly injected
profile-scoped credential mapping, and it refuses ``os.environ`` by identity.

Nothing in this module performs a network call, reads a credential file, or
activates a live capability.  The Slice 1 superseding ADR remains the
authority gate for running a live end-to-end campaign; this module only
defines and enforces the boundary that ADR will govern.  Secret values are
resolved into a deliberately non-serializable holder and never enter a record:
records carry identifiers, sources, and hashes only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Iterable, Mapping

from ..phase2.provider_registry import (
    UnknownProviderError,
    provider_secret_variables,
    provider_spec,
)
from .records import (
    CampaignProvenanceError,
    canonical_bytes,
    canonical_hash,
    public_value,
)


CREDENTIAL_SCHEMA_VERSION = "adaivy.campaign-credentials.v1"

#: The default live profile named by the end-to-end runtime plan (section 2.1).
DEFAULT_LIVE_PROFILE_ID = "adaivy"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SETTING_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class CredentialProfileError(CampaignProvenanceError):
    """A credential profile is malformed, unresolved, or misused."""


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise CredentialProfileError(f"{field} is not a valid identifier")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CredentialProfile:
    """One named, non-secret provider route.

    ``endpoint_settings`` carries only the provider's declared NON-SECRET
    operational settings (endpoint, deployment, api version, region).  A
    credential variable name appearing here is rejected: secret material has
    no representation inside a profile record.
    """

    profile_id: str
    provider: str
    model_identifier: str
    embedding_model_identifier: str | None
    endpoint_settings: tuple[tuple[str, str], ...]
    credential_source: str
    schema_version: str = CREDENTIAL_SCHEMA_VERSION
    record_type: str = "credential_profile"
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != CREDENTIAL_SCHEMA_VERSION:
            raise CredentialProfileError("unsupported credential-profile schema")
        if self.record_type != "credential_profile":
            raise CredentialProfileError("unsupported credential-profile record type")
        _identifier(self.profile_id, "profile_id")
        _identifier(self.credential_source, "credential_source")
        _identifier(self.model_identifier, "model_identifier")
        if self.embedding_model_identifier is not None:
            _identifier(self.embedding_model_identifier, "embedding_model_identifier")
        try:
            spec = provider_spec(self.provider)
        except UnknownProviderError as error:
            raise CredentialProfileError(
                f"profile provider is not admitted: {self.provider!r}"
            ) from error
        declared = frozenset(spec.required_settings + spec.optional_settings)
        secrets = frozenset(spec.required_credentials + spec.optional_credentials)
        if not isinstance(self.endpoint_settings, tuple):
            raise CredentialProfileError("endpoint_settings must be a tuple of pairs")
        names: list[str] = []
        for item in self.endpoint_settings:
            if (
                not isinstance(item, tuple) or len(item) != 2
                or not isinstance(item[0], str) or not isinstance(item[1], str)
            ):
                raise CredentialProfileError("endpoint_settings must be (name, value) string pairs")
            name, value = item
            if name in secrets:
                raise CredentialProfileError(
                    f"endpoint_settings names the credential variable {name}; "
                    "secret material has no representation inside a profile"
                )
            if name not in declared or not _SETTING_NAME.fullmatch(name):
                raise CredentialProfileError(
                    f"endpoint_settings names an undeclared setting: {name}"
                )
            if not value:
                raise CredentialProfileError(f"endpoint setting {name} must be non-empty")
            names.append(name)
        if len(names) != len(set(names)):
            raise CredentialProfileError("endpoint_settings contains a duplicate name")
        if names != sorted(names):
            raise CredentialProfileError("endpoint_settings must be sorted by name")
        missing = sorted(set(spec.required_settings) - set(names))
        if missing:
            raise CredentialProfileError(
                "profile is missing required non-secret settings: " + ", ".join(missing)
            )

    @property
    def route_hash(self) -> str:
        """Hash of exactly the non-secret settings that determine the route."""

        return canonical_hash({
            "provider": self.provider,
            "settings": {name: value for name, value in self.endpoint_settings},
        })

    @property
    def credential_variable_names(self) -> tuple[str, ...]:
        """Names (never values) of the secret variables this profile needs."""

        return provider_secret_variables(self.provider)

    def finalized(self) -> "CredentialProfile":
        payload = public_value(replace(self, content_hash=""))
        return replace(self, content_hash=canonical_hash(payload))

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CredentialProfileError(
                f"credential profile {self.profile_id} content_hash mismatch"
            )


class ResolvedProfileCredentials:
    """Secret values for one profile.  Deliberately not a dataclass, not a
    record, and not serializable through ``public_value``: its only admitted
    uses are constructing a gateway and redaction/leak scanning."""

    __slots__ = ("profile_id", "_values")

    def __init__(self, profile_id: str, values: Mapping[str, str]) -> None:
        self.profile_id = _identifier(profile_id, "profile_id")
        self._values = dict(values)

    def value(self, name: str) -> str:
        try:
            return self._values[name]
        except KeyError as error:
            raise CredentialProfileError(
                f"profile {self.profile_id} resolved no credential named {name}"
            ) from error

    def secret_values(self) -> tuple[str, ...]:
        """Sorted, de-duplicated values for redaction and leak scans only."""

        return tuple(sorted({value for value in self._values.values() if value}))

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"ResolvedProfileCredentials(profile_id={self.profile_id!r}, "
            f"variables={len(self._values)}, values=<redacted>)"
        )

    def __reduce__(self) -> Any:
        raise CredentialProfileError("resolved credentials are not serializable")


def resolve_credential_profile(
    profile: CredentialProfile,
    *,
    credential_environment: Mapping[str, str],
) -> ResolvedProfileCredentials:
    """Resolve secrets from the profile's OWN scoped mapping, and nothing else.

    ``os.environ`` is refused by identity: the ambient process environment of
    the host session is never an admitted credential source for a campaign
    path.  A missing required credential is a terminal refusal, never a
    fallback to an ambient or host-agent credential.
    """

    if credential_environment is os.environ:
        raise CredentialProfileError(
            "the ambient process environment is not an admitted credential "
            "source; supply the profile-scoped credential mapping explicitly"
        )
    spec = provider_spec(profile.provider)
    required = spec.required_credentials
    allowed = frozenset(required) | frozenset(spec.optional_credentials)
    unknown = sorted(set(credential_environment) - allowed)
    if unknown:
        raise CredentialProfileError(
            f"profile {profile.profile_id} received undeclared credential "
            "variables: " + ", ".join(unknown)
        )
    missing = sorted(
        name for name in required
        if not (credential_environment.get(name) or "").strip()
    )
    if missing:
        raise CredentialProfileError(
            f"profile {profile.profile_id} is missing required credentials "
            f"({', '.join(missing)}); ambient process credentials are not "
            "consulted and no fallback provider is admitted"
        )
    values = {
        name: value.strip()
        for name, value in credential_environment.items()
        if value and value.strip()
    }
    return ResolvedProfileCredentials(profile.profile_id, values)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileSelectionRecord:
    """What the campaign recorded when it selected a profile.

    Identifiers and sources only; the record never carries a secret value.
    A deliberately selected alternate profile is allowed but must state why.
    """

    campaign_id: str
    profile_id: str
    credential_source: str
    provider: str
    model_identifier: str
    embedding_model_identifier: str | None
    route_hash: str
    profile_content_hash: str
    is_default_profile: bool
    alternate_selection_reason: str | None
    selected_at: str
    schema_version: str = CREDENTIAL_SCHEMA_VERSION
    record_type: str = "credential_profile_selection"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({"selected_at"})

    def __post_init__(self) -> None:
        if self.schema_version != CREDENTIAL_SCHEMA_VERSION:
            raise CredentialProfileError("unsupported profile-selection schema")
        if self.record_type != "credential_profile_selection":
            raise CredentialProfileError("unsupported profile-selection record type")
        for field in ("campaign_id", "profile_id", "credential_source", "model_identifier"):
            _identifier(getattr(self, field), field)
        if self.embedding_model_identifier is not None:
            _identifier(self.embedding_model_identifier, "embedding_model_identifier")
        for field in ("route_hash", "profile_content_hash"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise CredentialProfileError(f"{field} is not a sha256 content hash")
        if self.is_default_profile != (self.profile_id == DEFAULT_LIVE_PROFILE_ID):
            raise CredentialProfileError(
                "is_default_profile must state exactly whether the default "
                f"live profile {DEFAULT_LIVE_PROFILE_ID!r} was selected"
            )
        if self.is_default_profile and self.alternate_selection_reason is not None:
            raise CredentialProfileError(
                "the default profile carries no alternate-selection reason"
            )
        if not self.is_default_profile and not (
            isinstance(self.alternate_selection_reason, str)
            and self.alternate_selection_reason
            and len(self.alternate_selection_reason) <= 2_000
        ):
            raise CredentialProfileError(
                "selecting a non-default profile requires a recorded reason"
            )
        if not isinstance(self.selected_at, str) or not self.selected_at:
            raise CredentialProfileError("selected_at must be supplied")

    def finalized(self) -> "ProfileSelectionRecord":
        payload = public_value(replace(self, content_hash="", operational_hash=""))
        semantic = {
            key: item for key, item in payload.items()
            if key not in self.OPERATIONAL_FIELDS
            and key not in {"content_hash", "operational_hash"}
        }
        content_hash = canonical_hash(semantic)
        payload["content_hash"] = content_hash
        payload.pop("operational_hash", None)
        return replace(
            self, content_hash=content_hash, operational_hash=canonical_hash(payload),
        )

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CredentialProfileError("profile selection content_hash mismatch")
        if self.operational_hash != expected.operational_hash:
            raise CredentialProfileError("profile selection operational_hash mismatch")


def select_credential_profile(
    registry: Mapping[str, CredentialProfile],
    profile_id: str,
    *,
    campaign_id: str,
    selected_at: str,
    alternate_selection_reason: str | None = None,
) -> tuple[CredentialProfile, ProfileSelectionRecord]:
    """Select one named profile, failing closed on anything unknown.

    An unknown identifier is terminal: there is no ambient or host-agent
    profile to fall back to, and the refusal names nothing beyond the
    identifier itself.
    """

    _identifier(profile_id, "profile_id")
    profile = registry.get(profile_id)
    if profile is None:
        raise CredentialProfileError(
            f"credential profile {profile_id!r} is not registered; ambient or "
            "host-agent credentials are never substituted for a named profile"
        )
    if profile.profile_id != profile_id:
        raise CredentialProfileError(
            "the registry maps an identifier to a differently named profile"
        )
    profile.verify_hashes()
    record = ProfileSelectionRecord(
        campaign_id=campaign_id,
        profile_id=profile.profile_id,
        credential_source=profile.credential_source,
        provider=profile.provider,
        model_identifier=profile.model_identifier,
        embedding_model_identifier=profile.embedding_model_identifier,
        route_hash=profile.route_hash,
        profile_content_hash=profile.content_hash,
        is_default_profile=profile.profile_id == DEFAULT_LIVE_PROFILE_ID,
        alternate_selection_reason=alternate_selection_reason,
        selected_at=selected_at,
    ).finalized()
    return profile, record


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignRoutePolicy:
    """The route authorization frozen at campaign start.

    Provider failure is terminal for a route unless this policy names a
    fallback profile.  The fallback carries no implicit budget: the budget
    module requires a dedicated sub-budget before a fallback route may charge
    anything, and there is never an implicit fallback to the host agent.
    """

    primary_profile_id: str
    fallback_profile_id: str | None
    fallback_authorized_reason: str | None
    schema_version: str = CREDENTIAL_SCHEMA_VERSION
    record_type: str = "campaign_route_policy"
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != CREDENTIAL_SCHEMA_VERSION:
            raise CredentialProfileError("unsupported route-policy schema")
        if self.record_type != "campaign_route_policy":
            raise CredentialProfileError("unsupported route-policy record type")
        _identifier(self.primary_profile_id, "primary_profile_id")
        if self.fallback_profile_id is not None:
            _identifier(self.fallback_profile_id, "fallback_profile_id")
            if self.fallback_profile_id == self.primary_profile_id:
                raise CredentialProfileError(
                    "a fallback profile must differ from the primary profile"
                )
            if not (
                isinstance(self.fallback_authorized_reason, str)
                and self.fallback_authorized_reason
                and len(self.fallback_authorized_reason) <= 2_000
            ):
                raise CredentialProfileError(
                    "a named fallback requires the initial campaign policy to "
                    "record why it was authorized"
                )
        elif self.fallback_authorized_reason is not None:
            raise CredentialProfileError(
                "a fallback reason without a named fallback profile is malformed"
            )

    def finalized(self) -> "CampaignRoutePolicy":
        payload = public_value(replace(self, content_hash=""))
        return replace(self, content_hash=canonical_hash(payload))

    def route_after_provider_failure(self, failed_profile_id: str) -> str:
        """The one admitted continuation after a provider failure, or terminal."""

        _identifier(failed_profile_id, "failed_profile_id")
        if failed_profile_id != self.primary_profile_id:
            raise CredentialProfileError(
                "provider failure on a non-primary route is terminal; a "
                "fallback route has no fallback of its own"
            )
        if self.fallback_profile_id is None:
            raise CredentialProfileError(
                f"provider failure is terminal for profile {failed_profile_id!r}: "
                "the initial campaign policy authorized no named fallback"
            )
        return self.fallback_profile_id


def assert_no_secret_values(payload: Any, secrets: Iterable[str]) -> None:
    """Refuse a record whose serialized form contains configured secret bytes."""

    blob = canonical_bytes(public_value(payload)).decode("utf-8")
    for secret in secrets:
        if secret and secret in blob:
            raise CredentialProfileError(
                "a campaign record contains secret credential material"
            )


def profile_public_fields(profile: CredentialProfile) -> tuple[str, ...]:
    """The exact non-secret fields a profile serializes; used by leak tests."""

    return tuple(item.name for item in fields(profile))


__all__ = [
    "CREDENTIAL_SCHEMA_VERSION",
    "CampaignRoutePolicy",
    "CredentialProfile",
    "CredentialProfileError",
    "DEFAULT_LIVE_PROFILE_ID",
    "ProfileSelectionRecord",
    "ResolvedProfileCredentials",
    "assert_no_secret_values",
    "profile_public_fields",
    "resolve_credential_profile",
    "select_credential_profile",
]
