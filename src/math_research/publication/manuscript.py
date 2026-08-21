"""Manuscript record set: load, validate, and index.

The manuscript is the input record set, not the document. It carries claims,
attestations, certificates, sources, citations, obligations and an ordered
section/block structure. Every collection is keyed into one identifier namespace
so a block's ``record_refs`` resolve unambiguously, and every field set is
exact: a missing or unknown field is a refusal rather than a default.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import PublicationValidationError
from .latexsafe import escape_prose, validate_math, validate_verbatim
from .serialization import canonical_hash, text_hash
from ..novelty import NoveltyRecheckError, load_recheck, require_announcement_chain

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

MAX_MANUSCRIPT_BYTES = 4_194_304

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version", "manuscript_id", "title", "authors", "abstract",
        "corpus_provenance", "novelty", "significance", "publication_approval",
        "toolchain", "run_disclosure", "sources", "citations", "attestations", "certificates",
        "claims", "obligations", "sections", "render_probes",
    }
)

# Every attestation outcome the Phase 3B adapter can report. Only bare
# ``kernel_checked`` can reach the Theorem environment; the rest are listed so
# that an unknown outcome is a refusal instead of a silent demotion.
ATTESTATION_OUTCOMES = frozenset(
    {
        "kernel_checked",
        "kernel_checked_approved_standard_axioms",
        "kernel_checked_unapproved_assumptions",
        "policy_rejection",
        "elaboration_failure",
        "meaning_test_failure",
        "timeout",
        "output_limit",
        "sandbox_failure",
    }
)

REPRESENTATION_STATUSES = frozenset({"proposed", "partially_verified", "verified", "refuted"})
EXACT_ARITHMETIC = frozenset({"fractions-exact", "integer-exact", "algebraic-exact"})
#: What a certificate is being offered as evidence *for*. A zero gap determines
#: an optimum and separates nothing; a nonzero gap separates two values and
#: determines nothing. Reading either as the other is the mistake this field
#: forecloses, and both directions demote.
CERTIFICATE_ROLES = frozenset({"determines_optimum", "separates_values"})
CITATION_CLASSES = frozenset({"mathlib_declaration", "source_record", "unresolved_folklore"})
CITED_OBJECTS = frozenset({"work", "problem", "definition", "hypothesis", "lemma", "theorem"})
PASSAGE_REQUIRED_FOR = frozenset({"problem", "definition", "hypothesis", "lemma", "theorem"})
BLOCK_KINDS = frozenset({"prose", "claim", "display_math", "certificate_table"})
RIGHTS_PERMITTED = "permitted"
PROBE_OUTCOMES = frozenset({"refusal", "demotion"})
LEAN_VERIFICATION_STATUSES = frozenset({"pending", "kernel_checked", "failed"})
AI_GENERATOR = "AdaIvy project"
AI_GENERATORS = frozenset({
    AI_GENERATOR,
    "external Codex",
    "mixed external and AdaIvy campaign",
})


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PublicationValidationError("field_not_object", f"{field} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], required: frozenset[str], field: str) -> None:
    if set(value) != set(required):
        missing = sorted(required - set(value))
        unknown = sorted(set(value) - required)
        raise PublicationValidationError(
            "manuscript_field_set_mismatch",
            f"{field} missing={missing} unknown={unknown}",
        )


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise PublicationValidationError("identifier_malformed", f"{field}={value!r}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH.match(value):
        raise PublicationValidationError("content_hash_malformed", f"{field}={value!r}")
    return value


def _enum(value: Any, allowed: frozenset[str] | set[str], code: str, field: str) -> str:
    """Membership checks guard the type first: an unhashable value must produce a
    typed refusal, not a ``TypeError`` from the set lookup."""

    if not isinstance(value, str) or value not in allowed:
        raise PublicationValidationError(code, f"{field}={value!r}")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PublicationValidationError("field_not_boolean", f"{field} must be a boolean")
    return value


def _rational(value: Any, field: str) -> str:
    """Exact rational literals only. A decimal here is a float in disguise."""

    if not isinstance(value, str) or not re.match(r"^-?\d+(/\d+)?$", value):
        raise PublicationValidationError(
            "rational_not_exact", f"{field}={value!r} is not an exact rational literal"
        )
    return value


@dataclass(frozen=True, slots=True)
class Manuscript:
    value: Mapping[str, Any]
    sources: Mapping[str, Mapping[str, Any]]
    citations: Mapping[str, Mapping[str, Any]]
    attestations: Mapping[str, Mapping[str, Any]]
    certificates: Mapping[str, Mapping[str, Any]]
    claims: Mapping[str, Mapping[str, Any]]
    obligations: Mapping[str, Mapping[str, Any]]
    blocks: Mapping[str, Mapping[str, Any]]
    record_ids: frozenset[str]

    @property
    def manuscript_id(self) -> str:
        return str(self.value["manuscript_id"])

    @property
    def hash(self) -> str:
        return canonical_hash(self.value)


def _validate_source(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({"source_id", "content_hash", "authority", "rights", "bibliographic", "passages"}),
        field,
    )
    _identifier(value["source_id"], f"{field}.source_id")
    _hash(value["content_hash"], f"{field}.content_hash")
    _enum(
        value["authority"], {"source_provenance", "human_final"},
        "source_authority_insufficient", f"{field}.authority",
    )
    rights = _mapping(value["rights"], f"{field}.rights")
    _exact_fields(rights, frozenset({"publication", "excerpting"}), f"{field}.rights")
    bibliographic = _mapping(value["bibliographic"], f"{field}.bibliographic")
    _exact_fields(
        bibliographic,
        frozenset({"entry_type", "author", "title", "container", "year", "identifier"}),
        f"{field}.bibliographic",
    )
    _enum(
        bibliographic["entry_type"],
        {"article", "book", "inproceedings", "misc", "unpublished"},
        "bib_entry_type_unknown", f"{field}.bibliographic.entry_type",
    )
    for key in ("author", "title", "container", "identifier"):
        escape_prose(str(bibliographic[key]), f"{field}.bibliographic.{key}")
    if not re.match(r"^\d{4}$", str(bibliographic["year"])):
        raise PublicationValidationError("bib_year_malformed", f"{field}.bibliographic.year")
    passages = value["passages"]
    if not isinstance(passages, list):
        raise PublicationValidationError("field_not_array", f"{field}.passages")
    for index, passage in enumerate(passages):
        passage_field = f"{field}.passages[{index}]"
        _mapping(passage, passage_field)
        _exact_fields(
            passage,
            frozenset({"passage_id", "anchor", "content_hash", "quotation_permitted"}),
            passage_field,
        )
        _identifier(passage["passage_id"], f"{passage_field}.passage_id")
        _hash(passage["content_hash"], f"{passage_field}.content_hash")
        escape_prose(str(passage["anchor"]), f"{passage_field}.anchor")
        _bool(passage["quotation_permitted"], f"{passage_field}.quotation_permitted")


def _validate_citation(value: Mapping[str, Any], field: str) -> None:
    citation_class = _enum(
        value.get("citation_class"), CITATION_CLASSES, "citation_class_unknown",
        f"{field}.citation_class",
    )
    if citation_class == "mathlib_declaration":
        _exact_fields(
            value,
            frozenset({"citation_id", "citation_class", "declaration", "mathlib_commit"}),
            field,
        )
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.']*$", str(value["declaration"])):
            raise PublicationValidationError("mathlib_declaration_malformed", f"{field}.declaration")
        if not re.match(r"^[0-9a-f]{40}$", str(value["mathlib_commit"])):
            raise PublicationValidationError("mathlib_commit_malformed", f"{field}.mathlib_commit")
    elif citation_class == "source_record":
        _exact_fields(
            value,
            frozenset({
                "citation_id", "citation_class", "source_id", "passage_id", "cited_object",
                "intended_use",
            }),
            field,
        )
        _enum(value["cited_object"], CITED_OBJECTS, "cited_object_unknown", f"{field}.cited_object")
        if value["intended_use"] != "publication":
            raise PublicationValidationError(
                "citation_intended_use_unsupported",
                f"{field}.intended_use must be publication for a rendered citation",
            )
    else:
        _exact_fields(
            value,
            frozenset({"citation_id", "citation_class", "description", "obligation_id"}),
            field,
        )
        escape_prose(str(value["description"]), f"{field}.description")
    _identifier(value["citation_id"], f"{field}.citation_id")


def _validate_attestation(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({
            "attestation_id", "finding_id", "declaration_name", "outcome", "approved_axioms",
            "unapproved_assumptions", "target_statement_hash", "wrapper_hash", "runtime_hash",
            "lean_source",
        }),
        field,
    )
    _identifier(value["attestation_id"], f"{field}.attestation_id")
    _enum(value["outcome"], ATTESTATION_OUTCOMES, "attestation_outcome_unknown", f"{field}.outcome")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.']*$", str(value["declaration_name"])):
        raise PublicationValidationError("declaration_name_malformed", f"{field}.declaration_name")
    for key in ("approved_axioms", "unapproved_assumptions"):
        if not isinstance(value[key], list) or any(not isinstance(item, str) for item in value[key]):
            raise PublicationValidationError("field_not_string_array", f"{field}.{key}")
    for key in ("target_statement_hash", "wrapper_hash", "runtime_hash"):
        _hash(value[key], f"{field}.{key}")
    validate_verbatim(str(value["lean_source"]), f"{field}.lean_source")


def _validate_certificate(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({
            "certificate_id", "case_id", "run_id", "engine", "arithmetic", "float_used",
            "primal_value", "dual_value", "gap", "classification", "result_hash",
        }),
        field,
    )
    _identifier(value["certificate_id"], f"{field}.certificate_id")
    _enum(
        value["arithmetic"], EXACT_ARITHMETIC, "certificate_not_exact", f"{field}.arithmetic",
    )
    if _bool(value["float_used"], f"{field}.float_used"):
        raise PublicationValidationError(
            "certificate_not_exact", f"{field} reports floating-point arithmetic"
        )
    for key in ("primal_value", "dual_value", "gap"):
        _rational(value[key], f"{field}.{key}")
    _hash(value["result_hash"], f"{field}.result_hash")


def _validate_claim(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({
            "claim_id", "prose_statement", "latex_statement", "lean_statement",
            "representation_id", "representation_status", "attestation_id", "certificate_id",
            "certificate_role", "citations", "authorship", "lean_artifact",
            "original_problem_citation_id", "derivation",
        }),
        field,
    )
    _identifier(value["claim_id"], f"{field}.claim_id")
    escape_prose(str(value["prose_statement"]), f"{field}.prose_statement")
    validate_math(str(value["latex_statement"]), f"{field}.latex_statement")
    if value["lean_statement"] is not None:
        validate_verbatim(str(value["lean_statement"]), f"{field}.lean_statement")
    _enum(
        value["representation_status"], REPRESENTATION_STATUSES,
        "representation_status_unknown", f"{field}.representation_status",
    )
    if not isinstance(value["citations"], list):
        raise PublicationValidationError("field_not_array", f"{field}.citations")
    for key in ("attestation_id", "certificate_id"):
        if value[key] is not None:
            _identifier(value[key], f"{field}.{key}")
    original_problem = value["original_problem_citation_id"]
    if original_problem is not None:
        _identifier(original_problem, f"{field}.original_problem_citation_id")
    derivation = _mapping(value["derivation"], f"{field}.derivation")
    _exact_fields(
        derivation, frozenset({"status", "summary", "citations"}), f"{field}.derivation"
    )
    _enum(
        derivation["status"], {"included", "unavailable"},
        "derivation_status_unknown", f"{field}.derivation.status",
    )
    summary = escape_prose(str(derivation["summary"]), f"{field}.derivation.summary")
    if not summary.strip():
        raise PublicationValidationError(
            "derivation_summary_empty", f"{field}.derivation.summary"
        )
    if not isinstance(derivation["citations"], list):
        raise PublicationValidationError("field_not_array", f"{field}.derivation.citations")
    for citation_id in derivation["citations"]:
        _identifier(citation_id, f"{field}.derivation.citations")
    role = value["certificate_role"]
    if role is not None:
        _enum(role, CERTIFICATE_ROLES, "certificate_role_unknown", f"{field}.certificate_role")
    if (value["certificate_id"] is None) != (role is None):
        raise PublicationValidationError(
            "certificate_role_unpaired",
            f"{field} must name a certificate and a role together or neither; a certificate "
            "whose role is unstated cannot be read as supporting anything",
        )
    authorship = _mapping(value["authorship"], f"{field}.authorship")
    _exact_fields(
        authorship, frozenset({"ai_generated", "generator"}), f"{field}.authorship"
    )
    ai_generated = _bool(authorship["ai_generated"], f"{field}.authorship.ai_generated")
    escape_prose(str(authorship["generator"]), f"{field}.authorship.generator")
    if ai_generated and authorship["generator"] not in AI_GENERATORS:
        raise PublicationValidationError(
            "ai_generator_mismatch",
            f"{field}.authorship.generator must identify an admitted derived origin "
            "when ai_generated is true",
        )
    artifact = value["lean_artifact"]
    if artifact is not None:
        artifact_field = f"{field}.lean_artifact"
        artifact = _mapping(artifact, artifact_field)
        _exact_fields(
            artifact,
            frozenset({
                "artifact_id", "declaration_name", "source", "source_hash",
                "verification_status", "finding_id",
            }),
            artifact_field,
        )
        _identifier(artifact["artifact_id"], f"{artifact_field}.artifact_id")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.']*$", str(artifact["declaration_name"])):
            raise PublicationValidationError(
                "declaration_name_malformed", f"{artifact_field}.declaration_name"
            )
        source = validate_verbatim(str(artifact["source"]), f"{artifact_field}.source")
        if not source.strip():
            raise PublicationValidationError("lean_artifact_empty", artifact_field)
        _hash(artifact["source_hash"], f"{artifact_field}.source_hash")
        if text_hash(source) != artifact["source_hash"]:
            raise PublicationValidationError(
                "lean_artifact_hash_mismatch",
                f"{artifact_field}.source_hash does not cover the exact source bytes",
            )
        status = _enum(
            artifact["verification_status"], LEAN_VERIFICATION_STATUSES,
            "lean_verification_status_unknown", f"{artifact_field}.verification_status",
        )
        finding_id = artifact["finding_id"]
        if finding_id is not None:
            _identifier(finding_id, f"{artifact_field}.finding_id")
        if status == "pending" and finding_id is not None:
            raise PublicationValidationError(
                "pending_lean_artifact_has_finding",
                f"{artifact_field} is pending but names a formal finding",
            )
        if status != "pending" and finding_id is None:
            raise PublicationValidationError(
                "lean_artifact_finding_required",
                f"{artifact_field} status {status!r} requires a formal finding id",
            )


def _validate_obligation(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value, frozenset({"obligation_id", "statement", "status", "reason"}), field
    )
    _identifier(value["obligation_id"], f"{field}.obligation_id")
    _enum(
        value["status"], {"open", "blocked", "discharged", "waived"},
        "obligation_status_unknown", f"{field}.status",
    )
    escape_prose(str(value["statement"]), f"{field}.statement")
    escape_prose(str(value["reason"]), f"{field}.reason")


def _validate_block(value: Mapping[str, Any], field: str) -> None:
    kind = _enum(value.get("kind"), BLOCK_KINDS, "block_kind_unknown", f"{field}.kind")
    if kind == "prose":
        _exact_fields(
            value, frozenset({"block_id", "kind", "record_refs", "runs", "citations"}), field
        )
        runs = value["runs"]
        if not isinstance(runs, list) or not runs:
            raise PublicationValidationError("prose_block_empty", f"{field}.runs")
        for index, run in enumerate(runs):
            run_field = f"{field}.runs[{index}]"
            _mapping(run, run_field)
            _exact_fields(run, frozenset({"t", "v"}), run_field)
            if run["t"] == "text":
                escape_prose(str(run["v"]), f"{run_field}.v")
            elif run["t"] == "math":
                validate_math(str(run["v"]), f"{run_field}.v")
            else:
                raise PublicationValidationError("prose_run_kind_unknown", f"{run_field}.t")
        if not isinstance(value["citations"], list):
            raise PublicationValidationError("field_not_array", f"{field}.citations")
    elif kind == "claim":
        _exact_fields(value, frozenset({"block_id", "kind", "record_refs", "claim_id"}), field)
    elif kind == "display_math":
        _exact_fields(value, frozenset({"block_id", "kind", "record_refs", "latex", "caption"}), field)
        validate_math(str(value["latex"]), f"{field}.latex")
        escape_prose(str(value["caption"]), f"{field}.caption")
    else:
        _exact_fields(
            value, frozenset({"block_id", "kind", "record_refs", "certificate_id"}), field
        )
    _identifier(value["block_id"], f"{field}.block_id")
    refs = value["record_refs"]
    if not isinstance(refs, list) or not refs:
        raise PublicationValidationError(
            "block_without_record_ref",
            f"{field} carries no record reference; the ledger cannot admit it",
        )


def _validate_probe(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({"probe_id", "field", "value", "expected_outcome", "expected", "rationale"}),
        field,
    )
    _identifier(value["probe_id"], f"{field}.probe_id")
    _enum(
        value["expected_outcome"], PROBE_OUTCOMES, "probe_outcome_unknown",
        f"{field}.expected_outcome",
    )
    if not isinstance(value["field"], str) or not value["field"]:
        raise PublicationValidationError("probe_field_malformed", f"{field}.field")
    expected = value["expected"]
    if not isinstance(expected, dict):
        raise PublicationValidationError("probe_expectation_malformed", f"{field}.expected")
    if value["expected_outcome"] == "refusal":
        if set(expected) != {"code"}:
            raise PublicationValidationError("probe_expectation_malformed", f"{field}.expected")
    elif set(expected) != {"claim_id", "evidence_class"}:
        raise PublicationValidationError("probe_expectation_malformed", f"{field}.expected")
    escape_prose(str(value["rationale"]), f"{field}.rationale")


def _validate_run_disclosure(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value,
        frozenset({
            "run_id", "usage_scope", "measurement_status", "models", "model_calls",
            "cost_usd", "budget_cap_usd", "input_tokens", "output_tokens", "total_tokens",
            "note",
        }),
        field,
    )
    _identifier(value["run_id"], f"{field}.run_id")
    escape_prose(str(value["usage_scope"]), f"{field}.usage_scope")
    _enum(
        value["measurement_status"], {"complete", "partial", "unavailable"},
        "usage_measurement_status_unknown", f"{field}.measurement_status",
    )
    models = value["models"]
    if not isinstance(models, list) or not models:
        raise PublicationValidationError("model_disclosure_empty", f"{field}.models")
    for index, model in enumerate(models):
        model_field = f"{field}.models[{index}]"
        _mapping(model, model_field)
        _exact_fields(
            model, frozenset({"provider", "model", "calls", "outcome"}), model_field
        )
        for key in ("provider", "model", "outcome"):
            escape_prose(str(model[key]), f"{model_field}.{key}")
        if not isinstance(model["calls"], int) or isinstance(model["calls"], bool) or model["calls"] < 0:
            raise PublicationValidationError("usage_count_invalid", f"{model_field}.calls")
    for key in ("model_calls", "input_tokens", "output_tokens", "total_tokens"):
        item = value[key]
        if item is not None and (
            not isinstance(item, int) or isinstance(item, bool) or item < 0
        ):
            raise PublicationValidationError("usage_count_invalid", f"{field}.{key}")
    if value["model_calls"] is not None and value["model_calls"] != sum(
        int(model["calls"]) for model in models
    ):
        raise PublicationValidationError("model_call_total_mismatch", field)
    if all(value[key] is not None for key in ("input_tokens", "output_tokens", "total_tokens")):
        if value["total_tokens"] != value["input_tokens"] + value["output_tokens"]:
            raise PublicationValidationError("token_total_mismatch", field)
    for key in ("cost_usd", "budget_cap_usd"):
        item = value[key]
        if item is not None and not re.match(r"^\d+(\.\d{1,6})?$", str(item)):
            raise PublicationValidationError("usd_amount_invalid", f"{field}.{key}")
    if value["measurement_status"] == "complete":
        required_usage = (
            "model_calls", "cost_usd", "input_tokens",
            "output_tokens", "total_tokens",
        )
        if any(value[key] is None for key in required_usage):
            raise PublicationValidationError(
                "complete_usage_has_missing_value",
                f"{field} is complete but omits one of {required_usage}",
            )
    escape_prose(str(value["note"]), f"{field}.note")


def _collection(
    value: Mapping[str, Any], key: str, id_field: str, validator: Any, seen: set[str]
) -> dict[str, Mapping[str, Any]]:
    items = value[key]
    if not isinstance(items, list):
        raise PublicationValidationError("field_not_array", key)
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(items):
        field = f"{key}[{index}]"
        _mapping(item, field)
        validator(item, field)
        identifier = str(item[id_field])
        if identifier in seen:
            raise PublicationValidationError(
                "identifier_not_unique", f"{identifier} appears in more than one collection"
            )
        seen.add(identifier)
        indexed[identifier] = item
    return indexed


def load_manuscript(payload: bytes | str | Mapping[str, Any]) -> Manuscript:
    if isinstance(payload, (bytes, str)):
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        if len(raw) > MAX_MANUSCRIPT_BYTES:
            raise PublicationValidationError(
                "manuscript_too_large", f"{len(raw)} bytes exceeds {MAX_MANUSCRIPT_BYTES}"
            )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PublicationValidationError("manuscript_not_json", str(error)) from error
    else:
        value = json.loads(json.dumps(payload))
    _mapping(value, "manuscript")
    _exact_fields(value, TOP_LEVEL_FIELDS, "manuscript")
    if value["schema_version"] != "1.3.0":
        raise PublicationValidationError(
            "manuscript_schema_unsupported", f"schema_version={value['schema_version']!r}"
        )
    _identifier(value["manuscript_id"], "manuscript.manuscript_id")
    escape_prose(str(value["title"]), "manuscript.title")
    escape_prose(str(value["abstract"]), "manuscript.abstract")
    _validate_run_disclosure(_mapping(value["run_disclosure"], "manuscript.run_disclosure"), "manuscript.run_disclosure")
    if value["corpus_provenance"] != "project_authored":
        raise PublicationValidationError(
            "corpus_provenance_unsupported",
            "only project_authored corpora are recordable in this slice",
        )
    for key in ("novelty", "significance"):
        assessment = _mapping(value[key], f"manuscript.{key}")
        _exact_fields(assessment, frozenset({"status", "inferred_from_warrant"}), f"manuscript.{key}")
        if assessment["status"] != "not_assessed" or assessment["inferred_from_warrant"] is not False:
            raise PublicationValidationError(
                "assessment_not_withheld",
                f"manuscript.{key} must stay not_assessed and never inferred from a warrant",
            )
    if value["publication_approval"] is not None:
        approval = _mapping(value["publication_approval"], "manuscript.publication_approval")
        _exact_fields(
            approval,
            frozenset({
                "approval_id", "approver", "authority", "recorded_at",
                "novelty_rechecks",
            }),
            "manuscript.publication_approval",
        )
        _identifier(approval["approval_id"], "manuscript.publication_approval.approval_id")
        _identifier(approval["approver"], "manuscript.publication_approval.approver")
        if approval["authority"] != "human_final":
            raise PublicationValidationError(
                "publication_approval_authority_insufficient",
                "publication approval requires human_final authority",
            )
    authors = value["authors"]
    if not isinstance(authors, list) or not authors:
        raise PublicationValidationError("authors_missing", "manuscript.authors")
    for index, author in enumerate(authors):
        field = f"manuscript.authors[{index}]"
        _mapping(author, field)
        _exact_fields(author, frozenset({"name", "role"}), field)
        escape_prose(str(author["name"]), f"{field}.name")
        escape_prose(str(author["role"]), f"{field}.role")
    toolchain = _mapping(value["toolchain"], "manuscript.toolchain")
    _exact_fields(
        toolchain,
        frozenset({"elan_version", "lean_version", "lean_commit", "mathlib_version", "mathlib_commit"}),
        "manuscript.toolchain",
    )
    for key in ("lean_commit", "mathlib_commit"):
        if not re.match(r"^[0-9a-f]{40}$", str(toolchain[key])):
            raise PublicationValidationError("toolchain_commit_malformed", f"manuscript.toolchain.{key}")

    seen: set[str] = set()
    sources = _collection(value, "sources", "source_id", _validate_source, seen)
    for source in sources.values():
        for passage in source["passages"]:
            identifier = str(passage["passage_id"])
            if identifier in seen:
                raise PublicationValidationError(
                    "identifier_not_unique", f"{identifier} appears in more than one collection"
                )
            seen.add(identifier)
    citations = _collection(value, "citations", "citation_id", _validate_citation, seen)
    attestations = _collection(value, "attestations", "attestation_id", _validate_attestation, seen)
    certificates = _collection(value, "certificates", "certificate_id", _validate_certificate, seen)
    claims = _collection(value, "claims", "claim_id", _validate_claim, seen)
    for claim in claims.values():
        artifact = claim["lean_artifact"]
        if artifact is None:
            continue
        artifact_id = str(artifact["artifact_id"])
        if artifact_id in seen:
            raise PublicationValidationError(
                "identifier_not_unique", f"{artifact_id} appears in more than one collection"
            )
        seen.add(artifact_id)
    obligations = _collection(value, "obligations", "obligation_id", _validate_obligation, seen)

    sections = value["sections"]
    if not isinstance(sections, list) or not sections:
        raise PublicationValidationError("sections_missing", "manuscript.sections")
    blocks: dict[str, Mapping[str, Any]] = {}
    for index, section in enumerate(sections):
        field = f"sections[{index}]"
        _mapping(section, field)
        _exact_fields(section, frozenset({"section_id", "title", "blocks"}), field)
        _identifier(section["section_id"], f"{field}.section_id")
        escape_prose(str(section["title"]), f"{field}.title")
        if section["section_id"] in seen:
            raise PublicationValidationError(
                "identifier_not_unique", f"{section['section_id']} appears in more than one collection"
            )
        seen.add(str(section["section_id"]))
        if not isinstance(section["blocks"], list) or not section["blocks"]:
            raise PublicationValidationError("section_empty", f"{field}.blocks")
        for block_index, block in enumerate(section["blocks"]):
            block_field = f"{field}.blocks[{block_index}]"
            _mapping(block, block_field)
            _validate_block(block, block_field)
            identifier = str(block["block_id"])
            if identifier in seen:
                raise PublicationValidationError(
                    "identifier_not_unique", f"{identifier} appears in more than one collection"
                )
            seen.add(identifier)
            blocks[identifier] = block

    for index, probe in enumerate(value["render_probes"]):
        field = f"render_probes[{index}]"
        _mapping(probe, field)
        _validate_probe(probe, field)

    record_ids = frozenset(
        set(sources) | set(citations) | set(attestations) | set(certificates)
        | set(claims) | set(obligations)
    )
    manuscript = Manuscript(
        value=value, sources=sources, citations=citations, attestations=attestations,
        certificates=certificates, claims=claims, obligations=obligations, blocks=blocks,
        record_ids=record_ids,
    )
    _validate_references(manuscript)
    _validate_announcement_novelty_gate(manuscript)
    return manuscript


def _announcement_subject_hash(manuscript: Manuscript) -> str:
    """Bind the final re-check to every exact result statement in the bundle."""

    return canonical_hash({
        "manuscript_id": manuscript.manuscript_id,
        "claims": [
            {
                "claim_id": claim_id,
                "prose_statement": claim["prose_statement"],
                "latex_statement": claim["latex_statement"],
                "lean_statement": claim["lean_statement"],
                "original_problem_citation_id": claim["original_problem_citation_id"],
            }
            for claim_id, claim in sorted(manuscript.claims.items())
        ],
    })


def _validate_announcement_novelty_gate(manuscript: Manuscript) -> None:
    approval = manuscript.value["publication_approval"]
    if approval is None:
        return
    records = approval["novelty_rechecks"]
    if not isinstance(records, list) or len(records) != 2:
        raise PublicationValidationError(
            "announcement_novelty_rechecks_required",
            "publication approval requires the pre-research and fresh pre-announcement re-checks",
        )
    try:
        start, announcement = (load_recheck(item) for item in records)
        require_announcement_chain(
            start, announcement, subject_id=manuscript.manuscript_id,
            subject_hash=_announcement_subject_hash(manuscript),
            approval_id=approval["approval_id"], approval_at=approval["recorded_at"],
        )
    except NoveltyRecheckError as error:
        raise PublicationValidationError("announcement_novelty_recheck_invalid", str(error)) from error


def _validate_references(manuscript: Manuscript) -> None:
    """Cross-collection closure. Every reference resolves or the load refuses."""

    for block_id, block in manuscript.blocks.items():
        for ref in block["record_refs"]:
            if ref not in manuscript.record_ids:
                raise PublicationValidationError(
                    "record_ref_unresolved", f"block {block_id} references {ref!r}"
                )
        if block["kind"] == "claim" and block["claim_id"] not in manuscript.claims:
            raise PublicationValidationError(
                "record_ref_unresolved", f"block {block_id} names claim {block['claim_id']!r}"
            )
        if block["kind"] == "certificate_table" and block["certificate_id"] not in manuscript.certificates:
            raise PublicationValidationError(
                "record_ref_unresolved",
                f"block {block_id} names certificate {block['certificate_id']!r}",
            )
        for citation_id in block.get("citations", ()):
            if citation_id not in manuscript.citations:
                raise PublicationValidationError(
                    "citation_not_declared", f"block {block_id} cites {citation_id!r}"
                )
            citation = manuscript.citations[citation_id]
            if citation["citation_class"] == "unresolved_folklore":
                raise PublicationValidationError(
                    "folklore_citation_in_prose",
                    f"block {block_id} cites unrecorded background {citation_id!r}; it belongs "
                    "in the obligations table, not in prose",
                )

    for claim_id, claim in manuscript.claims.items():
        citation_fields = [
            *claim["citations"], *claim["derivation"]["citations"],
            *([claim["original_problem_citation_id"]]
              if claim["original_problem_citation_id"] is not None else []),
        ]
        for citation_id in citation_fields:
            if citation_id not in manuscript.citations:
                raise PublicationValidationError(
                    "citation_not_declared", f"claim {claim_id} cites {citation_id!r}"
                )
            if manuscript.citations[citation_id]["citation_class"] == "unresolved_folklore":
                raise PublicationValidationError(
                    "folklore_citation_in_prose",
                    f"claim {claim_id} cites unrecorded background {citation_id!r}; it belongs "
                    "in the obligations table, not beside a claim",
                )
        original_problem = claim["original_problem_citation_id"]
        if original_problem is not None:
            citation = manuscript.citations[original_problem]
            if (
                citation["citation_class"] != "source_record"
                or citation["cited_object"] != "problem"
            ):
                raise PublicationValidationError(
                    "original_problem_citation_invalid",
                    f"claim {claim_id} must cite a located source_record problem",
                )
        attestation_id = claim["attestation_id"]
        if attestation_id is not None:
            if attestation_id not in manuscript.attestations:
                raise PublicationValidationError(
                    "record_ref_unresolved", f"claim {claim_id} names attestation {attestation_id!r}"
                )
            if claim["lean_statement"] is None:
                raise PublicationValidationError(
                    "attestation_without_lean_statement",
                    f"claim {claim_id} is attested but carries no Lean statement to bind it to",
                )
            expected = text_hash(str(claim["lean_statement"]))
            recorded = manuscript.attestations[attestation_id]["target_statement_hash"]
            if expected != recorded:
                raise PublicationValidationError(
                    "lean_statement_hash_mismatch",
                    f"claim {claim_id} hashes to {expected} but attestation {attestation_id} "
                    f"covers {recorded}",
                )
        certificate_id = claim["certificate_id"]
        if certificate_id is not None and certificate_id not in manuscript.certificates:
            raise PublicationValidationError(
                "record_ref_unresolved", f"claim {claim_id} names certificate {certificate_id!r}"
            )
        artifact = claim["lean_artifact"]
        if artifact is not None:
            attestation_id = claim["attestation_id"]
            if artifact["verification_status"] == "kernel_checked":
                if attestation_id is None:
                    raise PublicationValidationError(
                        "kernel_checked_artifact_without_attestation",
                        f"claim {claim_id} has no attestation backing its artifact status",
                    )
                attestation = manuscript.attestations[str(attestation_id)]
                if artifact["finding_id"] != attestation["finding_id"]:
                    raise PublicationValidationError(
                        "lean_artifact_finding_mismatch",
                        f"claim {claim_id} artifact finding differs from attestation {attestation_id}",
                    )
                if artifact["source"] != attestation["lean_source"]:
                    raise PublicationValidationError(
                        "lean_artifact_attestation_source_mismatch",
                        f"claim {claim_id} artifact bytes differ from the attested source",
                    )

    passages = {
        str(passage["passage_id"]): (source_id, passage)
        for source_id, source in manuscript.sources.items()
        for passage in source["passages"]
    }
    for citation_id, citation in manuscript.citations.items():
        if citation["citation_class"] == "source_record":
            source_id = citation["source_id"]
            if source_id not in manuscript.sources:
                raise PublicationValidationError(
                    "citation_without_source_record",
                    f"citation {citation_id} names source {source_id!r}, which has no record",
                )
            source = manuscript.sources[source_id]
            if source["rights"]["publication"] != RIGHTS_PERMITTED:
                raise PublicationValidationError(
                    "rights_outcome_forbids_use",
                    f"citation {citation_id} needs publication rights on {source_id}; "
                    f"the record says {source['rights']['publication']!r}",
                )
            passage_id = citation["passage_id"]
            if citation["cited_object"] in PASSAGE_REQUIRED_FOR and passage_id is None:
                raise PublicationValidationError(
                    "lemma_citation_without_passage",
                    f"citation {citation_id} cites a {citation['cited_object']} at work level; "
                    "a located passage is required because the paper can exist while the "
                    "cited statement does not",
                )
            if passage_id is not None:
                if passage_id not in passages or passages[passage_id][0] != source_id:
                    raise PublicationValidationError(
                        "record_ref_unresolved",
                        f"citation {citation_id} names passage {passage_id!r} of {source_id}",
                    )
                if not passages[passage_id][1]["quotation_permitted"]:
                    if source["rights"]["excerpting"] != RIGHTS_PERMITTED:
                        raise PublicationValidationError(
                            "passage_quotation_not_permitted",
                            f"citation {citation_id} locates {passage_id} but neither the passage "
                            "nor the source permits excerpting",
                        )
        elif citation["citation_class"] == "unresolved_folklore":
            obligation_id = citation["obligation_id"]
            if obligation_id not in manuscript.obligations:
                raise PublicationValidationError(
                    "record_ref_unresolved",
                    f"citation {citation_id} names obligation {obligation_id!r}",
                )
            if manuscript.obligations[obligation_id]["status"] != "open":
                raise PublicationValidationError(
                    "folklore_without_open_obligation",
                    f"citation {citation_id} is unrecorded background, so obligation "
                    f"{obligation_id} must stay open",
                )
        else:
            recorded = manuscript.value["toolchain"]["mathlib_commit"]
            if citation["mathlib_commit"] != recorded:
                raise PublicationValidationError(
                    "mathlib_commit_mismatch",
                    f"citation {citation_id} pins {citation['mathlib_commit']} but the manuscript "
                    f"toolchain pins {recorded}",
                )


def manuscript_hash(payload: bytes | str | Mapping[str, Any]) -> str:
    return load_manuscript(payload).hash


def read_manuscript(path: Path) -> Manuscript:
    return load_manuscript(path.read_bytes())
