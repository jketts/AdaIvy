"""Repository-wide structural invariants.

ADR-0026 makes the acceptance suite the executable record of a slice's
thresholds. These tests encode the standing properties that every slice must
preserve, so drift fails here rather than being discovered by reading diffs.
"""

from __future__ import annotations

import ast
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
LOCAL_ROOTS = frozenset({"math_research", "phase0_harness"})

# Modules that can open an outbound connection. The offline acceptance path must
# not import any of these at module scope; a gated adapter loads what it needs
# lazily inside its own authorized call path.
NETWORK_MODULES = frozenset(
    {
        "socket", "ssl", "asyncio", "selectors", "webbrowser",
        "urllib.request", "urllib.error", "http.client", "http.server",
        "ftplib", "smtplib", "imaplib", "poplib", "telnetlib",
        "xmlrpc.client", "xmlrpc.server", "socketserver",
        "requests", "httpx", "urllib3", "aiohttp",
    }
)

# The only authorized lazy loads of a non-standard-library module, as
# (path relative to src, module name). Each is an opt-in gated boundary that the
# offline path never reaches. Adding an entry is an architecture change and
# needs an ADR.
GATED_DYNAMIC_IMPORTS = frozenset(
    {
        ("math_research/phase2/model_gateway.py", "openai"),
        ("phase0_harness/adapters/probes.py", "paperqa"),
    }
)


def source_files() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _root(name: str) -> str:
    return name.split(".", 1)[0]


def _is_third_party(name: str) -> bool:
    root = _root(name)
    return root not in sys.stdlib_module_names and root not in LOCAL_ROOTS


def _module_level_imports(tree: ast.Module) -> list[tuple[str, int]]:
    """Imports that execute on import, i.e. not inside a function or method.

    Class bodies execute at import time, so they count; function bodies do not.
    """
    found: list[tuple[str, int]] = []

    def walk(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, ast.Import):
                found.extend((alias.name, node.lineno) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    found.append((node.module, node.lineno))
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                # Guarded module-level imports still execute at import time.
                for attr in ("body", "orelse", "finalbody", "handlers"):
                    block = getattr(node, attr, None) or []
                    walk([n for n in block if isinstance(n, ast.stmt)])
                    for handler in (h for h in block if isinstance(h, ast.ExceptHandler)):
                        walk(handler.body)
            elif isinstance(node, ast.ClassDef):
                walk(node.body)

    walk(tree.body)
    return found


class NoNetworkAtImportTimeTests(unittest.TestCase):
    def test_no_module_level_network_import(self) -> None:
        violations = []
        for path in source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for name, lineno in _module_level_imports(tree):
                if name in NETWORK_MODULES or _root(name) in NETWORK_MODULES:
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{lineno} imports {name}")
        self.assertEqual(
            violations,
            [],
            "the offline path must not import a network module at module scope; "
            "load it lazily inside a gated adapter instead",
        )


class StandardLibraryOnlyRuntimeTests(unittest.TestCase):
    def test_no_module_level_third_party_import(self) -> None:
        violations = []
        for path in source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for name, lineno in _module_level_imports(tree):
                if _is_third_party(name):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{lineno} imports {name}")
        self.assertEqual(
            violations,
            [],
            "the runtime is standard-library only; a new dependency needs an ADR "
            "and a pinned, hash-recorded manifest",
        )

    def test_dynamic_third_party_loads_are_declared_gated_boundaries(self) -> None:
        """importlib.import_module / find_spec on a literal third-party name."""
        observed = set()
        for path in source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel = path.relative_to(SRC_ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"import_module", "find_spec"}:
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if _is_third_party(arg.value):
                            observed.add((rel, _root(arg.value)))
        self.assertEqual(
            observed,
            set(GATED_DYNAMIC_IMPORTS),
            "the set of lazy third-party loads changed; each one is a gated "
            "external boundary and must be declared in GATED_DYNAMIC_IMPORTS",
        )

    def test_pyproject_declares_no_runtime_dependency(self) -> None:
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["dependencies"], [])


class PackagingTests(unittest.TestCase):
    def test_console_scripts_resolve_to_real_entry_points(self) -> None:
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        self.assertTrue(scripts, "expected at least one console script")
        for name, target in scripts.items():
            module_path, _, attr = target.partition(":")
            path = SRC_ROOT / (module_path.replace(".", "/") + ".py")
            self.assertTrue(path.is_file(), f"{name} points at missing module {module_path}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            defined = {
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            self.assertIn(attr, defined, f"{name} points at missing callable {target}")


if __name__ == "__main__":
    unittest.main()
