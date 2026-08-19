"""Fail-closed validation for restricted theorem/proof fragments."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from ..domain.entities import OpaqueId
from . import MAX_STDIN_BYTES, SCHEMA_VERSION
from .records import DeclaredAssumption, FormalCheckRequest, MeaningTest, PolicyRejection, SourceKind

ALLOWED_IMPORTS = ("Mathlib.Data.Nat.Basic",)
_NAME = re.compile(r"^AdaIvy[A-Za-z0-9_]{1,63}$")
_ASSUMPTION_NAME = re.compile(r"^AdaIvyAssumption[A-Za-z0-9_]{1,48}$")
_TEST_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,63}$")
_FORBIDDEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:import|prelude|namespace|section|end|open|export|include|omit|"
    r"axiom|theorem|lemma|def|abbrev|opaque|example|instance|structure|class|inductive|"
    r"attribute|mutual|initialize|builtin_initialize|register_option|declare_syntax_cat|"
    r"universe|variable|local|private|protected|noncomputable|unsafe|partial|extern|"
    r"macro|syntax|elab|scoped|set_option|run_tac|run_io|"
    r"sorry|admit|by\?|exact\?|apply\?|simp\?|native_decide|ofReduceBool|"
    r"IO|System|FilePath|Process|Lake|Lean\.Elab|Lean\.Parser|C\.)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_HASH_COMMAND = re.compile(r"#[A-Za-z_]")
_PLACEHOLDER = re.compile(r"(?<![A-Za-z0-9_])_(?![A-Za-z0-9_])|\?[A-Za-z0-9_]")


class RequestValidationError(ValueError):
    def __init__(self, rejections: tuple[PolicyRejection, ...]) -> None:
        self.rejections = rejections
        super().__init__("; ".join(f"{item.field}:{item.code}" for item in rejections))


def _exact_fields(value: Mapping[str, Any], expected: set[str], field: str, errors: list[PolicyRejection]) -> None:
    missing, extra = expected - set(value), set(value) - expected
    if missing:
        errors.append(PolicyRejection("missing_fields", field, ",".join(sorted(missing))))
    if extra:
        errors.append(PolicyRejection("unknown_fields", field, ",".join(sorted(extra))))


def _fragment(value: Any, field: str, errors: list[PolicyRejection], *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(PolicyRejection("invalid_fragment", field, "must be a non-empty string"))
        return ""
    if len(value.encode("utf-8")) > max_length:
        errors.append(PolicyRejection("fragment_too_large", field, f"maximum is {max_length} UTF-8 bytes"))
    if "\x00" in value or "\r" in value:
        errors.append(PolicyRejection("invalid_character", field, "NUL and carriage return are forbidden"))
    if "--" in value or "/-" in value or "-/" in value or '"' in value:
        errors.append(PolicyRejection("comments_or_strings_forbidden", field, "comments and string literals are outside v1"))
    match = _FORBIDDEN.search(value)
    if match:
        errors.append(PolicyRejection("forbidden_lean_feature", field, match.group(0)))
    if _HASH_COMMAND.search(value):
        errors.append(PolicyRejection("command_forbidden", field, "Lean hash commands are outside v1"))
    if _PLACEHOLDER.search(value):
        errors.append(PolicyRejection("placeholder_forbidden", field, "holes and metavariables are outside v1"))
    return value.strip()


def parse_request_bytes(data: bytes) -> FormalCheckRequest:
    if len(data) > MAX_STDIN_BYTES:
        raise RequestValidationError((PolicyRejection("request_too_large", "$", str(len(data))),))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RequestValidationError((PolicyRejection("invalid_utf8", "$", str(error)),)) from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise RequestValidationError((PolicyRejection("malformed_json", "$", f"line {error.lineno} column {error.colno}"),)) from error
    return parse_request(value)


def parse_request(value: Any) -> FormalCheckRequest:
    errors: list[PolicyRejection] = []
    if not isinstance(value, Mapping):
        raise RequestValidationError((PolicyRejection("invalid_type", "$", "expected object"),))
    expected = {field.name for field in fields(FormalCheckRequest)}
    _exact_fields(value, expected, "$", errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(PolicyRejection("unsupported_schema", "schema_version", repr(value.get("schema_version"))))

    def identifier(field: str, *, optional: bool = False) -> OpaqueId | None:
        item = value.get(field)
        if optional and item is None:
            return None
        try:
            return OpaqueId(item) if isinstance(item, str) else (_ for _ in ()).throw(ValueError())
        except ValueError:
            errors.append(PolicyRejection("invalid_identifier", field, repr(item)))
            return None

    request_id = identifier("request_id")
    claim_id = identifier("claim_id")
    alignment_id = identifier("semantic_alignment_id", optional=True)
    try:
        source_kind = SourceKind(value.get("source_kind"))
    except (ValueError, TypeError):
        errors.append(PolicyRejection("invalid_source_kind", "source_kind", repr(value.get("source_kind"))))
        source_kind = SourceKind.EXTERNAL
    declaration_name = value.get("declaration_name")
    if not isinstance(declaration_name, str) or not _NAME.fullmatch(declaration_name):
        errors.append(PolicyRejection("invalid_declaration_name", "declaration_name", repr(declaration_name)))
        declaration_name = "AdaIvyInvalid"
    imports_value = value.get("imports")
    imports: tuple[str, ...] = ()
    if not isinstance(imports_value, list) or not all(isinstance(item, str) for item in imports_value):
        errors.append(PolicyRejection("invalid_import_manifest", "imports", "expected an array of strings"))
    else:
        imports = tuple(imports_value)
        if imports != tuple(sorted(set(imports))):
            errors.append(PolicyRejection("noncanonical_import_manifest", "imports", "must be unique and sorted"))
        unknown = tuple(item for item in imports if item not in ALLOWED_IMPORTS)
        if unknown:
            errors.append(PolicyRejection("unknown_import", "imports", ",".join(unknown)))
    assumptions_value = value.get("assumptions")
    assumptions: list[DeclaredAssumption] = []
    if not isinstance(assumptions_value, list) or len(assumptions_value) > 16:
        errors.append(PolicyRejection("invalid_assumptions", "assumptions", "expected at most 16 assumptions"))
    else:
        seen: set[str] = set()
        for index, item in enumerate(assumptions_value):
            field = f"assumptions[{index}]"
            if not isinstance(item, Mapping):
                errors.append(PolicyRejection("invalid_assumption", field, "expected object")); continue
            _exact_fields(item, {"name", "type_expression"}, field, errors)
            name = item.get("name")
            if not isinstance(name, str) or not _ASSUMPTION_NAME.fullmatch(name) or name in seen:
                errors.append(PolicyRejection("invalid_assumption_name", f"{field}.name", repr(name))); continue
            seen.add(name)
            assumptions.append(DeclaredAssumption(name, _fragment(item.get("type_expression"), f"{field}.type_expression", errors, max_length=8_192)))
        if tuple(item.name for item in assumptions) != tuple(sorted(item.name for item in assumptions)):
            errors.append(PolicyRejection("noncanonical_assumptions", "assumptions", "must be sorted by name"))
    target = _fragment(value.get("target_statement"), "target_statement", errors, max_length=65_536)
    proof = _fragment(value.get("proof_fragment"), "proof_fragment", errors, max_length=131_072)
    tests_value = value.get("meaning_tests")
    tests: list[MeaningTest] = []
    if not isinstance(tests_value, list) or len(tests_value) > 16:
        errors.append(PolicyRejection("invalid_meaning_tests", "meaning_tests", "expected at most 16 tests"))
    else:
        seen_tests: set[str] = set()
        for index, item in enumerate(tests_value):
            field = f"meaning_tests[{index}]"
            if not isinstance(item, Mapping):
                errors.append(PolicyRejection("invalid_meaning_test", field, "expected object")); continue
            _exact_fields(item, {"test_id", "statement", "proof_fragment"}, field, errors)
            test_id = item.get("test_id")
            if not isinstance(test_id, str) or not _TEST_ID.fullmatch(test_id) or test_id in seen_tests:
                errors.append(PolicyRejection("invalid_test_id", f"{field}.test_id", repr(test_id))); continue
            seen_tests.add(test_id)
            tests.append(MeaningTest(test_id, _fragment(item.get("statement"), f"{field}.statement", errors, max_length=8_192), _fragment(item.get("proof_fragment"), f"{field}.proof_fragment", errors, max_length=16_384)))
    if errors:
        raise RequestValidationError(tuple(errors))
    assert request_id is not None and claim_id is not None
    return FormalCheckRequest(request_id, claim_id, alignment_id, source_kind, declaration_name, imports, tuple(assumptions), target, proof, tuple(tests))
