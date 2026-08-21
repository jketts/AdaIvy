"""Licence-gated adapters for two independent SDP engines.

Authorisation (ADR-0045) is narrow and is enforced here, not only documented:

* permitted: Clarabel (Apache-2.0), SCS (MIT), CVXPY (Apache-2.0), plus the
  BSD/MIT numeric closure those three require (NumPy, SciPy);
* excluded: CVXOPT (GPL-3.0-or-later) and MOSEK (commercial EULA), together
  with the other copyleft/commercial solvers CVXPY lists as optional extras.

Three independent controls keep an excluded engine out:

1. :func:`authorize_module` is the only door to a dynamic import and it rejects
   every name that is not in :data:`AUTHORIZED_MODULES`. An excluded name gets
   a specific refusal, not a generic one.
2. Every load goes through :meth:`ModuleResolver.load_gated_module` with a
   literal module name, so ``tests/test_repository_invariants.py`` can enumerate
   the complete set of gated boundaries statically and fail on an undeclared
   one.
3. The CVXPY adapter refuses to run at all if an excluded solver is present in
   the environment, and refuses to accept a result if CVXPY selected any solver
   other than SCS. A licence violation therefore fails closed instead of
   producing a usable number.

No adapter can produce anything but a candidate: it returns
:class:`~.ports.NumericSolution`, whose trust level is a constant.

Nothing here is imported on the offline path. With the engines absent every
adapter returns a :class:`~.ports.MissingTool` record; that is the behaviour the
offline acceptance suite asserts, without a skip.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import math
import time
from dataclasses import dataclass
from typing import Any

from .encoding import ExactProgram, upper_triangle_indices
from .ports import (
    EngineDescriptor,
    EngineProbe,
    EngineRun,
    MissingTool,
    ModuleResolver,
    NumericSolution,
    OperationalObservation,
)


class LicenseNotPermittedError(RuntimeError):
    """A module outside the ADR-0045 permissive allowlist was requested."""


class EngineUnavailableError(RuntimeError):
    """An authorised module is not importable, so the engine cannot run."""


PERMITTED_LICENSE_EXPRESSIONS = frozenset(
    {"Apache-2.0", "MIT", "MIT-0", "BSD-3-Clause"}
)

EXCLUDED_MODULES: dict[str, str] = {
    "cvxopt": "GPL-3.0-or-later; out of scope by owner restriction (ADR-0045)",
    "mosek": "commercial EULA and licence token; out of scope (ADR-0045)",
    "ecos": "GPL-3.0-or-later; a CVXPY extra that is never selected (ADR-0045)",
    "gurobipy": "commercial licence; out of scope (ADR-0045)",
    "xpress": "commercial licence; out of scope (ADR-0045)",
    "cylp": "copyleft/commercial closure unreviewed; out of scope (ADR-0045)",
    "coptpy": "commercial licence; out of scope (ADR-0045)",
    "knitro": "commercial licence; out of scope (ADR-0045)",
}
"""Names that must never be imported, probed, or adopted by this spike."""

FORBIDDEN_CVXPY_SOLVERS = frozenset({"CVXOPT", "MOSEK", "ECOS", "ECOS_BB", "GUROBI", "XPRESS", "COPT", "CBC"})
"""CVXPY solver identifiers whose presence makes the environment unauthorised."""


@dataclass(frozen=True, slots=True)
class ModuleLicense:
    license_expression: str
    license_url: str
    role: str


AUTHORIZED_MODULES: dict[str, ModuleLicense] = {
    "clarabel": ModuleLicense(
        "Apache-2.0",
        "https://github.com/oxfordcontrol/Clarabel.rs",
        "direct interior-point SDP engine",
    ),
    "scs": ModuleLicense(
        "MIT",
        "https://github.com/cvxgrp/scs",
        "first-order operator-splitting SDP engine",
    ),
    "cvxpy": ModuleLicense(
        "Apache-2.0",
        "https://github.com/cvxpy/cvxpy",
        "modelling layer used only to drive SCS",
    ),
    "numpy": ModuleLicense(
        "BSD-3-Clause",
        "https://github.com/numpy/numpy",
        "dense array interchange required by both engines",
    ),
    "scipy": ModuleLicense(
        "BSD-3-Clause",
        "https://github.com/scipy/scipy",
        "sparse CSC matrices required by the Clarabel API",
    ),
}


def authorize_module(module_name: str) -> ModuleLicense:
    """The single authorisation door for a dynamic third-party load."""

    if not isinstance(module_name, str) or not module_name:
        raise LicenseNotPermittedError("module name must be a nonempty string")
    root = module_name.split(".", 1)[0]
    excluded = EXCLUDED_MODULES.get(root.lower())
    if excluded is not None:
        raise LicenseNotPermittedError(
            f"{root} is excluded by the ADR-0045 licence restriction: {excluded}"
        )
    entry = AUTHORIZED_MODULES.get(root)
    if entry is None:
        raise LicenseNotPermittedError(
            f"{root} is not in the ADR-0045 permissive allowlist; adding one needs an ADR"
        )
    if entry.license_expression not in PERMITTED_LICENSE_EXPRESSIONS:
        raise LicenseNotPermittedError(
            f"{root} declares {entry.license_expression}, which is not permitted"
        )
    return entry


@dataclass(frozen=True, slots=True)
class GatedImportlibResolver:
    """The real gated dynamic boundary. Authorises, then imports lazily."""

    def load_gated_module(self, module_name: str) -> Any | None:
        authorize_module(module_name)
        if importlib.util.find_spec(module_name) is None:
            return None
        return importlib.import_module(module_name)

    def gated_module_version(self, module_name: str) -> str | None:
        authorize_module(module_name)
        try:
            return importlib.metadata.version(module_name)
        except importlib.metadata.PackageNotFoundError:
            return None


@dataclass(frozen=True, slots=True)
class AbsentModuleResolver:
    """A resolver for which no engine is ever importable.

    This is how the acceptance suite exercises the fail-closed path
    deterministically, on any machine, with no skip.
    """

    def load_gated_module(self, module_name: str) -> Any | None:
        authorize_module(module_name)
        return None

    def gated_module_version(self, module_name: str) -> str | None:
        authorize_module(module_name)
        return None


def _probe(
    descriptor: EngineDescriptor,
    loaded: dict[str, Any | None],
    versions_by_name: dict[str, str | None],
) -> tuple[EngineProbe, dict[str, Any]]:
    """Build a probe from modules the adapter loaded by LITERAL name.

    The adapter, not this helper, names each module, so every gated load has a
    literal argument that ``tests/test_repository_invariants.py`` can enumerate
    statically. A drift between the descriptor and what was actually loaded
    fails closed rather than silently under-reporting a boundary.
    """

    if tuple(sorted(loaded)) != tuple(sorted(descriptor.modules)):
        raise EngineUnavailableError(
            f"{descriptor.engine_id} loaded {sorted(loaded)} but declares "
            f"{sorted(descriptor.modules)}"
        )
    present = sorted(name for name, module in loaded.items() if module is not None)
    absent = sorted(name for name, module in loaded.items() if module is None)
    modules = {name: module for name, module in loaded.items() if module is not None}
    versions = [
        (name, versions_by_name.get(name) or "unknown")
        for name in present
    ]
    available = not absent
    probe = EngineProbe(
        engine_id=descriptor.engine_id,
        available=available,
        reason_code="available" if available else "module_absent",
        modules_present=tuple(present),
        modules_absent=tuple(absent),
        module_versions=tuple(sorted(versions)),
        network_attempted=False,
    )
    return (probe, modules)


def _missing(descriptor: EngineDescriptor, probe: EngineProbe) -> EngineRun:
    return EngineRun(
        engine_id=descriptor.engine_id,
        probe=probe,
        missing_tool=MissingTool(
            engine_id=descriptor.engine_id,
            reason_code=probe.reason_code,
            detail=(
                f"{descriptor.engine_id} did not run because "
                f"{', '.join(probe.modules_absent) or 'the environment'} is not importable; "
                "build the disposable environment from "
                "requirements-phase5-sdp-comparison-py314-macos-arm64.txt to run it. "
                "An absent engine is recorded, never counted as a pass and never skipped."
            ),
            modules_absent=probe.modules_absent,
        ),
    )


def _scaled_svec(matrix: Any, indices: tuple[tuple[int, int], ...], root_two: float) -> list[float]:
    return [
        float(matrix[i][j]) if i == j else float(matrix[i][j]) * root_two
        for (i, j) in indices
    ]


def _smat_from_scaled(vector: Any, size: int, root_two: float) -> tuple[tuple[float, ...], ...]:
    out = [[0.0] * size for _ in range(size)]
    for position, (i, j) in enumerate(upper_triangle_indices(size)):
        value = float(vector[position])
        if i == j:
            out[i][i] = value
        else:
            out[i][j] = value / root_two
            out[j][i] = out[i][j]
    return tuple(tuple(row) for row in out)


CLARABEL_SETTINGS: tuple[tuple[str, str], ...] = (
    ("max_iter", "200"),
    ("tol_feas", "1e-12"),
    ("tol_gap_abs", "1e-12"),
    ("tol_gap_rel", "1e-12"),
    ("verbose", "False"),
)

SCS_SETTINGS: tuple[tuple[str, str], ...] = (
    ("eps_abs", "1e-11"),
    ("eps_rel", "1e-11"),
    ("max_iters", "200000"),
    ("solver", "SCS"),
    ("verbose", "False"),
)


@dataclass(frozen=True, slots=True)
class ClarabelEngine:
    """Direct native Clarabel adapter. Apache-2.0.

    Builds the standard cone form ``min q'x s.t. Ax + s = b`` with one
    ``ZeroConeT`` block for ``sum_i X_i = I`` and one ``PSDTriangleConeT`` per
    outcome, from the exact encoding only.
    """

    resolver: ModuleResolver = GatedImportlibResolver()

    descriptor = EngineDescriptor(
        engine_id="clarabel",
        modules=("clarabel", "numpy", "scipy"),
        license_expression="Apache-2.0",
        license_url="https://github.com/oxfordcontrol/Clarabel.rs",
        role="direct native interior-point engine",
        formulation="native_zero_cone_plus_psd_triangle_cone",
    )

    def _gated_load(self) -> tuple[dict[str, Any | None], dict[str, str | None]]:
        """The gated boundary. Every module name here is a literal, by design."""

        loaded = {
            "clarabel": self.resolver.load_gated_module("clarabel"),
            "numpy": self.resolver.load_gated_module("numpy"),
            "scipy": self.resolver.load_gated_module("scipy"),
        }
        versions = {
            "clarabel": self.resolver.gated_module_version("clarabel"),
            "numpy": self.resolver.gated_module_version("numpy"),
            "scipy": self.resolver.gated_module_version("scipy"),
        }
        return (loaded, versions)

    def probe(self) -> EngineProbe:
        return _probe(self.descriptor, *self._gated_load())[0]

    def solve(self, program: ExactProgram) -> EngineRun:
        probe, modules = _probe(self.descriptor, *self._gated_load())
        if not probe.available:
            return _missing(self.descriptor, probe)
        clarabel = modules["clarabel"]
        numpy = modules["numpy"]
        scipy_sparse = self.resolver.load_gated_module("scipy.sparse")
        if scipy_sparse is None:
            return _missing(self.descriptor, probe)

        started = time.perf_counter()
        m = program.block_dimension
        n = program.outcomes
        indices = upper_triangle_indices(m)
        triangle = len(indices)
        root_two = math.sqrt(2.0)

        q = numpy.array(
            [
                -value
                for block in program.objective_blocks
                for value in _scaled_svec(block, indices, root_two)
            ],
            dtype=float,
        )
        columns = n * triangle
        identity_rhs = [1.0 if i == j else 0.0 for (i, j) in indices]
        rows: list[list[float]] = []
        for row in range(triangle):
            dense = [0.0] * columns
            for block in range(n):
                dense[block * triangle + row] = 1.0
            rows.append(dense)
        for column in range(columns):
            dense = [0.0] * columns
            dense[column] = -1.0
            rows.append(dense)
        matrix_a = scipy_sparse.csc_matrix(numpy.array(rows, dtype=float))
        matrix_p = scipy_sparse.csc_matrix((columns, columns), dtype=float)
        vector_b = numpy.array(identity_rhs + [0.0] * columns, dtype=float)
        cones = [clarabel.ZeroConeT(triangle)] + [clarabel.PSDTriangleConeT(m) for _ in range(n)]

        settings = clarabel.DefaultSettings()
        settings.verbose = False
        settings.max_iter = 200
        settings.tol_feas = 1e-12
        settings.tol_gap_abs = 1e-12
        settings.tol_gap_rel = 1e-12
        setup_ms = (time.perf_counter() - started) * 1000.0

        solve_started = time.perf_counter()
        solver = clarabel.DefaultSolver(matrix_p, q, matrix_a, vector_b, cones, settings)
        solution = solver.solve()
        solve_ms = (time.perf_counter() - solve_started) * 1000.0

        status = str(getattr(solution, "status", "unknown"))
        scale = float(program.objective_scale)
        primal_blocks = tuple(
            _smat_from_scaled(solution.x[block * triangle : (block + 1) * triangle], m, root_two)
            for block in range(n)
        )
        dual_block = _smat_from_scaled(solution.z[:triangle], m, root_two)
        observation = OperationalObservation(
            elapsed_milliseconds=round(setup_ms + solve_ms, 3),
            setup_milliseconds=round(setup_ms, 3),
            solve_milliseconds=round(solve_ms, 3),
            iterations=int(getattr(solution, "iterations", 0)) or None,
            primal_residual=_maybe_float(getattr(solution, "r_prim", None)),
            dual_residual=_maybe_float(getattr(solution, "r_dual", None)),
            duality_gap_residual=_gap(
                _maybe_float(getattr(solution, "obj_val", None)),
                _maybe_float(getattr(solution, "obj_val_dual", None)),
            ),
            primal_objective=_negate_scale(getattr(solution, "obj_val", None), scale),
            dual_objective=_negate_scale(getattr(solution, "obj_val_dual", None), scale),
            primal_blocks=primal_blocks,
            dual_block=dual_block,
            raw_engine_fields=tuple(
                sorted(
                    (name, str(getattr(solution, name, None)))
                    for name in ("status", "obj_val", "obj_val_dual", "r_prim", "r_dual", "iterations", "solve_time")
                )
            ),
            derivation_notes=(
                "q was set to -svec(objective blocks), so Clarabel minimises the negated "
                "objective; primal_objective = -obj_val * objective_scale.",
                "dual_block is smat(z[:triangle]) in the embedded space; "
                "tr(dual_block) * objective_scale is the dual objective value.",
            ),
        )
        return EngineRun(
            engine_id=self.descriptor.engine_id,
            probe=probe,
            solution=NumericSolution(
                engine_id=self.descriptor.engine_id,
                engine_status=status,
                engine_claims_optimal=status.endswith("Solved"),
                settings=CLARABEL_SETTINGS,
                solver_actually_used="clarabel",
                operational=observation,
            ),
        )


@dataclass(frozen=True, slots=True)
class CvxpyScsEngine:
    """SCS (MIT) driven through CVXPY (Apache-2.0).

    CVXPY's native Hermitian variables are deliberately NOT used: both engines
    must consume the identical real-embedded exact encoding, so that a
    disagreement is about the engines and not about two different models.
    """

    resolver: ModuleResolver = GatedImportlibResolver()

    descriptor = EngineDescriptor(
        engine_id="cvxpy-scs",
        modules=("cvxpy", "scs", "numpy"),
        license_expression="Apache-2.0 AND MIT",
        license_url="https://github.com/cvxgrp/scs",
        role="independent first-order engine behind a modelling layer",
        formulation="cvxpy_psd_variable_real_embedding_solver_scs",
    )

    def _gated_load(self) -> tuple[dict[str, Any | None], dict[str, str | None]]:
        """The gated boundary. Every module name here is a literal, by design.

        ``scs`` is probed even though CVXPY loads it internally, so an absent
        SCS is reported as an absent engine rather than surfacing later as an
        unexpected CVXPY solver selection.
        """

        loaded = {
            "cvxpy": self.resolver.load_gated_module("cvxpy"),
            "scs": self.resolver.load_gated_module("scs"),
            "numpy": self.resolver.load_gated_module("numpy"),
        }
        versions = {
            "cvxpy": self.resolver.gated_module_version("cvxpy"),
            "scs": self.resolver.gated_module_version("scs"),
            "numpy": self.resolver.gated_module_version("numpy"),
        }
        return (loaded, versions)

    def probe(self) -> EngineProbe:
        return _probe(self.descriptor, *self._gated_load())[0]

    def solve(self, program: ExactProgram) -> EngineRun:
        probe, modules = _probe(self.descriptor, *self._gated_load())
        if not probe.available:
            return _missing(self.descriptor, probe)
        cvxpy = modules["cvxpy"]
        numpy = modules["numpy"]

        installed = tuple(str(item) for item in cvxpy.installed_solvers())
        forbidden = sorted(set(installed) & FORBIDDEN_CVXPY_SOLVERS)
        if forbidden:
            return EngineRun(
                engine_id=self.descriptor.engine_id,
                probe=probe,
                missing_tool=MissingTool(
                    engine_id=self.descriptor.engine_id,
                    reason_code="forbidden_solver_present_in_environment",
                    detail=(
                        "refusing to run: this environment exposes solvers excluded by the "
                        f"ADR-0045 licence restriction ({', '.join(forbidden)}). "
                        "Rebuild the disposable environment from the pinned manifest with no extras."
                    ),
                    modules_absent=(),
                ),
            )

        started = time.perf_counter()
        m = program.block_dimension
        blocks = [
            numpy.array([[float(item) for item in row] for row in block], dtype=float)
            for block in program.objective_blocks
        ]
        variables = [cvxpy.Variable((m, m), PSD=True) for _ in blocks]
        total = variables[0]
        for variable in variables[1:]:
            total = total + variable
        constraints = [total == numpy.eye(m)]
        objective = cvxpy.Maximize(
            sum(cvxpy.trace(block @ variable) for block, variable in zip(blocks, variables))
        )
        problem = cvxpy.Problem(objective, constraints)
        setup_ms = (time.perf_counter() - started) * 1000.0

        solve_started = time.perf_counter()
        problem.solve(solver="SCS", eps_abs=1e-11, eps_rel=1e-11, max_iters=200000, verbose=False)
        solve_ms = (time.perf_counter() - solve_started) * 1000.0

        stats = problem.solver_stats
        used = str(getattr(stats, "solver_name", "unknown"))
        if used != "SCS":
            return EngineRun(
                engine_id=self.descriptor.engine_id,
                probe=probe,
                missing_tool=MissingTool(
                    engine_id=self.descriptor.engine_id,
                    reason_code="unexpected_solver_selected",
                    detail=(
                        f"CVXPY reported solver {used!r} rather than the authorised SCS; "
                        "the observation is discarded rather than attributed to SCS."
                    ),
                    modules_absent=(),
                ),
            )

        status = str(problem.status)
        scale = float(program.objective_scale)
        extra = getattr(stats, "extra_stats", None)
        info = extra.get("info", {}) if isinstance(extra, dict) else {}
        primal_blocks = tuple(
            tuple(tuple(float(value) for value in row) for row in numpy.asarray(variable.value))
            for variable in variables
            if variable.value is not None
        )
        dual_raw = constraints[0].dual_value
        dual_block = (
            tuple(tuple(float(value) for value in row) for row in numpy.asarray(dual_raw))
            if dual_raw is not None
            else ()
        )
        observation = OperationalObservation(
            elapsed_milliseconds=round(setup_ms + solve_ms, 3),
            setup_milliseconds=round(setup_ms, 3),
            solve_milliseconds=round(solve_ms, 3),
            iterations=_maybe_int(getattr(stats, "num_iters", None)),
            primal_residual=_maybe_float(info.get("res_pri")),
            dual_residual=_maybe_float(info.get("res_dual")),
            duality_gap_residual=_maybe_float(info.get("gap")),
            primal_objective=_scale_value(problem.value, scale),
            dual_objective=_negate_scale(info.get("dobj"), scale),
            primal_blocks=primal_blocks,
            dual_block=dual_block,
            raw_engine_fields=tuple(
                sorted(
                    [("problem.status", str(problem.status)), ("problem.value", str(problem.value))]
                    + [
                        (f"scs.info.{key}", str(info.get(key)))
                        for key in ("status", "status_val", "pobj", "dobj", "res_pri", "res_dual", "gap", "iter", "solve_time")
                        if isinstance(info, dict)
                    ]
                )
            ),
            derivation_notes=(
                "CVXPY canonicalises Maximize(f) to Minimize(-f), so SCS's pobj/dobj are "
                "in the negated internal units; dual_objective = -dobj * objective_scale.",
                "the CVXPY model objective is sum_i <J(W_i), X_i> in the embedded space, so "
                "primal_objective = problem.value * objective_scale.",
                "dual_block is the CVXPY dual value of the equality constraint, in the "
                "embedded space; tr(dual_block) * objective_scale is the dual objective.",
            ),
        )
        return EngineRun(
            engine_id=self.descriptor.engine_id,
            probe=probe,
            solution=NumericSolution(
                engine_id=self.descriptor.engine_id,
                engine_status=status,
                engine_claims_optimal=status == "optimal",
                settings=SCS_SETTINGS,
                solver_actually_used=used,
                operational=observation,
            ),
        )


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scale_value(value: Any, scale: float) -> float | None:
    numeric = _maybe_float(value)
    return None if numeric is None else numeric * scale


def _negate_scale(value: Any, scale: float) -> float | None:
    numeric = _maybe_float(value)
    return None if numeric is None else -numeric * scale


def _gap(primal: float | None, dual: float | None) -> float | None:
    if primal is None or dual is None:
        return None
    return abs(primal - dual)


def default_engines(resolver: ModuleResolver | None = None) -> tuple[Any, ...]:
    """The two authorised, independent engines, in a deterministic order."""

    active = resolver if resolver is not None else GatedImportlibResolver()
    return (ClarabelEngine(resolver=active), CvxpyScsEngine(resolver=active))


AUTHORIZED_ENGINE_IDS = frozenset({"clarabel", "cvxpy-scs"})
"""Only these engine ids may count towards the two-engine requirement."""


__all__ = [
    "AUTHORIZED_ENGINE_IDS",
    "AUTHORIZED_MODULES",
    "CLARABEL_SETTINGS",
    "EXCLUDED_MODULES",
    "FORBIDDEN_CVXPY_SOLVERS",
    "PERMITTED_LICENSE_EXPRESSIONS",
    "SCS_SETTINGS",
    "AbsentModuleResolver",
    "ClarabelEngine",
    "CvxpyScsEngine",
    "EngineUnavailableError",
    "GatedImportlibResolver",
    "LicenseNotPermittedError",
    "ModuleLicense",
    "authorize_module",
    "default_engines",
]
