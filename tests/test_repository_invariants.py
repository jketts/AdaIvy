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
SPIKES_ROOT = REPO_ROOT / "spikes"
LOCAL_ROOTS = frozenset({"math_research", "phase0_harness", "spikes"})

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
# (path relative to the repository root, module name). Each is an opt-in gated
# boundary that the offline path never reaches. Adding an entry is an
# architecture change and needs an ADR.
#
# The five spike entries are the ADR-0045 noncommuting-SDP engine comparison.
# Its licence restriction is permissive-only: Clarabel (Apache-2.0), SCS (MIT),
# CVXPY (Apache-2.0) plus the BSD numeric closure they require. CVXOPT
# (GPL-3.0-or-later) and MOSEK (commercial EULA) are out of scope and must never
# appear here; `spikes/phase5_noncommuting_sdp/engines.py` also refuses them at
# runtime, and `tests/test_phase5_noncommuting_sdp_comparison.py` asserts both.
GATED_DYNAMIC_IMPORTS = frozenset(
    {
        ("src/math_research/phase2/anthropic_gateway.py", "anthropic"),
        ("src/math_research/phase2/model_gateway.py", "openai"),
        ("src/phase0_harness/adapters/probes.py", "paperqa"),
        ("spikes/phase5_noncommuting_sdp/engines.py", "clarabel"),
        ("spikes/phase5_noncommuting_sdp/engines.py", "cvxpy"),
        ("spikes/phase5_noncommuting_sdp/engines.py", "numpy"),
        ("spikes/phase5_noncommuting_sdp/engines.py", "scipy"),
        ("spikes/phase5_noncommuting_sdp/engines.py", "scs"),
    }
)

# Call names that constitute a gated dynamic load. `load_gated_module` and
# `gated_module_version` are the ModuleResolver seam in the ADR-0045 spike; they
# take a literal module name at every call site precisely so this file can
# enumerate the complete set statically.
GATED_CALL_NAMES = frozenset(
    {"import_module", "find_spec", "load_gated_module", "gated_module_version"}
)

# Pre-existing module-level third-party imports outside `src/`. `src/` allows
# none at all. This is a declared exception, not an unscanned directory: the
# Phase 4 gate spike is only ever run inside the disposable pinned validator
# environment described in docs/phase-4/DEPENDENCY_LICENSE_ASSESSMENT.md.
DECLARED_MODULE_LEVEL_THIRD_PARTY = frozenset(
    {("spikes/phase4_gate/gate_spike.py", "jsonschema")}
)


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def source_files() -> list[Path]:
    return _python_files(SRC_ROOT)


def spike_files() -> list[Path]:
    return _python_files(SPIKES_ROOT)


def scanned_files() -> list[Path]:
    """Every non-test module the offline acceptance path can reach."""

    return source_files() + spike_files()


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
        for path in scanned_files():
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
        """A gated call taking a literal third-party module name."""
        observed = set()
        for path in scanned_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel = path.relative_to(REPO_ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name not in GATED_CALL_NAMES:
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

    def test_no_third_party_import_at_any_nesting_level(self) -> None:
        """A gated boundary must be the ONLY route to a third-party module.

        A plain `import numpy` inside a function would be a third-party load
        this file cannot enumerate, so it is forbidden even though it is not at
        module scope. The declared exception list is checked separately.
        """
        declared = {
            (path, module)
            for path, module in DECLARED_MODULE_LEVEL_THIRD_PARTY
        }
        violations = []
        for path in scanned_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[tuple[str, int]] = []
                if isinstance(node, ast.Import):
                    names = [(alias.name, node.lineno) for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [(node.module, node.lineno)]
                for name, lineno in names:
                    if not _is_third_party(name):
                        continue
                    if (rel, _root(name)) in declared:
                        continue
                    violations.append(f"{rel}:{lineno} imports {name}")
        self.assertEqual(
            violations,
            [],
            "a third-party module may only be reached through a declared gated "
            "load with a literal module name; add an ADR and a declaration first",
        )

    def test_declared_module_level_third_party_exceptions_still_exist(self) -> None:
        """A stale exception must be removed, not left to hide a later import."""
        for rel, module in DECLARED_MODULE_LEVEL_THIRD_PARTY:
            path = REPO_ROOT / rel
            self.assertTrue(path.is_file(), f"declared exception {rel} no longer exists")
            self.assertIn(module, path.read_text(encoding="utf-8"))

    def test_no_exception_may_ever_cover_a_production_module(self) -> None:
        """`src/` allows no module-level third-party import, with no exception.

        The exception list is the one route by which this file's guarantee could
        be eroded, so the claim that it never covers production code is asserted
        rather than left to the comment above it. A spike runs only inside its
        own declared disposable environment; `src/` is the offline acceptance
        path and has no equivalent escape.
        """
        production = sorted(
            rel for rel, _ in DECLARED_MODULE_LEVEL_THIRD_PARTY
            if rel.startswith("src/")
        )
        self.assertEqual(
            production,
            [],
            "a declared third-party exception names a module under src/; the "
            "offline acceptance path must reach a third-party module only "
            "through a gated load with a literal module name",
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
