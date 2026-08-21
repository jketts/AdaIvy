"""Clean-room replay verification of a Phase 6 release bundle.

ADR-0024 claims the Phase 6 release package binds its artifacts "for restart and
clean-room replay". Restart is real; clean-room replay was not implemented.
``Phase6Workspace.save_verified_export`` checks only that the export envelope is
self-consistent -- its declared ``content_hash`` equals the hash of the envelope
minus that key -- and then stores the blob in a table no integrity check reads.
Re-sealing that one hash is enough to smuggle a payload edit, including flipping
``graph_admitted`` from ``false`` to ``true``, past ingest.

This module is the missing half. It re-derives a release from the bundle alone
and refuses anything it cannot reproduce. It follows the Phase 4B precedent in
``math_research.phase4b.interchange.verify_export_bytes``: non-canonical bytes
are rejected, every record is validated against an expected sequence, derived
values are recomputed rather than read, and envelope hashes are re-derived last.

Three properties are deliberate and load-bearing.

* **Read only.** Nothing here opens a workspace, a database, or a caller path.
  The only filesystem state is a temporary clean room this module creates and
  discards, into which the three inputs are copied before being read back. No
  row is ever added to ``phase6_verified_exports``.
* **Independent restatement.** Producer constants, guards, and derived tables
  are restated here rather than imported from ``phase6.service``, so the check
  is an independent derivation and not a tautology. The acceptance suite pins
  each restatement against the producer, so drift fails loudly.
* **Named gaps, in two kinds.** Some release fields are affirmations no record
  supports. They are returned in ``unverifiable`` (a claim about facts outside
  the system's view) or ``not_derived`` (a constant presented as a measured
  outcome), never silently signed off. A verifier that laundered an assertion
  into a check would be worse than no verifier at all, and one label for both
  kinds would let a reader mistake a constant for a measurement.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..phase5.quantum import DiagonalCase, QuantumInputError, run_case
from ..phase5.serialization import canonical_bytes, canonical_hash, stable_id
from .generality import GeneralitySuiteError, SUITE_SCHEMA_VERSION, run_suite


class Phase6ReplayError(ValueError):
    """A clean-room replay rejection. Raised instead of returning a verdict."""


VERIFIER_SCHEMA_VERSION = "adaivy.phase6-clean-room-replay.v1"

# Bounds. The verifier owns its own limits: it must not inherit a producer bound
# that would let a hostile bundle exhaust memory before the first check runs.
MAX_VERIFY_BYTES = 4_194_304
MAX_PHASE6_RECORDS = 1024
MAX_PHASE5_RECORDS = 4096
MAX_FIXTURE_CASES = 64
MAX_JSON_DEPTH = 32

# Restated producer identities. Every one of these is pinned against the
# producer by tests/test_phase6_clean_room_replay.py.
PHASE6_EXPORT_VERSION = "adaivy.phase6-release.v1"
PHASE6_RECORD_VERSION = "adaivy.phase6-record.v1"
PHASE5_EXPORT_VERSION = "adaivy.phase5-workspace.v1"
PHASE5_RECORD_VERSION = "adaivy.phase5-record.v1"
FIXTURE_VERSION = "adaivy.quantum-diagonal-fixture.v1"
PROTOCOL_VERSION = "adaivy.confirmatory-protocol.v1"
RESULT_VERSION = "adaivy.confirmatory-result.v2"
RELEASE_VERSION = "adaivy.phase6-release-package.v2"
BENCHMARK_ID = "QD-FS-01"
STOPPING_RULE = "one_pass_no_adaptation"
PHASE_NAME = "confirmatory"
GENERALITY_SUITE_ID = "suite.phase6.generality-controls-v1"
GENERALITY_SUITE_HASH = "sha256:e2e4d640ea54b4eafd56908d218e86aa20cfac7830109c1dd3518c964ea168c4"

PHASE6_EXPORT_FIELDS = frozenset(
    {"schema_version", "phase5_export_hash", "records", "content_hash"}
)
PHASE5_EXPORT_FIELDS = frozenset(
    {"schema_version", "records", "material_results", "content_hash"}
)
FIXTURE_FIELDS = frozenset({"schema_version", "benchmark_id", "cases"})
RECORD_FIELDS = frozenset(
    {
        "schema_version", "record_id", "record_type", "subject_id", "sequence",
        "recorded_at", "payload", "content_hash",
    }
)
PROTOCOL_FIELDS = frozenset(
    {
        "schema_version", "protocol_id", "version", "phase", "benchmark_id",
        "phase5_fixture_hash", "heldout_case_ids", "allowed_capabilities", "metrics",
        "success_criteria", "stopping_rule", "baseline", "frozen_at", "frozen_by",
        "generality_suite_id", "generality_suite_hash",
    }
)
ALLOWED_CAPABILITIES = frozenset(
    {
        "execute_exact_diagonal_case", "read_frozen_case_only",
        "write_confirmatory_result",
    }
)
PROTOCOL_PAYLOAD_FIELDS = frozenset({"protocol", "protocol_hash", "frozen"})
RUN_PAYLOAD_FIELDS = frozenset(
    {
        "run_id", "protocol_id", "phase5_run_id", "phase5_run_hash", "method",
        "access_manifest", "status", "stopping_reason",
    }
)
METHOD_FIELDS = frozenset({"adapter", "arithmetic", "selection"})
ACCESS_MANIFEST_FIELDS = frozenset(
    {
        "allowed_capabilities", "heldout_case_ids_exposed", "access_count",
        "exploratory_result_access_during_execution",
        "method_hash_frozen_before_access", "adaptations_after_access",
        "access_record_ids", "first_access_recorded_at", "adaptation_protocol_ids",
        "refused_access_count",
    }
)
RESULT_FIELDS = frozenset(
    {
        "schema_version", "case_id", "status", "case_result_hash", "exact_feasibility",
        "independent_primal_dual_agreement", "generality_controls",
        "generality_suite_id", "generality_suite_hash",
        "mathematical_warrant", "applicability_status", "graph_admitted",
        "external_cost_usd", "model_calls", "network_calls",
    }
)
ACCESS_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version", "benchmark_id", "case_id", "protocol_id",
        "protocol_hash", "stopping_rule", "allowed_capabilities",
        "method_hash_frozen_before_access",
    }
)
NOVELTY_FIELDS = frozenset({"status", "limitations", "inferred_from_warrant"})
SIGNIFICANCE_FIELDS = frozenset(
    {"status", "rubric_id", "assessor_id", "inferred_from_warrant"}
)
CONTRIBUTION_FIELDS = frozenset({"actor_type", "contribution_type", "artifact_id"})
BASELINE_FIELDS = frozenset(
    {
        "capability", "simplest_baseline_passed", "phase6_passed",
        "additional_external_cost_usd", "additional_expert_actions",
        "positive_controls_passed", "probes_flipped", "is_generality_measure",
        "interpretation",
    }
)
RELEASE_FIELDS = frozenset(
    {
        "schema_version", "protocol_id", "protocol_hash", "phase5_run_id",
        "phase5_export_hash", "confirmatory_run_id", "confirmatory_run_hash",
        "confirmatory_result_id", "confirmatory_result_hash", "confirmatory_result",
        "semantic_fidelity", "novelty", "novelty_record_id", "significance",
        "significance_record_id", "contributions", "contribution_record_ids",
        "heldout_accesses", "adaptations_after_access", "controls_passed",
        "controls_total", "material_result_count",
        "negative_and_superseded_attempts_retained", "baseline_comparison",
        "release_limitations", "release_hash",
        "heldout_access_record_id", "heldout_access_violation_records",
        "generality_suite_id", "generality_suite_hash", "generality_suite_record_id",
        "control_corpus_provenance", "probes_flipped", "probes_total",
        "positive_control_admitted", "positive_control_ids",
        "generality_categories_covered", "generality_control_verdicts",
    }
)

# The exact record emission order of an `adaivy.phase6-release.v1` bundle. A
# reordered bundle whose sequences and hashes have been re-sealed is caught here
# and nowhere else, because no derived identity in the bundle depends on order.
EXPECTED_RECORD_TYPES = (
    "confirmatory_protocol",
    "heldout_access",
    "generality_control_suite",
    "confirmatory_run",
    "confirmatory_result",
    "novelty_assessment",
    "significance_assessment",
    "contribution",
    "contribution",
    "contribution",
    "release_package",
)

# The frozen execution method. Restated so a bundle cannot rename its own
# adapter or claim inexact arithmetic and still verify.
EXPECTED_METHOD = {
    "adapter": "exact_diagonal_jrf_v1",
    "arithmetic": "fractions-exact",
    "selection": "protocol_frozen_before_access",
}

# The accepted ADR-0034 suite is named by stable identities. Its full source
# specification is reconstructed from the recorded execution result, hashed
# against the protocol, and executed again below.
EXPECTED_CONTROL_IDS = (
    "GC-01", "GC-02A", "GC-02B", "GC-03", "GC-04", "GC-05", "GC-06A",
    "GC-06B", "GC-07", "GC-08A", "GC-08B", "GC-09A", "GC-09B",
)
EXPECTED_CONTROLS = EXPECTED_CONTROL_IDS

SUITE_SOURCE_FIELDS = frozenset(
    {"schema_version", "suite_id", "version", "control_corpus_provenance", "limitations", "controls"}
)
CONTROL_SOURCE_FIELDS = frozenset(
    {
        "control_id", "category", "blueprint_reference", "polarity", "engine",
        "parameters", "expected", "probe", "limitations",
    }
)
PROBE_SOURCE_FIELDS = frozenset(
    {"probe_id", "field", "value", "forbidden_outcome", "expected"}
)

# Release fields this verifier declines to sign off, in two distinct kinds. The
# distinction is load-bearing: one label for both would let a reader treat a
# constant as a measurement of unknown quality.
#
# `unverifiable` -- a claim about facts outside the system's view. The bundle
# genuinely cannot settle it.
UNVERIFIABLE_FIELDS = (
    (
        "semantic_fidelity",
        "No semantic-alignment review record exists in the bundle. The producer "
        "writes the literal \"researcher_approved\" at phase6/service.py:273, so "
        "this is an assertion about a human review, not a derivable fact.",
    ),
    (
        "negative_and_superseded_attempts_retained",
        "The producer writes the literal True at phase6/service.py:285. The "
        "verifier does derive which negative and superseded records are actually "
        "present -- see the negative_and_superseded_attempts_observed check -- but "
        "completeness of retention is not expressible from the bundle, so the "
        "boolean itself stays unverified.",
    ),
)

# `not_derived` -- the value is a constant. It cannot vary, no computation stands
# behind it, and the release package presents it as a measured outcome. A number
# that cannot vary is not a measurement; it carries zero bits. Naming these
# separately is what stops a later reader treating them as evidence.
#
# Deriving any of them would change `release_hash` for every historical Phase 6
# release, which is a separate decision needing its own ADR and an owner ruling.
# Out of scope here: report only, fix nothing.
NOT_DERIVED_FIELDS = (
    (
        "baseline_comparison",
        "The Phase 6 operand is derived from executed controls, but the simplest "
        "baseline operand is still a literal: no baseline run is bundled. This "
        "block counts enforced boundaries and is not a generality rate.",
    ),
    (
        "baseline_comparison.simplest_baseline_passed",
        "The literal 0 at phase6/service.py:288, and the only occurrence of "
        "`simplest_baseline` anywhere in src/. The baseline the protocol names at "
        "fixtures/phase6/confirmatory-protocol-v1.json:27, "
        "\"arithmetic_only_without_trust_controls\", is never executed and never "
        "referenced by name. There is nothing to check this value against, so the "
        "verifier reports it and signs off nothing.",
    ),
)


def _fail(message: str) -> Any:
    raise Phase6ReplayError(message)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Phase6ReplayError(message)


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise Phase6ReplayError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _decode(data: object, label: str) -> dict[str, Any]:
    """Decode one bundle input. Fails closed on every malformed shape."""

    if not isinstance(data, (bytes, bytearray)):
        _fail(f"{label} must be raw bytes")
    if len(data) > MAX_VERIFY_BYTES:
        _fail(f"{label} exceeds the bounded {MAX_VERIFY_BYTES}-byte replay limit")
    try:
        value = json.loads(
            bytes(data).decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda item: _fail(f"{label} has a non-finite number: {item}"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Phase6ReplayError(f"{label} is not valid UTF-8 JSON") from error
    except RecursionError as error:
        raise Phase6ReplayError(f"{label} is nested too deeply") from error
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    _depth(value, label)
    return value


def _depth(value: Any, label: str, level: int = 0) -> None:
    if level > MAX_JSON_DEPTH:
        _fail(f"{label} exceeds the bounded nesting depth")
    if isinstance(value, Mapping):
        for item in value.values():
            _depth(item, label, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, label, level + 1)


def _object(value: object, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    assert isinstance(value, Mapping)
    observed = set(value)
    if observed != set(fields):
        _fail(
            f"{label} field set differs; missing={sorted(set(fields) - observed)} "
            f"unknown={sorted(observed - set(fields))}"
        )
    return value


def _self_hash(value: Mapping[str, Any], key: str) -> str:
    """Hash a mapping excluding its own declared-hash key.

    This is the Phase 5 `content_hash` rule generalized to the release, whose
    self key is `release_hash`. It is restated rather than imported so the
    verifier does not inherit a producer helper.
    """

    return canonical_hash({name: item for name, item in value.items() if name != key})


def _canonical(data: bytes, value: Mapping[str, Any], label: str) -> None:
    if bytes(data) != canonical_bytes(value):
        _fail(f"{label} is not canonical JSON bytes")


def _derived_record_id(record: Mapping[str, Any]) -> str:
    """The producer's default identity for an appended record."""

    identity = {
        "record_type": record["record_type"],
        "subject_id": record["subject_id"],
        "payload": record["payload"],
    }
    return stable_id(str(record["record_type"]).replace("_", "-"), identity)


def _validate_envelope_records(
    records: object, *, label: str, schema_version: str, maximum: int
) -> list[Mapping[str, Any]]:
    if not isinstance(records, list):
        _fail(f"{label} records must be a list")
    assert isinstance(records, list)
    if len(records) > maximum:
        _fail(f"{label} record count exceeds the bounded limit")
    seen: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for index, item in enumerate(records):
        record = _object(item, RECORD_FIELDS, f"{label} record {index}")
        if record["schema_version"] != schema_version:
            _fail(f"{label} record {index} has an unknown record schema version")
        if not isinstance(record["sequence"], int) or isinstance(record["sequence"], bool):
            _fail(f"{label} record {index} sequence must be an integer")
        if record["sequence"] != index:
            _fail(
                f"{label} record sequence is not contiguous from zero: "
                f"position {index} declares {record['sequence']}"
            )
        for key in ("record_id", "record_type", "subject_id", "recorded_at"):
            if not isinstance(record[key], str) or not record[key]:
                _fail(f"{label} record {index} {key} must be a non-empty string")
        if not isinstance(record["payload"], Mapping):
            _fail(f"{label} record {index} payload must be an object")
        if _self_hash(record, "content_hash") != record["content_hash"]:
            _fail(f"{label} record {index} content hash is not derived from its content")
        if record["record_id"] in seen:
            _fail(f"{label} duplicate record identity: {record['record_id']}")
        seen.add(str(record["record_id"]))
        validated.append(record)
    return validated


def _one(records: Sequence[Mapping[str, Any]], record_type: str) -> Mapping[str, Any]:
    found = [item for item in records if item["record_type"] == record_type]
    if len(found) != 1:
        _fail(f"the bundle must contain exactly one {record_type} record")
    return found[0]


def _positive_zero(value: object, label: str) -> None:
    if isinstance(value, bool) or value != 0 or not isinstance(value, int):
        _fail(f"{label} must be the integer zero in a Phase 6 release")


def _reconstruct_suite(result: Mapping[str, Any]) -> dict[str, Any]:
    """Recover the frozen suite input from its self-describing execution result."""

    controls = result.get("controls")
    if not isinstance(controls, list):
        _fail("generality suite controls must be a list")
    source_controls: list[dict[str, Any]] = []
    for index, item in enumerate(controls):
        if not isinstance(item, Mapping):
            _fail(f"generality control {index} must be an object")
        missing = CONTROL_SOURCE_FIELDS - set(item)
        if missing:
            _fail(f"generality control {index} omits source fields: {sorted(missing)}")
        probe = item.get("probe")
        if not isinstance(probe, Mapping):
            _fail(f"generality control {index} probe must be an object")
        probe_missing = PROBE_SOURCE_FIELDS - set(probe)
        if probe_missing:
            _fail(f"generality control {index} probe omits source fields: {sorted(probe_missing)}")
        source = {key: item[key] for key in CONTROL_SOURCE_FIELDS}
        source["probe"] = {key: probe[key] for key in PROBE_SOURCE_FIELDS}
        source_controls.append(source)
    return {
        "schema_version": SUITE_SCHEMA_VERSION,
        "suite_id": result.get("suite_id"),
        "version": result.get("suite_version"),
        "control_corpus_provenance": result.get("control_corpus_provenance"),
        "limitations": result.get("limitations"),
        "controls": source_controls,
    }


def verify_release_bundle(
    phase6_export_bytes: bytes,
    phase5_export_bytes: bytes,
    phase5_fixture_bytes: bytes,
) -> dict[str, Any]:
    """Independently re-derive a Phase 6 release from its bundle.

    Returns a verdict on success and raises :class:`Phase6ReplayError` on any
    check the bundle cannot reproduce. Side-effect free: the only state created
    is a temporary clean room, and it is discarded before returning.
    """

    for label, data in (
        ("Phase 6 export", phase6_export_bytes),
        ("Phase 5 export", phase5_export_bytes),
        ("Phase 5 fixture", phase5_fixture_bytes),
    ):
        if not isinstance(data, (bytes, bytearray)):
            _fail(f"{label} must be raw bytes")
        if len(data) > MAX_VERIFY_BYTES:
            _fail(f"{label} exceeds the bounded {MAX_VERIFY_BYTES}-byte replay limit")

    with tempfile.TemporaryDirectory(prefix="adaivy-phase6-replay-") as clean_room:
        room = Path(clean_room)
        names = (
            ("phase6-export.json", phase6_export_bytes),
            ("phase5-export.json", phase5_export_bytes),
            ("phase5-fixture.json", phase5_fixture_bytes),
        )
        for name, data in names:
            (room / name).write_bytes(bytes(data))
        # Everything below reads the clean-room copies only. No caller path,
        # workspace, or database is touched.
        return _verify(
            (room / "phase6-export.json").read_bytes(),
            (room / "phase5-export.json").read_bytes(),
            (room / "phase5-fixture.json").read_bytes(),
        )


def _verify(
    phase6_data: bytes, phase5_data: bytes, fixture_data: bytes
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def passed(name: str, **detail: Any) -> None:
        checks.append({"check": name, "status": "passed", "detail": detail})

    # 1. Canonical byte encoding and closed envelopes.
    phase6 = _decode(phase6_data, "Phase 6 export")
    phase5 = _decode(phase5_data, "Phase 5 export")
    fixture = _decode(fixture_data, "Phase 5 fixture")
    _object(phase6, PHASE6_EXPORT_FIELDS, "Phase 6 export")
    _object(phase5, PHASE5_EXPORT_FIELDS, "Phase 5 export")
    _object(fixture, FIXTURE_FIELDS, "Phase 5 fixture")
    _canonical(phase6_data, phase6, "Phase 6 export")
    _canonical(phase5_data, phase5, "Phase 5 export")
    _require(
        phase6["schema_version"] == PHASE6_EXPORT_VERSION,
        "Phase 6 export schema version is unknown",
    )
    _require(
        phase5["schema_version"] == PHASE5_EXPORT_VERSION,
        "Phase 5 export schema version is unknown",
    )
    _require(
        fixture["schema_version"] == FIXTURE_VERSION
        and fixture["benchmark_id"] == BENCHMARK_ID,
        "Phase 5 fixture schema version or benchmark is unknown",
    )
    # The fixture is a human-authored source document with no declared hash of
    # its own; the protocol binds it by value, so byte canonicality is recorded
    # as an observation rather than enforced. Both exports are machine-produced
    # canonical envelopes and are byte-checked above.
    fixture_bytes_canonical = bytes(fixture_data) == canonical_bytes(fixture)
    passed(
        "canonical_input_encoding",
        phase6_export_bytes=len(phase6_data),
        phase5_export_bytes=len(phase5_data),
        phase5_fixture_bytes=len(fixture_data),
        phase5_fixture_bytes_canonical=fixture_bytes_canonical,
        phase5_fixture_binding="by_value_hash",
    )

    # 2. Per-record derivation, contiguity, and identity.
    records = _validate_envelope_records(
        phase6["records"],
        label="Phase 6 export",
        schema_version=PHASE6_RECORD_VERSION,
        maximum=MAX_PHASE6_RECORDS,
    )
    phase5_records = _validate_envelope_records(
        phase5["records"],
        label="Phase 5 export",
        schema_version=PHASE5_RECORD_VERSION,
        maximum=MAX_PHASE5_RECORDS,
    )
    observed_types = tuple(str(item["record_type"]) for item in records)
    _require(
        observed_types == EXPECTED_RECORD_TYPES,
        "Phase 6 record type order differs from the frozen release emission order: "
        f"{list(observed_types)}",
    )
    passed(
        "phase6_record_sequence_and_identity",
        record_count=len(records),
        record_types=list(observed_types),
    )
    # Phase 5 records the producer identifies by default derivation must
    # reproduce; the two explicit-identity types are bound by their own payload
    # identity below and by the export hash agreement.
    phase5_explicit = {
        "material_partial_result_event",
        "material_partial_result_steering_action",
        "material_partial_result_lifecycle",
    }
    for index, record in enumerate(phase5_records):
        if record["record_type"] in phase5_explicit:
            _require(
                record["record_id"] == record["subject_id"],
                f"Phase 5 record {index} explicit identity differs from its subject",
            )
            continue
        _require(
            record["record_id"] == _derived_record_id(record),
            f"Phase 5 record {index} identity is not derived from its content",
        )
    passed(
        "phase5_record_sequence_and_identity",
        record_count=len(phase5_records),
        derived_identity_scope="all record types except the three explicit-identity"
        " material-result types, which are bound by payload identity and the"
        " export hash",
    )

    protocol_record = _one(records, "confirmatory_protocol")
    access_record = _one(records, "heldout_access")
    suite_record = _one(records, "generality_control_suite")
    run_record = _one(records, "confirmatory_run")
    result_record = _one(records, "confirmatory_result")
    novelty_record = _one(records, "novelty_assessment")
    significance_record = _one(records, "significance_assessment")
    release_record = _one(records, "release_package")
    contribution_records = [
        item for item in records if item["record_type"] == "contribution"
    ]

    # 3. Protocol hash plus every producer guard, re-run against the embedded
    #    protocol. A retroactively loosened protocol is rejected here.
    protocol_payload = _object(
        protocol_record["payload"], PROTOCOL_PAYLOAD_FIELDS, "confirmatory protocol payload"
    )
    protocol = _object(protocol_payload["protocol"], PROTOCOL_FIELDS, "confirmatory protocol")
    _require(protocol_payload["frozen"] is True, "the embedded protocol is not marked frozen")
    _require(
        protocol_payload["protocol_hash"] == canonical_hash(dict(protocol)),
        "protocol hash is not derived from the embedded protocol",
    )
    _require(
        protocol["schema_version"] == PROTOCOL_VERSION
        and protocol["phase"] == PHASE_NAME
        and protocol["benchmark_id"] == BENCHMARK_ID
        and protocol["stopping_rule"] == STOPPING_RULE,
        "unsupported or unfrozen confirmatory protocol",
    )
    _require(
        isinstance(protocol["frozen_at"], str)
        and isinstance(protocol_record["recorded_at"], str)
        and protocol["frozen_at"] <= protocol_record["recorded_at"],
        "confirmatory protocol must be frozen before execution",
    )
    heldout = protocol["heldout_case_ids"]
    _require(
        isinstance(heldout, list) and len(heldout) == 1 and len(set(heldout)) == 1,
        "this bounded protocol requires exactly one frozen held-out case",
    )
    _require(
        isinstance(protocol["allowed_capabilities"], list)
        and set(protocol["allowed_capabilities"]) == set(ALLOWED_CAPABILITIES),
        "held-out capability boundary differs from the frozen allowlist",
    )
    _require(
        protocol["generality_suite_id"] == GENERALITY_SUITE_ID
        and protocol["generality_suite_hash"] == GENERALITY_SUITE_HASH,
        "confirmatory protocol names an unknown generality control suite",
    )
    _require(
        protocol_record["record_id"] == protocol["protocol_id"]
        and protocol_record["subject_id"] == protocol["protocol_id"],
        "confirmatory protocol record identity differs from the protocol id",
    )
    protocol_hash = str(protocol_payload["protocol_hash"])
    passed(
        "protocol_hash_and_producer_guards",
        protocol_id=protocol["protocol_id"],
        protocol_hash=protocol_hash,
        guards=[
            "closed_field_set", "schema_version", "phase", "benchmark_id",
            "stopping_rule", "frozen_before_execution", "exactly_one_heldout_case",
            "capability_allowlist",
        ],
    )

    # 4. Fixture binding. This must hold BEFORE any held-out recomputation, so
    #    a swapped fixture can never reach `run_case`.
    fixture_hash = canonical_hash(dict(fixture))
    _require(
        fixture_hash == protocol["phase5_fixture_hash"],
        "held-out fixture hash differs from the frozen protocol",
    )
    cases = fixture["cases"]
    _require(
        isinstance(cases, list) and 0 < len(cases) <= MAX_FIXTURE_CASES,
        "Phase 5 fixture case list is empty or exceeds the bounded limit",
    )
    passed("phase5_fixture_hash_binding", phase5_fixture_hash=fixture_hash)

    # 5. Independent recomputation of the held-out case.
    selected_id = heldout[0]
    selected = [
        item for item in cases
        if isinstance(item, Mapping) and item.get("case_id") == selected_id
    ]
    _require(
        len(selected) == 1,
        "frozen held-out case does not resolve exactly once in the fixture",
    )
    try:
        case_result = run_case(DiagonalCase.from_value(dict(selected[0])))
    except (QuantumInputError, AssertionError) as error:
        raise Phase6ReplayError(
            f"held-out case does not reproduce: {error}"
        ) from error
    result = _object(result_record["payload"], RESULT_FIELDS, "confirmatory result")
    _require(
        result["schema_version"] == RESULT_VERSION,
        "confirmatory result schema version is unknown",
    )
    _require(
        result["case_id"] == selected_id,
        "confirmatory result case differs from the frozen held-out case",
    )
    _require(
        result["case_result_hash"] == case_result["result_hash"],
        "recomputed held-out case result hash differs from the recorded hash: "
        f"recomputed {case_result['result_hash']}, recorded {result['case_result_hash']}",
    )
    _require(
        result["mathematical_warrant"] == case_result["mathematical_warrant"]
        and result["applicability_status"] == case_result["applicability_status"],
        "confirmatory result warrant or applicability differs from the recomputation",
    )
    agreement = (
        case_result["independent_primal_optimum"] == case_result["independent_dual_optimum"]
    )
    _require(
        result["independent_primal_dual_agreement"] is agreement,
        "primal/dual agreement differs from the recomputation",
    )
    _require(result["exact_feasibility"] is True, "exact feasibility is not asserted")
    passed(
        "heldout_case_independently_recomputed",
        case_id=selected_id,
        case_result_hash=case_result["result_hash"],
        independent_primal_optimum=case_result["independent_primal_optimum"],
        independent_dual_optimum=case_result["independent_dual_optimum"],
    )

    # 6. Generality controls. Reconstruct the frozen suite source from the
    #    recorded execution, verify its protocol-bound hash, then execute every
    #    control and falsifiability probe again.
    suite_result = suite_record["payload"]
    _require(isinstance(suite_result, Mapping), "generality suite record must be an object")
    suite_spec = _reconstruct_suite(suite_result)
    _require(
        suite_spec["suite_id"] == GENERALITY_SUITE_ID
        and canonical_hash(suite_spec) == GENERALITY_SUITE_HASH,
        "generality suite source differs from the protocol-bound frozen suite",
    )
    try:
        replayed_suite = run_suite(suite_spec)
    except GeneralitySuiteError as error:
        raise Phase6ReplayError(f"generality suite does not replay: {error}") from error
    _require(
        canonical_bytes(suite_result) == canonical_bytes(replayed_suite),
        "generality suite execution differs from clean-room replay",
    )
    _require(
        tuple(item["control_id"] for item in replayed_suite["controls"])
        == EXPECTED_CONTROL_IDS,
        "generality control identities differ from the frozen ADR-0034 suite",
    )
    _require(
        suite_record["record_id"] == stable_id("suite.phase6", replayed_suite)
        and suite_record["subject_id"] == GENERALITY_SUITE_ID,
        "generality suite record identity is not derived from its result",
    )
    _require(
        canonical_bytes(result["generality_controls"]) == canonical_bytes(replayed_suite)
        and result["generality_suite_id"] == GENERALITY_SUITE_ID
        and result["generality_suite_hash"] == GENERALITY_SUITE_HASH,
        "confirmatory result generality suite binding differs from the replayed suite",
    )
    controls_total = int(replayed_suite["controls_total"])
    controls_passed = int(replayed_suite["controls_passed"])
    probes_total = int(replayed_suite["probes_total"])
    probes_flipped = int(replayed_suite["probes_flipped"])
    expected_status = "passed" if (agreement and replayed_suite["suite_passed"] is True) else "failed"
    _require(
        result["status"] == expected_status,
        f"confirmatory status is not derived: recorded {result['status']!r}, "
        f"derived {expected_status!r}",
    )
    passed(
        "generality_controls_reexecuted",
        controls_passed=controls_passed,
        controls_total=controls_total,
        probes_flipped=probes_flipped,
        probes_total=probes_total,
        derived_status=expected_status,
        measures_capability=True,
        positive_control_present=bool(replayed_suite["positive_control_ids"]),
    )

    # 7. Confirmatory run: method, access manifest, and the Phase 5 run binding.
    run_payload = _object(run_record["payload"], RUN_PAYLOAD_FIELDS, "confirmatory run payload")
    method = _object(run_payload["method"], METHOD_FIELDS, "confirmatory method")
    _require(dict(method) == EXPECTED_METHOD, "confirmatory execution method differs")
    manifest = _object(
        run_payload["access_manifest"], ACCESS_MANIFEST_FIELDS, "held-out access manifest"
    )
    access_payload = _object(
        access_record["payload"], ACCESS_PAYLOAD_FIELDS, "held-out access record payload"
    )
    expected_access_id = stable_id(
        "access.phase6", {"benchmark_id": BENCHMARK_ID, "case_id": selected_id}
    )
    _require(
        access_record["record_id"] == expected_access_id
        and access_record["subject_id"] == selected_id,
        "held-out access record identity is not derived from benchmark and case",
    )
    _require(
        access_payload["schema_version"] == "adaivy.heldout-access.v1"
        and access_payload["benchmark_id"] == BENCHMARK_ID
        and access_payload["case_id"] == selected_id
        and access_payload["protocol_id"] == protocol["protocol_id"]
        and access_payload["protocol_hash"] == protocol_hash
        and access_payload["stopping_rule"] == STOPPING_RULE
        and list(access_payload["allowed_capabilities"]) == sorted(ALLOWED_CAPABILITIES),
        "held-out access record differs from the frozen protocol boundary",
    )
    _require(
        manifest["method_hash_frozen_before_access"] == canonical_hash(dict(method)),
        "frozen method hash is not derived from the recorded method",
    )
    _require(
        access_payload["method_hash_frozen_before_access"] == canonical_hash(dict(method)),
        "held-out access record method hash is not derived from the recorded method",
    )
    _require(
        list(manifest["allowed_capabilities"]) == sorted(ALLOWED_CAPABILITIES),
        "access manifest capability list differs from the frozen allowlist",
    )
    _require(
        list(manifest["heldout_case_ids_exposed"]) == [selected_id],
        "access manifest exposes a different held-out case",
    )
    _require(
        list(manifest["access_record_ids"]) == [expected_access_id]
        and manifest["first_access_recorded_at"] == access_record["recorded_at"]
        and list(manifest["adaptation_protocol_ids"]) == []
        and manifest["refused_access_count"] == 0,
        "access manifest does not reproduce the held-out access ledger",
    )
    _require(
        manifest["exploratory_result_access_during_execution"] is False,
        "the confirmatory run read exploratory results during execution",
    )
    _require(
        run_payload["protocol_id"] == protocol["protocol_id"],
        "confirmatory run cites another protocol",
    )
    _require(
        run_payload["status"] == expected_status,
        "confirmatory run status is not the derived status",
    )
    _require(
        run_payload["stopping_reason"] == "frozen_one_pass_complete",
        "confirmatory run stopping reason differs from the frozen one-pass rule",
    )
    phase5_run_id = str(run_payload["phase5_run_id"])
    phase5_run_records = [
        item for item in phase5_records
        if item["record_type"] == "run" and item["subject_id"] == phase5_run_id
    ]
    _require(
        len(phase5_run_records) == 1,
        "the Phase 5 export does not contain exactly one matching exploratory run",
    )
    phase5_run = phase5_run_records[0]
    _require(
        phase5_run["content_hash"] == run_payload["phase5_run_hash"],
        "recorded Phase 5 run hash differs from the supplied Phase 5 export",
    )
    _require(
        phase5_run["payload"]["fixture_hash"] == protocol["phase5_fixture_hash"],
        "the Phase 5 exploratory run used another fixture",
    )
    derived_phase5_run_id = stable_id(
        "run.phase5",
        {
            "objective_id": phase5_run["payload"]["objective_id"],
            "fixture_hash": fixture_hash,
        },
    )
    _require(
        derived_phase5_run_id == phase5_run_id,
        "Phase 5 run identity is not derived from its objective and this fixture",
    )
    confirmatory_run_id = stable_id(
        "run.phase6", {"protocol_hash": protocol_hash, "phase5_run_id": phase5_run_id}
    )
    _require(
        run_record["record_id"] == confirmatory_run_id
        and run_record["subject_id"] == confirmatory_run_id
        and run_payload["run_id"] == confirmatory_run_id,
        "confirmatory run identity is not derived from the protocol and Phase 5 run",
    )
    passed(
        "confirmatory_run_identity_and_access_manifest",
        confirmatory_run_id=confirmatory_run_id,
        phase5_run_id=phase5_run_id,
        method_hash=canonical_hash(dict(method)),
    )

    # 8. Result, assessment, and contribution identities.
    result_id = stable_id(
        "evaluation.phase6", {"run_id": confirmatory_run_id, "result": dict(result)}
    )
    _require(
        result_record["record_id"] == result_id
        and result_record["subject_id"] == confirmatory_run_id,
        "confirmatory result identity is not derived from the run and result",
    )
    novelty = _object(novelty_record["payload"], NOVELTY_FIELDS, "novelty assessment")
    significance = _object(
        significance_record["payload"], SIGNIFICANCE_FIELDS, "significance assessment"
    )
    for record, label in ((novelty_record, "novelty"), (significance_record, "significance")):
        _require(
            record["subject_id"] == result_id,
            f"{label} assessment does not attach to the confirmatory result",
        )
        _require(
            record["record_id"] == _derived_record_id(record),
            f"{label} assessment identity is not derived from its content",
        )
    expected_contributions = [
        {
            "actor_type": "human",
            "contribution_type": "protocol_freeze",
            "artifact_id": protocol["protocol_id"],
        },
        {
            "actor_type": "tool",
            "contribution_type": "exact_computation",
            "artifact_id": case_result["result_hash"],
        },
        {
            "actor_type": "system",
            "contribution_type": "verification",
            "artifact_id": result_id,
        },
    ]
    _require(
        len(contribution_records) == len(expected_contributions),
        "the bundle must contain exactly three contribution records",
    )
    for index, record in enumerate(contribution_records):
        contribution = _object(
            record["payload"], CONTRIBUTION_FIELDS, f"contribution {index}"
        )
        _require(
            dict(contribution) == expected_contributions[index],
            f"contribution {index} is not the derived contribution",
        )
        _require(
            record["subject_id"] == result_id
            and record["record_id"] == _derived_record_id(record),
            f"contribution {index} identity is not derived from its content",
        )
    passed(
        "result_assessment_and_contribution_identities",
        confirmatory_result_id=result_id,
        contribution_record_ids=[str(item["record_id"]) for item in contribution_records],
    )

    # 9. Release package: re-derived hash, identity, and record agreement.
    release = _object(release_record["payload"], RELEASE_FIELDS, "release package")
    _require(
        release["schema_version"] == RELEASE_VERSION,
        "release package schema version is unknown",
    )
    release_hash = _self_hash(release, "release_hash")
    _require(
        release["release_hash"] == release_hash,
        "release hash is not derived from the release package: "
        f"recomputed {release_hash}, declared {release['release_hash']}",
    )
    release_id = stable_id(
        "release.phase6", {"run_id": confirmatory_run_id, "release_hash": release_hash}
    )
    _require(
        release_record["record_id"] == release_id
        and release_record["subject_id"] == confirmatory_run_id,
        "release record identity is not derived from the run and release hash",
    )
    _require(
        release["protocol_id"] == protocol["protocol_id"]
        and release["protocol_hash"] == protocol_hash,
        "release protocol binding differs from the protocol record",
    )
    _require(
        release["phase5_run_id"] == phase5_run_id
        and release["confirmatory_run_id"] == confirmatory_run_id
        and release["confirmatory_run_hash"] == run_record["content_hash"],
        "release run binding differs from the confirmatory run record",
    )
    _require(
        release["confirmatory_result_id"] == result_id
        and release["confirmatory_result_hash"] == result_record["content_hash"],
        "release result binding differs from the confirmatory result record",
    )
    # 10. The embedded copy must equal the record, byte for byte.
    _require(
        canonical_bytes(release["confirmatory_result"]) == canonical_bytes(dict(result)),
        "the release's embedded confirmatory result differs from the record",
    )
    _require(
        canonical_bytes(release["novelty"]) == canonical_bytes(dict(novelty))
        and release["novelty_record_id"] == novelty_record["record_id"],
        "the release's embedded novelty assessment differs from the record",
    )
    _require(
        canonical_bytes(release["significance"]) == canonical_bytes(dict(significance))
        and release["significance_record_id"] == significance_record["record_id"],
        "the release's embedded significance assessment differs from the record",
    )
    _require(
        list(release["contributions"]) == expected_contributions
        and list(release["contribution_record_ids"])
        == [str(item["record_id"]) for item in contribution_records],
        "the release's embedded contributions differ from the records",
    )
    _require(
        release["controls_passed"] == controls_passed
        and release["controls_total"] == controls_total
        and release["probes_flipped"] == probes_flipped
        and release["probes_total"] == probes_total,
        "release control or probe counts are not the derived counts",
    )
    _require(
        release["generality_suite_id"] == GENERALITY_SUITE_ID
        and release["generality_suite_hash"] == GENERALITY_SUITE_HASH
        and release["generality_suite_record_id"] == suite_record["record_id"]
        and release["control_corpus_provenance"]
        == replayed_suite["control_corpus_provenance"]
        and release["positive_control_admitted"]
        is replayed_suite["positive_control_admitted"]
        and list(release["positive_control_ids"])
        == list(replayed_suite["positive_control_ids"])
        and list(release["generality_categories_covered"])
        == list(replayed_suite["categories_covered"]),
        "release generality suite binding differs from the replayed suite",
    )
    expected_verdicts = [
        {
            "control_id": item["control_id"],
            "category": item["category"],
            "polarity": item["polarity"],
            "engine": item["engine"],
            "passed": item["passed"],
            "probe_id": item["probe"]["probe_id"],
            "probe_flipped": item["probe"]["flipped"],
        }
        for item in replayed_suite["controls"]
    ]
    _require(
        list(release["generality_control_verdicts"]) == expected_verdicts,
        "release generality control verdicts differ from clean-room replay",
    )
    _require(
        release["heldout_access_record_id"] == access_record["record_id"]
        and release["heldout_access_violation_records"] == 0,
        "release held-out access binding differs from the access ledger",
    )
    _require(
        list(release["release_limitations"]) == [
            "Exact commuting/diagonal case only.",
            "No universal noncommuting QD-FS-01 resolution.",
            "Novelty and significance remain unassessed.",
            *replayed_suite["limitations"],
        ],
        "release limitations differ from the frozen limitation set",
    )
    # The baseline block's shape is closed and its cost/labour fields must be
    # zero, but `simplest_baseline_passed` and `phase6_passed` are constants and
    # are reported under `not_derived` rather than signed off here. See
    # NOT_DERIVED_FIELDS: both operands of the advertised 5-versus-0 comparison
    # are literals, so there is nothing to compare them against.
    baseline = _object(
        release["baseline_comparison"], BASELINE_FIELDS, "baseline comparison"
    )
    _require(
        baseline["capability"] == "trust_boundary_rejections",
        "baseline comparison names another capability",
    )
    _require(
        baseline["phase6_passed"] == replayed_suite["negative_controls_passed"]
        and baseline["positive_controls_passed"]
        == replayed_suite["positive_controls_passed"]
        and baseline["probes_flipped"] == probes_flipped
        and baseline["is_generality_measure"] is False
        and isinstance(baseline["interpretation"], str)
        and "NOT a generality rate" in baseline["interpretation"],
        "baseline comparison differs from the derived boundary counts",
    )
    _positive_zero(baseline["additional_external_cost_usd"], "additional external cost")
    _positive_zero(baseline["additional_expert_actions"], "additional expert actions")
    passed(
        "release_hash_identity_and_record_agreement",
        release_id=release_id,
        release_hash=release_hash,
    )

    # 11. Phase 5 export hash agreement across all three bindings.
    phase5_export_hash = _self_hash(phase5, "content_hash")
    _require(
        phase5_export_hash == phase5["content_hash"],
        "Phase 5 export hash is not derived from its content",
    )
    _require(
        phase6["phase5_export_hash"] == phase5_export_hash,
        "the Phase 6 export cites a different Phase 5 export",
    )
    _require(
        release["phase5_export_hash"] == phase5_export_hash,
        "the release cites a different Phase 5 export",
    )
    passed("phase5_export_hash_agreement", phase5_export_hash=phase5_export_hash)

    # 12. Material-result count derived from the Phase 5 export.
    material = phase5["material_results"]
    _require(isinstance(material, list), "Phase 5 material results must be a list")
    run_material = [
        item for item in material
        if isinstance(item, Mapping) and item.get("run_id") == phase5_run_id
    ]
    _require(
        len(run_material) > 0,
        "confirmatory evaluation requires a non-empty Phase 5 material-result trace",
    )
    _require(
        release["material_result_count"] == len(run_material),
        "release material-result count differs from the Phase 5 material-result trace: "
        f"recorded {release['material_result_count']}, observed {len(run_material)}",
    )
    passed(
        "material_result_count_derived",
        material_result_count=len(run_material),
        material_result_event_ids=sorted(
            str(item.get("event_id")) for item in run_material
        ),
    )

    # 13. Retained negative and superseded attempts, derived from records.
    #     Blueprint :2242 is observed here, not read off the hardcoded boolean
    #     at phase6/service.py:285.
    expected_dead_ends: list[str] = []
    seen_result_hashes: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            _fail(f"Phase 5 fixture case {index} must be an object")
        try:
            case_hash = run_case(DiagonalCase.from_value(dict(case)))["result_hash"]
        except (QuantumInputError, AssertionError) as error:
            raise Phase6ReplayError(
                f"Phase 5 fixture case {index} does not reproduce: {error}"
            ) from error
        branch_id = stable_id(
            "branch.phase5", {"run_id": phase5_run_id, "case_id": case.get("case_id")}
        )
        if case_hash in seen_result_hashes:
            expected_dead_ends.append(branch_id)
        seen_result_hashes.add(case_hash)
    observed_dead_ends = [
        str(item["payload"].get("branch_id"))
        for item in phase5_records
        if item["record_type"] == "dead_end"
    ]
    _require(
        observed_dead_ends == expected_dead_ends,
        "retained dead-end records are not the dead ends this fixture produces: "
        f"observed {observed_dead_ends}, derived {expected_dead_ends}",
    )
    falsification_branches = [
        str(item["subject_id"]) for item in phase5_records
        if item["record_type"] == "branch"
        and item["payload"].get("kind") == "falsification"
    ]
    negative_classifications = sorted(
        str(item["payload"].get("classification"))
        for item in phase5_records
        if item["record_type"] == "materiality_assessment"
        and item["payload"].get("classification") in {"restricts", "refutes"}
    )
    _require(
        bool(observed_dead_ends or falsification_branches or negative_classifications),
        "the Phase 5 trace retains no negative or superseded attempt",
    )
    passed(
        "negative_and_superseded_attempts_observed",
        dead_end_records=len(observed_dead_ends),
        derived_dead_ends=len(expected_dead_ends),
        falsification_branches=len(falsification_branches),
        negative_classifications=negative_classifications,
    )

    # 14. Refusal invariants. None of these may be promoted by a bundle.
    _require(
        result["graph_admitted"] is False,
        "a Phase 6 bundle may never admit its result to the trusted claim graph",
    )
    _require(
        release["confirmatory_result"]["graph_admitted"] is False,
        "the release's embedded result may never claim graph admission",
    )
    _require(
        novelty["status"] == "not_assessed" and novelty["inferred_from_warrant"] is False,
        "novelty must remain not_assessed and never be inferred from a warrant",
    )
    _require(
        significance["status"] == "not_assessed"
        and significance["inferred_from_warrant"] is False
        and significance["rubric_id"] is None
        and significance["assessor_id"] is None,
        "significance must remain not_assessed and never be inferred from a warrant",
    )
    _require(
        release["novelty"]["status"] == "not_assessed"
        and release["significance"]["status"] == "not_assessed",
        "the release may not assess novelty or significance",
    )
    _require(
        release["heldout_accesses"] == 1
        and not isinstance(release["heldout_accesses"], bool)
        and manifest["access_count"] == 1
        and not isinstance(manifest["access_count"], bool),
        "the frozen held-out case must be accessed exactly once",
    )
    _positive_zero(release["adaptations_after_access"], "adaptations after held-out access")
    _positive_zero(manifest["adaptations_after_access"], "manifest adaptations after access")
    _positive_zero(result["model_calls"], "model calls")
    _positive_zero(result["network_calls"], "network calls")
    _positive_zero(result["external_cost_usd"], "external cost")
    passed(
        "refusal_invariants",
        graph_admitted=False,
        novelty_status="not_assessed",
        significance_status="not_assessed",
        heldout_accesses=1,
        adaptations_after_access=0,
        model_calls=0,
        network_calls=0,
        external_cost_usd=0,
    )

    # 15. Envelope hash re-derivation last, following the Phase 4B shape.
    phase6_export_hash = _self_hash(phase6, "content_hash")
    _require(
        phase6_export_hash == phase6["content_hash"],
        "Phase 6 export hash is not derived from its content: "
        f"recomputed {phase6_export_hash}, declared {phase6['content_hash']}",
    )
    passed(
        "envelope_hashes_rederived",
        phase6_export_hash=phase6_export_hash,
        phase5_export_hash=phase5_export_hash,
    )

    return {
        "schema_version": VERIFIER_SCHEMA_VERSION,
        "verified": True,
        "checks": checks,
        "unverifiable": [
            {
                "field": field,
                "release_value": _release_value(release, field),
                "counted_as_evidence": False,
                "reason": reason,
            }
            for field, reason in UNVERIFIABLE_FIELDS
        ],
        "not_derived": [
            {
                "field": field,
                "release_value": _release_value(release, field),
                "varies": False,
                "counted_as_evidence": False,
                "reason": reason,
            }
            for field, reason in NOT_DERIVED_FIELDS
        ],
        "bound_identities": {
            "case_result_hash": case_result["result_hash"],
            "confirmatory_result_id": result_id,
            "confirmatory_run_id": confirmatory_run_id,
            "phase5_export_hash": phase5_export_hash,
            "phase5_fixture_hash": fixture_hash,
            "phase5_run_id": phase5_run_id,
            "phase6_export_hash": phase6_export_hash,
            "protocol_hash": protocol_hash,
            "release_hash": release_hash,
            "release_id": release_id,
        },
    }


def _release_value(release: Mapping[str, Any], field: str) -> Any:
    node: Any = release
    for part in field.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


__all__ = [
    "ALLOWED_CAPABILITIES",
    "EXPECTED_CONTROLS",
    "EXPECTED_METHOD",
    "EXPECTED_RECORD_TYPES",
    "MAX_VERIFY_BYTES",
    "NOT_DERIVED_FIELDS",
    "PROTOCOL_FIELDS",
    "Phase6ReplayError",
    "UNVERIFIABLE_FIELDS",
    "VERIFIER_SCHEMA_VERSION",
    "verify_release_bundle",
]
