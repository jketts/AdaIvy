"""Manuscript record set: load, validate, and index.

The manuscript is the input record set, not the document. It carries claims,
attestations, certificates, sources, citations, obligations and an ordered
section/block structure. Every collection is keyed into one identifier namespace
so a block's ``record_refs`` resolve unambiguously, and every field set is
exact: a missing or unknown field is a refusal rather than a default.

Schema 1.4.0 moves three questions that used to be answerable only by reading
prose into the record set, and puts each of them upstream of the proposition
rather than downstream of it (ADR-0058, ADR-0059, ADR-0060).

* **Which reading is this claim asserted under?** A claim naming a
  ``resolution_target`` is *resolution-typed*, and a resolution-typed claim must
  name a ``verdict_matrix_id`` bound to a convention record carried in the same
  manuscript. The reader-facing scope is derived by
  :func:`math_research.conventions.classify_scope` from that matrix; nothing here
  supplies it.
* **Was the competing candidate compared?** Citing an acquired work is
  engagement with the target problem *by default*, including whenever the
  question cannot be decided. Escaping the replay obligation takes an
  attributable ``target_exclusion`` record naming a reason from a closed
  vocabulary, and a ``prior_resolution_candidate`` can never be excluded at all.
  Silence triggers the gate; it never satisfies it.
* **Did anyone actually read the source?** A passage separates the bytes we hold
  (``content_hash``) from how well we read them (``extraction_method``,
  ``reading_status``, ``verbatim_text``, ``verbatim_hash``). A reading in a
  convention record may not claim a status stronger than the passage it is drawn
  from, and a reading the reader may not be shown is, for the reader, asserted.

Every rule here demotes or refuses. No field added in 1.4.0 can promote a claim,
create warrant, assert novelty or significance, or approve semantic alignment.
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
from ..conventions import (
    READING_STATUSES,
    READING_STATUS_ORDER,
    ConventionError,
    ConventionRecord,
    VerdictMatrix,
    load_convention,
    load_verdict_matrix,
    require_convention_binding,
    weakest_reading_status,
)
from ..conventions import VERDICTS as READING_VERDICTS
from ..novelty import (
    NoveltyRecheck,
    NoveltyRecheckError,
    load_recheck,
    require_announcement_chain,
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

MAX_MANUSCRIPT_BYTES = 4_194_304

#: ADR-0058 and ADR-0060 replace and add required fields on a fail-closed path,
#: so the version moves with them. Two field sets under one version is the
#: mixed-schema case this repository refuses.
SCHEMA_VERSION = "1.4.0"

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version", "manuscript_id", "title_stem", "authors", "abstract",
        "corpus_provenance", "novelty", "significance", "publication_approval",
        "toolchain", "run_disclosure", "sources", "citations", "attestations", "certificates",
        "claims", "obligations", "sections", "render_probes",
        "conventions", "verdict_matrices", "counter_candidate_replays",
        "prior_art_engagement", "novelty_rechecks",
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
CITED_OBJECTS = frozenset({
    "work", "problem", "definition", "hypothesis", "lemma", "theorem",
    # ADR-0059. A work that publishes its own candidate resolution of the same
    # conjecture. It is the strongest available signal that a comparison is owed,
    # so it is the one cited object that no exclusion record can talk down.
    "prior_resolution_candidate",
})
PASSAGE_REQUIRED_FOR = frozenset({
    "problem", "definition", "hypothesis", "lemma", "theorem",
    "prior_resolution_candidate",
})

#: ADR-0058 section 4.2. Frozen, shared with the renderer, matched
#: case-insensitively on word boundaries. ``source-faithful`` is here
#: deliberately: it is a semantic claim wearing a provenance claim's clothes.
#: Under amendment A2 it carries its own refusal code, computed from reading
#: statuses alone, so an author is told which rule they broke.
RESOLUTION_LEXICON = (
    "counterexample", "counter-example", "refutation", "refutes", "refuted",
    "disproof", "disproves", "resolves", "resolved", "settles", "settled",
    "proof of", "proves", "solves", "solved", "source-faithful",
)
SOURCE_FIDELITY_PHRASE = "source-faithful"

#: ADR-0059. Text asserting that a literature search happened. The rule mirrors
#: ``bibliography.py``: an uncited bibliography implies reading that did not
#: happen, and unbacked prose about a search is worse than silence because it
#: reads as diligence.
SEARCH_LEXICON = (
    "search", "searched", "found no", "no prior", "literature review",
    "prior art", "pre-research review",
)

#: Amendment B6. Claim prose is mathematical exposition, not a headline, and the
#: two honest uses of a resolution word there are a hedge ("a *candidate*
#: counterexample") and a denial ("this repository holds *no* proof of the
#: statement"). Both appear in the shipped fixtures. A screen that refused them
#: would force every author to paraphrase around the standard technical term,
#: which is a rule nobody would keep, so an occurrence is discounted when one of
#: these tokens stands within two words in front of it.
#:
#: Named boundary: the window is two tokens and the vocabulary is frozen, so
#: "no doubt this is a counterexample" is discounted and this screen does not see
#: it. It is a screen on author prose, never a promotion path -- nothing here can
#: raise an evidence class, a scope, or a derived title -- and the headline text
#: it does not cover (``title_stem`` and ``abstract``) stays strict, because the
#: headline is the one string a summary keeps.
NON_ASSERTIVE_QUALIFIERS = frozenset({
    "candidate", "candidates", "claimed", "conjectural", "conjectured", "never",
    "no", "not", "possible", "proposed", "purported", "putative", "reported",
    "unverified", "without",
})
QUALIFIER_WINDOW = 2

RESOLUTION_TARGET_KINDS = frozenset({"refutation", "proof"})

#: Amendment A1. Derived, never declared: a citation *addresses the target* by
#: default and whenever the question cannot be decided. The declared boolean this
#: replaces let ``false`` escape a demotion by omission, which is promotion.
TARGET_ENGAGEMENT = ("addresses_target", "excluded_by_record")
EXCLUSION_REASONS = (
    "different_conjecture", "different_object_class",
    "cited_for_method_only", "cited_for_definition_only",
)
UNEXCLUDABLE_CITED_OBJECTS = frozenset({"prior_resolution_candidate"})

#: ADR-0060. By what means the bytes became characters, and how reproducible the
#: resulting text is. The two are separate axes: ``extraction_method`` is not a
#: quality score, it records the mechanism a reader must repeat.
EXTRACTION_METHODS = frozenset({"text_layer", "ocr", "manual_transcription", "unextractable"})
#: Amendment A8 as corrected by amendment B2 and ADR-0060, stated as data rather
#: than left to prose. ``unextractable`` admits only ``asserted``. ``ocr`` and
#: ``manual_transcription`` admit ``transcribed`` or ``asserted`` and never
#: ``verbatim_confirmed``: a hand transcription cannot be re-derived from the
#: file, so calling it byte-confirmed overclaims exactly the distinction this
#: change exists to draw. Only ``text_layer`` admits every status, because only
#: there can a reader repeat the extraction and obtain the same bytes.
METHOD_READING_STATUSES = {
    "unextractable": frozenset({"asserted"}),
    "ocr": frozenset({"transcribed", "asserted"}),
    "text_layer": READING_STATUSES,
    "manual_transcription": frozenset({"transcribed", "asserted"}),
}

#: ADR-0059. "Is this obligation about novelty?" used to be answerable only by
#: reading its prose, and the ADR-0058 headline gate has to read it mechanically.
OBLIGATION_TAGS = frozenset({"novelty", "prior_art", "reading", "human_review", "formalization"})

#: ADR-0059 replay payloads, as produced by
#: ``exact_graph.replay.ReplayResult.payload()`` plus the manuscript-level
#: ``citation_id`` that binds a replay to the citation whose witness it replays.
#: Without that binding a replay cannot discharge anything, because nothing says
#: whose candidate was replayed.
REPLAY_FIELDS = frozenset({
    "schema_version", "replay_id", "witness_graph_id", "witness_spec_hash", "engine",
    "arithmetic", "float_used", "order", "triangle_free", "connected", "readings",
    "creates_mathematical_warrant", "result_hash", "citation_id",
})
REPLAY_READING_FIELDS = frozenset({"reading", "inverse_even", "range_value", "verdict", "detail"})
REPLAY_SCHEMA_VERSION = "adaivy.counter-candidate-replay.v1"
#: An exact rational, an exact comparison outcome against one, or the recorded
#: absence of an evaluation. There is no decimal form, because a decimal here is
#: a float in disguise and a refused evaluation must stay refused.
_REPLAY_VALUE = re.compile(
    r"^(not_evaluated|-?\d+(/\d+)?|(less|greater)_than:-?\d+(/\d+)?|equal_to:-?\d+(/\d+)?)$"
)
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


def _field_set(
    value: Mapping[str, Any], required: frozenset[str], optional: frozenset[str], field: str
) -> None:
    """``_exact_fields`` with a named optional set.

    Only used where absence is itself a recorded fact -- ADR-0060 admits an
    absent ``verbatim_text`` exactly when the reading is ``asserted``, and
    admitting it as ``null`` instead would make "we could not read it" and "we
    read it and it was empty" the same record.
    """

    present = set(value)
    if not present >= required or not present <= (required | optional):
        missing = sorted(required - present)
        unknown = sorted(present - (required | optional))
        raise PublicationValidationError(
            "manuscript_field_set_mismatch",
            f"{field} missing={missing} unknown={unknown}",
        )


def _tag_list(value: Any, allowed: frozenset[str], code: str, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PublicationValidationError("field_not_array", field)
    tags = tuple(
        _enum(item, allowed, code, f"{field}[{index}]") for index, item in enumerate(value)
    )
    if len(set(tags)) != len(tags):
        raise PublicationValidationError("tag_duplicated", field)
    return tags


def _lexicon_hits(text: str, lexicon: tuple[str, ...]) -> tuple[str, ...]:
    """Case-insensitive, word-boundary matches, in lexicon order."""

    haystack = str(text)
    return tuple(
        phrase for phrase in lexicon
        if re.search(r"\b" + re.escape(phrase) + r"\b", haystack, re.IGNORECASE)
    )


#: Public under its own name because the renderer screens one derived string --
#: the subject label it quotes in the composed title -- against the same lexicon.
lexicon_hits = _lexicon_hits


def _unqualified_lexicon_hits(text: str, lexicon: tuple[str, ...]) -> tuple[str, ...]:
    """Lexicon hits that no non-assertive qualifier stands in front of.

    Every occurrence is examined. A phrase survives the discount only if *every*
    one of its occurrences is qualified, so "a candidate counterexample, and in
    fact a counterexample" is still a hit.
    """

    haystack = str(text)
    hits: list[str] = []
    for phrase in lexicon:
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        occurrences = list(pattern.finditer(haystack))
        if not occurrences:
            continue
        for match in occurrences:
            window = re.findall(r"[A-Za-z-]+", haystack[: match.start()])
            preceding = [item.lower() for item in window[-QUALIFIER_WINDOW:]]
            if not any(token in NON_ASSERTIVE_QUALIFIERS for token in preceding):
                hits.append(phrase)
                break
    return tuple(hits)


def passage_effective_reading_status(passage: Mapping[str, Any]) -> str:
    """Reader-facing strength of a passage (amendment A5).

    The record keeps two facts apart: that we read it, and that the reader may be
    shown it. This derivation merges them, because a reading the reader cannot be
    shown is, to that reader, unsupported. It only ever weakens.
    """

    if passage.get("publication_restricted") is True or passage.get("quotation_permitted") is False:
        return "asserted"
    return str(passage["reading_status"])


def citation_target_engagement(citation: Mapping[str, Any]) -> str:
    """Amendment A1. Fail closed: engagement is the default, silence never escapes.

    ``excluded_by_record`` is reachable only through a well-formed, attributable
    ``target_exclusion``. An absent, empty, or unrecognised reason leaves the
    citation addressing the target, so the burden is on the author to show a
    cited work is *not* about the same problem.
    """

    exclusion = citation.get("target_exclusion")
    if (
        isinstance(exclusion, Mapping)
        and exclusion.get("reason") in EXCLUSION_REASONS
        and isinstance(exclusion.get("excluded_by"), str)
        and bool(exclusion.get("excluded_by"))
    ):
        return "excluded_by_record"
    return "addresses_target"


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
    conventions: Mapping[str, ConventionRecord]
    verdict_matrices: Mapping[str, VerdictMatrix]
    replays: Mapping[str, Mapping[str, Any]]
    rechecks: Mapping[str, NoveltyRecheck]

    @property
    def manuscript_id(self) -> str:
        return str(self.value["manuscript_id"])

    @property
    def hash(self) -> str:
        return canonical_hash(self.value)

    # -- derived reads. Every one of these only ever weakens a reader-facing
    # -- label; there is no accessor here that a manuscript field can promote.

    def resolution_claim_ids(self) -> tuple[str, ...]:
        """Claims carrying a non-null ``resolution_target``, sorted."""

        return tuple(
            claim_id for claim_id, claim in sorted(self.claims.items())
            if claim["resolution_target"] is not None
        )

    def verdict_matrix_for(self, claim_id: str) -> VerdictMatrix | None:
        matrix_id = self.claims[claim_id]["verdict_matrix_id"]
        if matrix_id is None:
            return None
        return self.verdict_matrices.get(str(matrix_id))

    def convention_for(self, claim_id: str) -> ConventionRecord | None:
        matrix = self.verdict_matrix_for(claim_id)
        if matrix is None:
            return None
        return self.conventions.get(matrix.convention_id)

    def derived_scope(self, claim_id: str) -> str | None:
        """The ADR-0058 scope, recomputed from the verdicts. Never read as input."""

        matrix = self.verdict_matrix_for(claim_id)
        if matrix is None:
            return None
        return matrix.scope(convention=self.convention_for(claim_id))

    def weakest_reading_status_for(self, claim_id: str) -> str | None:
        """The weakest reading any enumerated tuple of this claim rests on."""

        matrix = self.verdict_matrix_for(claim_id)
        convention = self.convention_for(claim_id)
        if matrix is None or convention is None:
            return None
        statuses = [
            weakest_reading_status(convention, reading_tuple)
            for reading_tuple in convention.reading_tuples()
        ]
        return min(statuses, key=READING_STATUS_ORDER.index)

    def open_obligation_tags(self) -> frozenset[str]:
        return frozenset(
            tag
            for obligation in self.obligations.values()
            if obligation["status"] in {"open", "blocked"}
            for tag in obligation["tags"]
        )

    def target_engagement(self) -> Mapping[str, str]:
        """Amendment A1's derived predicate, per acquired-source citation."""

        return {
            citation_id: citation_target_engagement(citation)
            for citation_id, citation in sorted(self.citations.items())
            if citation["citation_class"] == "source_record"
        }

    def prior_art_recheck(self) -> NoveltyRecheck | None:
        engagement = self.value["prior_art_engagement"]
        if engagement is None:
            return None
        return self.rechecks.get(str(engagement["recheck"]["recheck_id"]))

    def every_reading_is_confirmed(self) -> bool:
        """Fail closed: with no convention record, no fidelity phrase is earned."""

        if not self.conventions:
            return False
        return all(
            reading.effective_reading_status() == "verbatim_confirmed"
            for convention in self.conventions.values()
            for reading in convention.readings().values()
        )

    def unearned_resolution_reasons(self) -> tuple[str, ...]:
        """Why the records do not earn resolution language, weakest link first."""

        reasons: list[str] = []
        resolution_claims = self.resolution_claim_ids()
        if not resolution_claims:
            reasons.append("no claim carries a resolution_target")
        for claim_id in resolution_claims:
            scope = self.derived_scope(claim_id)
            if scope != "unconditional":
                reasons.append(f"{claim_id} has derived scope {scope}")
        if self.value["prior_art_engagement"] is None:
            reasons.append("prior_art_engagement is null")
        open_tags = self.open_obligation_tags() & {"novelty", "prior_art"}
        if open_tags:
            reasons.append(f"open obligations tagged {sorted(open_tags)}")
        return tuple(reasons)


def _validate_passage(value: Mapping[str, Any], field: str) -> None:
    """ADR-0060. What bytes we hold is one fact; how well we read them is another.

    A content hash is a tamper-evidence mechanism. It was being relied on as a
    faithfulness mechanism, and those are different properties: the shipped
    Graffiti 322 bundle carried a verified hash over a passage whose text nobody
    outside the run could extract, and the paper called the result
    source-faithful. These fields are what a reader needs in order to repeat the
    reading and contradict it.
    """

    # Checked before the field set, so that deleting a status field produces the
    # rule's own code rather than a generic field-set mismatch: a probe must be
    # able to name the rule it falsifies.
    unrecorded = sorted({"extraction_method", "reading_status"} - set(value))
    if unrecorded:
        raise PublicationValidationError(
            "passage_reading_unrecorded",
            f"{field} omits {unrecorded}; a located passage with no recorded reading "
            "proves that bytes exist, not that anyone read them",
        )
    _field_set(
        value,
        frozenset({
            "passage_id", "anchor", "content_hash", "quotation_permitted",
            "extraction_method", "reading_status", "verbatim_hash", "publication_restricted",
        }),
        frozenset({"verbatim_text"}),
        field,
    )
    _identifier(value["passage_id"], f"{field}.passage_id")
    _hash(value["content_hash"], f"{field}.content_hash")
    escape_prose(str(value["anchor"]), f"{field}.anchor")
    quotation_permitted = _bool(value["quotation_permitted"], f"{field}.quotation_permitted")
    restricted = _bool(value["publication_restricted"], f"{field}.publication_restricted")
    method = _enum(
        value["extraction_method"], EXTRACTION_METHODS,
        "passage_extraction_method_unknown", f"{field}.extraction_method",
    )
    status = _enum(
        value["reading_status"], READING_STATUSES,
        "passage_reading_status_unknown", f"{field}.reading_status",
    )
    if status not in METHOD_READING_STATUSES[method]:
        raise PublicationValidationError(
            "passage_extraction_inconsistent",
            f"{field} records extraction_method={method!r} with reading_status={status!r}; "
            f"that method admits only {sorted(METHOD_READING_STATUSES[method])}",
        )
    recorded_hash = value["verbatim_hash"]
    text_value = value.get("verbatim_text")
    if status == "asserted":
        if isinstance(text_value, str) and text_value:
            raise PublicationValidationError(
                "passage_asserted_carries_text",
                f"{field} records text while declaring the reading asserted; a record cannot "
                "both hold the reading and disclaim it",
            )
        if recorded_hash is not None:
            raise PublicationValidationError(
                "passage_verbatim_hash_mismatch",
                f"{field}.verbatim_hash covers no text, because the reading is asserted",
            )
        return
    if not isinstance(text_value, str) or not text_value:
        raise PublicationValidationError(
            "passage_verbatim_missing",
            f"{field} claims reading_status={status!r} but records no text, so nothing a "
            "reader could re-extract is on the record",
        )
    escape_prose(text_value, f"{field}.verbatim_text")
    validate_verbatim(text_value, f"{field}.verbatim_text")
    _hash(recorded_hash, f"{field}.verbatim_hash")
    if text_hash(text_value) != recorded_hash:
        raise PublicationValidationError(
            "passage_verbatim_hash_mismatch",
            f"{field}.verbatim_hash does not cover the exact recorded reading",
        )
    if not quotation_permitted and not restricted:
        # Amendment A5. The coherent restricted case is retained: the record may
        # keep that we read it while every derived reader-facing label treats it
        # as asserted. Only the incoherent combination is refused.
        raise PublicationValidationError(
            "passage_verbatim_rights_conflict",
            f"{field} publishes text the rights do not permit quoting and does not record "
            "publication_restricted; the bundle publishes records/, so this text would ship",
        )


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
        _validate_passage(passage, passage_field)


def _validate_target_exclusion(value: Any, field: str, cited_object: str) -> None:
    """Amendment A1. The only route out of the replay obligation, and it is narrow.

    ``None`` is not an escape: it leaves the citation addressing the target. What
    is validated here is the *record* that claims otherwise -- a reason from the
    closed vocabulary and the principal who signed it -- so that a claim of
    irrelevance is hashed, published, and attributable rather than silent.
    """

    if value is None:
        return
    if cited_object in UNEXCLUDABLE_CITED_OBJECTS:
        raise PublicationValidationError(
            "prior_candidate_cannot_be_excluded",
            f"{field} excludes a {cited_object}; a work publishing its own candidate "
            "resolution of the same conjecture is the one case no record may talk down",
        )
    if not isinstance(value, dict) or set(value) != {"reason", "excluded_by"}:
        raise PublicationValidationError(
            "target_exclusion_unjustified",
            f"{field} must carry exactly a reason and the principal who excluded it",
        )
    if value["reason"] not in EXCLUSION_REASONS:
        raise PublicationValidationError(
            "target_exclusion_unjustified",
            f"{field}.reason={value['reason']!r} is not one of {list(EXCLUSION_REASONS)}; an "
            "empty, absent, or not_applicable reason excludes nothing",
        )
    if not isinstance(value["excluded_by"], str) or not _ID.match(value["excluded_by"]):
        raise PublicationValidationError(
            "target_exclusion_unjustified",
            f"{field}.excluded_by must name the principal who takes responsibility",
        )


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
                "intended_use", "target_exclusion",
            }),
            field,
        )
        cited_object = _enum(
            value["cited_object"], CITED_OBJECTS, "cited_object_unknown", f"{field}.cited_object"
        )
        _validate_target_exclusion(
            value["target_exclusion"], f"{field}.target_exclusion", cited_object
        )
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
            "original_problem_citation_id", "derivation", "resolution_target",
            "verdict_matrix_id",
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
    _validate_resolution_target(value["resolution_target"], f"{field}.resolution_target")
    if value["verdict_matrix_id"] is not None:
        _identifier(value["verdict_matrix_id"], f"{field}.verdict_matrix_id")
    if value["resolution_target"] is not None and value["verdict_matrix_id"] is None:
        raise PublicationValidationError(
            "resolution_claim_without_verdict_matrix",
            f"{field} is resolution-typed, so it must name the verdict matrix that carries "
            "one verdict per enumerated reading; a claim that resolves a conjecture under an "
            "unstated reading is the defect this field exists to prevent",
        )
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


def _validate_resolution_target(value: Any, field: str) -> None:
    """ADR-0058. A claim that resolves a conjecture says which conjecture, where.

    Any structural problem is one code, because the author needs to be told that
    the resolution target is malformed rather than that some identifier is.
    """

    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"subject_id", "citation_id", "kind"}:
        raise PublicationValidationError(
            "resolution_target_malformed",
            f"{field} must carry exactly a subject_id, a citation_id, and a kind",
        )
    for key in ("subject_id", "citation_id"):
        if not isinstance(value[key], str) or not _ID.match(value[key]):
            raise PublicationValidationError(
                "resolution_target_malformed", f"{field}.{key}={value[key]!r}"
            )
    if value["kind"] not in RESOLUTION_TARGET_KINDS:
        raise PublicationValidationError(
            "resolution_target_malformed",
            f"{field}.kind={value['kind']!r} is not one of {sorted(RESOLUTION_TARGET_KINDS)}",
        )


def _validate_obligation(value: Mapping[str, Any], field: str) -> None:
    _exact_fields(
        value, frozenset({"obligation_id", "statement", "status", "reason", "tags"}), field
    )
    _identifier(value["obligation_id"], f"{field}.obligation_id")
    _enum(
        value["status"], {"open", "blocked", "discharged", "waived"},
        "obligation_status_unknown", f"{field}.status",
    )
    escape_prose(str(value["statement"]), f"{field}.statement")
    escape_prose(str(value["reason"]), f"{field}.reason")
    _tag_list(value["tags"], OBLIGATION_TAGS, "obligation_tag_unknown", f"{field}.tags")


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


def _validate_replay(value: Mapping[str, Any], field: str) -> None:
    """ADR-0059. A prior candidate, re-evaluated by our engine under every reading.

    A retrieved number is not a comparison (Section 16.3), so what is recorded
    here is the output of a local exact evaluation. The manuscript checks that the
    payload is exact, complete over its readings, and attributable to the citation
    whose witness it replays; it does not re-derive ``result_hash``, which is the
    engine's own content binding.
    """

    _exact_fields(value, REPLAY_FIELDS, field)
    if value["schema_version"] != REPLAY_SCHEMA_VERSION:
        raise PublicationValidationError(
            "counter_candidate_replay_invalid",
            f"{field}.schema_version={value['schema_version']!r}",
        )
    if value["creates_mathematical_warrant"] is not False:
        raise PublicationValidationError(
            "counter_candidate_replay_invalid",
            f"{field} claims to create mathematical warrant; a replay is an evaluation",
        )
    _identifier(value["replay_id"], f"{field}.replay_id")
    _hash(value["witness_spec_hash"], f"{field}.witness_spec_hash")
    _hash(value["result_hash"], f"{field}.result_hash")
    witness = value["witness_graph_id"]
    if not isinstance(witness, str) or not witness.strip() or len(witness) > 128:
        raise PublicationValidationError(
            "counter_candidate_replay_invalid", f"{field}.witness_graph_id={witness!r}"
        )
    escape_prose(witness, f"{field}.witness_graph_id")
    escape_prose(str(value["engine"]), f"{field}.engine")
    _enum(
        value["arithmetic"], EXACT_ARITHMETIC, "counter_candidate_replay_invalid",
        f"{field}.arithmetic",
    )
    if _bool(value["float_used"], f"{field}.float_used"):
        raise PublicationValidationError(
            "replay_used_floating_point",
            f"{field} reports floating-point arithmetic; an inexact replay decides nothing",
        )
    for key in ("triangle_free", "connected"):
        _bool(value[key], f"{field}.{key}")
    order = value["order"]
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise PublicationValidationError("counter_candidate_replay_invalid", f"{field}.order")
    if value["citation_id"] is not None:
        _identifier(value["citation_id"], f"{field}.citation_id")
    readings = value["readings"]
    if not isinstance(readings, list) or not readings:
        raise PublicationValidationError(
            "counter_candidate_replay_invalid", f"{field}.readings is empty"
        )
    seen_readings: set[tuple[str, ...]] = set()
    for index, reading in enumerate(readings):
        reading_field = f"{field}.readings[{index}]"
        _mapping(reading, reading_field)
        _exact_fields(reading, REPLAY_READING_FIELDS, reading_field)
        names = reading["reading"]
        if not isinstance(names, list) or not names or any(
            not isinstance(item, str) or not item for item in names
        ):
            raise PublicationValidationError(
                "counter_candidate_replay_invalid", f"{reading_field}.reading"
            )
        key = tuple(str(item) for item in names)
        if key in seen_readings:
            raise PublicationValidationError(
                "counter_candidate_replay_invalid",
                f"{reading_field}.reading repeats {list(key)}",
            )
        seen_readings.add(key)
        _enum(
            reading["verdict"], READING_VERDICTS, "counter_candidate_replay_invalid",
            f"{reading_field}.verdict",
        )
        for key_name in ("inverse_even", "range_value"):
            item = reading[key_name]
            if not isinstance(item, str) or not _REPLAY_VALUE.match(item):
                raise PublicationValidationError(
                    "replay_value_not_exact",
                    f"{reading_field}.{key_name}={item!r} is not an exact value, an exact "
                    "comparison outcome, or a recorded absence of one",
                )
        escape_prose(str(reading["detail"]), f"{reading_field}.detail")


_CONVENTION_PASSTHROUGH = frozenset({
    "convention_hash_mismatch", "convention_id_mismatch", "verdict_matrix_incomplete",
})


def _load_conventions(
    value: Mapping[str, Any], seen: set[str]
) -> dict[str, ConventionRecord]:
    items = value["conventions"]
    if not isinstance(items, list):
        raise PublicationValidationError("field_not_array", "conventions")
    records: dict[str, ConventionRecord] = {}
    for index, item in enumerate(items):
        field = f"conventions[{index}]"
        _mapping(item, field)
        try:
            record = load_convention(item)
        except ConventionError as error:
            raise PublicationValidationError(
                "convention_record_invalid", f"{field}: {error}"
            ) from error
        if record.convention_id in seen:
            raise PublicationValidationError(
                "identifier_not_unique",
                f"{record.convention_id} appears in more than one collection",
            )
        seen.add(record.convention_id)
        records[record.convention_id] = record
    return records


def _prebind_verdict_matrix(
    item: Mapping[str, Any], conventions: Mapping[str, ConventionRecord], field: str
) -> None:
    """Refuse a matrix that names a reading set this manuscript does not hold.

    Only well-shaped payloads are judged here; anything else falls through to
    ``load_verdict_matrix``, which owns the shape refusals.
    """

    convention = conventions.get(str(item.get("convention_id")))
    if convention is None:
        return
    if item.get("convention_hash") != convention.content_hash:
        raise PublicationValidationError(
            "convention_hash_mismatch",
            f"{field} is asserted under reading set {item.get('convention_hash')!r}, but "
            f"convention {convention.convention_id} on record hashes to "
            f"{convention.content_hash}; re-reading a term strands every claim decided "
            "under the old reading, which is the point",
        )
    verdicts = item.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return
    covered: set[tuple[str, ...]] = set()
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            return
        reading_tuple = verdict.get("reading_tuple")
        if not isinstance(reading_tuple, list) or not all(
            isinstance(part, str) for part in reading_tuple
        ):
            return
        covered.add(tuple(reading_tuple))
    expected = set(convention.reading_tuples())
    if covered != expected:
        raise PublicationValidationError(
            "verdict_matrix_incomplete",
            f"{field} carries verdicts for {sorted(covered)} while convention "
            f"{convention.convention_id} enumerates {sorted(expected)}; a partial matrix "
            "must not read as a full sweep",
        )


def _load_verdict_matrices(
    value: Mapping[str, Any], conventions: Mapping[str, ConventionRecord], seen: set[str]
) -> dict[str, VerdictMatrix]:
    items = value["verdict_matrices"]
    if not isinstance(items, list):
        raise PublicationValidationError("field_not_array", "verdict_matrices")
    matrices: dict[str, VerdictMatrix] = {}
    for index, item in enumerate(items):
        field = f"verdict_matrices[{index}]"
        _mapping(item, field)
        # The binding and coverage questions are answered on the payload as
        # supplied, *before* the record's own content hash is verified. Both are
        # refusals either way, so the only thing at stake is which rule the author
        # is told they broke -- and every single-field mutation of a content-hashed
        # record also breaks its hash, so checking the hash first would collapse
        # every semantic rule in this record onto one bookkeeping code and leave
        # `convention_hash_mismatch` and `verdict_matrix_incomplete` with no
        # reachable falsification (ADR-0034).
        _prebind_verdict_matrix(item, conventions, field)
        try:
            matrix = load_verdict_matrix(item)
        except ConventionError as error:
            raise PublicationValidationError(
                "verdict_matrix_invalid", f"{field}: {error}"
            ) from error
        if matrix.convention_id not in conventions:
            raise PublicationValidationError(
                "record_ref_unresolved",
                f"{field} names convention {matrix.convention_id!r}, which this manuscript "
                "does not carry; a scope asserted under an absent reading set is unreadable",
            )
        try:
            require_convention_binding(matrix, conventions[matrix.convention_id])
        except ConventionError as error:
            code = str(error)
            raise PublicationValidationError(
                code if code in _CONVENTION_PASSTHROUGH else "verdict_matrix_invalid",
                f"{field}: {error}",
            ) from error
        if matrix.matrix_id in seen:
            raise PublicationValidationError(
                "identifier_not_unique", f"{matrix.matrix_id} appears in more than one collection"
            )
        seen.add(matrix.matrix_id)
        matrices[matrix.matrix_id] = matrix
    return matrices


def _load_rechecks(value: Mapping[str, Any], seen: set[str]) -> dict[str, NoveltyRecheck]:
    """ADR-0059's missing slot: a classification that does not need an approval.

    Until now an ADR-0055 record could only live inside ``publication_approval``,
    which is null for every draft, so an unapproved report had nowhere to put one
    and prose filled the vacuum.
    """

    payloads: list[tuple[str, Any]] = []
    engagement = value["prior_art_engagement"]
    if engagement is not None:
        engagement = _mapping(engagement, "manuscript.prior_art_engagement")
        _exact_fields(engagement, frozenset({"recheck"}), "manuscript.prior_art_engagement")
        payloads.append(("manuscript.prior_art_engagement.recheck", engagement["recheck"]))
    items = value["novelty_rechecks"]
    if not isinstance(items, list):
        raise PublicationValidationError("field_not_array", "novelty_rechecks")
    for index, item in enumerate(items):
        payloads.append((f"novelty_rechecks[{index}]", item))
    records: dict[str, NoveltyRecheck] = {}
    for field, payload in payloads:
        _mapping(payload, field)
        code = (
            "prior_art_engagement_invalid"
            if field.startswith("manuscript.prior_art_engagement")
            else "novelty_recheck_invalid"
        )
        try:
            record = load_recheck(payload)
        except NoveltyRecheckError as error:
            raise PublicationValidationError(code, f"{field}: {error}") from error
        existing = records.get(record.recheck_id)
        if existing is not None and existing.content_hash == record.content_hash:
            continue
        if record.recheck_id in seen:
            raise PublicationValidationError(
                "identifier_not_unique", f"{record.recheck_id} appears in more than one collection"
            )
        seen.add(record.recheck_id)
        records[record.recheck_id] = record
    return records


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
    if value["schema_version"] != SCHEMA_VERSION:
        raise PublicationValidationError(
            "manuscript_schema_unsupported", f"schema_version={value['schema_version']!r}"
        )
    _identifier(value["manuscript_id"], "manuscript.manuscript_id")
    escape_prose(str(value["title_stem"]), "manuscript.title_stem")
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
    conventions = _load_conventions(value, seen)
    verdict_matrices = _load_verdict_matrices(value, conventions, seen)
    replays = _collection(
        value, "counter_candidate_replays", "replay_id", _validate_replay, seen
    )
    rechecks = _load_rechecks(value, seen)

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
        | set(claims) | set(obligations) | set(conventions) | set(verdict_matrices)
        | set(replays) | set(rechecks)
    )
    manuscript = Manuscript(
        value=value, sources=sources, citations=citations, attestations=attestations,
        certificates=certificates, claims=claims, obligations=obligations, blocks=blocks,
        record_ids=record_ids, conventions=conventions, verdict_matrices=verdict_matrices,
        replays=replays, rechecks=rechecks,
    )
    _validate_references(manuscript)
    _validate_reading_provenance(manuscript)
    _validate_resolution_gates(manuscript)
    _validate_prose_search_claims(manuscript)
    _validate_headline_claims(manuscript)
    _validate_announcement_novelty_gate(manuscript)
    return manuscript


def announcement_subject_hash(manuscript: Manuscript) -> str:
    """Bind a re-check to every exact result statement in the bundle.

    Public because amendment A4 makes artifact production require a
    prior-art classification bound to *this* manuscript. The binding is over
    the claim statements rather than the whole record set, so re-rendering a
    bundle from the same statements stays possible: subject binding is
    time-invariant, which is exactly why it, and not freshness, is the
    render-time requirement.
    """

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
            subject_hash=announcement_subject_hash(manuscript),
            approval_id=approval["approval_id"], approval_at=approval["recorded_at"],
        )
    except NoveltyRecheckError as error:
        raise PublicationValidationError("announcement_novelty_recheck_invalid", str(error)) from error


#: Retained name for the callers that predate amendment A4.
_announcement_subject_hash = announcement_subject_hash


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


def _passage_index(manuscript: Manuscript) -> dict[str, Mapping[str, Any]]:
    return {
        str(passage["passage_id"]): passage
        for source in manuscript.sources.values()
        for passage in source["passages"]
    }


def _validate_reading_provenance(manuscript: Manuscript) -> None:
    """Close the two dangling references a convention record could otherwise carry.

    A ``Reading`` names the passage it is drawn from and a ``ReadingVerdict``
    names the evidence behind it. Neither resolved to anything before this slice,
    which meant a reading could cite a passage this manuscript does not hold and a
    verdict could cite a replay that was never run -- and nothing failed. Both are
    now closures, and the reading closure is directional: a reading may not be
    better attested than its own source.
    """

    passages = _passage_index(manuscript)
    for convention_id, convention in sorted(manuscript.conventions.items()):
        for reading_id, reading in sorted(convention.readings().items()):
            reference = reading.source_passage_ref
            if reference not in passages:
                raise PublicationValidationError(
                    "reading_passage_unresolved",
                    f"convention {convention_id} reading {reading_id} is drawn from passage "
                    f"{reference!r}, which no source record in this manuscript carries",
                )
            passage = passages[reference]
            recorded = str(passage["reading_status"])
            effective = passage_effective_reading_status(passage)
            for claimed, against in (
                (reading.reading_status, recorded),
                (reading.effective_reading_status(), effective),
            ):
                if READING_STATUS_ORDER.index(claimed) > READING_STATUS_ORDER.index(against):
                    raise PublicationValidationError(
                        "reading_status_exceeds_passage",
                        f"convention {convention_id} reading {reading_id} claims {claimed!r} "
                        f"from passage {reference} recorded as {against!r}; a reading cannot be "
                        "better attested than the source it is drawn from",
                    )

    evidence_ids = (
        {str(item["result_hash"]) for item in manuscript.replays.values()}
        | set(manuscript.replays)
        | {str(item["result_hash"]) for item in manuscript.certificates.values()}
    )
    for matrix_id, matrix in sorted(manuscript.verdict_matrices.items()):
        for verdict in matrix.verdicts:
            reference = verdict.evidence_ref
            if reference is None:
                continue
            if reference not in evidence_ids:
                raise PublicationValidationError(
                    "verdict_evidence_ref_unresolved",
                    f"verdict matrix {matrix_id} backs {list(verdict.reading_tuple)} with "
                    f"{reference!r}, which is neither a replay in this manuscript nor a "
                    "certificate result it carries",
                )


def _validate_resolution_gates(manuscript: Manuscript) -> None:
    """ADR-0058 and ADR-0059 closure for resolution-typed claims."""

    for matrix_id, matrix in sorted(manuscript.verdict_matrices.items()):
        if matrix.claim_id not in manuscript.claims:
            raise PublicationValidationError(
                "record_ref_unresolved",
                f"verdict matrix {matrix_id} names claim {matrix.claim_id!r}",
            )
    for claim_id, claim in sorted(manuscript.claims.items()):
        matrix_id = claim["verdict_matrix_id"]
        if matrix_id is not None:
            if str(matrix_id) not in manuscript.verdict_matrices:
                raise PublicationValidationError(
                    "record_ref_unresolved", f"claim {claim_id} names verdict matrix {matrix_id!r}"
                )
            if manuscript.verdict_matrices[str(matrix_id)].claim_id != claim_id:
                raise PublicationValidationError(
                    "verdict_matrix_claim_mismatch",
                    f"claim {claim_id} names matrix {matrix_id}, which carries the verdicts of "
                    f"{manuscript.verdict_matrices[str(matrix_id)].claim_id}",
                )
        target = claim["resolution_target"]
        if target is None:
            continue
        citation_id = str(target["citation_id"])
        if citation_id not in manuscript.citations:
            raise PublicationValidationError(
                "citation_not_declared",
                f"claim {claim_id} resolves a target located by {citation_id!r}",
            )
        # ADR-0060: a resolution asserted under a reading nobody re-extracted is
        # an open obligation naming what is unreproduced, not a footnote.
        if manuscript.weakest_reading_status_for(claim_id) == "asserted":
            if "reading" not in manuscript.open_obligation_tags():
                raise PublicationValidationError(
                    "asserted_reading_without_obligation",
                    f"claim {claim_id} rests on an asserted reading, so an open obligation "
                    "tagged reading must name the passage and reading nobody re-extracted",
                )

    resolution_claims = manuscript.resolution_claim_ids()
    if not resolution_claims:
        return
    # The claim's own target-problem citation is the target, not a competing
    # candidate: replaying the conjecture statement is not a comparison. The
    # exemption is anchored to attributable fields that are separately validated
    # to locate a source_record problem, so it cannot be used to wave through a
    # rival paper without declaring that paper to be the problem statement.
    exempt: set[str] = set()
    for claim_id in resolution_claims:
        claim = manuscript.claims[claim_id]
        if claim["original_problem_citation_id"] is not None:
            exempt.add(str(claim["original_problem_citation_id"]))
        exempt.add(str(claim["resolution_target"]["citation_id"]))
    replayed = {
        str(replay["citation_id"])
        for replay in manuscript.replays.values()
        if replay["citation_id"] is not None
    }
    for citation_id, engagement in manuscript.target_engagement().items():
        if citation_id in exempt or engagement != "addresses_target":
            continue
        if citation_id not in replayed:
            raise PublicationValidationError(
                "resolution_claim_without_prior_art_engagement",
                f"citation {citation_id} addresses the target problem of "
                f"{list(resolution_claims)} and no counter-candidate replay names it; either "
                "replay its witness under every enumerated reading or record why it is not "
                "about the same problem",
            )


def _validate_prose_search_claims(manuscript: Manuscript) -> None:
    """An asserted literature search that no record backs is refused (ADR-0059).

    This mirrors the rule already in ``bibliography.py``: an uncited bibliography
    implies reading that did not happen. The shipped Graffiti 322 report asserted
    a pre-research review of the Roucairol-Cazenave publication record that no
    record in the bundle backed.
    """

    recheck_ids = set(manuscript.rechecks)
    for block_id, block in sorted(manuscript.blocks.items()):
        if block["kind"] != "prose":
            continue
        prose = " ".join(
            str(run["v"]) for run in block["runs"] if run["t"] == "text"
        )
        hits = _lexicon_hits(prose, SEARCH_LEXICON)
        if not hits:
            continue
        if not any(str(ref) in recheck_ids for ref in block["record_refs"]):
            raise PublicationValidationError(
                "prose_asserts_unrecorded_search",
                f"block {block_id} asserts {list(hits)} and references no novelty re-check "
                "record; an unbacked claim of having searched reads as diligence",
            )


def _screen_author_text(
    manuscript: Manuscript, *, field: str, text: str, code: str, hits: tuple[str, ...]
) -> None:
    """One screen, two rules (amendment A2), applied to one author-supplied string.

    The fidelity phrase is computed from reading statuses alone and carries its own
    code, because it is a different rule with a different remedy: no amount of
    exact arithmetic earns "source-faithful" if nobody could re-extract the source.
    """

    if not hits:
        return
    if SOURCE_FIDELITY_PHRASE in hits and not manuscript.every_reading_is_confirmed():
        raise PublicationValidationError(
            "source_fidelity_overclaimed",
            f"{field} calls the result {SOURCE_FIDELITY_PHRASE!r} while some reading it "
            "rests on is not verbatim-confirmed; fidelity is earned from reading "
            "statuses, not asserted in prose",
        )
    resolution_hits = tuple(hit for hit in hits if hit != SOURCE_FIDELITY_PHRASE)
    if not resolution_hits:
        return
    unearned = manuscript.unearned_resolution_reasons()
    if unearned:
        raise PublicationValidationError(
            code, f"{field} asserts {list(resolution_hits)} while {list(unearned)}"
        )


def _validate_headline_claims(manuscript: Manuscript) -> None:
    """Reader-facing author text may not out-claim the records (ADR-0058, A2, B6).

    Three strings reach a reader with no derivation behind them: ``title_stem``,
    ``abstract``, and each claim's ``prose_statement``. The first two are screened
    strictly, because a headline is the one string a summary keeps. Claim prose is
    screened under the same *condition* but with the amendment B6 discount, because
    it is exposition rather than a headline and the honest hedge and the honest
    denial both belong there.

    The renderer composes the displayed title from ``title_stem`` plus a derived
    qualifier; this rule is what keeps the stem from doing the qualifier's job.
    """

    for key, code in (
        ("title_stem", "title_stem_asserts_resolution"),
        ("abstract", "abstract_overclaims_evidence"),
    ):
        text = str(manuscript.value[key])
        _screen_author_text(
            manuscript, field=f"manuscript.{key}", text=text, code=code,
            hits=_lexicon_hits(text, RESOLUTION_LEXICON),
        )
    for claim_id, claim in sorted(manuscript.claims.items()):
        text = str(claim["prose_statement"])
        _screen_author_text(
            manuscript, field=f"claim {claim_id}.prose_statement", text=text,
            code="claim_prose_overclaims_evidence",
            hits=_unqualified_lexicon_hits(text, RESOLUTION_LEXICON),
        )


def manuscript_hash(payload: bytes | str | Mapping[str, Any]) -> str:
    return load_manuscript(payload).hash


def read_manuscript(path: Path) -> Manuscript:
    return load_manuscript(path.read_bytes())
