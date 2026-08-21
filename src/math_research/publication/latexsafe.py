"""LaTeX is a programming language, so every interpolated field is validated.

Blueprint Section 16 makes retrieved documents untrusted data. A mathematical
fragment that reaches a ``.tex`` file is executed by the typesetter, so the same
rule extends here: ``\\write18`` in a source-derived statement is a code
execution path wearing a document's clothes.

Two surfaces, two rules.

* **Prose** is escaped character-wise. No macro survives escaping, so prose
  cannot carry mathematics; a prose block that needs mathematics declares an
  explicit ``math`` run instead of relying on delimiter parsing.
* **Mathematics** is validated against a frozen allowlist. Refusal is by class,
  so an unrecognised macro is refused rather than passed through, and there is no
  trusted-input mode: project-authored fixtures are validated identically.
"""

from __future__ import annotations

import re

from .errors import PublicationValidationError

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "^": r"\textasciicircum{}",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "%": r"\%",
}

_MACRO = re.compile(r"\\([A-Za-z@]+|.)", re.DOTALL)
_ENVIRONMENT = re.compile(r"\\(begin|end)\s*\{([^{}]*)\}")

# Non-letter control sequences that carry no semantics beyond spacing or an
# escaped literal.
ALLOWED_SYMBOL_ESCAPES = frozenset({",", ";", "!", ":", " ", "\\", "{", "}", "%", "&", "#", "_", "|"})

ALLOWED_ENVIRONMENTS = frozenset(
    {"aligned", "array", "bmatrix", "cases", "matrix", "pmatrix", "smallmatrix", "vmatrix"}
)

ALLOWED_MACROS = frozenset(
    {
        # structure
        "begin", "end", "left", "right", "bigl", "bigr", "Bigl", "Bigr", "quad", "qquad",
        "text", "textrm", "mathrm", "mathbb", "mathcal", "mathbf", "mathsf", "operatorname",
        # arithmetic and relations
        "frac", "tfrac", "dfrac", "binom", "sqrt", "sum", "prod", "int", "lim", "sup", "inf",
        "max", "min", "log", "exp", "sin", "cos", "tan", "det", "dim", "ker", "deg",
        "leq", "geq", "neq", "approx", "equiv", "sim", "simeq", "cong", "propto",
        "succeq", "preceq", "succ", "prec", "ll", "gg",
        # operators and symbols
        "cdot", "cdots", "ldots", "dots", "vdots", "ddots", "times", "otimes", "oplus",
        "pm", "mp", "ast", "star", "circ", "dagger", "bullet", "infty", "partial", "nabla",
        "hat", "bar", "tilde", "vec", "overline", "underline",
        "langle", "rangle", "lvert", "rvert", "lVert", "rVert", "mid", "colon",
        # sets and logic
        "in", "notin", "ni", "subset", "subseteq", "supset", "supseteq", "cup", "cap",
        "setminus", "emptyset", "forall", "exists", "neg", "land", "lor",
        # arrows
        "to", "mapsto", "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
        "leftrightarrow", "Leftrightarrow", "implies", "iff", "longmapsto",
        # lowercase Greek
        "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta",
        "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "varrho",
        "sigma", "varsigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
        # uppercase Greek
        "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi",
        "Omega",
    }
)

# Named only to give a refusal a class rather than a bare "unknown macro". The
# allowlist above is what actually admits anything.
_PRIMITIVE_CLASSES: dict[str, str] = {
    **{name: "file_input" for name in ("input", "include", "openin", "read", "endinput", "InputIfFileExists")},
    **{name: "file_or_process_output" for name in (
        "write", "openout", "closeout", "immediate", "special", "directlua", "latelua",
        "pdfprimitive", "shipout", "systemcall", "shellescape",
    )},
    **{name: "name_or_catcode_manipulation" for name in (
        "catcode", "csname", "endcsname", "expandafter", "def", "gdef", "edef", "xdef",
        "let", "futurelet", "newcommand", "renewcommand", "providecommand", "string",
        "meaning", "aftergroup", "lowercase", "uppercase",
    )},
    **{name: "package_or_class_loading" for name in (
        "usepackage", "RequirePackage", "documentclass", "LoadClass", "makeatletter",
    )},
    **{name: "nondeterminism" for name in (
        "year", "month", "day", "time", "jobname", "pdfcreationdate", "pdfmdfivesum",
    )},
    **{name: "control_flow" for name in ("loop", "repeat", "csname@", "batchmode", "scrollmode")},
}


def _reject_control_characters(value: str, field: str) -> None:
    for character in value:
        if character in "\n\t":
            continue
        if ord(character) < 0x20 or ord(character) == 0x7F:
            raise PublicationValidationError(
                "control_character_in_field", f"{field} contains U+{ord(character):04X}"
            )


def escape_prose(value: str, field: str) -> str:
    """Escape every LaTeX-active character. No macro survives this."""

    if not isinstance(value, str):
        raise PublicationValidationError("field_not_text", f"{field} must be text")
    _reject_control_characters(value, field)
    return "".join(_ESCAPES.get(character, character) for character in value)


def validate_math(value: str, field: str) -> str:
    """Return ``value`` unchanged, or refuse it by class."""

    if not isinstance(value, str):
        raise PublicationValidationError("field_not_text", f"{field} must be text")
    if not value.strip():
        raise PublicationValidationError("empty_math_fragment", f"{field} is empty")
    _reject_control_characters(value, field)
    if "$" in value:
        raise PublicationValidationError(
            "math_shift_in_fragment", f"{field} carries an explicit math shift"
        )
    if "%" in value.replace(r"\%", ""):
        raise PublicationValidationError(
            "comment_in_math_fragment", f"{field} carries a LaTeX comment"
        )
    depth = 0
    for character in value:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise PublicationValidationError("latex_unbalanced_braces", f"{field} closes too early")
    if depth:
        raise PublicationValidationError("latex_unbalanced_braces", f"{field} leaves {depth} open")
    for kind, name in _ENVIRONMENT.findall(value):
        if name not in ALLOWED_ENVIRONMENTS:
            raise PublicationValidationError(
                "unsafe_latex_environment", f"{field} uses \\{kind}{{{name}}}"
            )
    for token in _MACRO.findall(value):
        if len(token) == 1 and not token.isalpha():
            if token not in ALLOWED_SYMBOL_ESCAPES:
                raise PublicationValidationError(
                    "unsafe_latex_macro", f"{field} uses the escape \\{token!r}"
                )
            continue
        if "@" in token:
            raise PublicationValidationError(
                "unsafe_latex_primitive",
                f"{field} uses the internal macro \\{token} (class name_or_catcode_manipulation)",
            )
        if token in _PRIMITIVE_CLASSES:
            raise PublicationValidationError(
                "unsafe_latex_primitive",
                f"{field} uses \\{token} (class {_PRIMITIVE_CLASSES[token]})",
            )
        if token not in ALLOWED_MACROS:
            raise PublicationValidationError(
                "unknown_latex_macro", f"{field} uses \\{token}, which the allowlist does not admit"
            )
    return value


def validate_verbatim(value: str, field: str) -> str:
    """Lean source and hashes are printed verbatim, so only the fence can break."""

    if not isinstance(value, str):
        raise PublicationValidationError("field_not_text", f"{field} must be text")
    _reject_control_characters(value, field)
    if r"\end{verbatim}" in value:
        raise PublicationValidationError(
            "verbatim_fence_in_field", f"{field} closes its own verbatim block"
        )
    return value
