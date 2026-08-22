"""The corpus run report, and the two boundaries it is required to state.

ADR-0067: "Every report must separate corpus size from the count of documents
carrying an applicability record, or corpus size reads as knowledge."  And: this
slice builds a corpus, it does not point retrieval at it.

Both are enforced rather than written down.  ``phase4c_fixture_document_count``
is READ from :mod:`math_research.phase4c.bounds` rather than restated, so if
Phase 4C's frozen fixture count ever moves, this report moves with it instead of
quietly disagreeing.  ``records_with_applicability_record`` must equal the length
of ``applicability_evidence``, which is computed from durable Phase 4A
applicability reviews, so the count cannot be inflated to match the record count.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import REPORT_SCHEMA_VERSION
from ..phase4c.bounds import BOUNDS
from .constants import (
    APPLICABILITY_CEILING, CORPUS_SCOPE, HASH_PATTERN, PROVIDER, TRUST_EFFECTS,
)
from .errors import (
    ApplicabilityCountInconsistentError, ApplicabilityPromotionForbiddenError,
    ReportInvalidError, RetrievalScopeClaimForbiddenError,
    WarrantPromotionForbiddenError,
)
from .records import verify_record
from .serialization import operational_hash_of, sealed, semantic_preimage, verify_sealed

STATUS_DRY_RUN = "dry_run"
STATUS_REPLAYED = "replayed"
STATUS_ACQUIRED = "acquired"
STATUS_FAILED = "failed"
STATUS_VALUES = (STATUS_ACQUIRED, STATUS_DRY_RUN, STATUS_FAILED, STATUS_REPLAYED)

REPORT_FIELDS = frozenset({
    "schema_version", "provider", "status", "activation_status", "activation_hash",
    "tranche_id", "plan_hash", "manifest_hash", "record_count",
    "records_with_applicability_record", "applicability_evidence",
    "applicability_ceiling", "rights_shards", "rights_records_written",
    "network_requests", "transport_calls", "scope", "trust_effects",
    "retrieval_scope", "boundaries", "record_ids", "content_hash",
})

RETRIEVAL_SCOPE_STATEMENT = (
    "This corpus is not wired into retrieval. Phase 4C enforces its own frozen "
    "fixture manifest and does not read corpus records; a large corpus is "
    "therefore not evidence of improved retrieval."
)
APPLICABILITY_STATEMENT = (
    "Corpus size is not knowledge. Ingestion scales with compute; applicability "
    "scales with human attention and is the real ceiling, so the count of "
    "records carrying a Phase 4A applicability record is reported separately and "
    "is computed from durable records rather than declared."
)
FULL_TEXT_STATEMENT = (
    "arXiv descriptive metadata and abstracts only. Full text is excluded by the "
    "ADR-0067 licence diligence: e-prints may not be stored or served without "
    "each author's permission, so no code path in this slice can fetch one."
)


def retrieval_scope() -> dict[str, Any]:
    return {
        "corpus_wired_into_retrieval": False,
        "phase4c_reads_this_corpus": False,
        "phase4c_fixture_document_count": int(BOUNDS.document_count),
        "statement": RETRIEVAL_SCOPE_STATEMENT,
    }


def boundaries() -> dict[str, Any]:
    return {
        "applicability": APPLICABILITY_STATEMENT,
        "full_text": FULL_TEXT_STATEMENT,
        "retrieval": RETRIEVAL_SCOPE_STATEMENT,
    }


def build_report(
    *, status: str, activation: Mapping[str, Any], plan: Mapping[str, Any],
    ingestion: Mapping[str, Any] | None, network_requests: int,
    transport_calls: int, manifest_hash: str | None,
    operational: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in STATUS_VALUES:
        raise ReportInvalidError(f"unknown corpus report status {status!r}")
    records = list(ingestion["records"]) if ingestion is not None else []
    evidence = list(ingestion["applicability_evidence"]) if ingestion is not None else []
    semantic = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "provider": PROVIDER,
        "status": status,
        "activation_status": activation["status"],
        "activation_hash": activation["content_hash"],
        "tranche_id": plan["tranche_id"],
        "plan_hash": plan["content_hash"],
        "manifest_hash": manifest_hash,
        "record_count": len(records),
        "records_with_applicability_record": len(evidence),
        "applicability_evidence": sorted(evidence),
        "applicability_ceiling": APPLICABILITY_CEILING,
        "rights_shards": list(ingestion["rights_shards"]) if ingestion else [],
        "rights_records_written": int(ingestion["rights_records_written"]) if ingestion else 0,
        "network_requests": int(network_requests),
        "transport_calls": int(transport_calls),
        "scope": dict(CORPUS_SCOPE),
        "trust_effects": dict(TRUST_EFFECTS),
        "retrieval_scope": retrieval_scope(),
        "boundaries": boundaries(),
        "record_ids": sorted(str(record["record_id"]) for record in records),
        "content_hash": None,
    }
    report = sealed(semantic)
    if operational is not None:
        report["operational"] = dict(operational)
        report["operational_hash"] = operational_hash_of(report)
    return report


def verify_report(
    value: Mapping[str, Any], *, records: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed verification of one corpus report."""

    if not isinstance(value, Mapping):
        raise ReportInvalidError("a corpus report must be an object")
    report = dict(value)
    operational = report.pop("operational", None)
    operational_hash = report.pop("operational_hash", None)
    if (operational is None) != (operational_hash is None):
        raise ReportInvalidError(
            "an operational block and its hash travel together"
        )
    if set(report) != REPORT_FIELDS:
        raise ReportInvalidError(
            "corpus report fields differ: "
            f"missing={sorted(REPORT_FIELDS - set(report))}, "
            f"extra={sorted(set(report) - REPORT_FIELDS)}"
        )
    scope = report["retrieval_scope"]
    if (
        not isinstance(scope, Mapping)
        or scope.get("corpus_wired_into_retrieval") is not False
        or scope.get("phase4c_reads_this_corpus") is not False
        or scope.get("phase4c_fixture_document_count") != int(BOUNDS.document_count)
        or scope.get("statement") != RETRIEVAL_SCOPE_STATEMENT
    ):
        raise RetrievalScopeClaimForbiddenError(
            "a corpus report may not claim retrieval reads this corpus; Phase 4C "
            f"enforces its own frozen {BOUNDS.document_count}-document fixture"
        )
    effects = report["trust_effects"]
    if not isinstance(effects, Mapping) or effects.get("applicability") != TRUST_EFFECTS[
        "applicability"
    ]:
        raise ApplicabilityPromotionForbiddenError(
            "a corpus report may not assess applicability"
        )
    if (
        effects.get("mathematical_warrant") != TRUST_EFFECTS["mathematical_warrant"]
        or effects.get("epistemic_warrant_created") is not False
    ):
        raise WarrantPromotionForbiddenError(
            "a corpus report may not create a mathematical warrant"
        )
    if dict(effects) != TRUST_EFFECTS:
        raise ReportInvalidError("corpus report trust effects differ")
    evidence = report["applicability_evidence"]
    count = report["records_with_applicability_record"]
    total = report["record_count"]
    if (
        not isinstance(evidence, list) or evidence != sorted(set(evidence))
        or isinstance(count, bool) or not isinstance(count, int)
        or isinstance(total, bool) or not isinstance(total, int)
        or count != len(evidence) or count > total or total < 0
    ):
        raise ApplicabilityCountInconsistentError(
            "the applicability count must equal the number of documents with a "
            "durable applicability record and may not exceed the record count; "
            f"got count={count!r}, evidence={len(evidence) if isinstance(evidence, list) else evidence!r}, "
            f"records={total!r}"
        )
    if report["applicability_ceiling"] != APPLICABILITY_CEILING:
        raise ApplicabilityCountInconsistentError(
            "a corpus report must state that applicability is human-only"
        )
    if report["boundaries"] != boundaries():
        raise ReportInvalidError("a corpus report must carry the ADR-0067 boundaries verbatim")
    if report["scope"] != CORPUS_SCOPE:
        raise ReportInvalidError("corpus report scope differs; full text is out of scope")
    if report["schema_version"] != REPORT_SCHEMA_VERSION or report["provider"] != PROVIDER:
        raise ReportInvalidError("corpus report schema or provider differs")
    if report["status"] not in STATUS_VALUES:
        raise ReportInvalidError(f"unknown corpus report status {report['status']!r}")
    for field in ("activation_hash", "plan_hash"):
        if not isinstance(report[field], str) or HASH_PATTERN.fullmatch(report[field]) is None:
            raise ReportInvalidError(f"corpus report {field} differs")
    if report["manifest_hash"] is not None and HASH_PATTERN.fullmatch(
        str(report["manifest_hash"])
    ) is None:
        raise ReportInvalidError("corpus report manifest hash differs")
    identifiers = report["record_ids"]
    if (
        not isinstance(identifiers, list) or identifiers != sorted(set(identifiers))
        or len(identifiers) != total
    ):
        raise ReportInvalidError("corpus report record ids differ from the record count")
    if report["status"] in {STATUS_DRY_RUN, STATUS_REPLAYED} and (
        report["network_requests"] != 0 or report["transport_calls"] != 0
    ):
        raise ReportInvalidError(
            f"a {report['status']} corpus report must record zero network requests"
        )
    if records is not None:
        for record in records:
            verify_record(record)
    verify_sealed(
        semantic_preimage(dict(value)), label="corpus report",
        code=ReportInvalidError.code,
    )
    if operational is not None and operational_hash_of(
        {**dict(value), "operational_hash": None}
    ) != operational_hash:
        raise ReportInvalidError("corpus report operational hash differs")
    return dict(value)


__all__ = [
    "APPLICABILITY_STATEMENT",
    "FULL_TEXT_STATEMENT",
    "REPORT_FIELDS",
    "RETRIEVAL_SCOPE_STATEMENT",
    "STATUS_ACQUIRED",
    "STATUS_DRY_RUN",
    "STATUS_FAILED",
    "STATUS_REPLAYED",
    "STATUS_VALUES",
    "boundaries",
    "build_report",
    "retrieval_scope",
    "verify_report",
]
