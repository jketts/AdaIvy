"""Bounded, offline, byte-reproducible typesetting of a written bundle.

LaTeX is a Turing-complete language with file and process access, so the compile
is treated like every other untrusted execution in this repository: no shell,
``-no-shell-escape``, a frozen environment allowlist, a wall clock bound, and
captured output.

Two rules make the PDF evidence rather than decoration. Undefined references and
undefined citations are build failures, because a ``??`` in a PDF is a trust
break and not a cosmetic defect. And the whole compile runs twice from a clean
state: unless both runs produce byte-identical PDFs, the result is refused, since
a nondeterministic build cannot be re-derived by a reader.

No model may iterate on a compile error. A repaired-by-retry document is not a
projection of anything.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import SOURCE_DATE_EPOCH
from .bundle import verify_bundle
from .errors import PublicationValidationError
from .serialization import canonical_bytes, canonical_hash, sha256_bytes

_ARTIFACTS = ("paper.aux", "paper.log", "paper.out", "paper.pdf", "paper.toc")


@dataclass(frozen=True, slots=True)
class ToolchainStatus:
    available: bool
    engine: str
    engine_path: str | None
    reason: str


def load_toolchain(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "toolchain_id", "pin_kind", "pin_note", "engine", "distribution",
        "engine_version_expected", "packages_required", "passes", "flags", "wall_seconds",
        "output_bytes_limit", "environment_allowlist", "refusal_patterns",
    }
    if set(value) != required:
        raise PublicationValidationError(
            "toolchain_descriptor_malformed",
            f"missing={sorted(required - set(value))} unknown={sorted(set(value) - required)}",
        )
    if "-no-shell-escape" not in value["flags"]:
        raise PublicationValidationError(
            "toolchain_shell_escape_not_disabled", "-no-shell-escape is mandatory"
        )
    if not 1 <= int(value["passes"]) <= 4:
        raise PublicationValidationError("toolchain_passes_out_of_range", str(value["passes"]))
    return value


def toolchain_status(toolchain: Mapping[str, Any]) -> ToolchainStatus:
    engine = str(toolchain["engine"])
    located = shutil.which(engine)
    if located is None:
        return ToolchainStatus(
            available=False, engine=engine, engine_path=None,
            reason=f"{engine} is not on PATH, so no compile has run and none may be reported",
        )
    try:
        completed = subprocess.run(  # noqa: S603 - located fixed executable, fixed argument
            [located, "--version"], capture_output=True, timeout=10, check=False, text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return ToolchainStatus(
            available=False, engine=engine, engine_path=located,
            reason=f"could not inspect {engine} version: {error}",
        )
    observed = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    expected = str(toolchain["engine_version_expected"])
    if completed.returncode != 0 or observed != expected:
        return ToolchainStatus(
            available=False, engine=engine, engine_path=located,
            reason=f"{engine} version mismatch: expected {expected!r}, observed {observed!r}",
        )
    return ToolchainStatus(
        available=True, engine=engine, engine_path=located,
        reason=f"located exact engine version {observed}",
    )


def build_command(toolchain: Mapping[str, Any], engine_path: str, entrypoint: str) -> tuple[str, ...]:
    return (engine_path, *(str(flag) for flag in toolchain["flags"]), entrypoint)


def build_environment(toolchain: Mapping[str, Any], source_date_epoch: int) -> dict[str, str]:
    allowed = {str(name) for name in toolchain["environment_allowlist"]}
    environment = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "TMPDIR")
        if name in os.environ and name in allowed
    }
    if "SOURCE_DATE_EPOCH" in allowed:
        environment["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    if "FORCE_SOURCE_DATE" in allowed:
        environment["FORCE_SOURCE_DATE"] = "1"
    return environment


def _clean(bundle_dir: Path) -> None:
    for name in _ARTIFACTS:
        target = bundle_dir / name
        if target.exists():
            target.unlink()


def _compile(
    bundle_dir: Path, toolchain: Mapping[str, Any], engine_path: str, entrypoint: str
) -> tuple[bytes, str, tuple[Mapping[str, Any], ...]]:
    command = build_command(toolchain, engine_path, entrypoint)
    environment = build_environment(toolchain, SOURCE_DATE_EPOCH)
    executions: list[Mapping[str, Any]] = []
    for index in range(int(toolchain["passes"])):
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, allowlisted env
                command, cwd=str(bundle_dir), env=environment, capture_output=True,
                timeout=int(toolchain["wall_seconds"]), check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise PublicationValidationError(
                "typeset_timeout", f"pass {index} exceeded {toolchain['wall_seconds']}s"
            ) from error
        limit = int(toolchain["output_bytes_limit"])
        stdout = completed.stdout[:limit]
        executions.append({
            "pass": index,
            "exit_code": completed.returncode,
            "stdout_sha256": sha256_bytes(completed.stdout),
            "stdout_bytes": len(completed.stdout),
            "stderr_bytes": len(completed.stderr),
            "stdout_truncated": len(completed.stdout) > limit,
            "retained_stdout_tail": stdout[-2048:].decode("utf-8", "replace"),
        })
        if completed.returncode != 0:
            raise PublicationValidationError(
                "typeset_engine_failed",
                f"pass {index} exited {completed.returncode}; tail: "
                + stdout[-1024:].decode("utf-8", "replace"),
            )
    log_path = bundle_dir / (Path(entrypoint).stem + ".log")
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    pdf_path = bundle_dir / (Path(entrypoint).stem + ".pdf")
    if not pdf_path.exists():
        raise PublicationValidationError("typeset_produced_no_pdf", entrypoint)
    return pdf_path.read_bytes(), log, tuple(executions)


def _refuse_on_log(log: str, toolchain: Mapping[str, Any]) -> None:
    for pattern in toolchain["refusal_patterns"]:
        marker = str(pattern)
        for line in log.splitlines():
            if marker in line and "Warning" in line or marker == line.strip():
                raise PublicationValidationError(
                    "typeset_unresolved_reference",
                    f"the log matched {marker!r}: {line.strip()[:200]}",
                )
        if marker in log and marker.startswith("There were"):
            raise PublicationValidationError(
                "typeset_unresolved_reference", f"the log reports: {marker}"
            )


def typeset_bundle(
    bundle_dir: Path, toolchain: Mapping[str, Any], *, entrypoint: str = "paper.tex"
) -> dict[str, Any]:
    """Compile twice from clean and refuse anything not byte-reproducible."""

    manifest = verify_bundle(bundle_dir)
    status = toolchain_status(toolchain)
    if not status.available or status.engine_path is None:
        raise PublicationValidationError("typeset_toolchain_absent", status.reason)

    _clean(bundle_dir)
    first_pdf, first_log, first_executions = _compile(
        bundle_dir, toolchain, status.engine_path, entrypoint
    )
    _refuse_on_log(first_log, toolchain)
    _clean(bundle_dir)
    second_pdf, second_log, second_executions = _compile(
        bundle_dir, toolchain, status.engine_path, entrypoint
    )
    _refuse_on_log(second_log, toolchain)
    if sha256_bytes(first_pdf) != sha256_bytes(second_pdf):
        raise PublicationValidationError(
            "typeset_not_reproducible",
            "two clean compiles produced different bytes, so the PDF cannot be re-derived",
        )
    (bundle_dir / "paper.pdf").write_bytes(second_pdf)
    pdf_hash = sha256_bytes(second_pdf)

    build_path = bundle_dir / "build.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    build.update({
        "typeset_status": "typeset",
        "pdf_sha256": pdf_hash,
        "toolchain": dict(toolchain),
        "invocation": list(build_command(toolchain, status.engine, entrypoint)),
        "environment_names": sorted(build_environment(toolchain, SOURCE_DATE_EPOCH)),
        "executions": [list(first_executions), list(second_executions)],
        "reproducible": True,
    })
    build_path.write_bytes(canonical_bytes(build) + b"\n")

    files = [entry for entry in manifest["files"] if entry["path"] not in {"build.json"}]
    for name in ("build.json", "paper.pdf"):
        data = (bundle_dir / name).read_bytes()
        files.append({"path": name, "sha256": sha256_bytes(data), "bytes": len(data)})
    updated = dict(manifest)
    updated.pop("bundle_hash", None)
    updated["files"] = sorted(files, key=lambda entry: str(entry["path"]))
    updated["typeset_status"] = "typeset"
    updated["pdf_sha256"] = pdf_hash
    updated["bundle_hash"] = canonical_hash(updated)
    (bundle_dir / "MANIFEST.json").write_bytes(
        json.dumps(updated, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    return updated
