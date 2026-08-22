"""The ADR-0067 falsifiability probes.

ADR-0034 established the standard and this slice keeps it: ``probes_flipped ==
probes_total`` gates the slice, because a bound that cannot be made to fail
proves nothing.

Each probe has two legs and a named expected refusal code.  The BASELINE leg
exercises the accepted path and must NOT produce the code; the MUTATED leg makes
one named change and must produce exactly that code.  A probe flips only when
both hold, so a probe passes neither by always failing nor by never firing.

Most probes mutate an INPUT.  Three state a positive property -- the static
e-print sweep, the zero-transport replay, and the abstract-page link -- so their
mutated leg fires the instrument against a deliberately wrong subject instead.
That distinction is recorded on each probe as ``mutation_target`` rather than
left to a reader.

Every fixture here is built in-module and in a temporary directory.  Nothing in
this file reads the repository fixtures, and no leg touches a network.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import PLAN_SCHEMA_VERSION, PROBE_REPORT_SCHEMA_VERSION
from ..phase4a.records import Processor, RightsReason, RightsUse, RightsValue
from ..phase4a.service import Phase4Service
from ..phase4a.workspace import Phase4Workspace
from .acquisition import acquire_tranche, dry_run
from .activation import STATUS_ACTIVE, STATUS_PENDING, _PINNED, validate_activation
from .atom import assert_markup_restricted, assert_no_foreign_urls, parse_feed
from .constants import (
    ARXIV_API_TERMS_URL, LIVE_ACKNOWLEDGEMENT, MAX_QUOTED_ABSTRACT_CHARS,
    METADATA_LICENCE, MIN_REQUEST_INTERVAL_MILLISECONDS, TRANCHE_MAX_RECORDS,
)
from .errors import (
    CorpusError, DocumentRightsAbsentError, TransportCallForbiddenError,
)
from .ingestion import ingest_from_store
from .pacing import (
    ManualClock, RequestPacer, SleeperThatAdvances, SleeperThatDoesNotSleep,
)
from .ports import MetadataResponse
from .projection import build_projection, verify_projection
from .records import build_record, source_id_for, verify_record
from .replay import ForbiddingMetadataTransport, replay_tranche
from .report import STATUS_REPLAYED, build_report, verify_report
from .rights import Phase4CorpusRightsWriter, assert_non_disclosing
from .serialization import canonical_bytes, sealed, sha256_bytes
from .sourcesweep import assert_acquisition_path_clean, sweep_source
from .store import (
    build_manifest, load_manifest, response_path, verify_manifest_against_plan,
    write_manifest, write_response,
)
from .tranche import (
    assert_metadata_target, planned_request_urls, request_budget, request_url,
    validate_plan,
)

RECORDED_AT = "2026-08-22T12:00:00Z"
_TERMS_EPOCH = int(
    datetime(2026, 8, 22, tzinfo=timezone.utc).timestamp()
)
OBSERVED_AT_EPOCH = _TERMS_EPOCH + 3_600


# --------------------------------------------------------------------------
# In-module fixtures. Project-authored, structurally impossible identifiers
# (YYMM 9901 predates the 0704 scheme), invented authors, no real arXiv data.
# --------------------------------------------------------------------------

_PROBE_ENTRIES = (
    (
        "9901.10001", "math.CO", ("math.CO",),
        "A probe fixture title",
        "A probe fixture abstract, project authored, asserting nothing.",
        ("A. Probe",),
    ),
    (
        "9901.10002", "math.CO", ("math.CO",),
        "A second probe fixture title",
        "A second probe fixture abstract, project authored.",
        ("B. Probe", "C. Probe"),
    ),
)


def probe_plan(**overrides: Any) -> dict[str, Any]:
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "tranche_id": "tranche.probe-project-authored-v1",
        "provider": "arxiv",
        "categories": ["math.CO"],
        "submitted_from": "202601010000",
        "submitted_until": "202602010000",
        "max_records": 2,
        "page_size": 2,
        "rights_declaration": {
            "actor_id": "human.probe-operator",
            "licence_basis": METADATA_LICENCE,
            "terms_url": ARXIV_API_TERMS_URL,
            "terms_reviewed_at": "2026-08-22",
            "valid_from": "2026-08-22T00:00:00Z",
            "valid_until": None,
            "evidence_refs": ["evidence.adr-0067-licence-diligence"],
        },
        "content_hash": None,
    }
    plan.update(overrides)
    return sealed(plan)


def probe_activation(*, status: str = STATUS_ACTIVE) -> dict[str, Any]:
    record = dict(_PINNED)
    record["status"] = status
    record["authorized_by"] = {
        "actor_id": "human.probe-operator",
        "actor_kind": "human",
        "authority": "human_final",
    }
    return validate_activation(sealed(record))


def probe_feed_bytes(entries: Sequence[Any] = _PROBE_ENTRIES) -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:arxiv="http://arxiv.org/schemas/atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">',
        "  <title>ADR-0067 probe fixture</title>",
        f"  <opensearch:totalResults>{len(entries)}</opensearch:totalResults>",
    ]
    for identifier, primary, categories, title, abstract, authors in entries:
        parts.append("  <entry>")
        parts.append(f"    <id>http://arxiv.org/abs/{identifier}</id>")
        parts.append("    <updated>2026-01-15T00:00:00Z</updated>")
        parts.append("    <published>2026-01-14T00:00:00Z</published>")
        parts.append(f"    <title>{title}</title>")
        parts.append(f"    <summary>{abstract}</summary>")
        for name in authors:
            parts.append(f"    <author><name>{name}</name></author>")
        parts.append(
            f'    <link href="http://arxiv.org/abs/{identifier}" rel="alternate"/>'
        )
        parts.append(
            '    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" '
            f'term="{primary}"/>'
        )
        for term in categories:
            parts.append(f'    <category term="{term}"/>')
        parts.append("  </entry>")
    parts.append("</feed>")
    return ("\n".join(parts) + "\n").encode("utf-8")


def build_probe_store(root: Path, plan: Mapping[str, Any]) -> str:
    """Write the probe store: one page, canonical manifest, no network."""

    pages = []
    for index, url in enumerate(planned_request_urls(plan)):
        body = probe_feed_bytes()
        digest = write_response(root, body)
        pages.append({
            "page_index": index, "request_url": url,
            "response_sha256": digest, "response_bytes": len(body),
        })
    return write_manifest(root, build_manifest(
        tranche_id=str(plan["tranche_id"]),
        plan_hash=str(plan["content_hash"]),
        pages=pages,
    ))


class _ProbeRightsWriter:
    """NOT a rights authority.

    A probe fixture, constructed only inside this module, that mimics the
    :class:`math_research.corpus.ports.RightsWriter` shape closely enough to
    order the ingestion path.  Production callers inject
    :class:`Phase4CorpusRightsWriter` onto a real Phase 4A workspace; probes that
    are not ABOUT rights use this so they neither create nor depend on a Phase 4A
    ledger.
    """

    def __init__(self) -> None:
        self.written: list[str] = []

    def write_tranche_rights(
        self, source_ids: Sequence[str], *, recorded_at: str,
    ) -> dict[str, tuple[str, ...]]:
        self.written = sorted(source_ids)
        return {source_id: self._ids(source_id) for source_id in self.written}

    @staticmethod
    def _ids(source_id: str) -> tuple[str, ...]:
        digest = sha256_bytes(source_id.encode("utf-8")).removeprefix("sha256:")
        return tuple(sorted(f"rights.probe-{use}-{digest[:16]}" for use in ("a", "p", "s")))

    def require_document_rights(self, source_id: str, *, at: str) -> tuple[str, ...]:
        if source_id not in self.written:
            raise DocumentRightsAbsentError(f"no probe rights for {source_id}")
        return self._ids(source_id)

    def shard_names_written(self) -> tuple[str, ...]:
        return ("shard-probe",)

    def rights_record_count(self) -> int:
        return len(self.written) * 3

    def applicability_source_ids(self) -> tuple[str, ...]:
        return ()


class _RightsDenyingWriter(_ProbeRightsWriter):
    """Writes nothing, so every document lacks a per-document decision."""

    def write_tranche_rights(
        self, source_ids: Sequence[str], *, recorded_at: str,
    ) -> dict[str, tuple[str, ...]]:
        return {}


class _ScriptedTransport:
    """Returns pre-built bytes. Counts attempts. Reaches no network."""

    def __init__(self, bodies: Sequence[bytes], *, status: int = 200) -> None:
        self.bodies = list(bodies)
        self.status = status
        self.attempts = 0

    def fetch(self, request: Any) -> MetadataResponse:
        assert_metadata_target(request.url)
        self.attempts += 1
        body = self.bodies[min(self.attempts - 1, len(self.bodies) - 1)]
        return MetadataResponse(
            status=self.status, media_type="application/atom+xml", body=body,
        )


class _DriftingTransport:
    """A deliberately wrong subject: its attempt counter moves on its own.

    The zero-transport replay property is positive, so its mutated leg fires the
    instrument at this object rather than mutating an input.
    """

    def __init__(self) -> None:
        self._attempts = 0

    @property
    def attempts(self) -> int:
        self._attempts += 1
        return self._attempts


# --------------------------------------------------------------------------
# Probe legs
# --------------------------------------------------------------------------

def _prepared(workspace: Path) -> tuple[dict[str, Any], Path, str]:
    plan = probe_plan()
    store = workspace.joinpath("store")
    manifest_hash = build_probe_store(store, plan)
    return plan, store, manifest_hash


def _ingest(store: Path, plan: Mapping[str, Any], writer: Any) -> dict[str, Any]:
    return ingest_from_store(
        store, plan, rights_writer=writer, recorded_at=RECORDED_AT,
    )


def _full_text_baseline(workspace: Path) -> None:
    assert_metadata_target(request_url(probe_plan(), 0))


def _full_text_mutated(workspace: Path) -> None:
    assert_metadata_target("https://export.arxiv.org/pdf/9901.10001v1")


def _sweep_baseline(workspace: Path) -> None:
    assert_acquisition_path_clean()


def _sweep_mutated(workspace: Path) -> None:
    from .errors import FullTextTokenOnAcquisitionPathError

    impure = 'URL = "https://export.arxiv.org/pdf/9901.10001v1"\n'
    findings = sweep_source(impure, module="deliberately-impure.py")
    if findings:
        raise FullTextTokenOnAcquisitionPathError(
            "; ".join(item.render() for item in findings)
        )


def _origin_baseline(workspace: Path) -> None:
    assert_metadata_target(request_url(probe_plan(), 0))


def _origin_mutated(workspace: Path) -> None:
    assert_metadata_target("https://arxiv.example.org/api/query?search_query=x")


def _pacer(sleeping: bool) -> RequestPacer:
    clock = ManualClock(0)
    sleeper = SleeperThatAdvances(clock) if sleeping else SleeperThatDoesNotSleep()
    return RequestPacer(clock, sleeper, max_requests=4)


def _rate_baseline(workspace: Path) -> None:
    pacer = _pacer(sleeping=True)
    for _ in range(3):
        with pacer.request():
            pass
    if pacer.observation()["min_observed_interval_milliseconds"] < MIN_REQUEST_INTERVAL_MILLISECONDS:
        raise AssertionError("an honest sleeper produced a too-short interval")


def _rate_mutated(workspace: Path) -> None:
    pacer = _pacer(sleeping=False)
    for _ in range(3):
        with pacer.request():
            pass


def _interval_pinned_baseline(workspace: Path) -> None:
    RequestPacer(ManualClock(0), SleeperThatAdvances(ManualClock(0)),
                 min_interval_milliseconds=MIN_REQUEST_INTERVAL_MILLISECONDS)


def _interval_pinned_mutated(workspace: Path) -> None:
    RequestPacer(ManualClock(0), SleeperThatAdvances(ManualClock(0)),
                 min_interval_milliseconds=MIN_REQUEST_INTERVAL_MILLISECONDS - 1)


def _connection_baseline(workspace: Path) -> None:
    pacer = _pacer(sleeping=True)
    with pacer.request():
        pass
    with pacer.request():
        pass


def _connection_mutated(workspace: Path) -> None:
    pacer = _pacer(sleeping=True)
    with pacer.request():
        pacer.start()


def _tranche_baseline(workspace: Path) -> None:
    validate_plan(probe_plan(max_records=TRANCHE_MAX_RECORDS, page_size=100))


def _tranche_mutated(workspace: Path) -> None:
    validate_plan(probe_plan(max_records=TRANCHE_MAX_RECORDS + 1, page_size=100))


def _shard_baseline(workspace: Path) -> None:
    from .rights import shard_plan

    shard_plan([f"arxiv.9901.{index:05d}" for index in range(TRANCHE_MAX_RECORDS)])


def _shard_mutated(workspace: Path) -> None:
    from .rights import shard_plan

    shard_plan([f"arxiv.9901.{index:05d}" for index in range(TRANCHE_MAX_RECORDS + 1)])


def _budget_baseline(workspace: Path) -> None:
    plan = probe_plan()
    request_url(plan, request_budget(plan) - 1)


def _budget_mutated(workspace: Path) -> None:
    plan = probe_plan()
    request_url(plan, request_budget(plan))


def _acquire(workspace: Path, **overrides: Any) -> dict[str, Any]:
    plan = probe_plan()
    arguments: dict[str, Any] = {
        "activation": probe_activation(),
        "plan": plan,
        "store_root": workspace.joinpath("acquired"),
        "transport": _ScriptedTransport([probe_feed_bytes()]),
        "pacer": _pacer(sleeping=True),
        "acknowledgement": LIVE_ACKNOWLEDGEMENT,
        "confirmed_plan_hash": plan["content_hash"],
        "observed_at_epoch": OBSERVED_AT_EPOCH,
        "operator_id": "human.probe-operator",
    }
    arguments.update(overrides)
    activation = arguments.pop("activation")
    plan_argument = arguments.pop("plan")
    result = acquire_tranche(activation, plan_argument, **arguments)
    if result["status"] != "acquired":
        raise AssertionError(f"probe acquisition did not succeed: {result['failures']}")
    return result


def _acknowledgement_baseline(workspace: Path) -> None:
    _acquire(workspace)


def _acknowledgement_mutated(workspace: Path) -> None:
    _acquire(workspace, acknowledgement="I_ACKNOWLEDGE_SOMETHING_ELSE")


def _activation_baseline(workspace: Path) -> None:
    _acquire(workspace)


def _activation_mutated(workspace: Path) -> None:
    _acquire(workspace, activation=probe_activation(status=STATUS_PENDING))


def _plan_hash_baseline(workspace: Path) -> None:
    _acquire(workspace)


def _plan_hash_mutated(workspace: Path) -> None:
    _acquire(workspace, confirmed_plan_hash="sha256:" + "0" * 64)


def _dry_run_makes_no_request(workspace: Path) -> None:
    result = dry_run(probe_activation(status=STATUS_PENDING), probe_plan(),
                     observed_at_epoch=OBSERVED_AT_EPOCH)
    if result["network_requests"] != 0 or result["requests_made"] != 0:
        raise AssertionError("a dry run recorded a request")


def _category_baseline(workspace: Path) -> None:
    validate_plan(probe_plan())


def _category_mutated(workspace: Path) -> None:
    validate_plan(probe_plan(categories=["cs.DM"]))


def _replay_zero_network_baseline(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    transport = ForbiddingMetadataTransport()
    result = replay_tranche(
        store, plan, rights_writer=_ProbeRightsWriter(), recorded_at=RECORDED_AT,
        transport=transport,
    )
    if transport.attempts != 0 or result["network_requests"] != 0:
        raise AssertionError("a replay reached a transport")


def _replay_zero_network_mutated(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    replay_tranche(
        store, plan, rights_writer=_ProbeRightsWriter(), recorded_at=RECORDED_AT,
        transport=_DriftingTransport(),
    )


def _missing_bytes_baseline(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    replay_tranche(
        store, plan, rights_writer=_ProbeRightsWriter(), recorded_at=RECORDED_AT,
        transport=ForbiddingMetadataTransport(),
    )


def _missing_bytes_mutated(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    manifest = load_manifest(store)
    response_path(store, manifest["pages"][0]["response_sha256"]).unlink()
    transport = ForbiddingMetadataTransport()
    try:
        replay_tranche(
            store, plan, rights_writer=_ProbeRightsWriter(),
            recorded_at=RECORDED_AT, transport=transport,
        )
    finally:
        if transport.attempts != 0:
            raise AssertionError("a replay tried to re-fetch absent bytes")


def _tamper_baseline(workspace: Path) -> None:
    _missing_bytes_baseline(workspace)


def _tamper_mutated(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    manifest = load_manifest(store)
    path = response_path(store, manifest["pages"][0]["response_sha256"])
    path.write_bytes(path.read_bytes() + b"<!-- tampered -->")
    replay_tranche(
        store, plan, rights_writer=_ProbeRightsWriter(), recorded_at=RECORDED_AT,
        transport=ForbiddingMetadataTransport(),
    )


def _unplanned_url_baseline(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    verify_manifest_against_plan(load_manifest(store), plan)


def _unplanned_url_mutated(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    manifest = load_manifest(store)
    pages = [dict(page) for page in manifest["pages"]]
    pages[0]["request_url"] = pages[0]["request_url"] + "&followed=1"
    replacement = build_manifest(
        tranche_id=str(manifest["tranche_id"]),
        plan_hash=str(manifest["plan_hash"]), pages=pages,
    )
    verify_manifest_against_plan(replacement, plan)


def _feed_link_baseline(workspace: Path) -> None:
    feed = parse_feed(probe_feed_bytes())
    for entry in feed["entries"]:
        assert_no_foreign_urls(entry)


def _feed_link_mutated(workspace: Path) -> None:
    feed = parse_feed(probe_feed_bytes())
    entry = dict(feed["entries"][0])
    entry["title"] = "see http://arxiv.org/abs/9901.99999 for more"
    assert_no_foreign_urls(entry)


def _markup_baseline(workspace: Path) -> None:
    assert_markup_restricted(probe_feed_bytes())


def _markup_mutated(workspace: Path) -> None:
    body = probe_feed_bytes()
    assert_markup_restricted(
        body.replace(b"<feed", b'<!DOCTYPE feed [<!ENTITY x "y">]>\n<feed', 1)
    )


def _rights_present_baseline(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    writer = Phase4CorpusRightsWriter(workspace.joinpath("rights"), plan["rights_declaration"])
    result = _ingest(store, plan, writer)
    if result["record_count"] != len(_PROBE_ENTRIES) or result["rights_records_written"] != 3 * len(_PROBE_ENTRIES):
        raise AssertionError(f"the real Phase 4A writer did not record rights: {result['rights_records_written']}")


def _rights_absent_mutated(workspace: Path) -> None:
    plan, store, _ = _prepared(workspace)
    _ingest(store, plan, _RightsDenyingWriter())


def _processor_null_baseline(workspace: Path) -> None:
    _append_parsing_rights(workspace, processor=None)


def _processor_null_mutated(workspace: Path) -> None:
    _append_parsing_rights(workspace, processor=Processor(
        processor_id="processor.openai.embeddings.v1", provider="openai",
        model_identifier="text-embedding-probe", disclosure_kind="text_leaves_process",
    ))


def _append_parsing_rights(workspace: Path, *, processor: Any) -> None:
    root = workspace.joinpath("phase4a")
    root.mkdir(parents=True, exist_ok=True)
    with Phase4Workspace(root) as ledger:
        service = Phase4Service(ledger)
        service.initialize_policy(actor_id="human.probe-operator", recorded_at=RECORDED_AT)
        service.append_rights(
            source_id="arxiv.9901.10001", intended_use=RightsUse.PARSING,
            value=RightsValue.ALLOWED, reason_code=RightsReason.PERMITTED,
            reason_detail="ADR-0067 probe: metadata parsing under CC0",
            evidence_refs=("evidence.adr-0067-licence-diligence",),
            actor_id="human.probe-operator", valid_from="2026-08-22T00:00:00Z",
            valid_until=None, recorded_at=RECORDED_AT,
            lifecycle_id="lifecycle.arxiv.9901.10001", processor=processor,
        )


def _disclosing_use_baseline(workspace: Path) -> None:
    assert_non_disclosing(RightsUse.PARSING)


def _disclosing_use_mutated(workspace: Path) -> None:
    assert_non_disclosing(RightsUse.EMBEDDING)


def _probe_record() -> dict[str, Any]:
    entry = parse_feed(probe_feed_bytes())["entries"][0]
    return build_record(
        entry, tranche_id="tranche.probe-project-authored-v1",
        plan_hash="sha256:" + "1" * 64,
        response_sha256="sha256:" + "2" * 64,
        rights_decision_ids=_ProbeRightsWriter._ids(source_id_for(entry["arxiv_id"])),
    )


def _record_baseline(workspace: Path) -> None:
    verify_record(_probe_record())


def _record_applicability_mutated(workspace: Path) -> None:
    record = _probe_record()
    record["trust_effects"] = {**record["trust_effects"], "applicability": "applicable"}
    verify_record(record)


def _record_warrant_mutated(workspace: Path) -> None:
    record = _probe_record()
    record["trust_effects"] = {
        **record["trust_effects"], "epistemic_warrant_created": True,
    }
    verify_record(record)


def _record_retrieval_mutated(workspace: Path) -> None:
    record = _probe_record()
    record["retrieval_indexed"] = True
    verify_record(record)


def _projection_baseline(workspace: Path) -> None:
    records = [_probe_record()]
    verify_projection(build_projection(records), records=records)


def _projection_link_mutated(workspace: Path) -> None:
    records = [_probe_record()]
    projection = build_projection(records)
    entries = [dict(entry) for entry in projection["entries"]]
    entries[0].pop("abstract_url")
    entries[0]["abstract_url"] = None
    verify_projection({**projection, "entries": entries})


def _projection_quotation_mutated(workspace: Path) -> None:
    records = [_probe_record()]
    projection = build_projection(records)
    entries = [dict(entry) for entry in projection["entries"]]
    entries[0]["abstract_quotation"] = "x" * (MAX_QUOTED_ABSTRACT_CHARS + 1)
    verify_projection({**projection, "entries": entries})


def _probe_report(workspace: Path, **overrides: Any) -> dict[str, Any]:
    plan, store, manifest_hash = _prepared(workspace)
    ingestion = _ingest(store, plan, _ProbeRightsWriter())
    report = build_report(
        status=STATUS_REPLAYED, activation=probe_activation(), plan=plan,
        ingestion=ingestion, network_requests=0, transport_calls=0,
        manifest_hash=manifest_hash,
    )
    report.update(overrides)
    return report


def _report_baseline(workspace: Path) -> None:
    verify_report(_probe_report(workspace))


def _report_retrieval_mutated(workspace: Path) -> None:
    report = _probe_report(workspace)
    report["retrieval_scope"] = {
        **report["retrieval_scope"], "phase4c_reads_this_corpus": True,
    }
    verify_report(report)


def _report_applicability_mutated(workspace: Path) -> None:
    report = _probe_report(workspace)
    report["records_with_applicability_record"] = report["record_count"]
    verify_report(report)


@dataclass(frozen=True, slots=True, kw_only=True)
class Probe:
    probe_id: str
    expected_code: str
    mutation_target: str
    detail: str
    baseline: Callable[[Path], None]
    mutated: Callable[[Path], None]


PROBES: tuple[Probe, ...] = (
    Probe(
        probe_id="pr.corpus-full-text-fetch-impossible",
        expected_code="full_text_url_forbidden",
        mutation_target="input",
        detail="an e-print request target is refused at the single URL choke point",
        baseline=_full_text_baseline, mutated=_full_text_mutated,
    ),
    Probe(
        probe_id="pr.corpus-full-text-token-absent-from-acquisition-path",
        expected_code="full_text_token_on_acquisition_path",
        mutation_target="instrument",
        detail="no acquisition-path module names an e-print path in a live literal",
        baseline=_sweep_baseline, mutated=_sweep_mutated,
    ),
    Probe(
        probe_id="pr.corpus-single-origin-enforced",
        expected_code="origin_not_authorized",
        mutation_target="input",
        detail="a request to any host other than the arXiv API is refused",
        baseline=_origin_baseline, mutated=_origin_mutated,
    ),
    Probe(
        probe_id="pr.corpus-rate-limit-enforced",
        expected_code="arxiv_rate_limit_violated",
        mutation_target="input",
        detail="a sleeper that does not advance the clock cannot leak a request",
        baseline=_rate_baseline, mutated=_rate_mutated,
    ),
    Probe(
        probe_id="pr.corpus-rate-limit-not-caller-widenable",
        expected_code="arxiv_rate_limit_violated",
        mutation_target="input",
        detail="a caller asking for a shorter interval than the terms allow is refused",
        baseline=_interval_pinned_baseline, mutated=_interval_pinned_mutated,
    ),
    Probe(
        probe_id="pr.corpus-single-connection-enforced",
        expected_code="arxiv_concurrent_request_forbidden",
        mutation_target="input",
        detail="a second overlapping request is refused",
        baseline=_connection_baseline, mutated=_connection_mutated,
    ),
    Probe(
        probe_id="pr.corpus-tranche-bound-enforced",
        expected_code="tranche_record_bound_exceeded",
        mutation_target="input",
        detail="a plan above the pinned first-tranche size is refused",
        baseline=_tranche_baseline, mutated=_tranche_mutated,
    ),
    Probe(
        probe_id="pr.corpus-rights-shard-bound-enforced",
        expected_code="corpus_rights_shard_bound_exceeded",
        mutation_target="input",
        detail="a tranche needing more rights shards than are pinned is refused",
        baseline=_shard_baseline, mutated=_shard_mutated,
    ),
    Probe(
        probe_id="pr.corpus-request-budget-derived",
        expected_code="corpus_request_budget_exceeded",
        mutation_target="input",
        detail="a page beyond the plan's derived request budget has no URL",
        baseline=_budget_baseline, mutated=_budget_mutated,
    ),
    Probe(
        probe_id="pr.corpus-live-requires-acknowledgement",
        expected_code="corpus_acknowledgement_required",
        mutation_target="input",
        detail="live acquisition without the exact acknowledgement is refused",
        baseline=_acknowledgement_baseline, mutated=_acknowledgement_mutated,
    ),
    Probe(
        probe_id="pr.corpus-live-requires-active-activation",
        expected_code="corpus_activation_not_active",
        mutation_target="input",
        detail="live acquisition against a pending activation record is refused",
        baseline=_activation_baseline, mutated=_activation_mutated,
    ),
    Probe(
        probe_id="pr.corpus-live-requires-confirmed-plan-hash",
        expected_code="corpus_plan_hash_mismatch",
        mutation_target="input",
        detail="live acquisition without the exact tranche plan hash is refused",
        baseline=_plan_hash_baseline, mutated=_plan_hash_mutated,
    ),
    Probe(
        probe_id="pr.corpus-non-mathematics-category-refused",
        expected_code="corpus_category_not_mathematics",
        mutation_target="input",
        detail="a tranche outside the arXiv mathematics categories is refused",
        baseline=_category_baseline, mutated=_category_mutated,
    ),
    Probe(
        probe_id="pr.corpus-replay-makes-zero-network-requests",
        expected_code="transport_call_during_replay",
        mutation_target="instrument",
        detail="replay reproduces every record with a forbidding transport installed",
        baseline=_replay_zero_network_baseline, mutated=_replay_zero_network_mutated,
    ),
    Probe(
        probe_id="pr.corpus-missing-stored-bytes-fail-closed",
        expected_code="stored_response_missing",
        mutation_target="input",
        detail="absent stored bytes refuse and never re-fetch",
        baseline=_missing_bytes_baseline, mutated=_missing_bytes_mutated,
    ),
    Probe(
        probe_id="pr.corpus-stored-bytes-tamper-detected",
        expected_code="stored_response_hash_mismatch",
        mutation_target="input",
        detail="altered stored bytes refuse rather than replay",
        baseline=_tamper_baseline, mutated=_tamper_mutated,
    ),
    Probe(
        probe_id="pr.corpus-unplanned-request-url-refused",
        expected_code="unplanned_request_url",
        mutation_target="input",
        detail="a stored request the plan does not derive is result following",
        baseline=_unplanned_url_baseline, mutated=_unplanned_url_mutated,
    ),
    Probe(
        probe_id="pr.corpus-feed-links-not-followed",
        expected_code="feed_link_surfaced",
        mutation_target="instrument",
        detail="no URL from the response reaches a parsed entry",
        baseline=_feed_link_baseline, mutated=_feed_link_mutated,
    ),
    Probe(
        probe_id="pr.corpus-xml-declaration-refused",
        expected_code="xml_declaration_forbidden",
        mutation_target="input",
        detail="a DOCTYPE or entity declaration never reaches the XML parser",
        baseline=_markup_baseline, mutated=_markup_mutated,
    ),
    Probe(
        probe_id="pr.corpus-document-rights-absent-refuses-processing",
        expected_code="corpus_document_rights_absent",
        mutation_target="input",
        detail="a document without its own Phase 4A decisions yields no record",
        baseline=_rights_present_baseline, mutated=_rights_absent_mutated,
    ),
    Probe(
        probe_id="pr.corpus-rights-processor-must-be-null",
        expected_code="non_disclosing_use_forbids_processor",
        mutation_target="input",
        detail="ADR-0064 refuses a named processor on a non-disclosing use",
        baseline=_processor_null_baseline, mutated=_processor_null_mutated,
    ),
    Probe(
        probe_id="pr.corpus-embedding-use-not-authorized",
        expected_code="corpus_disclosing_rights_use_forbidden",
        mutation_target="input",
        detail="this slice cannot record an embedding or model-context use",
        baseline=_disclosing_use_baseline, mutated=_disclosing_use_mutated,
    ),
    Probe(
        probe_id="pr.corpus-record-cannot-claim-applicability",
        expected_code="corpus_applicability_promotion_forbidden",
        mutation_target="input",
        detail="a record claiming applicability or a premise is refused",
        baseline=_record_baseline, mutated=_record_applicability_mutated,
    ),
    Probe(
        probe_id="pr.corpus-record-cannot-claim-warrant",
        expected_code="corpus_warrant_promotion_forbidden",
        mutation_target="input",
        detail="a record claiming an epistemic warrant is refused",
        baseline=_record_baseline, mutated=_record_warrant_mutated,
    ),
    Probe(
        probe_id="pr.corpus-record-cannot-claim-retrieval",
        expected_code="retrieval_scope_claim_forbidden",
        mutation_target="input",
        detail="a record claiming it is indexed for retrieval is refused",
        baseline=_record_baseline, mutated=_record_retrieval_mutated,
    ),
    Probe(
        probe_id="pr.corpus-projection-requires-abstract-link",
        expected_code="abstract_link_missing",
        mutation_target="input",
        detail="a projection omitting the arXiv abstract page link is refused",
        baseline=_projection_baseline, mutated=_projection_link_mutated,
    ),
    Probe(
        probe_id="pr.corpus-projection-refuses-excess-quotation",
        expected_code="abstract_reproduction_exceeds_fair_quotation",
        mutation_target="input",
        detail="a projection reproducing more than the pinned quotation is refused",
        baseline=_projection_baseline, mutated=_projection_quotation_mutated,
    ),
    Probe(
        probe_id="pr.corpus-report-cannot-claim-retrieval",
        expected_code="retrieval_scope_claim_forbidden",
        mutation_target="input",
        detail="a report claiming Phase 4C reads this corpus is refused",
        baseline=_report_baseline, mutated=_report_retrieval_mutated,
    ),
    Probe(
        probe_id="pr.corpus-applicability-count-must-be-evidenced",
        expected_code="applicability_count_inconsistent",
        mutation_target="input",
        detail="an applicability count without durable evidence is refused",
        baseline=_report_baseline, mutated=_report_applicability_mutated,
    ),
)


def _extract_code(error: BaseException) -> str:
    if isinstance(error, CorpusError):
        return error.code
    head = str(error).split(":", 1)[0].strip()
    if head and head.replace("_", "").isalnum() and head == head.casefold():
        return head
    return type(error).__name__


def _observe(leg: Callable[[Path], None], workspace: Path) -> str:
    try:
        leg(workspace)
    except BaseException as error:  # noqa: BLE001 - the code is the observation
        return _extract_code(error)
    return ""


def _run_leg(leg: Callable[[Path], None]) -> str:
    workspace = Path(tempfile.mkdtemp(prefix="adaivy-corpus-probe."))
    try:
        return _observe(leg, workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_probes() -> dict[str, Any]:
    """Run every probe in its own temporary workspace. Deterministic order."""

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for probe in PROBES:
        if probe.probe_id in seen:
            raise CorpusError(f"duplicate probe id {probe.probe_id}",
                              code="probe_id_duplicated")
        seen.add(probe.probe_id)
        baseline_code = _run_leg(probe.baseline)
        mutated_code = _run_leg(probe.mutated)
        flipped = mutated_code == probe.expected_code and baseline_code != probe.expected_code
        results.append({
            "probe_id": probe.probe_id,
            "expected_code": probe.expected_code,
            "mutation_target": probe.mutation_target,
            "detail": probe.detail,
            "baseline_observed": baseline_code,
            "mutated_observed": mutated_code,
            "flipped": flipped,
        })
    results.sort(key=lambda item: item["probe_id"])
    return {
        "schema_version": PROBE_REPORT_SCHEMA_VERSION,
        "probes_total": len(results),
        "probes_flipped": sum(1 for item in results if item["flipped"]),
        "unflipped_probe_ids": sorted(
            item["probe_id"] for item in results if not item["flipped"]
        ),
        "acquisition_path_modules": list(
            __import__(
                "math_research.corpus.sourcesweep", fromlist=["ACQUISITION_PATH_MODULES"],
            ).ACQUISITION_PATH_MODULES
        ),
        "probes": results,
        "creates_epistemic_warrant": False,
        "asserts_source_applicability": False,
        "retrieval_corpus_wired": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
    }


__all__ = ["PROBES", "Probe", "run_probes"]
