"""Strict, non-reconstructive replay artifacts for Phase 4B candidates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .parsing import PARSER_BOUNDS, PROFILES, REQUEST_SCHEMA, RESULT_SCHEMA, TRUST_EFFECTS
from .records import RecordType
from .serialization import canonical_bytes, canonical_hash, sha256_bytes, stable_id


ARTIFACT_SCHEMA = "adaivy.phase4b-replay-artifact.v1"
ACQUISITION_TRACE = "acquisition_attempt_trace"
PARSE_PROPOSAL = "parse_proposal"
MAX_ARTIFACTS = 8_192
MAX_ITEMS = 16_384
_HASH = "sha256:"


class ReplayArtifactError(ValueError):
    pass


def _exact(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ReplayArtifactError(f"{label} fields differ")
    return value


def _text(value: object, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ReplayArtifactError(f"{label} is invalid")
    if any(ord(character) < 0x20 for character in value):
        raise ReplayArtifactError(f"{label} contains a control character")
    return value


def _hash(value: object, label: str) -> str:
    text = _text(value, label, 71)
    if len(text) != 71 or not text.startswith(_HASH):
        raise ReplayArtifactError(f"{label} is not sha256")
    try:
        int(text[7:], 16)
    except ValueError as error:
        raise ReplayArtifactError(f"{label} is not sha256") from error
    if text[7:] != text[7:].lower():
        raise ReplayArtifactError(f"{label} is not canonical")
    return text


def _count(value: object, label: str, maximum: int = 67_108_864) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ReplayArtifactError(f"{label} is outside its bound")
    return value


def _list(value: object, label: str, maximum: int = MAX_ITEMS) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) > maximum:
        raise ReplayArtifactError(f"{label} is not a bounded list")
    return value


def acquisition_trace_payload(result: object) -> dict[str, Any]:
    """Capture the adapter's canonical trace; source bodies are not in either envelope."""
    semantic_bytes = getattr(result, "semantic_bytes")
    operational_bytes = getattr(result, "operational_bytes")
    semantic = json.loads(semantic_bytes)
    operational = json.loads(operational_bytes)
    payload = {
        "semantic": semantic,
        "semantic_sha256": "sha256:" + getattr(result, "semantic_hash"),
        "operational": operational,
        "operational_sha256": "sha256:" + getattr(result, "operational_hash"),
    }
    validate_acquisition_trace(payload)
    return payload


def validate_acquisition_trace(value: object) -> Mapping[str, Any]:
    trace = _exact(value, {"semantic", "semantic_sha256", "operational", "operational_sha256"}, "trace")
    semantic = _exact(trace["semantic"], {"schema_version", "run_id", "policy_hash", "results"}, "trace semantic")
    operational = _exact(
        trace["operational"],
        {"schema_version", "semantic_hash", "actor_id", "capability_id", "recorded_at_epoch", "operations"},
        "trace operational",
    )
    if semantic["schema_version"] != "adaivy.phase4b-acquisition-semantic.v1":
        raise ReplayArtifactError("trace semantic schema differs")
    if operational["schema_version"] != "adaivy.phase4b-acquisition-operational.v1":
        raise ReplayArtifactError("trace operational schema differs")
    _text(semantic["run_id"], "run_id", 256)
    _text(operational["actor_id"], "actor_id", 256)
    _text(operational["capability_id"], "capability_id", 256)
    _text(semantic["policy_hash"], "policy_hash", 128)
    _count(operational["recorded_at_epoch"], "recorded_at_epoch", 4_102_444_800)
    results = _list(semantic["results"], "results", 256)
    operations = _list(operational["operations"], "operations", 1_024)
    # Exact adapter envelopes are already canonical and bounded. Reject any key
    # capable of carrying response content and bound every nested scalar.
    allowed_result = {
        "request_id", "outcome", "reason", "status", "redirects", "candidate_id",
        "disposition", "applicability_status", "mathematical_warrant", "graph_admission", "hops",
    }
    allowed_hop = {
        "url", "status", "header_hash", "header_bytes", "content_sha256", "byte_length",
        "rights", "terms_snapshot_id", "terms_content_hash", "robots_snapshot_id", "robots_content_hash",
    }
    hop_base = allowed_hop - {"header_bytes", "content_sha256", "byte_length"}
    allowed_operation = {
        "request_id", "url", "retry", "started_at_milliseconds", "resolved_addresses",
        "connected_peer", "status", "elapsed_milliseconds", "transport_failure", "policy_failure",
    }
    for result in results:
        if not isinstance(result, Mapping) or not set(result) <= allowed_result or not {"request_id", "outcome"} <= set(result):
            raise ReplayArtifactError("trace result fields differ")
        _text(result["request_id"], "request_id", 256)
        _text(result["outcome"], "outcome", 128)
        for name in (
            "reason", "candidate_id", "disposition", "applicability_status",
            "mathematical_warrant", "graph_admission",
        ):
            if name in result:
                _text(result[name], name, 256)
        if "status" in result:
            _count(result["status"], "result status", 599)
        if "redirects" in result:
            for item in _list(result["redirects"], "redirects", 8):
                _text(item, "redirect", 2_048)
        if "hops" in result:
            for hop in _list(result["hops"], "hops", 8):
                if not isinstance(hop, Mapping) or set(hop) not in (allowed_hop, hop_base):
                    raise ReplayArtifactError("trace hop fields differ")
                _text(hop["url"], "hop url", 2_048)
                _count(hop["status"], "hop status", 599)
                if "byte_length" in hop:
                    _count(hop["byte_length"], "hop byte_length", 2_097_152)
                    _hash("sha256:" + str(hop["content_sha256"]), "hop content hash")
                _text(hop["header_hash"], "header hash", 128)
                _count(hop.get("header_bytes", 0), "header bytes", 65_536)
                for name in ("terms_snapshot_id", "robots_snapshot_id"):
                    _text(hop[name], name, 256)
                for name in ("terms_content_hash", "robots_content_hash"):
                    _hash("sha256:" + str(hop[name]), name)
                for item in _list(hop["rights"], "rights", 2):
                    _text(item, "rights decision", 256)
    for operation in operations:
        if not isinstance(operation, Mapping) or not set(operation) <= allowed_operation or not {"request_id", "url"} <= set(operation):
            raise ReplayArtifactError("trace operation fields differ")
        _text(operation["request_id"], "operation request_id", 256)
        _text(operation["url"], "operation url", 2_048)
        if "retry" in operation:
            _count(operation["retry"], "retry", 2)
        for name in ("started_at_milliseconds", "elapsed_milliseconds"):
            if name in operation:
                _count(operation[name], name, 1_800_000)
        if "status" in operation:
            _count(operation["status"], "operation status", 599)
        for name in ("transport_failure", "policy_failure", "connected_peer"):
            if name in operation:
                _text(operation[name], name, 256)
        if "resolved_addresses" in operation:
            for address in _list(operation["resolved_addresses"], "resolved addresses", 16):
                _text(address, "resolved address", 64)
        for forbidden in ("body", "content", "response_bytes", "source_text"):
            if forbidden in operation:
                raise ReplayArtifactError("trace contains response content")
    semantic_hash = _hash(trace["semantic_sha256"], "semantic_sha256")
    operational_hash = _hash(trace["operational_sha256"], "operational_sha256")
    if semantic_hash != sha256_bytes(canonical_bytes(semantic)):
        raise ReplayArtifactError("trace semantic hash differs")
    if operational["semantic_hash"] != semantic_hash[7:]:
        raise ReplayArtifactError("trace linkage differs")
    if operational_hash != sha256_bytes(canonical_bytes(operational)):
        raise ReplayArtifactError("trace operational hash differs")
    return trace


def _anchor(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "end": value["end"], "object_id_hash": sha256_bytes(value["object_id"].encode("utf-8")) if value["object_id"] else None,
        "original_sha256": value["original_sha256"], "page_index": value["page_index"],
        "slice_sha256": value["slice_sha256"], "start": value["start"],
    }


def parse_proposal_payload(result: object) -> dict[str, Any]:
    semantic = getattr(result, "semantic_record")()
    operation = getattr(result, "operation").to_record()
    segments = []
    for item in semantic["segments"]:
        encoded = item["normalized_text"].encode("utf-8")
        segments.append({
            "anchor": _anchor(item["anchor"]), "kind": item["kind"], "load_bearing": item["load_bearing"],
            "normalized_text_byte_length": len(encoded), "normalized_text_sha256": sha256_bytes(encoded),
            "segment_id_hash": sha256_bytes(item["segment_id"].encode("utf-8")),
        })
    references = []
    for item in semantic["references"]:
        encoded = item["target"].encode("utf-8")
        references.append({
            "anchor": _anchor(item["anchor"]), "reference_id_hash": sha256_bytes(item["reference_id"].encode("utf-8")),
            "target_byte_length": len(encoded), "target_sha256": sha256_bytes(encoded),
        })
    payload = {
        "adapter_status": getattr(result, "adapter_status"),
        "bounds": semantic["bounds"],
        "disposition": semantic["disposition"],
        "failure_code": semantic["failure_code"],
        "formula_segment_id_hashes": [sha256_bytes(item.encode("utf-8")) for item in semantic["formula_segment_ids"]],
        "operation": operation,
        "original_lineage": semantic["original_lineage"],
        "parser_identity": semantic["parser_identity"],
        "references": references,
        "request_metadata": {key: value for key, value in semantic["request"].items() if key not in {"original_sha256", "original_byte_length"}},
        "result_schema_version": semantic["schema_version"],
        "result_semantic_sha256": getattr(result, "semantic_sha256"),
        "result_operational_sha256": getattr(result, "operational_sha256"),
        "segments": segments,
        "transformations": [{"byte_length": len(item.encode("utf-8")), "sha256": sha256_bytes(item.encode("utf-8"))} for item in semantic["transformations"]],
        "trust_effects": semantic["trust_effects"],
        "warnings": [{"byte_length": len(item.encode("utf-8")), "sha256": sha256_bytes(item.encode("utf-8"))} for item in semantic["warnings"]],
    }
    validate_parse_proposal(payload)
    return payload


def validate_parse_proposal(value: object) -> Mapping[str, Any]:
    fields = {
        "adapter_status", "bounds", "disposition", "failure_code", "formula_segment_id_hashes", "operation",
        "original_lineage", "parser_identity", "references", "request_metadata", "result_schema_version",
        "result_semantic_sha256", "result_operational_sha256", "segments", "transformations", "trust_effects", "warnings",
    }
    proposal = _exact(value, fields, "parse proposal")
    if proposal["result_schema_version"] != RESULT_SCHEMA:
        raise ReplayArtifactError("parse result schema differs")
    _hash(proposal["result_semantic_sha256"], "result semantic hash")
    _hash(proposal["result_operational_sha256"], "result operational hash")
    adapter_status = _text(proposal["adapter_status"], "adapter status", 256)
    disposition = _text(proposal["disposition"], "disposition", 128)
    if proposal["failure_code"] is not None:
        _text(proposal["failure_code"], "failure code", 256)
    segments = _list(proposal["segments"], "segments", 4_096)
    references = _list(proposal["references"], "references", 2_048)
    failure_code = proposal["failure_code"]
    if disposition == "candidate_proposal":
        if adapter_status != "completed" or failure_code is not None or not segments:
            raise ReplayArtifactError("candidate proposal status differs")
    elif disposition == "quarantined":
        if adapter_status != "rejected" or failure_code is None or segments or references:
            raise ReplayArtifactError("quarantined proposal status differs")
    elif disposition == "failed":
        if adapter_status not in {"failed", "missing_dependency", "not_invoked"} or failure_code is None or segments or references:
            raise ReplayArtifactError("failed proposal status differs")
    else:
        raise ReplayArtifactError("parse disposition differs")
    segment_ids: list[str] = []
    for item in segments:
        segment = _exact(item, {"anchor", "kind", "load_bearing", "normalized_text_byte_length", "normalized_text_sha256", "segment_id_hash"}, "segment")
        segment_ids.append(_hash(segment["segment_id_hash"], "segment id hash"))
        if segment["kind"] not in {"text", "formula"} or not isinstance(segment["load_bearing"], bool):
            raise ReplayArtifactError("segment kind or bearing differs")
        if _count(segment["normalized_text_byte_length"], "segment bytes", 8_388_608) < 1:
            raise ReplayArtifactError("segment text is empty")
        _hash(segment["normalized_text_sha256"], "segment text hash")
        _validate_sanitized_anchor(segment["anchor"])
    if len(set(segment_ids)) != len(segment_ids):
        raise ReplayArtifactError("segment identities duplicate")
    formulas = tuple(_hash(item, "formula id hash") for item in _list(proposal["formula_segment_id_hashes"], "formula ids", 2_048))
    if formulas != tuple(item["segment_id_hash"] for item in segments if item["kind"] == "formula"):
        raise ReplayArtifactError("formula identity projection differs")
    reference_ids: list[str] = []
    for item in references:
        reference = _exact(item, {"anchor", "reference_id_hash", "target_byte_length", "target_sha256"}, "reference")
        reference_ids.append(_hash(reference["reference_id_hash"], "reference id hash"))
        if _count(reference["target_byte_length"], "target bytes", 8_388_608) < 1:
            raise ReplayArtifactError("reference target is empty")
        _hash(reference["target_sha256"], "target hash")
        _validate_sanitized_anchor(reference["anchor"])
    if len(set(reference_ids)) != len(reference_ids):
        raise ReplayArtifactError("reference identities duplicate")
    for item in _list(proposal["warnings"], "warnings", 16_384):
        warning = _exact(item, {"byte_length", "sha256"}, "warning")
        _count(warning["byte_length"], "warning bytes", 8_388_608)
        _hash(warning["sha256"], "warning hash")
    for item in _list(proposal["transformations"], "transformations", 64):
        transformation = _exact(item, {"byte_length", "sha256"}, "transformation")
        _count(transformation["byte_length"], "transformation bytes", 8_388_608)
        _hash(transformation["sha256"], "transformation hash")
    bounds = _exact(proposal["bounds"], {
        "max_anchor_object_id_bytes", "max_anchor_page_index", "max_decoded_output_bytes", "max_expansion_ratio",
        "max_formulas", "max_memory_bytes", "max_nesting_depth", "max_open_files", "max_processes", "max_raw_input_bytes",
        "max_references", "max_segments", "max_temp_bytes", "max_transformations", "max_wall_seconds", "max_warnings",
    }, "bounds")
    if dict(bounds) != PARSER_BOUNDS.to_record():
        raise ReplayArtifactError("parser bounds differ from the closed policy")
    operation = _exact(proposal["operation"], {
        "attempt_ordinal", "duration_ms", "operation_id", "stderr_byte_length", "stderr_sha256",
        "stdout_byte_length", "stdout_sha256", "worker_exit_code",
    }, "operation")
    if _count(operation["attempt_ordinal"], "attempt ordinal", 1_000_000) < 1:
        raise ReplayArtifactError("attempt ordinal begins at one")
    _count(operation["duration_ms"], "duration milliseconds", 1_800_000)
    for name in ("stdout_byte_length", "stderr_byte_length"):
        _count(operation[name], name, 8_388_608)
    if operation["worker_exit_code"] is not None and (
        isinstance(operation["worker_exit_code"], bool)
        or not isinstance(operation["worker_exit_code"], int)
        or not -255 <= operation["worker_exit_code"] <= 255
    ):
        raise ReplayArtifactError("worker exit code differs")
    _hash(operation["stdout_sha256"], "stdout hash")
    _hash(operation["stderr_sha256"], "stderr hash")
    lineage = _exact(proposal["original_lineage"], {"byte_length", "sha256"}, "original lineage")
    if _count(lineage["byte_length"], "original bytes", 2_097_152) < 1:
        raise ReplayArtifactError("original input is empty")
    _hash(lineage["sha256"], "original hash")
    decoded_bytes = sum(item["normalized_text_byte_length"] for item in segments)
    decoded_bytes += sum(item["target_byte_length"] for item in references)
    if (
        decoded_bytes > PARSER_BOUNDS.max_decoded_output_bytes
        or decoded_bytes > lineage["byte_length"] * PARSER_BOUNDS.max_expansion_ratio
    ):
        raise ReplayArtifactError("decoded replay output exceeds parser policy")
    for item in tuple(segments) + tuple(references):
        anchor = item["anchor"]
        if anchor["original_sha256"] != lineage["sha256"] or anchor["end"] > lineage["byte_length"]:
            raise ReplayArtifactError("anchor lineage differs from original input")
    identity = _exact(proposal["parser_identity"], {
        "adapter_implementation_sha256", "adapter_name", "adapter_version", "dependency_environment_sha256",
        "policy_sha256", "profile_name", "profile_sha256", "profile_version",
    }, "parser identity")
    for name in ("adapter_implementation_sha256", "dependency_environment_sha256", "policy_sha256", "profile_sha256"):
        _hash(identity[name], name)
    for name in ("adapter_name", "adapter_version", "profile_name", "profile_version"):
        _text(identity[name], name, 256)
    request = _exact(proposal["request_metadata"], {
        "content_object_id", "media_type", "parser_policy_sha256", "profile_name", "representation_id",
        "request_id", "schema_version", "source_id",
    }, "request metadata")
    for name in ("content_object_id", "representation_id", "request_id", "source_id"):
        _text(request[name], name, 256)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise ReplayArtifactError("parse request schema differs")
    profile = PROFILES.get(str(request["profile_name"]))
    if profile is None or request["media_type"] != profile.media_type:
        raise ReplayArtifactError("request media/profile binding differs")
    if (
        identity["profile_name"] != profile.name
        or identity["profile_version"] != profile.version
        or identity["profile_sha256"] != profile.sha256
        or identity["policy_sha256"] != PARSER_BOUNDS.policy_sha256
        or request["parser_policy_sha256"] != PARSER_BOUNDS.policy_sha256
    ):
        raise ReplayArtifactError("parser identity/profile policy differs")
    trust = _exact(proposal["trust_effects"], {
        "applicability", "graph_admission", "mathematical_warrant", "novelty", "publication", "redistribution", "significance",
    }, "trust effects")
    if dict(trust) != TRUST_EFFECTS:
        raise ReplayArtifactError("parse proposal trust effects differ")
    if disposition == "candidate_proposal" and (
        operation["worker_exit_code"] not in {None, 0}
        or operation["duration_ms"] > PARSER_BOUNDS.max_wall_seconds * 1_000
    ):
        raise ReplayArtifactError("successful parser operation exceeds policy")
    operational_preimage = {
        "adapter_status": proposal["adapter_status"], "operation": dict(operation),
        "semantic_sha256": proposal["result_semantic_sha256"],
    }
    if sha256_bytes(canonical_bytes(operational_preimage)) != proposal["result_operational_sha256"]:
        raise ReplayArtifactError("parse operational identity differs")
    return proposal


def durable_parse_failure_code(disposition: str, failure: str | None) -> str:
    """Project a parser result onto the closed durable failure vocabulary."""
    value = failure or "parser_failed"
    if value.startswith("missing_dependency:"):
        return "missing_dependency"
    if "bound_exceeded" in value:
        return "resource_limit"
    if value in {
        "unsupported_parser_profile", "media_profile_mismatch",
        "acquisition_media_type_mismatch",
    }:
        return "unsupported_media"
    if disposition == "quarantined":
        return "malformed_input"
    return "parser_failed"


def parse_proposal_binding_hash(proposal: Mapping[str, Any]) -> str:
    """Hash the non-reconstructive semantic projection bound to its owner."""
    validate_parse_proposal(proposal)
    semantic = dict(proposal)
    for name in ("adapter_status", "operation", "result_operational_sha256"):
        semantic.pop(name)
    return canonical_hash(semantic)


def validate_artifact_owner(
    artifact: Mapping[str, Any], owner: Mapping[str, Any],
    records_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Cross-bind replay evidence to the exact semantic and operational owner."""
    if artifact["owner_record_id"] != owner["record_id"]:
        raise ReplayArtifactError("replay artifact owner identity differs")
    if artifact["artifact_type"] != PARSE_PROPOSAL:
        return
    proposal = validate_parse_proposal(artifact["payload"])
    payload = owner["payload"]
    record_type = owner["record_type"]
    if record_type == RecordType.PARSE_CANDIDATE.value:
        if proposal["disposition"] != "candidate_proposal":
            raise ReplayArtifactError("parse candidate disposition differs from owner")
        expected_candidate = stable_id("candidate.parse", {
            "result_semantic_sha256": proposal["result_semantic_sha256"],
            "proposal_binding_sha256": parse_proposal_binding_hash(proposal),
        })
        if payload["candidate_id"] != expected_candidate:
            raise ReplayArtifactError("parse semantic identity is detached from owner")
        identity = proposal["parser_identity"]
        if (
            payload["parser_id"] != identity["adapter_name"]
            or payload["parser_version"] != identity["adapter_version"]
            or payload["parser_configuration_hash"] != canonical_hash(identity)
        ):
            raise ReplayArtifactError("parser identity differs from owner")
        if (
            payload["input_byte_length"] != proposal["original_lineage"]["byte_length"]
            or payload["output_byte_length"] != sum(item["normalized_text_byte_length"] for item in proposal["segments"])
                + sum(item["target_byte_length"] for item in proposal["references"])
            or payload["segment_count"] != len(proposal["segments"])
            or payload["formula_count"] != len(proposal["formula_segment_id_hashes"])
            or payload["reference_count"] != len(proposal["references"])
        ):
            raise ReplayArtifactError("parse result counts differ from owner")
        expected_anchors: dict[tuple[int, int], dict[str, Any]] = {}
        for item in tuple(proposal["segments"]) + tuple(proposal["references"]):
            anchor = item["anchor"]
            expected_anchors[(anchor["start"], anchor["end"])] = {
                "start_offset": anchor["start"], "end_offset": anchor["end"],
                "exact_text_hash": anchor["slice_sha256"],
                "page_number": anchor["page_index"] + 1 if anchor["page_index"] is not None else None,
                "object_id_hash": anchor["object_id_hash"],
            }
        if payload["anchors"] != [expected_anchors[key] for key in sorted(expected_anchors)]:
            raise ReplayArtifactError("parse anchors differ from owner")
    elif record_type == RecordType.FAILURE.value and payload["operation"] == "parse":
        if proposal["disposition"] == "candidate_proposal":
            raise ReplayArtifactError("parse failure cannot own a candidate proposal")
        expected_candidate = stable_id("candidate.parse-failure", {
            "result_semantic_sha256": proposal["result_semantic_sha256"],
            "proposal_binding_sha256": parse_proposal_binding_hash(proposal),
        })
        if payload["candidate_id"] != expected_candidate:
            raise ReplayArtifactError("failed parse semantic identity is detached from owner")
        if payload["failure_code"] != durable_parse_failure_code(
            proposal["disposition"], proposal["failure_code"]
        ):
            raise ReplayArtifactError("parse failure code differs from owner")
        if payload["observed_byte_count"] != proposal["original_lineage"]["byte_length"]:
            raise ReplayArtifactError("failed parse input length differs from owner")
    else:
        raise ReplayArtifactError("parse proposal owner type differs")
    if (
        owner["subject_id"] != proposal["request_metadata"]["source_id"]
        or payload["source_id"] != owner["subject_id"]
        or payload.get("artifact_hash", payload.get("input_hash")) != proposal["original_lineage"]["sha256"]
    ):
        raise ReplayArtifactError("parse input lineage differs from owner")
    if records_by_id is not None:
        predecessors = payload.get("predecessor_record_ids", [])
        if len(predecessors) != 1:
            raise ReplayArtifactError("parse replay requires one acquisition predecessor")
        predecessor = records_by_id.get(predecessors[0])
        if predecessor is None or predecessor["record_type"] != RecordType.ACQUISITION_CANDIDATE.value:
            raise ReplayArtifactError("parse replay predecessor differs")
        acquired = predecessor["payload"]
        request = proposal["request_metadata"]
        media_matches = (
            sha256_bytes(request["media_type"].encode("utf-8"))
            == acquired["media_type_hash"]
        )
        declared_mismatch = proposal["failure_code"] in {
            "media_profile_mismatch", "acquisition_media_type_mismatch",
        }
        if (
            predecessor["subject_id"] != owner["subject_id"]
            or request["content_object_id"] != acquired["content_object_id"]
            or proposal["original_lineage"]["sha256"] != acquired["artifact_hash"]
            or (not media_matches and not declared_mismatch)
        ):
            raise ReplayArtifactError("parse replay acquisition binding differs")
    operation = proposal["operation"]
    observed_operational = {
        "attempt_number": operation["attempt_ordinal"],
        "elapsed_milliseconds": operation["duration_ms"],
        "exit_status": operation["worker_exit_code"],
        "stdout_hash": operation["stdout_sha256"],
        "stderr_hash": operation["stderr_sha256"],
        "stdout_bytes": operation["stdout_byte_length"],
        "stderr_bytes": operation["stderr_byte_length"],
    }
    if owner["operational"] != observed_operational:
        raise ReplayArtifactError("parse operational identity differs from owner")


def _validate_sanitized_anchor(value: object) -> None:
    anchor = _exact(value, {"end", "object_id_hash", "original_sha256", "page_index", "slice_sha256", "start"}, "anchor")
    start = _count(anchor["start"], "anchor start", 2_097_152)
    end = _count(anchor["end"], "anchor end", 2_097_152)
    if end <= start:
        raise ReplayArtifactError("anchor is empty")
    _hash(anchor["original_sha256"], "anchor original hash")
    _hash(anchor["slice_sha256"], "anchor slice hash")
    if anchor["object_id_hash"] is not None:
        _hash(anchor["object_id_hash"], "anchor object hash")
    if anchor["page_index"] is not None:
        _count(anchor["page_index"], "anchor page", 1_000_000)


def build_artifact(owner_record_id: str, artifact_type: str, payload: Mapping[str, Any], *, sequence: int) -> dict[str, Any]:
    _text(owner_record_id, "owner record id", 256)
    if artifact_type == ACQUISITION_TRACE:
        validate_acquisition_trace(payload)
    elif artifact_type == PARSE_PROPOSAL:
        validate_parse_proposal(payload)
    else:
        raise ReplayArtifactError("artifact type differs")
    core = {"artifact_type": artifact_type, "owner_record_id": owner_record_id, "payload": dict(payload), "schema_version": ARTIFACT_SCHEMA}
    value = {**core, "artifact_id": stable_id("phase4b-replay-artifact", core), "sequence": sequence}
    value["content_hash"] = canonical_hash(core)
    return value


def validate_artifact(value: object, *, expected_sequence: int | None = None) -> Mapping[str, Any]:
    artifact = _exact(value, {"artifact_id", "artifact_type", "content_hash", "owner_record_id", "payload", "schema_version", "sequence"}, "replay artifact")
    if artifact["schema_version"] != ARTIFACT_SCHEMA:
        raise ReplayArtifactError("artifact schema differs")
    sequence = _count(artifact["sequence"], "artifact sequence", MAX_ARTIFACTS - 1)
    if expected_sequence is not None and sequence != expected_sequence:
        raise ReplayArtifactError("artifact sequence is not contiguous")
    rebuilt = build_artifact(str(artifact["owner_record_id"]), str(artifact["artifact_type"]), artifact["payload"], sequence=sequence)
    if artifact["artifact_id"] != rebuilt["artifact_id"] or artifact["content_hash"] != rebuilt["content_hash"]:
        raise ReplayArtifactError("artifact identity differs")
    return artifact


__all__ = [
    "ACQUISITION_TRACE", "ARTIFACT_SCHEMA", "PARSE_PROPOSAL", "ReplayArtifactError",
    "acquisition_trace_payload", "build_artifact", "durable_parse_failure_code",
    "parse_proposal_binding_hash", "parse_proposal_payload", "validate_artifact",
    "validate_artifact_owner",
]
