"""AWS Signature Version 4 request signing, standard library only.

This module exists so the Bedrock gateway can reach a partner-operated
endpoint without adding a heavy optional SDK. ADR-0030 records the hard gate
that applies to it: "hand-rolled SigV4, if used, is subtle enough that
unverified signing is worse than a dependency". Accordingly every rule below is
pinned by an executable assertion in ``tests/test_phase2_aws_sigv4.py`` against
AWS's published worked examples, and the canonicalisation choices follow the
reference client (botocore ``SigV4Auth``) rather than a paraphrase of the prose.

The module is inert on import: no clock is read, no credential is resolved, no
network or third-party module is touched. Callers pass an explicit UTC instant,
which is what makes signing tests deterministic.

Secret handling: :class:`AwsCredentials` never renders its own values. The
derived signing key is a local, never returned and never stored on any result
object. What a :class:`SignedRequest` carries is the finished ``Authorization``
header; it is a MAC over the request, not the secret, but it is still treated
as sensitive and :meth:`SignedRequest.loggable_headers` is the only view any
diagnostic path may use.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence
from urllib.parse import quote, urlsplit


ALGORITHM = "AWS4-HMAC-SHA256"
TERMINATOR = "aws4_request"
SIGV4_IMPLEMENTATION_VERSION = "adaivy-aws-sigv4/1.0.0"
EMPTY_PAYLOAD_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"

AMZ_DATE_HEADER = "x-amz-date"
SECURITY_TOKEN_HEADER = "x-amz-security-token"
CONTENT_SHA256_HEADER = "x-amz-content-sha256"
AUTHORIZATION_HEADER = "authorization"

# RFC 7230 token, i.e. the only header names that may be signed or sent.
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_FORBIDDEN_VALUE_CHARACTERS = ("\r", "\n", "\x00")
# `authorization` is computed, not supplied; `host` is derived from the URL so a
# signed Host can never disagree with the connected authority.
_CALLER_FORBIDDEN_HEADERS = frozenset({AUTHORIZATION_HEADER, "host"})
_MAX_HEADER_COUNT = 128
_REGION = re.compile(r"^[a-z0-9-]{1,64}$")
_SERVICE = re.compile(r"^[a-z0-9-]{1,64}$")


class SigV4Error(ValueError):
    """A signing input violates the signature contract. Always fails closed."""


@dataclass(frozen=True, slots=True)
class AwsCredentials:
    """Signing credentials that never disclose themselves.

    ``__repr__`` and ``__str__`` are overridden because the generated dataclass
    repr would otherwise place the secret access key and session token into any
    traceback, log line, or ``ProviderFailureDiagnostic`` preview that happens
    to interpolate the object.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("access_key_id", self.access_key_id),
            ("secret_access_key", self.secret_access_key),
        ):
            if not isinstance(value, str) or not value:
                raise SigV4Error(f"{name} must be a non-empty string")
        if self.session_token is not None and (
            not isinstance(self.session_token, str) or not self.session_token
        ):
            raise SigV4Error("session_token must be a non-empty string or None")
        for value in (self.access_key_id, self.secret_access_key, self.session_token or ""):
            if any(character in value for character in _FORBIDDEN_VALUE_CHARACTERS):
                raise SigV4Error("credential values must not contain control characters")

    def __repr__(self) -> str:
        return (
            "AwsCredentials(access_key_id='[REDACTED]', secret_access_key='[REDACTED]', "
            f"session_token={'None' if self.session_token is None else chr(39) + '[REDACTED]' + chr(39)})"
        )

    __str__ = __repr__

    @property
    def secret_material(self) -> tuple[str, ...]:
        """Every value that must be scrubbed before any value reaches a record."""
        material = [self.secret_access_key, self.access_key_id]
        if self.session_token is not None:
            material.append(self.session_token)
        return tuple(material)


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    method: str
    canonical_uri: str
    canonical_query_string: str
    canonical_headers: str
    signed_headers: str
    payload_hash: str

    @property
    def text(self) -> str:
        return "\n".join(
            (
                self.method,
                self.canonical_uri,
                self.canonical_query_string,
                self.canonical_headers,
                self.signed_headers,
                self.payload_hash,
            )
        )

    @property
    def hash_hex(self) -> str:
        return sha256_hex(self.text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SignedRequest:
    """A fully signed request. Carries no signing key and no secret."""

    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    canonical_request: CanonicalRequest
    string_to_sign: str
    credential_scope: str
    amz_date: str
    signature: str
    region: str
    service: str
    implementation_version: str = SIGV4_IMPLEMENTATION_VERSION

    @property
    def authorization(self) -> str:
        for name, value in self.headers:
            if name.lower() == AUTHORIZATION_HEADER:
                return value
        raise SigV4Error("signed request is missing its Authorization header")

    def header_mapping(self) -> dict[str, str]:
        return {name: value for name, value in self.headers}

    def loggable_headers(self) -> tuple[tuple[str, str], ...]:
        """The only header view a diagnostic, log, or record may use."""
        sensitive = {AUTHORIZATION_HEADER, SECURITY_TOKEN_HEADER}
        return tuple(
            (name, "[REDACTED]" if name.lower() in sensitive else value)
            for name, value in self.headers
        )


def sha256_hex(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise SigV4Error("payload must be bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def format_amz_date(moment: datetime) -> str:
    return _require_utc(moment).strftime("%Y%m%dT%H%M%SZ")


def format_date_stamp(moment: datetime) -> str:
    return _require_utc(moment).strftime("%Y%m%d")


def _require_utc(moment: datetime) -> datetime:
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise SigV4Error("signing instant must be a timezone-aware datetime")
    if moment.utcoffset() != timezone.utc.utcoffset(None):
        raise SigV4Error("signing instant must be expressed in UTC")
    return moment


def remove_dot_segments(path: str) -> str:
    """RFC 3986 dot-segment removal plus AWS's collapse of repeated slashes.

    AWS canonicalisation for non-S3 services drops empty segments as well as
    ``.``/``..`` segments, so ``//example//`` signs as ``/example/``. That is
    behaviour the published test suite pins, not an interpretation, and it is
    the reason this is not a plain RFC 3986 implementation.
    """
    if not path:
        return ""
    output: list[str] = []
    for segment in path.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            if output:
                output.pop()
            continue
        output.append(segment)
    leading = "/" if path[0] == "/" else ""
    trailing = (
        "/"
        if path.endswith("/") or path.endswith("/.") or path.endswith("/..")
        else ""
    )
    joined = "/".join(output)
    if not joined:
        return "/" if leading or trailing else ""
    return leading + joined + trailing


def canonical_uri_from_path(path: str, *, double_encode: bool = True) -> str:
    """Canonical URI.

    ``double_encode`` reflects the split in AWS's own rules: every service
    except S3 percent-encodes the (already percent-encoded) path a second time
    and applies dot-segment removal, while S3 signs the path verbatim. Bedrock
    is not S3, so the default is the double-encoding form. Guessing here is not
    an option, which is why it is an explicit argument.
    """
    if not isinstance(path, str):
        raise SigV4Error("path must be a string")
    if not path:
        return "/"
    if not double_encode:
        return path
    normalized = remove_dot_segments(path)
    if not normalized:
        return "/"
    return quote(normalized, safe="/~")


def canonical_query_string(query: str) -> str:
    """Canonicalise an already percent-encoded query string from a URL.

    Pairs are sorted by encoded name and then encoded value, and a bare name is
    signed as ``name=``. Nothing is re-encoded: the caller's URL is taken as the
    authority on encoding, because re-encoding an encoded query would corrupt
    it. Use :func:`canonical_query_string_from_params` for unencoded input.
    """
    if not query:
        return ""
    pairs: list[tuple[str, str]] = []
    for pair in query.split("&"):
        name, _, value = pair.partition("=")
        pairs.append((name, value))
    return "&".join(f"{name}={value}" for name, value in sorted(pairs))


def canonical_query_string_from_params(params: Sequence[tuple[str, str]]) -> str:
    """Canonicalise unencoded query parameters, encoding each component."""
    encoded: list[tuple[str, str]] = []
    for name, value in params:
        if not isinstance(name, str) or not isinstance(value, str):
            raise SigV4Error("query parameters must be strings")
        encoded.append((quote(name, safe="-_.~"), quote(value, safe="-_.~")))
    return "&".join(f"{name}={value}" for name, value in sorted(encoded))


def _header_value(value: str) -> str:
    """Trim and collapse internal whitespace runs, per the reference client."""
    return " ".join(value.split())


def canonical_headers(headers: Iterable[tuple[str, str]]) -> tuple[str, str]:
    """Return ``(canonical_headers_block, signed_headers)``.

    Names are lowercased, values trimmed and internally collapsed, entries
    sorted by name, and repeated names joined with ``,`` in the order supplied.
    """
    collected: dict[str, list[str]] = {}
    count = 0
    for name, value in headers:
        count += 1
        if count > _MAX_HEADER_COUNT:
            raise SigV4Error("too many headers to sign")
        if not isinstance(name, str) or not isinstance(value, str):
            raise SigV4Error("headers must be string pairs")
        if _HEADER_NAME.fullmatch(name) is None:
            raise SigV4Error(f"invalid header name: {name!r}")
        if any(character in value for character in _FORBIDDEN_VALUE_CHARACTERS):
            raise SigV4Error(f"invalid header value for {name!r}")
        collected.setdefault(name.lower(), []).append(_header_value(value))
    if "host" not in collected:
        raise SigV4Error("the host header must be signed")
    names = sorted(collected)
    block = "".join(f"{name}:{','.join(collected[name])}\n" for name in names)
    return block, ";".join(names)


def credential_scope(date_stamp: str, region: str, service: str) -> str:
    return f"{date_stamp}/{region}/{service}/{TERMINATOR}"


def derive_signing_key(
    secret_access_key: str, date_stamp: str, region: str, service: str
) -> bytes:
    """``HMAC`` chain from the secret to the request-scoped signing key.

    The result is a local secret. It is deliberately not attached to any
    returned value object.
    """
    if not secret_access_key:
        raise SigV4Error("secret_access_key must be a non-empty string")
    key = _hmac(("AWS4" + secret_access_key).encode("utf-8"), date_stamp)
    key = _hmac(key, region)
    key = _hmac(key, service)
    return _hmac(key, TERMINATOR)


def create_canonical_request(
    *,
    method: str,
    canonical_uri: str,
    canonical_query: str,
    headers: Iterable[tuple[str, str]],
    payload_hash: str,
) -> CanonicalRequest:
    if not isinstance(method, str) or not method or method != method.upper():
        raise SigV4Error("method must be an uppercase HTTP method")
    block, signed = canonical_headers(headers)
    return CanonicalRequest(
        method=method,
        canonical_uri=canonical_uri,
        canonical_query_string=canonical_query,
        canonical_headers=block,
        signed_headers=signed,
        payload_hash=payload_hash,
    )


def create_string_to_sign(
    *, amz_date: str, scope: str, canonical_request_hash: str
) -> str:
    return "\n".join((ALGORITHM, amz_date, scope, canonical_request_hash))


def sign_request(
    *,
    method: str,
    url: str,
    headers: Sequence[tuple[str, str]] = (),
    body: bytes = b"",
    credentials: AwsCredentials,
    region: str,
    service: str,
    moment: datetime,
    double_encode_path: bool = True,
    include_content_sha256: bool = False,
) -> SignedRequest:
    """Sign a request and return it with the headers that must be sent.

    ``moment`` is required and never defaulted from the system clock, so the
    caller owns the clock and the offline suite can freeze it.
    """
    if not isinstance(credentials, AwsCredentials):
        raise SigV4Error("credentials must be AwsCredentials")
    if not isinstance(region, str) or _REGION.fullmatch(region) is None:
        raise SigV4Error("region must be a lowercase AWS region identifier")
    if not isinstance(service, str) or _SERVICE.fullmatch(service) is None:
        raise SigV4Error("service must be a lowercase AWS service identifier")
    if not isinstance(body, (bytes, bytearray)):
        raise SigV4Error("body must be bytes")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise SigV4Error("signing requires an absolute https URL")
    if parts.fragment:
        raise SigV4Error("signing requires a URL without a fragment")
    if parts.username is not None or parts.password is not None:
        raise SigV4Error("signing requires a URL without embedded credentials")

    amz_date = format_amz_date(moment)
    date_stamp = format_date_stamp(moment)
    payload_hash = sha256_hex(bytes(body))

    supplied: list[tuple[str, str]] = []
    for name, value in headers:
        if not isinstance(name, str):
            raise SigV4Error("headers must be string pairs")
        lowered = name.lower()
        if lowered in _CALLER_FORBIDDEN_HEADERS:
            raise SigV4Error(f"{lowered} is derived, not supplied")
        if lowered in {AMZ_DATE_HEADER, SECURITY_TOKEN_HEADER}:
            raise SigV4Error(f"{lowered} is derived, not supplied")
        supplied.append((name, value))

    signing_headers: list[tuple[str, str]] = [("host", parts.netloc)]
    signing_headers.extend(supplied)
    signing_headers.append((AMZ_DATE_HEADER, amz_date))
    if credentials.session_token is not None:
        signing_headers.append((SECURITY_TOKEN_HEADER, credentials.session_token))
    if include_content_sha256:
        signing_headers.append((CONTENT_SHA256_HEADER, payload_hash))

    canonical = create_canonical_request(
        method=method,
        canonical_uri=canonical_uri_from_path(parts.path, double_encode=double_encode_path),
        canonical_query=canonical_query_string(parts.query),
        headers=signing_headers,
        payload_hash=payload_hash,
    )
    scope = credential_scope(date_stamp, region, service)
    string_to_sign = create_string_to_sign(
        amz_date=amz_date, scope=scope, canonical_request_hash=canonical.hash_hex
    )
    signing_key = derive_signing_key(
        credentials.secret_access_key, date_stamp, region, service
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"{ALGORITHM} Credential={credentials.access_key_id}/{scope}, "
        f"SignedHeaders={canonical.signed_headers}, Signature={signature}"
    )
    wire_headers = tuple(signing_headers) + (("Authorization", authorization),)
    return SignedRequest(
        method=method,
        url=url,
        headers=wire_headers,
        body=bytes(body),
        canonical_request=canonical,
        string_to_sign=string_to_sign,
        credential_scope=scope,
        amz_date=amz_date,
        signature=signature,
        region=region,
        service=service,
    )


__all__ = [
    "ALGORITHM",
    "AMZ_DATE_HEADER",
    "AUTHORIZATION_HEADER",
    "AwsCredentials",
    "CONTENT_SHA256_HEADER",
    "CanonicalRequest",
    "EMPTY_PAYLOAD_SHA256",
    "SECURITY_TOKEN_HEADER",
    "SIGV4_IMPLEMENTATION_VERSION",
    "SigV4Error",
    "SignedRequest",
    "TERMINATOR",
    "UNSIGNED_PAYLOAD",
    "canonical_headers",
    "canonical_query_string",
    "canonical_query_string_from_params",
    "canonical_uri_from_path",
    "create_canonical_request",
    "create_string_to_sign",
    "credential_scope",
    "derive_signing_key",
    "format_amz_date",
    "format_date_stamp",
    "remove_dot_segments",
    "sha256_hex",
    "sign_request",
]
