"""AST sweep proving no acquisition-path module can name an e-print target.

ADR-0067 excludes full text: "A code path that can fetch a PDF is out of scope
and must not exist."  That is a claim about source text, so it is checked as one.
:func:`assert_metadata_target` already admits exactly one endpoint at runtime;
this sweep is the complementary static property, so a second request builder
added later cannot quietly introduce an e-print path.

Only NON-DOCSTRING string literals are inspected.  Comments never reach the AST,
and a docstring that discusses e-prints -- as several in this package do -- is
prose, not a request target.  A literal that could become part of a URL is a
different thing, and that is what is refused.

The sweep is deliberately usable on arbitrary text (:func:`sweep_source`) so
``pr.corpus-full-text-token-absent-from-acquisition-path`` can fire the
instrument against a deliberately impure module before asserting the real
modules are clean.  A check that cannot be made to fail proves nothing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: Every module that can take part in composing or issuing a request, or in
#: deriving a record from a response.  ``sourcesweep.py`` and ``probes.py`` are
#: excluded because they carry the forbidden tokens as test data.
ACQUISITION_PATH_MODULES = (
    "__init__.py", "acquisition.py", "activation.py", "atom.py", "constants.py",
    "errors.py", "ingestion.py", "live.py", "pacing.py", "ports.py",
    "projection.py", "records.py", "replay.py", "report.py", "rights.py",
    "serialization.py", "store.py", "tranche.py",
)

#: Path fragments of arXiv's e-print and rendering endpoints.  A string literal
#: containing one of these could only ever be used to build a request for
#: content this slice is not licensed to store.
FORBIDDEN_URL_TOKENS = (
    "/pdf", "/ps/", "/dvi", "/format/", "/e-print", "/src/", "/tarball",
    "/ftp/", "/bulk", "arxiv.org/pdf",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SweepFinding:
    module: str
    line: int
    token: str
    detail: str

    def render(self) -> str:
        return f"{self.module}:{self.line} names {self.token} in {self.detail}"


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Identity set of the string constants that are docstrings."""

    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def sweep_source(text: str, *, module: str) -> tuple[SweepFinding, ...]:
    """Findings for one module's source text. Empty means metadata-only."""

    tree = ast.parse(text, filename=module)
    docstrings = _docstring_nodes(tree)
    findings: list[SweepFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docstrings:
            continue
        value = node.value
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", "strict")
            except UnicodeDecodeError:
                continue
        if not isinstance(value, str):
            continue
        lowered = value.casefold()
        for token in FORBIDDEN_URL_TOKENS:
            if token in lowered:
                findings.append(SweepFinding(
                    module=module, line=int(getattr(node, "lineno", 0)),
                    token=token, detail="a non-docstring string literal",
                ))
    findings.sort(key=lambda item: (item.module, item.line, item.token))
    return tuple(findings)


def package_root() -> Path:
    return Path(__file__).resolve().parent


def sweep_acquisition_path(root: Path | None = None) -> tuple[SweepFinding, ...]:
    """Sweep every declared acquisition-path module of this package."""

    directory = root or package_root()
    findings: list[SweepFinding] = []
    for name in ACQUISITION_PATH_MODULES:
        path = directory.joinpath(name)
        findings.extend(sweep_source(path.read_text(encoding="utf-8"), module=name))
    findings.sort(key=lambda item: (item.module, item.line, item.token))
    return tuple(findings)


def assert_acquisition_path_clean(root: Path | None = None) -> None:
    from .errors import FullTextTokenOnAcquisitionPathError

    findings = sweep_acquisition_path(root)
    if findings:
        raise FullTextTokenOnAcquisitionPathError(
            "; ".join(finding.render() for finding in findings)
        )


__all__ = [
    "ACQUISITION_PATH_MODULES",
    "FORBIDDEN_URL_TOKENS",
    "SweepFinding",
    "assert_acquisition_path_clean",
    "package_root",
    "sweep_acquisition_path",
    "sweep_source",
]
