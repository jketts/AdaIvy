"""AST sweep proving the replay path constructs no float and never divides.

The ADR's exactness claim is a property of source text, so it is checked as one.
A float on the read path would make every ranking comparison rest on machine
noise, and division would reintroduce the quotient the exact comparator exists to
avoid. Both are therefore structural refusals rather than review conventions.

The sweep is deliberately usable on arbitrary text (`sweep_source`) so
`pr.no-float-in-retrieval-path` can fire the instrument against a deliberately
impure module before asserting the real modules are clean. A check that cannot be
made to fail proves nothing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: The modules a replay reaches. Ingestion converts provider floats exactly once
#: (see :mod:`quantization`) and is not on this list by design.
READ_PATH_MODULES = (
    "constants.py", "errors.py", "partition.py", "replay.py", "similarity.py",
)

#: Names whose mere appearance would put an inexact value on the read path.
FORBIDDEN_NAMES = ("float", "complex")

# The division ban is ABSOLUTE and carries no exception list. `pathlib` overloads
# `/` for path composition, which is not arithmetic, but a static sweep cannot
# tell the two apart without type inference -- and an exception list is exactly
# where a real division would eventually hide. So the replay-path modules compose
# paths with `Path.joinpath` and `/` never appears in them at all.

#: Modules that would import inexact arithmetic wholesale.
FORBIDDEN_IMPORTS = ("math", "cmath", "statistics", "numpy", "random")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadPathFinding:
    module: str
    line: int
    kind: str
    detail: str

    def render(self) -> str:
        return f"{self.module}:{self.line} {self.kind} {self.detail}"


def sweep_source(text: str, *, module: str) -> tuple[ReadPathFinding, ...]:
    """Findings for one module's source text. Empty means exact."""

    tree = ast.parse(text, filename=module)
    findings: list[ReadPathFinding] = []

    def add(node: ast.AST, kind: str, detail: str) -> None:
        findings.append(
            ReadPathFinding(
                module=module, line=int(getattr(node, "lineno", 0)),
                kind=kind, detail=detail,
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, complex):
                add(node, "inexact_literal", "complex literal")
            elif isinstance(node.value, bool):
                continue
            elif type(node.value).__name__ == "float":
                add(node, "inexact_literal", f"float literal {node.value!r}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            add(node, "inexact_name", node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            add(node, "inexact_name", node.attr)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
            add(node, "division", type(node.op).__name__)
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
            add(node, "division", type(node.op).__name__)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    add(node, "inexact_import", alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in FORBIDDEN_IMPORTS:
                add(node, "inexact_import", node.module or "")
    findings.sort(key=lambda item: (item.module, item.line, item.kind, item.detail))
    return tuple(findings)


def package_root() -> Path:
    return Path(__file__).resolve().parent


def sweep_read_path(root: Path | None = None) -> tuple[ReadPathFinding, ...]:
    """Sweep every declared replay-path module of this package."""

    directory = root or package_root()
    findings: list[ReadPathFinding] = []
    for name in READ_PATH_MODULES:
        path = directory / name
        findings.extend(
            sweep_source(path.read_text(encoding="utf-8"), module=name)
        )
    findings.sort(key=lambda item: (item.module, item.line, item.kind, item.detail))
    return tuple(findings)


__all__ = [
    "FORBIDDEN_IMPORTS",
    "FORBIDDEN_NAMES",
    "READ_PATH_MODULES",
    "ReadPathFinding",
    "package_root",
    "sweep_read_path",
    "sweep_source",
]
