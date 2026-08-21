"""Phase 2 proposal to Phase 3B request bridge (ADR-0043).

What this module does: it carries identity, content hashes, and lineage across
the Phase 2 / Phase 3B seam. A committed Phase 2 proposal supplies the claim
identity, the semantic-alignment identity, and the provenance triple (run,
proposal artifact hash, model call). Lean text supplies the target statement and
the proof fragment. The output is a canonical `FormalCheckRequest` that
`validation.parse_request_bytes` accepts, plus a durable record binding the
request hashes to the proposal that occasioned it.

What this module does NOT do, and cannot: it does not translate the Phase 2
`mathematical_payload` -- prose plus informal steps -- into Lean, it never
derives, guesses, completes, or repairs Lean text, and it performs NO comparison
between that payload and the supplied Lean. The two could be about different
theorems and every check here would still pass, because the only cross-check
available to a bridge is IDENTITY (does the artifact name the same claim ID the
dossier names?), not MEANING. That limit is recorded in every record it writes
as `bridge_correspondence_check = "none_performed_by_bridge"`, and the
correspondence is `unattested_operator_correspondence` until a named operator
attests it through `build_correspondence_attestation`. An attestation is a human
assertion; it is not a verification and does not become one.

Nothing here creates an `EpistemicWarrant`, approves semantic alignment,
asserts source applicability, or sets novelty, significance, or contribution.
Every record carries `disposition = "proposal"` and `trust_effect = "none"`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Protocol

from ..domain.entities import OpaqueId, ResearchDossier
from ..interchange import export_dossier_dict
from ..phase2.artifacts import ArtifactIntegrityError, FileArtifactStore
from ..phase2.records import ProposalRecord, RunRecord
from ..phase2.sqlite_workspace import SQLiteWorkspace
from . import MAX_STDIN_BYTES, SCHEMA_VERSION
from .records import FormalCheckRequest, PolicyRejection, SourceKind
from .serialization import (
    canonical_bytes, canonical_hash, canonical_json, public_value, sha256_bytes, stable_id,
)
from .validation import RequestValidationError, parse_request, parse_request_bytes

BRIDGE_RECORD_TYPE = "phase3b_bridged_request"
ATTESTATION_RECORD_TYPE = "phase3b_bridge_correspondence_attestation"
BRIDGE_HASH_PROFILE = "phase3b-bridge-semantic-v1"

#: The bridge identity version participates in every derived ID, so a future
#: change to what the bridge binds cannot silently reuse an existing ID.
BRIDGE_IDENTITY_VERSION = "phase3b-request-bridge-v1"

#: Named so that it cannot be misread as an assurance. There is exactly one
#: permitted value and the durable schema enforces it with a CHECK constraint.
BRIDGE_CORRESPONDENCE_CHECK = "none_performed_by_bridge"

#: Correspondence states. The unattested state is the state at build time and is
#: never rewritten; an attestation is a separate append-only record.
CORRESPONDENCE_UNATTESTED = "unattested_operator_correspondence"
CORRESPONDENCE_OPERATOR_ASSERTED = "operator_asserted_correspondence"

#: The only basis an attestation may declare. A tool-checked basis is not
#: offered, because no tool in this slice checks the correspondence.
ATTESTATION_BASIS = "human_reading"
ATTESTER_ROLE_OPERATOR = "operator"

CORRESPONDENCE_NOTICE = (
    "The Phase 2 mathematical payload is prose plus informal steps. This bridge "
    "did not compare it with the supplied Lean target statement and cannot do "
    "so. Only the separately recorded operator attestation asserts that "
    "correspondence, and an attestation is a human assertion rather than a "
    "verification."
)

#: Lean the bridge will carry: authored by the operator, or authored by a model
#: and declared as such. `external` is refused because the bridge has no way to
#: name the third party responsible for the text.
BRIDGEABLE_LEAN_SOURCE_KINDS = (SourceKind.OPERATOR, SourceKind.MODEL)

MAX_TARGET_STATEMENT_BYTES = 65_536
MAX_PROOF_FRAGMENT_BYTES = 131_072
MAX_SIDECAR_BYTES = 65_536
MAX_ATTESTATION_STATEMENT_BYTES = 4_096
MAX_LISTED_ALTERNATIVES = 8

INSTANT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
PRINCIPAL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:@-]{0,127}$")


# --------------------------------------------------------------------------- #
# Ports
#
# Declared here rather than in `phase3b/ports.py` so this slice adds nothing to
# an existing module in the package. They are read-only by construction: no
# method that mutates Phase 2 state, or a Phase 3B finding, is part of any port.
# --------------------------------------------------------------------------- #


class Phase2ProposalSource(Protocol):
    """Read-only view of a Phase 2 workspace."""

    def get_run(self, run_id: OpaqueId) -> RunRecord: ...
    def load_dossier(self, dossier_id: OpaqueId) -> ResearchDossier: ...
    def list_proposals(self, run_id: OpaqueId) -> tuple[ProposalRecord, ...]: ...


class ArtifactSource(Protocol):
    """Content-addressed read side of the Phase 2 artifact store."""

    def exists(self, content_hash: str) -> bool: ...
    def get(self, content_hash: str) -> bytes: ...


class FindingSource(Protocol):
    """Read-only view of persisted Phase 3B findings, used only by `trace`."""

    def finding(self, finding_id: str) -> dict[str, Any]: ...


class BridgeRefusal(ValueError):
    """A refusal that names the missing or inconsistent input.

    Structured like `RequestValidationError`: the caller receives every reason
    at once, so a missing Lean input and a bad instant are not discovered one
    round trip at a time.
    """

    def __init__(self, rejections: Sequence[PolicyRejection]) -> None:
        self.rejections = tuple(rejections)
        super().__init__("; ".join(f"{item.field}:{item.code}" for item in self.rejections))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.rejections)


class _Collector:
    def __init__(self) -> None:
        self.items: list[PolicyRejection] = []

    def add(self, code: str, field: str, detail: str) -> None:
        self.items.append(PolicyRejection(code, field, detail))

    def raise_if_any(self) -> None:
        if self.items:
            raise BridgeRefusal(tuple(self.items))


@dataclass(frozen=True, slots=True, kw_only=True)
class TrustGrants:
    """Every orthogonal decision this bridge is forbidden to make, named.

    The fields exist so the boundary is machine-checkable rather than implied by
    the absence of a field. All of them are permanently `False` here; the
    workspace refuses to persist a record in which any is true.
    """

    semantic_alignment_approved: bool = False
    source_applicability_approved: bool = False
    novelty_approved: bool = False
    significance_approved: bool = False
    contribution_approved: bool = False
    epistemic_warrant_created: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimIdentityProvenance:
    """Where `claim_id` came from. It is read, never invented or parsed out of Lean."""

    claim_id: OpaqueId
    claim_id_source: str
    claim_id_derived_from_lean: bool
    problem_id: OpaqueId
    formalization_id: OpaqueId
    dossier_id: OpaqueId
    dossier_hash: str
    formalization_statement_hash: str
    formal_language: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticAlignmentProvenance:
    semantic_alignment_id: OpaqueId
    semantic_alignment_source: str
    status: str
    approved_by: str | None
    compared_claim_id: OpaqueId
    strength_relation: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Phase2ProposalProvenance:
    """The durable lineage: run, proposal, artifact hash, model call."""

    run_id: OpaqueId
    run_status: str
    dossier_id: OpaqueId
    dossier_hash: str
    proposal_id: OpaqueId
    proposal_kind: str
    proposal_disposition: str
    proposal_source_kind: str
    artifact_hash: str
    artifact_media_type: str
    model_call_id: str | None
    payload_hash: str
    payload_target_claim_id: OpaqueId


@dataclass(frozen=True, slots=True, kw_only=True)
class LeanSourceProvenance:
    """Who authored the Lean. Declared at the call site; there is no default."""

    source_kind: SourceKind
    authored_by: str | None
    declaration_name: str
    target_statement_hash: str
    proof_fragment_hash: str
    imports: tuple[str, ...]
    assumption_names: tuple[str, ...]
    meaning_test_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PayloadCorrespondence:
    """The unverified seam, stated as a first-class fact."""

    bridge_correspondence_check: str
    correspondence_state_at_build: str
    payload_hash: str
    target_statement_hash: str
    proof_fragment_hash: str
    notice: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeOperationalContext:
    """Machine-local and byte-incidental observations.

    Excluded from the semantic content hash under the Phase 3B split: moving the
    input files or adding a trailing newline changes none of the meaning the
    request carries.
    """

    phase2_workspace_path: str
    artifact_store_path: str
    target_statement_path: str
    proof_fragment_path: str
    target_statement_source_bytes_hash: str
    proof_fragment_source_bytes_hash: str
    target_statement_source_byte_length: int
    proof_fragment_source_byte_length: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgedRequestRecord:
    bridge_id: OpaqueId
    claim_identity: ClaimIdentityProvenance
    semantic_alignment: SemanticAlignmentProvenance
    phase2_proposal: Phase2ProposalProvenance
    lean_source: LeanSourceProvenance
    payload_correspondence: PayloadCorrespondence
    trust_grants: TrustGrants
    request: FormalCheckRequest
    request_canonical_hash: str
    request_bytes_hash: str
    request_byte_length: int
    operational: BridgeOperationalContext
    created_at: str
    content_hash: str
    operational_hash: str
    record_type: str = BRIDGE_RECORD_TYPE
    disposition: str = "proposal"
    trust_effect: str = "none"
    hash_profile: str = BRIDGE_HASH_PROFILE
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrespondenceAttestation:
    """A named human assertion that the prose and the Lean say the same thing.

    `attested_at` is part of the attestation's meaning -- who asserted what,
    when -- so unlike the bridge record's `created_at` it is inside the content
    hash rather than in an operational block.
    """

    attestation_id: OpaqueId
    bridge_id: OpaqueId
    request_canonical_hash: str
    claim_id: OpaqueId
    attester_id: str
    statement: str
    payload_hash: str
    target_statement_hash: str
    proof_fragment_hash: str
    attested_at: str
    content_hash: str
    trust_grants: TrustGrants = TrustGrants()
    record_type: str = ATTESTATION_RECORD_TYPE
    attester_role: str = ATTESTER_ROLE_OPERATOR
    basis: str = ATTESTATION_BASIS
    bridge_correspondence_check: str = BRIDGE_CORRESPONDENCE_CHECK
    correspondence_state: str = CORRESPONDENCE_OPERATOR_ASSERTED
    disposition: str = "proposal"
    trust_effect: str = "none"
    hash_profile: str = BRIDGE_HASH_PROFILE
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeInputs:
    """Explicit inputs. Nothing here has a default that could be guessed."""

    phase2_workspace: Path
    artifact_root: Path
    run_id: str
    proposal_id: str
    target_statement_path: Path
    proof_fragment_path: Path
    lean_source_kind: SourceKind
    created_at: str
    lean_authored_by: str | None = None
    declaration_name: str | None = None
    imports: tuple[str, ...] = ()
    assumptions_path: Path | None = None
    meaning_tests_path: Path | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeResult:
    record: BridgedRequestRecord
    request_bytes: bytes


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #


def bridge_hash_preimage(value: Any) -> dict[str, Any]:
    """Semantic preimage: no clock, no filesystem, no byte incidentals."""
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("bridged request hash preimage must be an object")
    result["content_hash"] = ""
    result.pop("operational_hash", None)
    result.pop("created_at", None)
    result.pop("operational", None)
    return result


def bridge_content_hash(value: Any) -> str:
    return canonical_hash(bridge_hash_preimage(value))


def bridge_operational_hash(value: Any) -> str:
    """Operational preimage: the complete record, including instant and paths."""
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("bridged request operational preimage must be an object")
    result.pop("operational_hash", None)
    return canonical_hash(result)


def attestation_content_hash(value: Any) -> str:
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("attestation hash preimage must be an object")
    result["content_hash"] = ""
    return canonical_hash(result)


def request_bytes_of(record: BridgedRequestRecord) -> bytes:
    """The exact bytes `phase3b check` should read, newline-terminated."""
    return canonical_bytes(record.request) + b"\n"


# --------------------------------------------------------------------------- #
# Input reading
# --------------------------------------------------------------------------- #


def _instant(value: str, field: str, issues: _Collector) -> str:
    """Time is an input, never a clock read (the ADR-0039 convention)."""
    if not isinstance(value, str) or not INSTANT_PATTERN.fullmatch(value):
        issues.add("invalid_instant", field, "must be an explicit UTC instant such as 2026-08-21T00:00:00Z")
        return ""
    return value


def _principal(value: str | None, field: str, issues: _Collector, *, required: bool) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            issues.add("missing_principal", field, "a named principal is required")
        return None
    if not isinstance(value, str) or not PRINCIPAL_PATTERN.fullmatch(value):
        issues.add("invalid_principal", field, repr(value))
        return None
    return value


def _read_lean_input(path: Path | None, field: str, issues: _Collector, *, max_bytes: int) -> tuple[str, bytes]:
    """Read Lean text. Absence is a refusal, never a derivation."""
    if path is None:
        issues.add("missing_lean_input", field, "no path was supplied; the bridge never derives Lean")
        return "", b""
    if not path.is_file():
        issues.add("missing_lean_input", field, f"{path} is not a readable file")
        return "", b""
    data = path.read_bytes()
    if len(data) > min(max_bytes, MAX_STDIN_BYTES):
        issues.add("lean_input_too_large", field, f"maximum is {min(max_bytes, MAX_STDIN_BYTES)} bytes")
        return "", data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        issues.add("invalid_utf8", field, str(error))
        return "", data
    if not text.strip():
        issues.add("empty_lean_input", field, f"{path} contains no Lean text")
        return "", data
    return text.strip(), data


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _load_json_list(path: Path | None, field: str, issues: _Collector) -> list[Any]:
    if path is None:
        return []
    if not path.is_file():
        issues.add("missing_sidecar_input", field, f"{path} is not a readable file")
        return []
    data = path.read_bytes()
    if len(data) > MAX_SIDECAR_BYTES:
        issues.add("sidecar_too_large", field, f"maximum is {MAX_SIDECAR_BYTES} bytes")
        return []
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, ValueError) as error:
        issues.add("malformed_sidecar_json", field, str(error))
        return []
    if not isinstance(value, list):
        issues.add("invalid_sidecar_shape", field, "expected a JSON array")
        return []
    return value


# --------------------------------------------------------------------------- #
# Phase 2 sources
# --------------------------------------------------------------------------- #


def resolve_workspace_path(path: Path) -> Path:
    return path / "workspace.sqlite3" if path.is_dir() else path


def open_phase2_sources(workspace_path: Path, artifact_root: Path) -> tuple[SQLiteWorkspace, FileArtifactStore]:
    """Open an EXISTING Phase 2 workspace and artifact store.

    Both are refused rather than created. `SQLiteWorkspace` would happily
    migrate a fresh database into existence and `FileArtifactStore` would create
    its directory tree, and either would turn an operator typo into a silently
    empty run.
    """
    issues = _Collector()
    database = resolve_workspace_path(workspace_path)
    if not database.is_file():
        issues.add("missing_phase2_workspace", "phase2_workspace", f"{database} is not a readable SQLite workspace")
    if not (artifact_root / "sha256").is_dir():
        issues.add("missing_artifact_store", "artifact_root", f"{artifact_root}/sha256 is not a readable artifact store")
    issues.raise_if_any()
    workspace = SQLiteWorkspace(database)
    try:
        artifacts = FileArtifactStore(artifact_root)
    except BaseException:
        workspace.close()
        raise
    return workspace, artifacts


def _load_run(workspace: Phase2ProposalSource, run_id: str, issues: _Collector) -> RunRecord | None:
    try:
        identifier = OpaqueId(run_id)
    except ValueError:
        issues.add("invalid_identifier", "run_id", repr(run_id))
        return None
    try:
        return workspace.get_run(identifier)
    except KeyError:
        issues.add("unknown_run", "run_id", run_id)
        return None


def _load_dossier(workspace: Phase2ProposalSource, run: RunRecord, issues: _Collector) -> ResearchDossier | None:
    try:
        return workspace.load_dossier(run.dossier_id)
    except KeyError:
        issues.add("unknown_dossier", "dossier_id", run.dossier_id.value)
        return None


def _select_proposal(
    workspace: Phase2ProposalSource, run: RunRecord, proposal_id: str, issues: _Collector,
) -> ProposalRecord | None:
    proposals = workspace.list_proposals(run.run_id)
    for item in proposals:
        if item.proposal_id.value == proposal_id:
            return item
    available = sorted(item.proposal_id.value for item in proposals)[:MAX_LISTED_ALTERNATIVES]
    issues.add(
        "unknown_proposal", "proposal_id",
        f"{proposal_id!r} is not committed on run {run.run_id.value}; available: {','.join(available) or 'none'}",
    )
    return None


def _load_payload(
    artifacts: ArtifactSource, proposal: ProposalRecord, issues: _Collector,
) -> tuple[Mapping[str, Any] | None, str]:
    """Load the committed proposal artifact. Prose in, prose out; nothing is translated."""
    try:
        data = artifacts.get(proposal.artifact_hash)
    except FileNotFoundError:
        issues.add("missing_proposal_artifact", "artifact_hash", proposal.artifact_hash)
        return None, ""
    except (ArtifactIntegrityError, ValueError) as error:
        issues.add("corrupt_proposal_artifact", "artifact_hash", str(error))
        return None, ""
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, ValueError) as error:
        issues.add("malformed_proposal_artifact", "artifact_hash", str(error))
        return None, ""
    if not isinstance(value, Mapping):
        issues.add("invalid_proposal_artifact", "artifact_hash", "expected a JSON object")
        return None, ""
    payload = value.get("mathematical_payload")
    if payload is None:
        issues.add(
            "missing_mathematical_payload", "artifact.mathematical_payload",
            f"proposal {proposal.proposal_id.value} carries no mathematical payload to formalize",
        )
        return None, ""
    return value, canonical_hash(payload)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def build_bridged_request(
    *, workspace: Phase2ProposalSource, artifacts: ArtifactSource, inputs: BridgeInputs,
) -> BridgeResult:
    """Construct one provenance-linked `FormalCheckRequest`.

    Deterministic: every identifier is a content hash of the inputs, the instant
    is an argument, and no field is read from a clock or a random source.
    """
    issues = _Collector()
    created_at = _instant(inputs.created_at, "created_at", issues)
    if inputs.lean_source_kind not in BRIDGEABLE_LEAN_SOURCE_KINDS:
        issues.add(
            "unsupported_lean_source_kind", "lean_source_kind",
            f"expected one of {','.join(item.value for item in BRIDGEABLE_LEAN_SOURCE_KINDS)}",
        )
    authored_by = _principal(inputs.lean_authored_by, "lean_authored_by", issues, required=False)
    target_text, target_raw = _read_lean_input(
        inputs.target_statement_path, "target_statement", issues, max_bytes=MAX_TARGET_STATEMENT_BYTES,
    )
    proof_text, proof_raw = _read_lean_input(
        inputs.proof_fragment_path, "proof_fragment", issues, max_bytes=MAX_PROOF_FRAGMENT_BYTES,
    )
    assumptions = _load_json_list(inputs.assumptions_path, "assumptions", issues)
    meaning_tests = _load_json_list(inputs.meaning_tests_path, "meaning_tests", issues)

    run = _load_run(workspace, inputs.run_id, issues)
    dossier = _load_dossier(workspace, run, issues) if run is not None else None
    proposal = _select_proposal(workspace, run, inputs.proposal_id, issues) if run is not None else None
    artifact_value: Mapping[str, Any] | None = None
    payload_hash = ""
    if proposal is not None:
        artifact_value, payload_hash = _load_payload(artifacts, proposal, issues)
    issues.raise_if_any()
    assert run is not None and dossier is not None and proposal is not None and artifact_value is not None

    # Identity cross-checks. These compare IDENTIFIERS, which is all a bridge
    # can compare; they say nothing about whether the Lean means the claim.
    claim_id = dossier.formalization.target_claim_id
    if proposal.target_claim_id is None:
        issues.add(
            "proposal_target_claim_absent", "proposal.target_claim_id",
            f"proposal {proposal.proposal_id.value} names no target claim",
        )
    elif proposal.target_claim_id != claim_id:
        issues.add(
            "proposal_target_claim_mismatch", "proposal.target_claim_id",
            f"proposal names {proposal.target_claim_id.value}, dossier formalization names {claim_id.value}",
        )
    payload_claim = artifact_value.get("target_claim_id")
    if payload_claim != claim_id.value:
        issues.add(
            "artifact_target_claim_mismatch", "artifact.target_claim_id",
            f"artifact names {payload_claim!r}, dossier formalization names {claim_id.value}",
        )
    if run.dossier_hash != dossier_content_hash(dossier):
        issues.add("dossier_hash_mismatch", "run.dossier_hash", "the stored dossier does not hash to the run's record")
    issues.raise_if_any()
    assert proposal.target_claim_id is not None

    alignment = dossier.semantic_alignment
    imports = tuple(sorted(set(inputs.imports)))
    sorted_assumptions = _sorted_assumptions(assumptions)
    identity = {
        "bridge_identity_version": BRIDGE_IDENTITY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "claim_id": claim_id.value,
        "semantic_alignment_id": alignment.id.value,
        "lean_source_kind": inputs.lean_source_kind.value,
        "lean_authored_by": authored_by,
        "target_statement_hash": sha256_bytes(target_text.encode("utf-8")),
        "proof_fragment_hash": sha256_bytes(proof_text.encode("utf-8")),
        "imports": list(imports),
        "assumptions": sorted_assumptions,
        "meaning_tests": meaning_tests,
        "phase2": {
            "run_id": run.run_id.value,
            "dossier_id": run.dossier_id.value,
            "dossier_hash": run.dossier_hash,
            "proposal_id": proposal.proposal_id.value,
            "artifact_hash": proposal.artifact_hash,
            "model_call_id": _model_call_id(proposal),
            "payload_hash": payload_hash,
        },
    }
    declaration_name = inputs.declaration_name or _derived_declaration_name(identity)
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "request_id": stable_id("request.bridge", identity).value,
        "claim_id": claim_id.value,
        "semantic_alignment_id": alignment.id.value,
        "source_kind": inputs.lean_source_kind.value,
        "declaration_name": declaration_name,
        "imports": list(imports),
        "assumptions": sorted_assumptions,
        "target_statement": target_text,
        "proof_fragment": proof_text,
        "meaning_tests": meaning_tests,
    }
    data = canonical_bytes(candidate)
    try:
        request = parse_request_bytes(data)
    except RequestValidationError as error:
        raise BridgeRefusal(error.rejections) from error
    canonical = canonical_bytes(request)
    if canonical_bytes(parse_request_bytes(canonical)) != canonical:
        raise BridgeRefusal((PolicyRejection("request_not_canonical", "$", "the accepted request is not byte-stable"),))
    request_bytes = canonical + b"\n"

    record = _assemble(
        run=run, dossier=dossier, proposal=proposal,
        request=request, request_bytes=request_bytes, payload_hash=payload_hash,
        inputs=inputs, authored_by=authored_by, created_at=created_at,
        target_raw=target_raw, proof_raw=proof_raw,
    )
    return BridgeResult(record=record, request_bytes=request_bytes)


def bridge_from_paths(inputs: BridgeInputs) -> BridgeResult:
    workspace, artifacts = open_phase2_sources(inputs.phase2_workspace, inputs.artifact_root)
    try:
        return build_bridged_request(workspace=workspace, artifacts=artifacts, inputs=inputs)
    finally:
        workspace.close()


def dossier_content_hash(dossier: ResearchDossier) -> str:
    """The Phase 1 canonical dossier hash, reused rather than reimplemented."""
    return str(export_dossier_dict(dossier)["content_hash"])


def _model_call_id(proposal: ProposalRecord) -> str | None:
    """The model call is named only when a model actually made it."""
    return proposal.source_id if proposal.source_kind == "model" else None


def _sorted_assumptions(items: list[Any]) -> list[Any]:
    """Canonical order for the validator. Ordering is not meaning, so sorting is safe."""
    if all(isinstance(item, Mapping) and isinstance(item.get("name"), str) for item in items):
        return [dict(item) for item in sorted(items, key=lambda item: str(item["name"]))]
    return items


def _derived_declaration_name(identity: Mapping[str, Any]) -> str:
    digest = canonical_hash(identity)
    return f"AdaIvyBridge{digest[7:31]}"


def _assemble(
    *, run: RunRecord, dossier: ResearchDossier, proposal: ProposalRecord,
    request: FormalCheckRequest, request_bytes: bytes,
    payload_hash: str, inputs: BridgeInputs, authored_by: str | None, created_at: str,
    target_raw: bytes, proof_raw: bytes,
) -> BridgedRequestRecord:
    alignment = dossier.semantic_alignment
    claim_identity = ClaimIdentityProvenance(
        claim_id=request.claim_id,
        claim_id_source="phase2_dossier.formalization.target_claim_id",
        claim_id_derived_from_lean=False,
        problem_id=dossier.problem.id,
        formalization_id=dossier.formalization.id,
        dossier_id=dossier.id,
        dossier_hash=run.dossier_hash,
        formalization_statement_hash=sha256_bytes(dossier.formalization.statement.encode("utf-8")),
        formal_language=dossier.formalization.formal_language,
    )
    alignment_provenance = SemanticAlignmentProvenance(
        semantic_alignment_id=alignment.id,
        semantic_alignment_source="phase2_dossier.semantic_alignment",
        status=alignment.status.value,
        approved_by=alignment.approved_by.value if alignment.approved_by else None,
        compared_claim_id=alignment.compared_claim_id,
        strength_relation=alignment.strength_relation.value,
    )
    phase2 = Phase2ProposalProvenance(
        run_id=run.run_id, run_status=run.status.value, dossier_id=run.dossier_id,
        dossier_hash=run.dossier_hash, proposal_id=proposal.proposal_id,
        proposal_kind=proposal.proposal_kind, proposal_disposition=proposal.disposition,
        proposal_source_kind=proposal.source_kind, artifact_hash=proposal.artifact_hash,
        artifact_media_type="application/vnd.adaivy.proposal+json",
        model_call_id=_model_call_id(proposal), payload_hash=payload_hash,
        payload_target_claim_id=request.claim_id,
    )
    lean_source = LeanSourceProvenance(
        source_kind=request.source_kind, authored_by=authored_by,
        declaration_name=request.declaration_name,
        target_statement_hash=sha256_bytes(request.target_statement.encode("utf-8")),
        proof_fragment_hash=sha256_bytes(request.proof_fragment.encode("utf-8")),
        imports=request.imports,
        assumption_names=tuple(item.name for item in request.assumptions),
        meaning_test_ids=tuple(item.test_id for item in request.meaning_tests),
    )
    correspondence = PayloadCorrespondence(
        bridge_correspondence_check=BRIDGE_CORRESPONDENCE_CHECK,
        correspondence_state_at_build=CORRESPONDENCE_UNATTESTED,
        payload_hash=payload_hash,
        target_statement_hash=lean_source.target_statement_hash,
        proof_fragment_hash=lean_source.proof_fragment_hash,
        notice=CORRESPONDENCE_NOTICE,
    )
    operational = BridgeOperationalContext(
        phase2_workspace_path=str(resolve_workspace_path(inputs.phase2_workspace)),
        artifact_store_path=str(inputs.artifact_root),
        target_statement_path=str(inputs.target_statement_path),
        proof_fragment_path=str(inputs.proof_fragment_path),
        target_statement_source_bytes_hash=sha256_bytes(target_raw),
        proof_fragment_source_bytes_hash=sha256_bytes(proof_raw),
        target_statement_source_byte_length=len(target_raw),
        proof_fragment_source_byte_length=len(proof_raw),
    )
    canonical = canonical_hash(request)
    provisional = BridgedRequestRecord(
        bridge_id=stable_id("bridge", {
            "bridge_identity_version": BRIDGE_IDENTITY_VERSION,
            "request_canonical_hash": canonical,
            "phase2": public_value(phase2),
            "lean_source": public_value(lean_source),
        }),
        claim_identity=claim_identity, semantic_alignment=alignment_provenance,
        phase2_proposal=phase2, lean_source=lean_source, payload_correspondence=correspondence,
        trust_grants=TrustGrants(), request=request, request_canonical_hash=canonical,
        request_bytes_hash=sha256_bytes(request_bytes), request_byte_length=len(request_bytes),
        operational=operational, created_at=created_at, content_hash="", operational_hash="",
    )
    with_content = replace(provisional, content_hash=bridge_content_hash(provisional))
    return replace(with_content, operational_hash=bridge_operational_hash(with_content))


# --------------------------------------------------------------------------- #
# Correspondence attestation
# --------------------------------------------------------------------------- #


def build_correspondence_attestation(
    record: BridgedRequestRecord, *, attester_id: str, statement: str, attested_at: str,
) -> CorrespondenceAttestation:
    """Record one named operator's assertion about the prose/Lean correspondence.

    This is the only path by which the correspondence stops being unattested,
    and it still does not become verified. The attestation binds the payload
    hash and both Lean hashes, so editing either side after the fact leaves an
    attestation that no longer resolves.
    """
    issues = _Collector()
    instant = _instant(attested_at, "attested_at", issues)
    attester = _principal(attester_id, "attester_id", issues, required=True)
    text = statement if isinstance(statement, str) else ""
    if not text.strip():
        issues.add("missing_attestation_statement", "statement", "the attester must state what they read")
    elif len(text.encode("utf-8")) > MAX_ATTESTATION_STATEMENT_BYTES:
        issues.add("attestation_statement_too_large", "statement", f"maximum is {MAX_ATTESTATION_STATEMENT_BYTES} bytes")
    elif any(ord(character) < 32 and character != "\n" for character in text):
        issues.add("invalid_character", "statement", "control characters other than newline are forbidden")
    if record.payload_correspondence.bridge_correspondence_check != BRIDGE_CORRESPONDENCE_CHECK:
        issues.add("invalid_bridge_record", "bridge_correspondence_check", "the bridge record was rewritten")
    if record.content_hash != bridge_content_hash(record):
        issues.add("bridge_content_hash_mismatch", "content_hash", "the bridge record does not hash to its own identity")
    issues.raise_if_any()
    assert attester is not None
    body = {
        "attestation_id": "",
        "bridge_id": record.bridge_id.value,
        "request_canonical_hash": record.request_canonical_hash,
        "claim_id": record.request.claim_id.value,
        "attester_id": attester,
        "attester_role": ATTESTER_ROLE_OPERATOR,
        "basis": ATTESTATION_BASIS,
        "statement": text.strip(),
        "payload_hash": record.payload_correspondence.payload_hash,
        "target_statement_hash": record.payload_correspondence.target_statement_hash,
        "proof_fragment_hash": record.payload_correspondence.proof_fragment_hash,
        "attested_at": instant,
        "bridge_identity_version": BRIDGE_IDENTITY_VERSION,
    }
    provisional = CorrespondenceAttestation(
        attestation_id=stable_id("correspondence-attestation", body),
        bridge_id=record.bridge_id,
        request_canonical_hash=record.request_canonical_hash,
        claim_id=record.request.claim_id,
        attester_id=attester,
        statement=text.strip(),
        payload_hash=record.payload_correspondence.payload_hash,
        target_statement_hash=record.payload_correspondence.target_statement_hash,
        proof_fragment_hash=record.payload_correspondence.proof_fragment_hash,
        attested_at=instant,
        content_hash="",
    )
    return replace(provisional, content_hash=attestation_content_hash(provisional))


def resolve_correspondence(
    record_value: Mapping[str, Any], attestations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute the visible correspondence state from append-only records.

    Absent an attestation the answer is `unattested_operator_correspondence`.
    The state is never stored as a mutable column, so it cannot drift away from
    the records that justify it.
    """
    correspondence = record_value.get("payload_correspondence")
    payload_hash = correspondence.get("payload_hash") if isinstance(correspondence, Mapping) else None
    target_hash = correspondence.get("target_statement_hash") if isinstance(correspondence, Mapping) else None
    resolving = [
        item for item in attestations
        if item.get("payload_hash") == payload_hash and item.get("target_statement_hash") == target_hash
    ]
    stale = [item for item in attestations if item not in resolving]
    return {
        "bridge_id": record_value.get("bridge_id"),
        "bridge_correspondence_check": BRIDGE_CORRESPONDENCE_CHECK,
        "correspondence_state": CORRESPONDENCE_OPERATOR_ASSERTED if resolving else CORRESPONDENCE_UNATTESTED,
        "correspondence_machine_verified_by_this_slice": False,
        "attesters": sorted({str(item.get("attester_id")) for item in resolving}),
        "attestation_ids": sorted(str(item.get("attestation_id")) for item in resolving),
        "stale_attestation_ids": sorted(str(item.get("attestation_id")) for item in stale),
        "notice": CORRESPONDENCE_NOTICE,
    }


def validate_bridged_record_dict(value: Mapping[str, Any]) -> None:
    """Fail-closed admission check for a bridged-request record."""
    if value.get("record_type") != BRIDGE_RECORD_TYPE or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("bridged request record type or schema version is unsupported")
    if value.get("hash_profile") != BRIDGE_HASH_PROFILE:
        raise ValueError("bridged request hash profile mismatch")
    if value.get("disposition") != "proposal" or value.get("trust_effect") != "none":
        raise ValueError("bridged request violates the Phase 3B proposal-only contract")
    grants = value.get("trust_grants")
    if not isinstance(grants, Mapping) or set(grants) != set(public_value(TrustGrants())):
        raise ValueError("bridged request trust grants are malformed")
    if any(item is not False for item in grants.values()):
        raise ValueError("a bridged request attempted to grant an orthogonal trust decision")
    correspondence = value.get("payload_correspondence")
    if not isinstance(correspondence, Mapping):
        raise ValueError("bridged request carries no payload correspondence block")
    if correspondence.get("bridge_correspondence_check") != BRIDGE_CORRESPONDENCE_CHECK:
        raise ValueError("a bridged request claimed a correspondence check the bridge cannot perform")
    if correspondence.get("correspondence_state_at_build") != CORRESPONDENCE_UNATTESTED:
        raise ValueError("a bridged request was built with a correspondence state other than unattested")
    claim_identity = value.get("claim_identity")
    if not isinstance(claim_identity, Mapping) or claim_identity.get("claim_id_derived_from_lean") is not False:
        raise ValueError("a bridged request claimed its claim ID came from Lean")
    if claim_identity.get("claim_id_source") != "phase2_dossier.formalization.target_claim_id":
        raise ValueError("a bridged request claim ID came from an unrecognized source")
    request = value.get("request")
    if not isinstance(request, Mapping) or request.get("claim_id") != claim_identity.get("claim_id"):
        raise ValueError("bridged request claim ID does not match its recorded provenance")
    if value.get("content_hash") != bridge_content_hash(value):
        raise ValueError("bridged request content hash mismatch")
    if value.get("operational_hash") != bridge_operational_hash(value):
        raise ValueError("bridged request operational hash mismatch")


def validate_attestation_dict(value: Mapping[str, Any]) -> None:
    if value.get("record_type") != ATTESTATION_RECORD_TYPE or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("correspondence attestation record type or schema version is unsupported")
    if value.get("attester_role") != ATTESTER_ROLE_OPERATOR or value.get("basis") != ATTESTATION_BASIS:
        raise ValueError("correspondence attestation role or basis is unsupported")
    if value.get("bridge_correspondence_check") != BRIDGE_CORRESPONDENCE_CHECK:
        raise ValueError("an attestation claimed a correspondence check the bridge cannot perform")
    if value.get("correspondence_state") != CORRESPONDENCE_OPERATOR_ASSERTED:
        raise ValueError("correspondence attestation state is unsupported")
    if value.get("disposition") != "proposal" or value.get("trust_effect") != "none":
        raise ValueError("correspondence attestation violates the proposal-only contract")
    grants = value.get("trust_grants")
    if not isinstance(grants, Mapping) or any(item is not False for item in grants.values()):
        raise ValueError("an attestation attempted to grant an orthogonal trust decision")
    attester = value.get("attester_id")
    if not isinstance(attester, str) or not PRINCIPAL_PATTERN.fullmatch(attester):
        raise ValueError("correspondence attestation has no named attester")
    if value.get("content_hash") != attestation_content_hash(value):
        raise ValueError("correspondence attestation content hash mismatch")


def _exact(value: Any, cls: type, field: str) -> Mapping[str, Any]:
    """Fail closed on a missing or unknown key before anything is constructed."""
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, Mapping) or set(value) != expected:
        missing = sorted(expected - set(value if isinstance(value, Mapping) else {}))
        extra = sorted(set(value if isinstance(value, Mapping) else {}) - expected)
        raise ValueError(f"{field} does not match {cls.__name__}: missing={missing} unknown={extra}")
    return value


def parse_bridged_record(value: Mapping[str, Any]) -> BridgedRequestRecord:
    """Reconstruct an immutable record from its canonical JSON, fail-closed.

    The reconstruction is checked by re-serializing: if the rebuilt record is not
    byte-identical to the document it came from, the document is refused rather
    than repaired.
    """
    validate_bridged_record_dict(value)
    top = _exact(value, BridgedRequestRecord, "$")
    claim = _exact(top["claim_identity"], ClaimIdentityProvenance, "claim_identity")
    alignment = _exact(top["semantic_alignment"], SemanticAlignmentProvenance, "semantic_alignment")
    phase2 = _exact(top["phase2_proposal"], Phase2ProposalProvenance, "phase2_proposal")
    lean = _exact(top["lean_source"], LeanSourceProvenance, "lean_source")
    correspondence = _exact(top["payload_correspondence"], PayloadCorrespondence, "payload_correspondence")
    grants = _exact(top["trust_grants"], TrustGrants, "trust_grants")
    operational = _exact(top["operational"], BridgeOperationalContext, "operational")
    record = BridgedRequestRecord(
        bridge_id=OpaqueId(top["bridge_id"]),
        claim_identity=ClaimIdentityProvenance(
            claim_id=OpaqueId(claim["claim_id"]),
            claim_id_source=claim["claim_id_source"],
            claim_id_derived_from_lean=claim["claim_id_derived_from_lean"],
            problem_id=OpaqueId(claim["problem_id"]),
            formalization_id=OpaqueId(claim["formalization_id"]),
            dossier_id=OpaqueId(claim["dossier_id"]),
            dossier_hash=claim["dossier_hash"],
            formalization_statement_hash=claim["formalization_statement_hash"],
            formal_language=claim["formal_language"],
        ),
        semantic_alignment=SemanticAlignmentProvenance(
            semantic_alignment_id=OpaqueId(alignment["semantic_alignment_id"]),
            semantic_alignment_source=alignment["semantic_alignment_source"],
            status=alignment["status"],
            approved_by=alignment["approved_by"],
            compared_claim_id=OpaqueId(alignment["compared_claim_id"]),
            strength_relation=alignment["strength_relation"],
        ),
        phase2_proposal=Phase2ProposalProvenance(
            run_id=OpaqueId(phase2["run_id"]), run_status=phase2["run_status"],
            dossier_id=OpaqueId(phase2["dossier_id"]), dossier_hash=phase2["dossier_hash"],
            proposal_id=OpaqueId(phase2["proposal_id"]), proposal_kind=phase2["proposal_kind"],
            proposal_disposition=phase2["proposal_disposition"],
            proposal_source_kind=phase2["proposal_source_kind"],
            artifact_hash=phase2["artifact_hash"], artifact_media_type=phase2["artifact_media_type"],
            model_call_id=phase2["model_call_id"], payload_hash=phase2["payload_hash"],
            payload_target_claim_id=OpaqueId(phase2["payload_target_claim_id"]),
        ),
        lean_source=LeanSourceProvenance(
            source_kind=SourceKind(lean["source_kind"]), authored_by=lean["authored_by"],
            declaration_name=lean["declaration_name"],
            target_statement_hash=lean["target_statement_hash"],
            proof_fragment_hash=lean["proof_fragment_hash"],
            imports=tuple(lean["imports"]), assumption_names=tuple(lean["assumption_names"]),
            meaning_test_ids=tuple(lean["meaning_test_ids"]),
        ),
        payload_correspondence=PayloadCorrespondence(
            bridge_correspondence_check=correspondence["bridge_correspondence_check"],
            correspondence_state_at_build=correspondence["correspondence_state_at_build"],
            payload_hash=correspondence["payload_hash"],
            target_statement_hash=correspondence["target_statement_hash"],
            proof_fragment_hash=correspondence["proof_fragment_hash"],
            notice=correspondence["notice"],
        ),
        trust_grants=TrustGrants(**dict(grants)),
        request=parse_request(top["request"]),
        request_canonical_hash=top["request_canonical_hash"],
        request_bytes_hash=top["request_bytes_hash"],
        request_byte_length=top["request_byte_length"],
        operational=BridgeOperationalContext(**dict(operational)),
        created_at=top["created_at"],
        content_hash=top["content_hash"],
        operational_hash=top["operational_hash"],
        record_type=top["record_type"],
        disposition=top["disposition"],
        trust_effect=top["trust_effect"],
        hash_profile=top["hash_profile"],
        schema_version=top["schema_version"],
    )
    if public_value(record) != dict(value):
        raise ValueError("bridged request record is not canonical")
    return record


# --------------------------------------------------------------------------- #
# Durable append-only store
#
# A separate database file inside the Phase 3B workspace directory, with its own
# migration set. Nothing is added to `formal_check_attempts`, to the
# `migrations/phase3b/` sequence, or to `FormalCheckWorkspace`: a bridged request
# is an envelope with provenance, not evidence, and keeping it in its own file
# means this slice cannot collide with another Phase 3B slice's schema.
# --------------------------------------------------------------------------- #

BRIDGE_DATABASE_NAME = "bridge.sqlite3"
BRIDGE_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "phase3b-bridge"


class BridgeStore:
    """Append-only persistence for bridged requests and their attestations."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not BRIDGE_MIGRATIONS_DIR.is_dir():
            raise RuntimeError(f"no request-bridge migrations found in {BRIDGE_MIGRATIONS_DIR}")
        self.durable = SQLiteWorkspace(
            self.root / BRIDGE_DATABASE_NAME, migrations_dir=BRIDGE_MIGRATIONS_DIR,
        )
        self.connection = self.durable.connection

    def __enter__(self) -> "BridgeStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.durable.close()

    @property
    def migration_versions(self) -> tuple[str, ...]:
        return tuple(f"phase3b-bridge:{item}" for item in self.durable.migration_versions)

    def save_bridged_request(self, record: BridgedRequestRecord, *, request_bytes: bytes) -> None:
        """Persist one bridged request together with the exact bytes it wrote.

        Both request hashes are stored because both are needed to trace a finding
        home: `request_bytes_hash` matches the bytes handed to `phase3b check`,
        and `request_canonical_hash` matches `wrapper_manifest.source_hash`.
        """
        validate_bridged_record_dict(public_value(record))
        if sha256_bytes(request_bytes) != record.request_bytes_hash:
            raise ValueError("bridged request bytes do not match the recorded bytes hash")
        parsed = parse_request_bytes(request_bytes)
        if canonical_hash(parsed) != record.request_canonical_hash:
            raise ValueError("bridged request bytes do not match the recorded canonical hash")
        if canonical_json(parsed) != canonical_json(record.request):
            raise ValueError("bridged request bytes do not match the embedded request")
        payload = canonical_json(record)
        correspondence = record.payload_correspondence
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM bridged_requests WHERE bridge_id=?", (record.bridge_id.value,)
            ).fetchone()
            if existing:
                if existing["canonical_json"] != payload:
                    raise ValueError("bridged request ID cannot be rewritten")
                return
            connection.execute(
                "INSERT INTO bridged_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.bridge_id.value, record.schema_version, record.record_type, record.hash_profile,
                    record.request.request_id.value, record.request_bytes_hash, record.request_canonical_hash,
                    record.request.claim_id.value,
                    record.request.semantic_alignment_id.value if record.request.semantic_alignment_id else None,
                    record.lean_source.source_kind.value, record.phase2_proposal.run_id.value,
                    record.phase2_proposal.dossier_id.value, record.phase2_proposal.dossier_hash,
                    record.phase2_proposal.proposal_id.value, record.phase2_proposal.artifact_hash,
                    record.phase2_proposal.model_call_id, record.phase2_proposal.payload_hash,
                    correspondence.bridge_correspondence_check, correspondence.correspondence_state_at_build,
                    record.disposition, record.trust_effect, record.content_hash, record.operational_hash,
                    payload, canonical_json(parsed), record.created_at,
                ),
            )
            connection.execute(
                "INSERT INTO bridge_events(event_id,bridge_id,event_type,payload_hash,created_at,idempotency_key)"
                " VALUES(?,?,?,?,?,?)",
                (
                    f"event.{record.bridge_id.value}.bridged", record.bridge_id.value,
                    "bridged_request_recorded",
                    canonical_hash({"bridge_id": record.bridge_id, "content_hash": record.content_hash}),
                    record.created_at, f"bridged-request:{record.bridge_id.value}",
                ),
            )

    def save_correspondence_attestation(self, attestation: CorrespondenceAttestation) -> None:
        """Append one operator attestation. It never rewrites the bridge row."""
        validate_attestation_dict(public_value(attestation))
        payload = canonical_json(attestation)
        with self.durable.transaction() as connection:
            bridge = connection.execute(
                "SELECT canonical_json, request_canonical_hash FROM bridged_requests WHERE bridge_id=?",
                (attestation.bridge_id.value,),
            ).fetchone()
            if bridge is None:
                raise KeyError(attestation.bridge_id.value)
            if bridge["request_canonical_hash"] != attestation.request_canonical_hash:
                raise ValueError("attestation does not correspond to the stored bridged request")
            recorded = json.loads(bridge["canonical_json"])["payload_correspondence"]
            if (
                recorded["payload_hash"] != attestation.payload_hash
                or recorded["target_statement_hash"] != attestation.target_statement_hash
                or recorded["proof_fragment_hash"] != attestation.proof_fragment_hash
            ):
                raise ValueError("attestation hashes do not match the bridged request they name")
            existing = connection.execute(
                "SELECT canonical_json FROM bridge_correspondence_attestations WHERE attestation_id=?",
                (attestation.attestation_id.value,),
            ).fetchone()
            if existing:
                if existing["canonical_json"] != payload:
                    raise ValueError("correspondence attestation ID cannot be rewritten")
                return
            connection.execute(
                "INSERT INTO bridge_correspondence_attestations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    attestation.attestation_id.value, attestation.schema_version, attestation.record_type,
                    attestation.hash_profile, attestation.bridge_id.value, attestation.request_canonical_hash,
                    attestation.claim_id.value, attestation.attester_id, attestation.attester_role,
                    attestation.basis, attestation.bridge_correspondence_check,
                    attestation.correspondence_state, attestation.payload_hash,
                    attestation.target_statement_hash, attestation.proof_fragment_hash,
                    attestation.content_hash, payload, attestation.attested_at,
                ),
            )
            connection.execute(
                "INSERT INTO bridge_events(event_id,bridge_id,event_type,payload_hash,created_at,idempotency_key)"
                " VALUES(?,?,?,?,?,?)",
                (
                    f"event.{attestation.attestation_id.value}.attested", attestation.bridge_id.value,
                    "correspondence_attested",
                    canonical_hash({
                        "attestation_id": attestation.attestation_id,
                        "content_hash": attestation.content_hash,
                    }),
                    attestation.attested_at,
                    f"correspondence-attestation:{attestation.attestation_id.value}",
                ),
            )

    def bridged_request(self, bridge_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM bridged_requests WHERE bridge_id=?", (bridge_id,)
        ).fetchone()
        if row is None:
            raise KeyError(bridge_id)
        return json.loads(row["canonical_json"])

    def canonical_bridged_requests(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT canonical_json FROM bridged_requests ORDER BY bridge_id"
            )
        )

    def bridged_request_for_request_hash(self, request_hash: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT canonical_json FROM bridged_requests"
            " WHERE request_bytes_hash=? OR request_canonical_hash=? ORDER BY bridge_id LIMIT 1",
            (request_hash, request_hash),
        ).fetchone()
        return json.loads(row["canonical_json"]) if row else None

    def bridged_request_for_request_id(self, request_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT canonical_json FROM bridged_requests WHERE request_id=? ORDER BY bridge_id LIMIT 1",
            (request_id,),
        ).fetchone()
        return json.loads(row["canonical_json"]) if row else None

    def correspondence_attestations(self, bridge_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT canonical_json FROM bridge_correspondence_attestations"
                " WHERE bridge_id=? ORDER BY attestation_id",
                (bridge_id,),
            )
        )

    def correspondence_state(self, bridge_id: str) -> dict[str, Any]:
        """Resolve the state from records rather than from a mutable column."""
        return resolve_correspondence(
            self.bridged_request(bridge_id), self.correspondence_attestations(bridge_id),
        )


def trace_finding(*, findings: FindingSource, store: BridgeStore, finding_id: str) -> dict[str, Any]:
    """Trace one persisted finding back to the Phase 2 proposal it formalizes.

    An absent bridge is reported as absent. A hand-authored request checked
    directly has no lineage, and inventing one would be the exact defect this
    slice exists to prevent.
    """
    finding = findings.finding(finding_id)
    manifest = finding.get("wrapper_manifest")
    record: dict[str, Any] | None = None
    if isinstance(manifest, Mapping) and isinstance(manifest.get("source_hash"), str):
        record = store.bridged_request_for_request_hash(str(manifest["source_hash"]))
    if record is None and isinstance(finding.get("request_id"), str):
        record = store.bridged_request_for_request_id(str(finding["request_id"]))
    return {
        "finding_id": finding_id,
        "outcome": finding.get("outcome"),
        "claim_id": finding.get("claim_id"),
        "request_id": finding.get("request_id"),
        "epistemic_warrant_created": finding.get("epistemic_warrant_created"),
        "bridge_provenance": "absent" if record is None else "resolved",
        "bridge_id": None if record is None else record.get("bridge_id"),
        "phase2_provenance": None if record is None else record.get("phase2_proposal"),
        "correspondence": None if record is None else store.correspondence_state(str(record["bridge_id"])),
    }
