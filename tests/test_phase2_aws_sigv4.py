"""Acceptance suite for the standard-library AWS Signature Version 4 signer.

ADR-0030 sets a hard gate on this module: "Hand-rolled SigV4 must validate
against AWS's published test vectors; failing that, a pinned SDK is required
instead." The vectors below are AWS's own published worked examples. Every
credential is the synthetic example credential AWS publishes for exactly this
purpose, and every signing instant is frozen, so the suite is hermetic: no
network, no socket, no real credential, and no reading of the system clock.

A matching signature is a strong check, not a weak one. The signature is an
HMAC over the string-to-sign, which embeds the SHA-256 of the canonical
request. If canonicalisation, header ordering, payload hashing, credential
scope, or the signing-key derivation were wrong by a single byte, the final
signature could not match.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from math_research.phase2 import aws_sigv4
from math_research.phase2.aws_sigv4 import (
    ALGORITHM,
    AwsCredentials,
    EMPTY_PAYLOAD_SHA256,
    SigV4Error,
    canonical_headers,
    canonical_query_string,
    canonical_query_string_from_params,
    canonical_uri_from_path,
    create_string_to_sign,
    credential_scope,
    derive_signing_key,
    format_amz_date,
    format_date_stamp,
    remove_dot_segments,
    sha256_hex,
    sign_request,
)


# AWS's published example credential. Not a real credential.
EXAMPLE_ACCESS_KEY_ID = "AKIDEXAMPLE"
EXAMPLE_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
EXAMPLE_MOMENT = datetime(2015, 8, 30, 12, 36, 0, tzinfo=timezone.utc)

# AWS's published S3 example credential. Not a real credential.
S3_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
S3_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
S3_MOMENT = datetime(2013, 5, 24, 0, 0, 0, tzinfo=timezone.utc)


def example_credentials(session_token: str | None = None) -> AwsCredentials:
    return AwsCredentials(
        access_key_id=EXAMPLE_ACCESS_KEY_ID,
        secret_access_key=EXAMPLE_SECRET_ACCESS_KEY,
        session_token=session_token,
    )


class PublishedTestVectorTests(unittest.TestCase):
    """The four published vectors that pin the whole algorithm."""

    def test_signing_key_derivation_matches_published_example(self) -> None:
        """AWS's documented "derive a signing key" worked example."""
        key = derive_signing_key(
            EXAMPLE_SECRET_ACCESS_KEY, "20150830", "us-east-1", "iam"
        )
        self.assertEqual(
            key.hex(),
            "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9",
        )

    def test_get_vanilla_vector(self) -> None:
        """``get-vanilla`` from AWS's Signature Version 4 test suite."""
        signed = sign_request(
            method="GET",
            url="https://example.amazonaws.com/",
            credentials=example_credentials(),
            region="us-east-1",
            service="service",
            moment=EXAMPLE_MOMENT,
        )
        self.assertEqual(
            signed.canonical_request.text,
            "GET\n"
            "/\n"
            "\n"
            "host:example.amazonaws.com\n"
            "x-amz-date:20150830T123600Z\n"
            "\n"
            "host;x-amz-date\n"
            + EMPTY_PAYLOAD_SHA256,
        )
        self.assertEqual(
            signed.string_to_sign,
            "AWS4-HMAC-SHA256\n"
            "20150830T123600Z\n"
            "20150830/us-east-1/service/aws4_request\n"
            + signed.canonical_request.hash_hex,
        )
        self.assertEqual(
            signed.signature,
            "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
        )
        self.assertEqual(
            signed.authorization,
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
        )

    def test_iam_list_users_vector(self) -> None:
        """AWS's documented end-to-end IAM ``ListUsers`` signing example.

        This vector adds a query string and a signed ``content-type`` header,
        and pins the canonical-request hash independently of the signature.
        """
        signed = sign_request(
            method="GET",
            url="https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08",
            headers=(
                ("Content-Type", "application/x-www-form-urlencoded; charset=utf-8"),
            ),
            credentials=example_credentials(),
            region="us-east-1",
            service="iam",
            moment=EXAMPLE_MOMENT,
        )
        self.assertEqual(
            signed.canonical_request.text,
            "GET\n"
            "/\n"
            "Action=ListUsers&Version=2010-05-08\n"
            "content-type:application/x-www-form-urlencoded; charset=utf-8\n"
            "host:iam.amazonaws.com\n"
            "x-amz-date:20150830T123600Z\n"
            "\n"
            "content-type;host;x-amz-date\n"
            + EMPTY_PAYLOAD_SHA256,
        )
        self.assertEqual(
            signed.canonical_request.hash_hex,
            "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59",
        )
        self.assertEqual(
            signed.string_to_sign,
            "AWS4-HMAC-SHA256\n"
            "20150830T123600Z\n"
            "20150830/us-east-1/iam/aws4_request\n"
            "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59",
        )
        self.assertEqual(
            signed.signature,
            "5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7",
        )
        self.assertEqual(
            signed.authorization,
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/iam/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date, "
            "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7",
        )

    def test_s3_get_object_range_vector(self) -> None:
        """AWS's documented S3 ``GET Object`` Authorization-header example.

        This is the vector that pins ``x-amz-content-sha256`` handling and the
        S3-only single-encoded path form, i.e. ``double_encode_path=False``.
        """
        signed = sign_request(
            method="GET",
            url="https://examplebucket.s3.amazonaws.com/test.txt",
            headers=(("Range", "bytes=0-9"),),
            credentials=AwsCredentials(
                access_key_id=S3_ACCESS_KEY_ID,
                secret_access_key=S3_SECRET_ACCESS_KEY,
            ),
            region="us-east-1",
            service="s3",
            moment=S3_MOMENT,
            double_encode_path=False,
            include_content_sha256=True,
        )
        self.assertEqual(
            signed.canonical_request.text,
            "GET\n"
            "/test.txt\n"
            "\n"
            "host:examplebucket.s3.amazonaws.com\n"
            "range:bytes=0-9\n"
            f"x-amz-content-sha256:{EMPTY_PAYLOAD_SHA256}\n"
            "x-amz-date:20130524T000000Z\n"
            "\n"
            "host;range;x-amz-content-sha256;x-amz-date\n"
            + EMPTY_PAYLOAD_SHA256,
        )
        self.assertEqual(
            signed.signature,
            "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
        )


class CanonicalUriTests(unittest.TestCase):
    def test_empty_and_root_paths_canonicalise_to_root(self) -> None:
        for path in ("", "/", "//", "/./", "/foo/..", "/foo/bar/../.."):
            with self.subTest(path=path):
                self.assertEqual(canonical_uri_from_path(path), "/")

    def test_dot_segment_removal(self) -> None:
        cases = {
            "/foo/bar/../baz": "/foo/baz",
            "/./foo": "/foo",
            "/foo/./bar": "/foo/bar",
            "/foo/bar/..": "/foo/",
            "//example//": "/example/",
            "/a/b/c/../../d": "/a/d",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(remove_dot_segments(path), expected)
                self.assertEqual(canonical_uri_from_path(path), expected)

    def test_unreserved_characters_are_never_encoded(self) -> None:
        unreserved = (
            "-._~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
        )
        self.assertEqual(
            canonical_uri_from_path("/" + unreserved), "/" + unreserved
        )

    def test_space_and_non_ascii_segments_are_percent_encoded(self) -> None:
        self.assertEqual(
            canonical_uri_from_path("/example space/"), "/example%20space/"
        )
        self.assertEqual(
            canonical_uri_from_path("/ᠠᛇᚻ"),
            "/%E1%A0%A0%E1%9B%87%E1%9A%BB",
        )

    def test_non_s3_services_encode_an_encoded_path_a_second_time(self) -> None:
        """The documented non-S3 double-encoding rule, which S3 does not use."""
        self.assertEqual(
            canonical_uri_from_path("/model/a%3Ab/invoke", double_encode=True),
            "/model/a%253Ab/invoke",
        )
        self.assertEqual(
            canonical_uri_from_path("/model/a%3Ab/invoke", double_encode=False),
            "/model/a%3Ab/invoke",
        )

    def test_s3_form_does_not_normalise_dot_segments(self) -> None:
        self.assertEqual(
            canonical_uri_from_path("/a/../b", double_encode=False), "/a/../b"
        )

    def test_non_string_path_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            canonical_uri_from_path(None)  # type: ignore[arg-type]


class CanonicalQueryStringTests(unittest.TestCase):
    def test_empty_query_is_empty(self) -> None:
        self.assertEqual(canonical_query_string(""), "")

    def test_pairs_sort_by_name_then_value(self) -> None:
        self.assertEqual(
            canonical_query_string("Param2=value2&Param1=value1"),
            "Param1=value1&Param2=value2",
        )
        self.assertEqual(
            canonical_query_string("Param1=value2&Param1=value1"),
            "Param1=value1&Param1=value2",
        )

    def test_uppercase_sorts_before_lowercase_by_encoded_bytes(self) -> None:
        self.assertEqual(
            canonical_query_string("param=value&Param=value"),
            "Param=value&param=value",
        )

    def test_valueless_parameter_signs_with_a_trailing_equals(self) -> None:
        self.assertEqual(canonical_query_string("Param1"), "Param1=")

    def test_params_form_encodes_each_component(self) -> None:
        self.assertEqual(
            canonical_query_string_from_params(
                (("b", "a b"), ("a", "x/y"), ("a", "-._~"))
            ),
            "a=-._~&a=x%2Fy&b=a%20b",
        )

    def test_params_form_rejects_non_strings(self) -> None:
        with self.assertRaises(SigV4Error):
            canonical_query_string_from_params(((b"a", "b"),))  # type: ignore[arg-type]


class CanonicalHeaderTests(unittest.TestCase):
    def test_names_lowercase_sort_and_values_trim_and_collapse(self) -> None:
        block, signed = canonical_headers(
            (
                ("X-Amz-Date", "20150830T123600Z"),
                ("Host", "example.amazonaws.com"),
                ("My-Header", "  a   b  "),
            )
        )
        self.assertEqual(
            block,
            "host:example.amazonaws.com\n"
            "my-header:a b\n"
            "x-amz-date:20150830T123600Z\n",
        )
        self.assertEqual(signed, "host;my-header;x-amz-date")

    def test_repeated_names_join_with_a_comma_in_supplied_order(self) -> None:
        block, signed = canonical_headers(
            (("Host", "h"), ("My-Header", "second"), ("my-header", "first"))
        )
        self.assertEqual(block, "host:h\nmy-header:second,first\n")
        self.assertEqual(signed, "host;my-header")

    def test_signed_headers_are_semicolon_joined_in_sorted_order(self) -> None:
        _, signed = canonical_headers(
            (("host", "h"), ("b", "1"), ("a", "1"), ("Z", "1"))
        )
        self.assertEqual(signed, "a;b;host;z")

    def test_missing_host_header_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            canonical_headers((("content-type", "application/json"),))

    def test_invalid_header_name_is_rejected(self) -> None:
        for name in ("bad name", "bad:name", "bad\nname", ""):
            with self.subTest(name=name):
                with self.assertRaises(SigV4Error):
                    canonical_headers((("host", "h"), (name, "v")))

    def test_header_value_with_crlf_or_nul_is_rejected(self) -> None:
        for value in ("a\r\nb", "a\nb", "a\x00b"):
            with self.subTest(value=value):
                with self.assertRaises(SigV4Error):
                    canonical_headers((("host", "h"), ("x", value)))

    def test_header_count_is_bounded(self) -> None:
        headers = [("host", "h")] + [(f"h{index}", "v") for index in range(200)]
        with self.assertRaises(SigV4Error):
            canonical_headers(headers)


class PayloadHashTests(unittest.TestCase):
    def test_empty_payload_hash_constant_is_correct(self) -> None:
        self.assertEqual(sha256_hex(b""), EMPTY_PAYLOAD_SHA256)

    def test_payload_hash_covers_the_body_bytes(self) -> None:
        signed = sign_request(
            method="POST",
            url="https://example.amazonaws.com/",
            body=b'{"a":1}',
            credentials=example_credentials(),
            region="us-east-1",
            service="service",
            moment=EXAMPLE_MOMENT,
        )
        self.assertEqual(
            signed.canonical_request.payload_hash, sha256_hex(b'{"a":1}')
        )
        self.assertNotEqual(
            signed.canonical_request.payload_hash, EMPTY_PAYLOAD_SHA256
        )

    def test_one_body_byte_change_changes_the_signature(self) -> None:
        def signature(body: bytes) -> str:
            return sign_request(
                method="POST", url="https://example.amazonaws.com/", body=body,
                credentials=example_credentials(), region="us-east-1",
                service="service", moment=EXAMPLE_MOMENT,
            ).signature

        self.assertNotEqual(signature(b'{"a":1}'), signature(b'{"a":2}'))

    def test_non_bytes_body_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            sign_request(
                method="POST", url="https://example.amazonaws.com/", body="text",  # type: ignore[arg-type]
                credentials=example_credentials(), region="us-east-1",
                service="service", moment=EXAMPLE_MOMENT,
            )


class CredentialScopeAndDateTests(unittest.TestCase):
    def test_scope_format(self) -> None:
        self.assertEqual(
            credential_scope("20150830", "us-east-1", "bedrock"),
            "20150830/us-east-1/bedrock/aws4_request",
        )

    def test_amz_date_and_date_stamp_formats(self) -> None:
        self.assertEqual(format_amz_date(EXAMPLE_MOMENT), "20150830T123600Z")
        self.assertEqual(format_date_stamp(EXAMPLE_MOMENT), "20150830")

    def test_string_to_sign_layout(self) -> None:
        self.assertEqual(
            create_string_to_sign(
                amz_date="20150830T123600Z",
                scope="20150830/us-east-1/bedrock/aws4_request",
                canonical_request_hash="ab" * 32,
            ),
            f"{ALGORITHM}\n20150830T123600Z\n"
            "20150830/us-east-1/bedrock/aws4_request\n" + "ab" * 32,
        )

    def test_naive_datetime_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            format_amz_date(datetime(2015, 8, 30, 12, 36, 0))

    def test_non_utc_datetime_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            format_amz_date(
                datetime(
                    2015, 8, 30, 12, 36, 0,
                    tzinfo=timezone(timedelta(hours=2)),
                )
            )

    def test_scope_binds_region_and_service(self) -> None:
        base = dict(
            method="GET", url="https://example.amazonaws.com/",
            credentials=example_credentials(), moment=EXAMPLE_MOMENT,
        )
        one = sign_request(region="us-east-1", service="bedrock", **base)
        two = sign_request(region="eu-west-1", service="bedrock", **base)
        three = sign_request(region="us-east-1", service="service", **base)
        self.assertNotEqual(one.signature, two.signature)
        self.assertNotEqual(one.signature, three.signature)


class SessionTokenTests(unittest.TestCase):
    TOKEN = "FQoDYXdzEEXAMPLESESSIONTOKENvalue=="

    def test_session_token_is_signed_and_sent_as_x_amz_security_token(self) -> None:
        signed = sign_request(
            method="POST",
            url="https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke",
            credentials=example_credentials(self.TOKEN),
            region="us-east-1",
            service="bedrock",
            moment=EXAMPLE_MOMENT,
        )
        self.assertIn("x-amz-security-token", signed.canonical_request.signed_headers)
        self.assertIn(
            f"x-amz-security-token:{self.TOKEN}",
            signed.canonical_request.canonical_headers,
        )
        self.assertEqual(
            signed.header_mapping()["x-amz-security-token"], self.TOKEN
        )

    def test_session_token_changes_the_signature(self) -> None:
        base = dict(
            method="POST", url="https://example.amazonaws.com/",
            region="us-east-1", service="bedrock", moment=EXAMPLE_MOMENT,
        )
        without = sign_request(credentials=example_credentials(), **base)
        with_token = sign_request(
            credentials=example_credentials(self.TOKEN), **base
        )
        self.assertNotEqual(without.signature, with_token.signature)

    def test_absent_session_token_adds_no_header(self) -> None:
        signed = sign_request(
            method="POST", url="https://example.amazonaws.com/",
            credentials=example_credentials(), region="us-east-1",
            service="bedrock", moment=EXAMPLE_MOMENT,
        )
        self.assertNotIn("x-amz-security-token", signed.header_mapping())


class SecretContainmentTests(unittest.TestCase):
    TOKEN = "SESSIONTOKENSECRETVALUE"

    def test_credentials_repr_and_str_disclose_nothing(self) -> None:
        credentials = example_credentials(self.TOKEN)
        for rendered in (repr(credentials), str(credentials), f"{credentials}"):
            self.assertNotIn(EXAMPLE_SECRET_ACCESS_KEY, rendered)
            self.assertNotIn(EXAMPLE_ACCESS_KEY_ID, rendered)
            self.assertNotIn(self.TOKEN, rendered)
            self.assertIn("[REDACTED]", rendered)

    def test_secret_material_lists_every_value_needing_scrubbing(self) -> None:
        credentials = example_credentials(self.TOKEN)
        self.assertEqual(
            set(credentials.secret_material),
            {EXAMPLE_SECRET_ACCESS_KEY, EXAMPLE_ACCESS_KEY_ID, self.TOKEN},
        )
        self.assertEqual(
            set(example_credentials().secret_material),
            {EXAMPLE_SECRET_ACCESS_KEY, EXAMPLE_ACCESS_KEY_ID},
        )

    def test_signed_request_never_carries_the_secret_or_signing_key(self) -> None:
        signed = sign_request(
            method="POST",
            url="https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke",
            body=b'{"a":1}',
            credentials=example_credentials(self.TOKEN),
            region="us-east-1",
            service="bedrock",
            moment=EXAMPLE_MOMENT,
        )
        signing_key = derive_signing_key(
            EXAMPLE_SECRET_ACCESS_KEY, "20150830", "us-east-1", "bedrock"
        )
        rendered = "\n".join(
            (
                repr(signed.canonical_request),
                signed.string_to_sign,
                signed.credential_scope,
                signed.signature,
                signed.authorization,
                repr(signed.loggable_headers()),
            )
        )
        self.assertNotIn(EXAMPLE_SECRET_ACCESS_KEY, rendered)
        self.assertNotIn(signing_key.hex(), rendered)
        self.assertNotIn("AWS4" + EXAMPLE_SECRET_ACCESS_KEY, rendered)
        # The session token is in the signed wire headers by necessity, but the
        # loggable view is the only view a diagnostic may use.
        self.assertNotIn(self.TOKEN, repr(signed.loggable_headers()))

    def test_loggable_headers_redact_authorization_and_security_token(self) -> None:
        signed = sign_request(
            method="POST", url="https://example.amazonaws.com/",
            credentials=example_credentials(self.TOKEN), region="us-east-1",
            service="bedrock", moment=EXAMPLE_MOMENT,
        )
        loggable = dict(signed.loggable_headers())
        self.assertEqual(loggable["Authorization"], "[REDACTED]")
        self.assertEqual(loggable["x-amz-security-token"], "[REDACTED]")
        self.assertEqual(loggable["host"], "example.amazonaws.com")
        rendered = repr(loggable)
        self.assertNotIn(signed.signature, rendered)
        self.assertNotIn(self.TOKEN, rendered)

    def test_credential_validation_messages_name_fields_not_values(self) -> None:
        with self.assertRaises(SigV4Error) as caught:
            AwsCredentials(access_key_id="", secret_access_key="s3cr3t-value")
        self.assertNotIn("s3cr3t-value", str(caught.exception))


class SigningInputValidationTests(unittest.TestCase):
    def _sign(self, **overrides: object):
        base = dict(
            method="POST",
            url="https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke",
            credentials=example_credentials(),
            region="us-east-1",
            service="bedrock",
            moment=EXAMPLE_MOMENT,
        )
        base.update(overrides)
        return sign_request(**base)  # type: ignore[arg-type]

    def test_non_https_url_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            self._sign(url="http://bedrock-runtime.us-east-1.amazonaws.com/x")

    def test_url_with_fragment_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            self._sign(url="https://example.amazonaws.com/x#frag")

    def test_url_with_embedded_credentials_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            self._sign(url="https://user:pass@example.amazonaws.com/x")

    def test_lowercase_method_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            self._sign(method="post")

    def test_invalid_region_or_service_is_rejected(self) -> None:
        for field, value in (
            ("region", "US-East-1"),
            ("region", ""),
            ("service", "Bedrock"),
            ("service", "bedrock runtime"),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(SigV4Error):
                    self._sign(**{field: value})

    def test_caller_may_not_supply_derived_headers(self) -> None:
        for name in (
            "Authorization", "authorization", "Host", "host",
            "X-Amz-Date", "x-amz-security-token",
        ):
            with self.subTest(name=name):
                with self.assertRaises(SigV4Error):
                    self._sign(headers=((name, "value"),))

    def test_host_is_derived_from_the_url_authority(self) -> None:
        signed = self._sign()
        self.assertEqual(
            signed.header_mapping()["host"],
            "bedrock-runtime.us-east-1.amazonaws.com",
        )
        self.assertIn(
            "host:bedrock-runtime.us-east-1.amazonaws.com",
            signed.canonical_request.canonical_headers,
        )

    def test_wrong_credentials_type_is_rejected(self) -> None:
        with self.assertRaises(SigV4Error):
            self._sign(credentials="AKIDEXAMPLE")

    def test_derive_signing_key_rejects_an_empty_secret(self) -> None:
        with self.assertRaises(SigV4Error):
            derive_signing_key("", "20150830", "us-east-1", "bedrock")


class DeterminismTests(unittest.TestCase):
    def test_identical_inputs_produce_byte_identical_signatures(self) -> None:
        def once():
            return sign_request(
                method="POST",
                url="https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke",
                headers=(("Content-Type", "application/json"),),
                body=b'{"b":2,"a":1}',
                credentials=example_credentials("TOKEN"),
                region="us-east-1",
                service="bedrock",
                moment=EXAMPLE_MOMENT,
            )

        first, second = once(), once()
        self.assertEqual(first.signature, second.signature)
        self.assertEqual(first.headers, second.headers)
        self.assertEqual(
            first.canonical_request.text, second.canonical_request.text
        )


class ImportHygieneTests(unittest.TestCase):
    def test_module_reads_no_clock_and_holds_no_network_or_sdk_reference(self) -> None:
        for forbidden in ("socket", "ssl", "http", "boto3", "botocore", "requests"):
            self.assertFalse(
                hasattr(aws_sigv4, forbidden),
                f"aws_sigv4 must not reference {forbidden}",
            )

    def test_signing_requires_an_explicit_instant(self) -> None:
        """No default clock: a missing instant is an error, not "now"."""
        with self.assertRaises(TypeError):
            sign_request(  # type: ignore[call-arg]
                method="GET", url="https://example.amazonaws.com/",
                credentials=example_credentials(), region="us-east-1",
                service="bedrock",
            )


if __name__ == "__main__":
    unittest.main()
