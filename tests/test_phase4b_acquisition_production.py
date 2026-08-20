from __future__ import annotations

from dataclasses import replace
import json
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicy,
    AcquisitionPolicyError,
    AcquisitionRequest,
    AuthorizedResource,
    Resolution,
    RightsDecision,
    RobotsSnapshot,
    RunAuthorization,
    TermsSnapshot,
    TransportFailure,
    TransportRequest,
    TransportResponse,
    acquire,
    canonical_url,
)


NOW = 200_000
HASH_A = "a" * 64
HASH_B = "b" * 64
START = "https://papers.example/start"
FINAL = "https://archive.example/final"
PUBLIC_A = "93.184.216.34"
PUBLIC_B = "8.8.8.8"


class FakeResolver:
    def __init__(self, values: dict[str, tuple[str, ...]] | None = None) -> None:
        self.values = values or {
            "papers.example": (PUBLIC_A,),
            "archive.example": (PUBLIC_B,),
        }
        self.calls: list[str] = []

    def resolve(self, hostname: str) -> Resolution:
        self.calls.append(hostname)
        return Resolution(hostname, self.values[hostname])


class FakeTransport:
    def __init__(self, values: dict[str, list[TransportResponse | Exception]]) -> None:
        self.values = values
        self.offsets: dict[str, int] = {}
        self.calls: list[TransportRequest] = []

    def fetch(self, request: TransportRequest) -> TransportResponse:
        self.calls.append(request)
        offset = self.offsets.get(request.url, 0)
        self.offsets[request.url] = offset + 1
        sequence = self.values[request.url]
        item = sequence[min(offset, len(sequence) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class FakeStartClock:
    def __init__(self, values: tuple[int, ...] | None = None) -> None:
        self.values = values
        self.calls = 0

    def now_milliseconds(self) -> int:
        if self.values is None:
            value = self.calls * 1_000
        else:
            value = self.values[self.calls]
        self.calls += 1
        return value


def response(
    *,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (("content-type", "text/plain"),),
    body: bytes = b"project-authored source",
    peer: str = PUBLIC_A,
    elapsed: int = 1,
) -> TransportResponse:
    return TransportResponse(status, headers, body, peer, elapsed)


class Phase4BAcquisitionProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AcquisitionPolicy()
        self.authorization = RunAuthorization(
            run_id="run.phase4b.test",
            actor_id="human.owner",
            actor_kind="human",
            authority="human_final",
            capability_id="capability.phase4b.acquire",
            operation="acquire_https",
            network_enabled=True,
            policy_hash=self.policy.content_hash,
            approved_origins=("https://papers.example",),
            resources=(AuthorizedResource("request.1", START),),
        )
        self.request = AcquisitionRequest(
            self.authorization.run_id, "request.1", self.authorization.actor_id, START
        )

    def rights_for(self, *urls: str) -> list[RightsDecision]:
        return [
            RightsDecision(
                f"rights.{index}.{use}", self.authorization.run_id, url, use,
                "allowed", "human", "human_final", NOW - 10, NOW + 10,
            )
            for index, url in enumerate(urls)
            for use in ("acquisition", "storage_and_retention")
        ]

    def terms_for(self, *origins: str, captured: int = NOW) -> list[TermsSnapshot]:
        return [
            TermsSnapshot(f"terms.{index}", origin, HASH_A, captured, True, True)
            for index, origin in enumerate(origins)
        ]

    def robots_for(self, *urls: str, captured: int = NOW) -> list[RobotsSnapshot]:
        return [
            RobotsSnapshot(f"robots.{index}", url, HASH_B, captured, True, True)
            for index, url in enumerate(urls)
        ]

    def execute(
        self,
        *,
        requests: tuple[AcquisitionRequest, ...] | None = None,
        authorization: RunAuthorization | None = None,
        policy: AcquisitionPolicy | None = None,
        rights: list[RightsDecision] | None = None,
        terms: list[TermsSnapshot] | None = None,
        robots: list[RobotsSnapshot] | None = None,
        resolver: FakeResolver | None = None,
        transport: FakeTransport | None = None,
        start_clock: FakeStartClock | None = None,
        recorded_at: int = NOW,
    ):
        resolver = resolver or FakeResolver()
        transport = transport or FakeTransport({START: [response()]})
        result = acquire(
            requests or (self.request,),
            authorization=authorization or self.authorization,
            policy=policy or self.policy,
            rights=rights if rights is not None else self.rights_for(START),
            terms=terms if terms is not None else self.terms_for("https://papers.example"),
            robots=robots if robots is not None else self.robots_for(START),
            resolver=resolver,
            transport=transport,
            start_clock=start_clock or FakeStartClock(),
            now_epoch=NOW,
            recorded_at_epoch=recorded_at,
        )
        return result, resolver, transport

    @staticmethod
    def semantic(result) -> dict:
        return json.loads(result.semantic_bytes)

    def test_authorized_fetch_returns_only_an_untrusted_candidate(self) -> None:
        result, resolver, transport = self.execute()
        self.assertEqual(["papers.example"], resolver.calls)
        self.assertEqual(1, len(transport.calls))
        self.assertEqual("GET", transport.calls[0].method)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("untrusted_candidate", candidate.disposition)
        self.assertEqual("not_assessed", candidate.applicability_status)
        self.assertEqual("none", candidate.mathematical_warrant)
        self.assertEqual("not_admitted", candidate.graph_admission)
        self.assertNotIn(b"project-authored source", result.semantic_bytes)
        self.assertNotIn(b"project-authored source", result.operational_bytes)

    def test_semantic_identity_excludes_operational_time_and_resolution(self) -> None:
        first, _, _ = self.execute(
            resolver=FakeResolver({"papers.example": (PUBLIC_A,)}),
            transport=FakeTransport({START: [response(elapsed=1)]}),
            recorded_at=NOW,
        )
        second, _, _ = self.execute(
            resolver=FakeResolver({"papers.example": ("1.1.1.1",)}),
            transport=FakeTransport({START: [response(peer="1.1.1.1", elapsed=9)]}),
            recorded_at=NOW + 99,
        )
        self.assertEqual(first.semantic_bytes, second.semantic_bytes)
        self.assertEqual(first.semantic_hash, second.semantic_hash)
        self.assertNotEqual(first.operational_bytes, second.operational_bytes)
        self.assertNotEqual(first.operational_hash, second.operational_hash)

    def test_exact_human_run_policy_and_resource_authority_is_required(self) -> None:
        resolver = FakeResolver()
        transport = FakeTransport({START: [response()]})
        for authorization in (
            replace(self.authorization, actor_kind="automation"),
            replace(self.authorization, authority="proposal"),
            replace(self.authorization, network_enabled=False),
            replace(self.authorization, operation="crawl"),
            replace(self.authorization, policy_hash="0" * 64),
        ):
            with self.subTest(authorization=authorization):
                with self.assertRaisesRegex(AcquisitionPolicyError, "run_authority_invalid"):
                    self.execute(authorization=authorization, resolver=resolver, transport=transport)
        self.assertEqual([], resolver.calls)
        self.assertEqual([], transport.calls)

        wrong = replace(self.request, actor_id="other.human")
        result, resolver, transport = self.execute(requests=(wrong,))
        self.assertEqual("request_not_exactly_authorized", self.semantic(result)["results"][0]["reason"])
        self.assertEqual([], resolver.calls)
        self.assertEqual([], transport.calls)

    def test_acquisition_and_storage_rights_are_separate_prefetch_gates(self) -> None:
        complete = self.rights_for(START)
        for retained, reason in (
            ([item for item in complete if item.intended_use != "acquisition"], "acquisition_rights_invalid"),
            ([item for item in complete if item.intended_use != "storage_and_retention"], "storage_and_retention_rights_invalid"),
        ):
            result, resolver, transport = self.execute(rights=retained)
            self.assertEqual(reason, self.semantic(result)["results"][0]["reason"])
            self.assertEqual([], resolver.calls)
            self.assertEqual([], transport.calls)

    def test_terms_and_robots_freshness_pass_at_limit_and_fail_one_over(self) -> None:
        captured = NOW - self.policy.max_snapshot_age_seconds
        result, _, transport = self.execute(
            terms=self.terms_for("https://papers.example", captured=captured),
            robots=self.robots_for(START, captured=captured),
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(1, len(transport.calls))
        for stale_terms, stale_robots, reason in (
            (self.terms_for("https://papers.example", captured=captured - 1), self.robots_for(START), "terms_snapshot_invalid_or_stale"),
            (self.terms_for("https://papers.example"), self.robots_for(START, captured=captured - 1), "robots_snapshot_invalid_or_stale"),
        ):
            result, resolver, transport = self.execute(terms=stale_terms, robots=stale_robots)
            self.assertEqual(reason, self.semantic(result)["results"][0]["reason"])
            self.assertEqual([], resolver.calls)
            self.assertEqual([], transport.calls)

    def test_canonical_https_url_policy_fails_before_resolution(self) -> None:
        values = (
            "http://papers.example/start",
            "https://user@papers.example/start",
            "https://papers.example:444/start",
            "https://papers.example/start#fragment",
            "https://papers.example/a/../start",
            "https://papers.example\\@evil.example/start",
            "https://under_score.example/start",
            "https://-leading-hyphen.example/start",
            "https://trailing-hyphen-.example/start",
        )
        for value in values:
            request = replace(self.request, url=value)
            result, resolver, transport = self.execute(requests=(request,))
            self.assertEqual("failed", self.semantic(result)["results"][0]["outcome"])
            self.assertEqual([], resolver.calls)
            self.assertEqual([], transport.calls)

    def test_url_byte_bound_passes_exactly_and_fails_one_over(self) -> None:
        prefix = "https://papers.example/"
        at_limit = prefix + "a" * (2_048 - len(prefix.encode("utf-8")))
        self.assertEqual(2_048, len(canonical_url(at_limit).encode("utf-8")))
        with self.assertRaisesRegex(AcquisitionPolicyError, "url_length_invalid"):
            canonical_url(at_limit + "a")

    def test_approved_origin_count_passes_at_four_and_fails_at_five(self) -> None:
        four = (
            "https://papers.example",
            "https://one.example",
            "https://two.example",
            "https://three.example",
        )
        result, _, _ = self.execute(
            authorization=replace(self.authorization, approved_origins=four)
        )
        self.assertEqual(1, len(result.candidates))
        with self.assertRaisesRegex(AcquisitionPolicyError, "approved_origin_count_invalid"):
            self.execute(
                authorization=replace(
                    self.authorization,
                    approved_origins=four + ("https://four.example",),
                )
            )

    def test_requested_resource_count_passes_at_one_hundred_and_fails_at_one_hundred_one(self) -> None:
        urls = tuple(f"https://papers.example/resource-{index}" for index in range(100))
        resources = tuple(
            AuthorizedResource(f"request.{index}", url) for index, url in enumerate(urls)
        )
        requests = tuple(
            AcquisitionRequest(
                self.authorization.run_id, resource.request_id,
                self.authorization.actor_id, resource.url,
            )
            for resource in resources
        )
        transport = FakeTransport({url: [response(body=b"x")] for url in urls})
        result, _, transport = self.execute(
            requests=requests,
            authorization=replace(self.authorization, resources=resources),
            rights=self.rights_for(*urls),
            robots=self.robots_for(*urls),
            transport=transport,
        )
        self.assertEqual(100, len(result.candidates))
        self.assertEqual(100, len(transport.calls))

        extra_url = "https://papers.example/resource-100"
        with self.assertRaisesRegex(AcquisitionPolicyError, "authorized_resource_count_invalid"):
            self.execute(
                requests=requests + (
                    AcquisitionRequest(
                        self.authorization.run_id, "request.100",
                        self.authorization.actor_id, extra_url,
                    ),
                ),
                authorization=replace(
                    self.authorization,
                    resources=resources + (AuthorizedResource("request.100", extra_url),),
                ),
            )

    def test_redirect_reauthorizes_origin_rights_terms_robots_and_address(self) -> None:
        authorization = replace(
            self.authorization,
            approved_origins=("https://papers.example", "https://archive.example"),
        )
        redirect = response(status=302, headers=(("location", FINAL),), body=b"")
        transport = FakeTransport(
            {START: [redirect], FINAL: [response(peer=PUBLIC_B, body=b"final bytes")]}
        )
        result, resolver, transport = self.execute(
            authorization=authorization,
            rights=self.rights_for(START, FINAL),
            terms=self.terms_for("https://papers.example", "https://archive.example"),
            robots=self.robots_for(START, FINAL),
            transport=transport,
        )
        self.assertEqual(["papers.example", "archive.example"], resolver.calls)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(FINAL, result.candidates[0].source_url)

        result, resolver, transport = self.execute(
            authorization=authorization,
            rights=self.rights_for(START),
            terms=self.terms_for("https://papers.example", "https://archive.example"),
            robots=self.robots_for(START, FINAL),
            transport=FakeTransport({START: [redirect]}),
        )
        self.assertEqual("acquisition_rights_invalid", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(["papers.example"], resolver.calls)
        self.assertEqual(1, len(transport.calls))

    def test_redirect_count_passes_at_five_and_fails_on_sixth(self) -> None:
        urls = (START,) + tuple(
            f"https://papers.example/redirect-{index}" for index in range(1, 7)
        )

        def redirect_transport(final_index: int) -> FakeTransport:
            scripted: dict[str, list[TransportResponse | Exception]] = {}
            for index in range(final_index):
                scripted[urls[index]] = [
                    response(status=302, headers=(("location", urls[index + 1]),), body=b"")
                ]
            scripted[urls[final_index]] = [response(body=b"done")]
            return FakeTransport(scripted)

        result, _, transport = self.execute(
            rights=self.rights_for(*urls[:6]),
            robots=self.robots_for(*urls[:6]),
            transport=redirect_transport(5),
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(5, len(self.semantic(result)["results"][0]["redirects"]))
        self.assertEqual(6, len(transport.calls))

        result, _, transport = self.execute(
            rights=self.rights_for(*urls),
            robots=self.robots_for(*urls),
            transport=redirect_transport(6),
        )
        self.assertEqual("redirect_limit_exhausted", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(6, len(transport.calls))

    def test_special_resolved_addresses_and_connected_peer_mismatch_are_denied(self) -> None:
        for address in (
            "127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0", "192.0.2.1", "::1", "fe80::1",
        ):
            with self.subTest(address=address):
                result, resolver, transport = self.execute(
                    resolver=FakeResolver({"papers.example": (address,)})
                )
                self.assertEqual("resolved_address_forbidden", self.semantic(result)["results"][0]["reason"])
                self.assertEqual(1, len(resolver.calls))
                self.assertEqual([], transport.calls)
        result, _, transport = self.execute(
            transport=FakeTransport({START: [response(peer=PUBLIC_B)]})
        )
        self.assertEqual("connected_peer_mismatch", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(1, len(transport.calls))
        result, _, _ = self.execute(
            transport=FakeTransport({START: [response(peer="127.0.0.1")]})
        )
        self.assertEqual("connected_peer_forbidden", self.semantic(result)["results"][0]["reason"])

    def test_cross_origin_redirect_strips_origin_bound_credentials(self) -> None:
        authorization = replace(
            self.authorization,
            approved_origins=("https://papers.example", "https://archive.example"),
        )
        request = replace(
            self.request,
            headers=(("Authorization", "secret"), ("Cookie", "session=x"), ("Referer", START), ("X-Safe", "kept")),
        )
        transport = FakeTransport(
            {
                START: [response(status=302, headers=(("location", FINAL),), body=b"")],
                FINAL: [response(peer=PUBLIC_B)],
            }
        )
        result, _, transport = self.execute(
            requests=(request,), authorization=authorization,
            rights=self.rights_for(START, FINAL),
            terms=self.terms_for("https://papers.example", "https://archive.example"),
            robots=self.robots_for(START, FINAL), transport=transport,
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            {"authorization", "cookie", "referer", "x-safe"},
            {name for name, _ in transport.calls[0].headers},
        )
        self.assertEqual((("x-safe", "kept"),), transport.calls[1].headers)

    def test_header_body_time_and_source_bounds_pass_at_limit_and_fail_one_over(self) -> None:
        header_policy = replace(self.policy, max_header_bytes=10)
        at_header = (("x", "12345"),)  # 1 + 2 + 5 + 2 = 10 bytes.
        result, _, _ = self.execute(
            policy=header_policy,
            authorization=replace(self.authorization, policy_hash=header_policy.content_hash),
            transport=FakeTransport({START: [response(headers=at_header)]}),
        )
        self.assertEqual(1, len(result.candidates))
        result, _, _ = self.execute(
            policy=header_policy,
            authorization=replace(self.authorization, policy_hash=header_policy.content_hash),
            transport=FakeTransport({START: [response(headers=(("x", "123456"),))]}),
        )
        self.assertEqual("response_headers_too_large", self.semantic(result)["results"][0]["reason"])

        body_policy = replace(self.policy, max_body_bytes=4, max_total_body_bytes=4)
        authority = replace(self.authorization, policy_hash=body_policy.content_hash)
        result, _, _ = self.execute(
            policy=body_policy, authorization=authority,
            transport=FakeTransport({START: [response(body=b"1234")]}),
        )
        self.assertEqual(1, len(result.candidates))
        result, _, _ = self.execute(
            policy=body_policy, authorization=authority,
            transport=FakeTransport({START: [response(body=b"12345")]}),
        )
        self.assertEqual("response_body_too_large", self.semantic(result)["results"][0]["reason"])

        time_policy = replace(self.policy, max_run_milliseconds=10)
        authority = replace(self.authorization, policy_hash=time_policy.content_hash)
        result, _, _ = self.execute(
            policy=time_policy, authorization=authority,
            transport=FakeTransport({START: [response(elapsed=10)]}),
            start_clock=FakeStartClock((0, 0, 0, 10)),
        )
        self.assertEqual(1, len(result.candidates))
        result, _, _ = self.execute(
            policy=time_policy, authorization=authority,
            transport=FakeTransport({START: [response(elapsed=11)]}),
            start_clock=FakeStartClock((0, 0, 0, 10)),
        )
        self.assertEqual("run_time_exhausted", self.semantic(result)["results"][0]["reason"])

        source_policy = replace(self.policy, max_sources=1)
        authority = replace(self.authorization, policy_hash=source_policy.content_hash)
        with self.assertRaisesRegex(AcquisitionPolicyError, "request_count_invalid"):
            self.execute(
                requests=(self.request, replace(self.request, request_id="request.2")),
                policy=source_policy, authorization=authority,
            )

    def test_total_body_budget_passes_at_limit_and_fails_one_over(self) -> None:
        second = "https://papers.example/second"
        requests = (
            self.request,
            AcquisitionRequest(
                self.authorization.run_id, "request.2", self.authorization.actor_id, second
            ),
        )
        resources = (
            AuthorizedResource("request.1", START),
            AuthorizedResource("request.2", second),
        )
        policy = replace(self.policy, max_body_bytes=4, max_total_body_bytes=8)
        authority = replace(self.authorization, policy_hash=policy.content_hash, resources=resources)
        common = {
            "requests": requests,
            "authorization": authority,
            "policy": policy,
            "rights": self.rights_for(START, second),
            "robots": self.robots_for(START, second),
        }
        result, _, _ = self.execute(
            **common,
            transport=FakeTransport({START: [response(body=b"1234")], second: [response(body=b"5678")]}),
        )
        self.assertEqual(2, len(result.candidates))

        policy = replace(policy, max_total_body_bytes=7)
        result, _, transport = self.execute(
            **{**common, "policy": policy, "authorization": replace(authority, policy_hash=policy.content_hash)},
            transport=FakeTransport({START: [response(body=b"1234")], second: [response(body=b"5678")]}),
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("run_body_budget_exhausted", self.semantic(result)["results"][1]["reason"])
        self.assertEqual(2, len(transport.calls))

    def test_retries_only_transport_408_429_and_5xx_and_never_exceed_two(self) -> None:
        transport = FakeTransport(
            {START: [TransportFailure("one"), response(status=500), response()]}
        )
        result, resolver, transport = self.execute(transport=transport)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(3, len(transport.calls))
        self.assertEqual(3, len(resolver.calls))

        transport = FakeTransport({START: [response(status=500)]})
        result, _, transport = self.execute(transport=transport)
        self.assertEqual("retry_exhausted_status", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(3, len(transport.calls))

        transport = FakeTransport({START: [response(status=404)]})
        result, _, transport = self.execute(transport=transport)
        self.assertEqual("http_status", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(1, len(transport.calls))

    def test_per_origin_start_rate_passes_at_one_second_and_fails_one_under(self) -> None:
        second = "https://papers.example/second"
        requests = (
            self.request,
            AcquisitionRequest(
                self.authorization.run_id, "request.2", self.authorization.actor_id, second
            ),
        )
        authorization = replace(
            self.authorization,
            resources=(
                AuthorizedResource("request.1", START),
                AuthorizedResource("request.2", second),
            ),
        )
        transport = FakeTransport({START: [response()], second: [response()]})
        result, _, transport = self.execute(
            requests=requests,
            authorization=authorization,
            rights=self.rights_for(START, second),
            robots=self.robots_for(START, second),
            transport=transport,
            start_clock=FakeStartClock((0, 0, 0, 0, 1_000, 1_000, 1_000, 1_000)),
        )
        self.assertEqual(2, len(result.candidates))
        self.assertEqual(2, len(transport.calls))

        transport = FakeTransport({START: [response()], second: [response()]})
        result, _, transport = self.execute(
            requests=requests,
            authorization=authorization,
            rights=self.rights_for(START, second),
            robots=self.robots_for(START, second),
            transport=transport,
            start_clock=FakeStartClock((0, 0, 0, 0, 999, 999, 999, 999)),
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("origin_start_rate_exceeded", self.semantic(result)["results"][1]["reason"])
        self.assertEqual(1, len(transport.calls))

    def test_retries_are_independently_rate_gated(self) -> None:
        transport = FakeTransport(
            {START: [TransportFailure("one"), response(status=500), response()]}
        )
        result, _, transport = self.execute(
            transport=transport,
            start_clock=FakeStartClock(
                (0, 0, 0, 0, 1_000, 1_000, 1_000, 1_000, 2_000, 2_000, 2_000, 2_000)
            ),
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(3, len(transport.calls))

        transport = FakeTransport({START: [TransportFailure("one"), response()]})
        result, _, transport = self.execute(
            transport=transport,
            start_clock=FakeStartClock((0, 0, 0, 0, 999, 999, 999, 999)),
        )
        self.assertEqual("origin_start_rate_exceeded", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(1, len(transport.calls))

    def test_failures_fabricate_no_content_and_use_no_real_network_adapter(self) -> None:
        transport = FakeTransport({START: [TransportFailure("offline failure")]})
        result, resolver, transport = self.execute(transport=transport)
        semantic = self.semantic(result)
        self.assertEqual([], list(result.candidates))
        self.assertEqual("retry_exhausted_transport", semantic["results"][0]["reason"])
        self.assertNotIn("content_sha256", semantic["results"][0])
        self.assertEqual(3, len(resolver.calls))
        self.assertEqual(3, len(transport.calls))

    def test_adapter_errors_and_malformed_responses_fail_closed_without_leaking(self) -> None:
        class ExplodingResolver:
            def resolve(self, hostname: str) -> Resolution:
                raise RuntimeError("resolver secret")

        result, _, transport = self.execute(resolver=ExplodingResolver())  # type: ignore[arg-type]
        self.assertEqual("resolver_adapter_error", self.semantic(result)["results"][0]["reason"])
        self.assertEqual([], transport.calls)
        self.assertNotIn(b"resolver secret", result.operational_bytes)
        self.assertNotIn(b"RuntimeError", result.operational_bytes)

        class MalformedResolver:
            def resolve(self, hostname: str) -> object:
                return object()

        result, _, transport = self.execute(resolver=MalformedResolver())  # type: ignore[arg-type]
        self.assertEqual("resolver_response_invalid", self.semantic(result)["results"][0]["reason"])
        self.assertEqual([], transport.calls)

        transport = FakeTransport({START: [RuntimeError("transport secret")]})
        result, _, transport = self.execute(transport=transport)
        self.assertEqual("retry_exhausted_transport", self.semantic(result)["results"][0]["reason"])
        operations = json.loads(result.operational_bytes)["operations"]
        self.assertEqual(3, len(operations))
        self.assertTrue(all(item["transport_failure"] == "transport_adapter_error" for item in operations))
        self.assertNotIn(b"transport secret", result.operational_bytes)
        self.assertNotIn(b"RuntimeError", result.operational_bytes)

        malformed = FakeTransport({START: [object()]})  # type: ignore[list-item]
        result, _, malformed = self.execute(transport=malformed)
        self.assertEqual("transport_response_invalid", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(1, len(malformed.calls))

    def test_absolute_deadline_covers_preflight_resolver_and_transport_failures(self) -> None:
        policy = replace(self.policy, max_run_milliseconds=10, max_retries=0)
        authority = replace(self.authorization, policy_hash=policy.content_hash)

        result, _, _ = self.execute(
            policy=policy,
            authorization=authority,
            transport=FakeTransport({START: [response(elapsed=10)]}),
            start_clock=FakeStartClock((0, 0, 0, 10)),
        )
        self.assertEqual(1, len(result.candidates), "the exact deadline is inclusive")

        result, _, transport = self.execute(
            policy=policy,
            authorization=authority,
            rights=[],
            start_clock=FakeStartClock((0, 11)),
        )
        self.assertEqual("run_time_exhausted", self.semantic(result)["results"][0]["reason"])
        self.assertEqual([], transport.calls)

        class SlowFailingResolver:
            def resolve(self, hostname: str) -> Resolution:
                raise OSError("private resolver detail")

        result, _, transport = self.execute(
            policy=policy,
            authorization=authority,
            resolver=SlowFailingResolver(),  # type: ignore[arg-type]
            start_clock=FakeStartClock((0, 0, 11)),
        )
        self.assertEqual("run_time_exhausted", self.semantic(result)["results"][0]["reason"])
        self.assertEqual([], transport.calls)

        result, _, transport = self.execute(
            policy=policy,
            authorization=authority,
            transport=FakeTransport({START: [TransportFailure("private transport detail")]}),
            start_clock=FakeStartClock((0, 0, 0, 11)),
        )
        self.assertEqual("run_time_exhausted", self.semantic(result)["results"][0]["reason"])
        self.assertEqual(1, len(transport.calls))
        self.assertNotIn(b"private", result.operational_bytes)


if __name__ == "__main__":
    unittest.main()
