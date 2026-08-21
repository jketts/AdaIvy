"""Content-bound definitional-reading records and derived claim scope.

A result can be exact and still not be what it says it is.  Graffiti 322 was
reported as an exact counterexample, but the report rested on a contested
reading of two words in the source -- whether ``Even(v)`` counts ``v`` itself,
and whether ``range`` means the number of distinct distance eigenvalues or the
spectral extent.  Those choices entered the document as free prose in a section
body, so nothing in the projection could see that a second reading makes an
already-published candidate sufficient and a third reading makes the result
false.

This module makes the definitional fork a record.  A ``ConventionRecord``
enumerates the contested terms and every reading of each, and says how well the
*source passage* behind each reading could actually be read.  A
``VerdictMatrix`` carries one verdict per enumerated reading tuple.  The
reader-facing scope -- unconditional, convention-relative, contested but
unevaluated, or refuted under no reading -- is *derived* from that matrix by
``classify_scope``; there is deliberately no input field that supplies it, and a
matrix that does not cover exactly the convention's reading tuples is a typed
refusal rather than an implied full sweep.

Two couplings are load-bearing.  ``coupled_subject_ids`` names the subjects
whose status flips together when a reading changes, so re-reading one word
visibly invalidates every claim asserted under it instead of silently
invalidating some of them.  ``weakest_reading_status`` reports when a claim
rests on a passage nobody could re-extract, so a renderer cannot describe such a
claim as source-faithful.

Nothing here creates mathematical warrant, novelty status, significance, or
graph admission, and nothing here decides which reading is correct.  Enumerating
a fork is not resolving it.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .phase2.serialization import canonical_hash, canonical_json


SCHEMA_VERSION = "adaivy.convention-reading.v1"
POLICY_ID = "convention-relative-claim-v1"
MAX_RECORD_BYTES = 65_536
MAX_TEXT_CHARS = 2_048
MAX_SUBJECT_IDS = 16
MAX_TERMS = 8
MAX_READINGS_PER_TERM = 8
MAX_READING_TUPLES = 64

READING_STATUSES = frozenset({"verbatim_confirmed", "transcribed", "asserted"})
VERDICTS = frozenset({"refutes", "does_not_refute", "not_evaluated"})
CONVENTION_SCOPES = frozenset({
    "unconditional",             # every enumerated reading tuple: refutes
    "convention_relative",       # some refutes, some does_not_refute, none unevaluated
    "contested_unevaluated",     # any reading tuple not_evaluated
    "refuted_under_no_reading",  # no reading tuple refutes
})

# Weakest first.  A tuple is only as strong as its least-well-read passage.
_READING_STATUS_STRENGTH = {"asserted": 0, "transcribed": 1, "verbatim_confirmed": 2}

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class ConventionError(ValueError):
    """A convention record or verdict matrix is malformed or unbound."""


# --------------------------------------------------------------------------- #
# strict primitives
# --------------------------------------------------------------------------- #


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ConventionError(f"duplicate_field:{key}")
        value[key] = item
    return value


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\r" in value
        or "\n" in value
        or len(value) > MAX_TEXT_CHARS
    ):
        raise ConventionError(f"invalid_text:{field}")
    return value


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _ID.fullmatch(value):
        raise ConventionError(f"invalid_identifier:{field}")
    return value


def _token(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _TOKEN.fullmatch(value):
        raise ConventionError(f"invalid_token:{field}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ConventionError(f"invalid_hash:{field}")
    return value


def _evidence_ref(value: Any, field: str) -> str:
    """A replay/certificate result hash, or the record id that will carry one."""

    if isinstance(value, str) and _HASH.fullmatch(value):
        return value
    return _identifier(value, field)


def _identifier_list(
    value: Any, field: str, *, maximum: int, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ConventionError(f"invalid_nonempty_list:{field}")
    if not value and not allow_empty:
        raise ConventionError(f"invalid_nonempty_list:{field}")
    items = tuple(
        _identifier(item, f"{field}[{index}]") for index, item in enumerate(value)
    )
    if len(set(items)) != len(items):
        raise ConventionError(f"duplicate_list_item:{field}")
    return items


def _decode(payload: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str):
        return _decode(payload.encode("utf-8"))
    if isinstance(payload, bytes):
        if len(payload) > MAX_RECORD_BYTES:
            raise ConventionError("record_too_large")
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_strict_object,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ConventionError(f"non_finite_json:{item}")
                ),
            )
        except UnicodeDecodeError as error:
            raise ConventionError("record_not_utf8") from error
        except json.JSONDecodeError as error:
            raise ConventionError("record_not_json") from error
    else:
        try:
            value = json.loads(
                json.dumps(payload, allow_nan=False),
                object_pairs_hook=_strict_object,
            )
        except (TypeError, ValueError) as error:
            raise ConventionError("record_not_json") from error
    if not isinstance(value, dict):
        raise ConventionError("record_not_json")
    return value


def _require_envelope(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION or value.get("policy_id") != POLICY_ID:
        raise ConventionError("version_or_policy_unsupported")


# --------------------------------------------------------------------------- #
# convention records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, kw_only=True)
class Reading:
    """One reading of one contested term, and how well its source was read."""

    reading_id: str
    statement: str
    source_passage_ref: str
    reading_status: str
    attributed_to: str | None

    def payload(self) -> dict[str, Any]:
        return {
            "reading_id": self.reading_id,
            "statement": self.statement,
            "source_passage_ref": self.source_passage_ref,
            "reading_status": self.reading_status,
            "attributed_to": self.attributed_to,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ContestedTerm:
    """A term with at least two readings.  One reading is not a contest."""

    term_id: str
    term: str
    readings: tuple[Reading, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "term_id": self.term_id,
            "term": self.term,
            "readings": [reading.payload() for reading in self.readings],
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ConventionRecord:
    """Repository-level, content-hashed reading set shared across reports."""

    convention_id: str
    subject_ids: tuple[str, ...]
    coupled_subject_ids: tuple[str, ...]
    terms: tuple[ContestedTerm, ...]
    content_hash: str = ""

    def reading_tuples(self) -> tuple[tuple[str, ...], ...]:
        """Cartesian product of readings, one position per term, sorted.

        Term positions are ordered by ``term_id`` and readings within a term by
        ``reading_id``, so the tuple layout is a function of the record alone and
        never of input order.
        """

        ordered = tuple(
            tuple(
                reading.reading_id
                for reading in sorted(term.readings, key=lambda item: item.reading_id)
            )
            for term in sorted(self.terms, key=lambda item: item.term_id)
        )
        return tuple(sorted(itertools.product(*ordered)))

    def readings(self) -> dict[str, Reading]:
        return {
            reading.reading_id: reading
            for term in self.terms
            for reading in term.readings
        }

    def governed_subject_ids(self) -> tuple[str, ...]:
        """Every subject a reading change here can invalidate."""

        return tuple(sorted(set(self.subject_ids) | set(self.coupled_subject_ids)))

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "convention_id": self.convention_id,
            "subject_ids": list(self.subject_ids),
            "coupled_subject_ids": list(self.coupled_subject_ids),
            "terms": [term.payload() for term in self.terms],
            "reading_tuples": [list(item) for item in self.reading_tuples()],
            "creates_mathematical_warrant": False,
            "resolves_contested_reading": False,
            "content_hash": self.content_hash if include_hash else None,
        }

    def finalized(self) -> "ConventionRecord":
        return replace(
            self, content_hash=canonical_hash(self.payload(include_hash=False))
        )


_CONVENTION_FIELDS = frozenset({
    "schema_version", "policy_id", "convention_id", "subject_ids",
    "coupled_subject_ids", "terms", "reading_tuples",
    "creates_mathematical_warrant", "resolves_contested_reading", "content_hash",
})
_TERM_FIELDS = frozenset({"term_id", "term", "readings"})
_READING_FIELDS = frozenset({
    "reading_id", "statement", "source_passage_ref", "reading_status",
    "attributed_to",
})


def _load_reading(value: Any, field: str) -> Reading:
    if not isinstance(value, dict) or set(value) != set(_READING_FIELDS):
        raise ConventionError("reading_field_set_mismatch")
    status = value["reading_status"]
    if not isinstance(status, str) or status not in READING_STATUSES:
        raise ConventionError("reading_status_unknown")
    attributed = value["attributed_to"]
    if attributed is not None:
        attributed = _identifier(attributed, f"{field}.attributed_to")
    return Reading(
        reading_id=_token(value["reading_id"], f"{field}.reading_id"),
        statement=_text(value["statement"], f"{field}.statement"),
        source_passage_ref=_identifier(
            value["source_passage_ref"], f"{field}.source_passage_ref"
        ),
        reading_status=status,
        attributed_to=attributed,
    )


def _load_term(value: Any, field: str) -> ContestedTerm:
    if not isinstance(value, dict) or set(value) != set(_TERM_FIELDS):
        raise ConventionError("term_field_set_mismatch")
    raw = value["readings"]
    if not isinstance(raw, list) or len(raw) > MAX_READINGS_PER_TERM:
        raise ConventionError("too_many_readings")
    if len(raw) < 2:
        raise ConventionError("term_not_contested")
    readings = tuple(
        _load_reading(item, f"{field}.readings[{index}]")
        for index, item in enumerate(raw)
    )
    ids = tuple(reading.reading_id for reading in readings)
    if len(set(ids)) != len(ids):
        raise ConventionError("reading_id_duplicated")
    return ContestedTerm(
        term_id=_token(value["term_id"], f"{field}.term_id"),
        term=_text(value["term"], f"{field}.term"),
        readings=readings,
    )


def load_convention(payload: bytes | str | Mapping[str, Any]) -> ConventionRecord:
    """Validate and bind a convention record.  Fails closed on every doubt."""

    value = _decode(payload)
    if set(value) != set(_CONVENTION_FIELDS):
        raise ConventionError("field_set_mismatch")
    _require_envelope(value)
    if value["creates_mathematical_warrant"] is not False:
        raise ConventionError("convention_cannot_create_mathematical_warrant")
    if value["resolves_contested_reading"] is not False:
        raise ConventionError("convention_cannot_resolve_contested_reading")
    raw_terms = value["terms"]
    if not isinstance(raw_terms, list) or not raw_terms:
        raise ConventionError("invalid_nonempty_list:terms")
    if len(raw_terms) > MAX_TERMS:
        raise ConventionError("too_many_terms")
    terms = tuple(
        _load_term(item, f"terms[{index}]") for index, item in enumerate(raw_terms)
    )
    term_ids = tuple(term.term_id for term in terms)
    if len(set(term_ids)) != len(term_ids):
        raise ConventionError("duplicate_term_id")
    all_reading_ids = [
        reading.reading_id for term in terms for reading in term.readings
    ]
    if len(set(all_reading_ids)) != len(all_reading_ids):
        raise ConventionError("reading_id_duplicated")
    subject_ids = _identifier_list(
        value["subject_ids"], "subject_ids", maximum=MAX_SUBJECT_IDS
    )
    coupled = _identifier_list(
        value["coupled_subject_ids"], "coupled_subject_ids",
        maximum=MAX_SUBJECT_IDS, allow_empty=True,
    )
    if set(coupled) & set(subject_ids):
        raise ConventionError("coupled_subject_is_own_subject")
    record = ConventionRecord(
        convention_id=_identifier(value["convention_id"], "convention_id"),
        subject_ids=subject_ids,
        coupled_subject_ids=coupled,
        terms=terms,
        content_hash=_hash(value["content_hash"], "content_hash"),
    )
    derived = [list(item) for item in record.reading_tuples()]
    if len(derived) > MAX_READING_TUPLES:
        raise ConventionError("reading_tuple_space_too_large")
    if value["reading_tuples"] != derived:
        raise ConventionError("reading_tuples_derived_mismatch")
    if record.content_hash != record.finalized().content_hash:
        raise ConventionError("content_hash_mismatch")
    return record


# --------------------------------------------------------------------------- #
# verdict matrices and the derived scope
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadingVerdict:
    """What the witness does under one enumerated reading tuple."""

    reading_tuple: tuple[str, ...]
    verdict: str
    evidence_ref: str | None
    detail: str

    def payload(self) -> dict[str, Any]:
        return {
            "reading_tuple": list(self.reading_tuple),
            "verdict": self.verdict,
            "evidence_ref": self.evidence_ref,
            "detail": self.detail,
        }


def classify_scope(
    verdicts: Iterable[ReadingVerdict],
    *,
    reading_tuples: Iterable[Iterable[str]] | None = None,
) -> str:
    """Derive the claim scope from a verdict matrix.  The load-bearing rule.

    ``reading_tuples`` is the convention's enumerated tuple set.  When supplied,
    the verdicts must cover it *exactly*: a matrix that evaluated three of four
    readings must not read as a full sweep, because that is precisely how a
    convention-relative result gets announced as unconditional.
    """

    items = tuple(verdicts)
    if not items:
        raise ConventionError("invalid_nonempty_list:verdicts")
    keys: list[tuple[str, ...]] = []
    arity: int | None = None
    for item in items:
        if item.verdict not in VERDICTS:
            raise ConventionError("verdict_unknown")
        key = tuple(item.reading_tuple)
        if not key or any(not isinstance(part, str) or not part for part in key):
            raise ConventionError("verdict_matrix_reading_tuple_malformed")
        if arity is None:
            arity = len(key)
        elif len(key) != arity:
            raise ConventionError("verdict_matrix_arity_inconsistent")
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ConventionError("verdict_matrix_duplicate_reading_tuple")
    if reading_tuples is not None:
        expected = {tuple(item) for item in reading_tuples}
        if set(keys) != expected:
            raise ConventionError("verdict_matrix_incomplete")
    outcomes = {item.verdict for item in items}
    if "not_evaluated" in outcomes:
        return "contested_unevaluated"
    if "refutes" not in outcomes:
        return "refuted_under_no_reading"
    if outcomes == {"refutes"}:
        return "unconditional"
    return "convention_relative"


@dataclass(frozen=True, slots=True, kw_only=True)
class VerdictMatrix:
    """One claim's verdicts across a convention's reading tuples."""

    matrix_id: str
    claim_id: str
    convention_id: str
    convention_hash: str
    verdicts: tuple[ReadingVerdict, ...]
    content_hash: str = ""

    def scope(self, *, convention: ConventionRecord | None = None) -> str:
        """Derived scope.  Never supplied; see :func:`classify_scope`."""

        return classify_scope(
            self.verdicts,
            reading_tuples=None if convention is None else convention.reading_tuples(),
        )

    def reading_tuples(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(item.reading_tuple) for item in self.verdicts)

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "matrix_id": self.matrix_id,
            "claim_id": self.claim_id,
            "convention_id": self.convention_id,
            "convention_hash": self.convention_hash,
            "verdicts": [item.payload() for item in self.verdicts],
            "derived_scope": self.scope(),
            "creates_mathematical_warrant": False,
            "creates_novelty_status": False,
            "content_hash": self.content_hash if include_hash else None,
        }

    def finalized(self) -> "VerdictMatrix":
        return replace(
            self, content_hash=canonical_hash(self.payload(include_hash=False))
        )


_MATRIX_FIELDS = frozenset({
    "schema_version", "policy_id", "matrix_id", "claim_id", "convention_id",
    "convention_hash", "verdicts", "derived_scope",
    "creates_mathematical_warrant", "creates_novelty_status", "content_hash",
})
_VERDICT_FIELDS = frozenset({"reading_tuple", "verdict", "evidence_ref", "detail"})


def _load_verdict(value: Any, field: str) -> ReadingVerdict:
    if not isinstance(value, dict) or set(value) != set(_VERDICT_FIELDS):
        raise ConventionError("verdict_field_set_mismatch")
    verdict = value["verdict"]
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise ConventionError("verdict_unknown")
    raw = value["reading_tuple"]
    if not isinstance(raw, list) or not raw or len(raw) > MAX_TERMS:
        raise ConventionError("verdict_matrix_reading_tuple_malformed")
    reading_tuple = tuple(
        _token(item, f"{field}.reading_tuple[{index}]")
        for index, item in enumerate(raw)
    )
    if len(set(reading_tuple)) != len(reading_tuple):
        raise ConventionError("verdict_matrix_reading_tuple_malformed")
    evidence = value["evidence_ref"]
    if verdict == "not_evaluated":
        if evidence is not None:
            raise ConventionError("verdict_evidence_ref_forbidden")
    else:
        if evidence is None:
            raise ConventionError("verdict_evidence_ref_required")
        evidence = _evidence_ref(evidence, f"{field}.evidence_ref")
    return ReadingVerdict(
        reading_tuple=reading_tuple,
        verdict=verdict,
        evidence_ref=evidence,
        detail=_text(value["detail"], f"{field}.detail"),
    )


def load_verdict_matrix(payload: bytes | str | Mapping[str, Any]) -> VerdictMatrix:
    """Validate and bind a verdict matrix.  The scope is recomputed, not read."""

    value = _decode(payload)
    if set(value) != set(_MATRIX_FIELDS):
        raise ConventionError("field_set_mismatch")
    _require_envelope(value)
    if value["creates_mathematical_warrant"] is not False:
        raise ConventionError("verdict_matrix_cannot_create_mathematical_warrant")
    if value["creates_novelty_status"] is not False:
        raise ConventionError("verdict_matrix_cannot_create_novelty_status")
    raw = value["verdicts"]
    if not isinstance(raw, list) or not raw or len(raw) > MAX_READING_TUPLES:
        raise ConventionError("invalid_nonempty_list:verdicts")
    verdicts = tuple(
        _load_verdict(item, f"verdicts[{index}]") for index, item in enumerate(raw)
    )
    matrix = VerdictMatrix(
        matrix_id=_identifier(value["matrix_id"], "matrix_id"),
        claim_id=_identifier(value["claim_id"], "claim_id"),
        convention_id=_identifier(value["convention_id"], "convention_id"),
        convention_hash=_hash(value["convention_hash"], "convention_hash"),
        verdicts=verdicts,
        content_hash=_hash(value["content_hash"], "content_hash"),
    )
    if value["derived_scope"] != matrix.scope():
        raise ConventionError("scope_derived_classification_mismatch")
    if matrix.content_hash != matrix.finalized().content_hash:
        raise ConventionError("content_hash_mismatch")
    return matrix


def require_convention_binding(
    matrix: VerdictMatrix, convention: ConventionRecord
) -> None:
    """Bind a matrix to the exact reading set it was decided under.

    Re-reading a word changes the convention's content hash, which strands every
    matrix asserted under the old reading.  That is the point: an invalidated
    claim must fail loudly rather than keep its old scope.
    """

    if matrix.convention_id != convention.convention_id:
        raise ConventionError("convention_id_mismatch")
    if matrix.convention_hash != convention.content_hash:
        raise ConventionError("convention_hash_mismatch")
    classify_scope(matrix.verdicts, reading_tuples=convention.reading_tuples())


def weakest_reading_status(
    convention: ConventionRecord, reading_tuple: Iterable[str]
) -> str:
    """The least-well-read passage in a reading tuple.

    ``asserted`` here means the claim rests on source text nobody in the review
    chain could re-extract.  Such a claim must not be described as
    source-faithful.
    """

    key = tuple(reading_tuple)
    if key not in convention.reading_tuples():
        raise ConventionError("reading_tuple_not_enumerated")
    index = convention.readings()
    return min(
        (index[reading_id].reading_status for reading_id in key),
        key=lambda status: (_READING_STATUS_STRENGTH[status], status),
    )


def reading_coupling_index(
    conventions: Iterable[ConventionRecord],
) -> dict[str, tuple[str, ...]]:
    """Map each reading id to every subject a change to it can invalidate.

    Roucairol and Cazenave hedge their own paper as "either Graffiti 197 is
    refuted or Graffiti 322 is refuted", depending on the meaning of ``range``.
    This index is what makes that coupling mechanical instead of editorial.
    """

    index: dict[str, set[str]] = {}
    for convention in conventions:
        subjects = set(convention.governed_subject_ids())
        for reading_id in convention.readings():
            index.setdefault(reading_id, set()).update(subjects)
    return {key: tuple(sorted(index[key])) for key in sorted(index)}


# --------------------------------------------------------------------------- #
# file access
# --------------------------------------------------------------------------- #


def read_convention(path: Path) -> ConventionRecord:
    return load_convention(path.read_bytes())


def read_verdict_matrix(path: Path) -> VerdictMatrix:
    return load_verdict_matrix(path.read_bytes())


def _write(payload: dict[str, Any], path: Path, code: str) -> None:
    rendered = canonical_json(payload) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ConventionError(code)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def write_convention(record: ConventionRecord, path: Path) -> None:
    _write(record.finalized().payload(), path, "convention_record_overwrite_refused")


def write_verdict_matrix(matrix: VerdictMatrix, path: Path) -> None:
    _write(matrix.finalized().payload(), path, "verdict_matrix_overwrite_refused")
