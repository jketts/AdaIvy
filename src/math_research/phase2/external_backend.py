"""Bounded filesystem/process interchange adapter for external backends."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

from ..domain.entities import OpaqueId, ResearchDossier
from ..interchange import export_dossier_bytes, export_dossier_dict
from . import PHASE2_SCHEMA_VERSION
from .ports import ArtifactStore, DurableWorkspace
from .model_gateway import redact_secrets
from .records import BackendResult, JobStatus, ProposalRecord, RunStatus
from .serialization import canonical_bytes, canonical_json, sha256_bytes
from .sqlite_workspace import LateCommitRejected


class ExternalPackageError(ValueError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatedExternalArtifact:
    schema_version: str = PHASE2_SCHEMA_VERSION
    path: str
    content: bytes
    content_hash: str
    kind: str
    target_claim_id: OpaqueId


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalExecution:
    schema_version: str = PHASE2_SCHEMA_VERSION
    status: str
    exit_status: int | None
    stdout_hash: str
    stderr_hash: str
    environment_hash: str
    package_hash: str | None
    artifacts: tuple[ValidatedExternalArtifact, ...]
    blocker: str | None


class FilesystemProcessBackend:
    def __init__(self, root: Path, artifacts: ArtifactStore) -> None:
        self.root = root.resolve()
        self.artifacts = artifacts
        self.root.mkdir(parents=True, exist_ok=True)

    def execute(
        self, *, backend_run_id: OpaqueId, dossier: ResearchDossier,
        manifest: dict[str, object], command: Sequence[str],
        timeout_milliseconds: int = 20_000,
        cancelled: Callable[[], bool] | None = None,
    ) -> ExternalExecution:
        run_dir = (self.root / backend_run_id.value).resolve()
        if run_dir.parent != self.root:
            raise ValueError("backend run directory escaped configured root")
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=False)
        dossier_bytes = export_dossier_bytes(dossier)
        manifest_bytes = canonical_bytes(manifest)
        (input_dir / "dossier.json").write_bytes(dossier_bytes)
        (input_dir / "manifest.json").write_bytes(manifest_bytes)
        environment_identity = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "command": redact_secrets(list(command)),
            "working_directory_role": "isolated_backend_run",
        }
        environment_ref = self.artifacts.put(canonical_bytes(environment_identity), media_type="application/vnd.adaivy.backend-environment+json")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "ADAIVY_BACKEND_RUN_DIR": str(run_dir),
        }
        process = subprocess.Popen(
            list(command), cwd=run_dir, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + timeout_milliseconds / 1000
        blocker: str | None = None
        while process.poll() is None:
            if cancelled and cancelled():
                blocker = "cancelled"
                process.terminate()
                break
            if time.monotonic() >= deadline:
                blocker = "timeout"
                process.terminate()
                break
            time.sleep(0.02)
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        secret_values = tuple(
            value for key, value in os.environ.items()
            if value and any(term in key.upper() for term in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        )
        stdout = str(redact_secrets(stdout.decode("utf-8", errors="replace"), secret_values)).encode("utf-8")
        stderr = str(redact_secrets(stderr.decode("utf-8", errors="replace"), secret_values)).encode("utf-8")
        stdout_ref = self.artifacts.put(stdout, media_type="text/plain")
        stderr_ref = self.artifacts.put(stderr, media_type="text/plain")
        if blocker:
            return ExternalExecution(
                status=blocker, exit_status=process.returncode,
                stdout_hash=stdout_ref.content_hash, stderr_hash=stderr_ref.content_hash,
                environment_hash=environment_ref.content_hash, package_hash=None,
                artifacts=(), blocker=blocker,
            )
        if process.returncode != 0:
            return ExternalExecution(
                status="failed", exit_status=process.returncode,
                stdout_hash=stdout_ref.content_hash, stderr_hash=stderr_ref.content_hash,
                environment_hash=environment_ref.content_hash, package_hash=None,
                artifacts=(), blocker=f"exit_status:{process.returncode}",
            )
        package_path = output_dir / "package.json"
        try:
            if package_path.is_symlink() or not package_path.is_file():
                raise ExternalPackageError("package must be a regular in-directory file")
            try:
                package_path.resolve().relative_to(output_dir.resolve())
            except ValueError as error:
                raise ExternalPackageError("package path traversal rejected") from error
            package_bytes = package_path.read_bytes()
            package = json.loads(package_bytes)
            validated = self._validate_package(
                package=package, output_dir=output_dir,
                expected_dossier_hash=export_dossier_dict(dossier)["content_hash"],
                expected_manifest_hash=sha256_bytes(manifest_bytes),
                valid_claim_ids={item.id.value for item in dossier.claims},
            )
        except (OSError, json.JSONDecodeError, ExternalPackageError) as error:
            return ExternalExecution(
                status="rejected", exit_status=process.returncode,
                stdout_hash=stdout_ref.content_hash, stderr_hash=stderr_ref.content_hash,
                environment_hash=environment_ref.content_hash,
                package_hash=sha256_bytes(package_bytes) if "package_bytes" in locals() else None,
                artifacts=(), blocker=str(error),
            )
        return ExternalExecution(
            status="succeeded", exit_status=process.returncode,
            stdout_hash=stdout_ref.content_hash, stderr_hash=stderr_ref.content_hash,
            environment_hash=environment_ref.content_hash,
            package_hash=sha256_bytes(package_bytes), artifacts=validated, blocker=None,
        )

    @staticmethod
    def _validate_package(
        *, package: object, output_dir: Path, expected_dossier_hash: str,
        expected_manifest_hash: str, valid_claim_ids: set[str],
    ) -> tuple[ValidatedExternalArtifact, ...]:
        if not isinstance(package, dict):
            raise ExternalPackageError("package must be an object")
        expected_fields = {"schema_version", "input_dossier_hash", "input_manifest_hash", "artifacts"}
        if set(package) != expected_fields or package.get("schema_version") != PHASE2_SCHEMA_VERSION:
            raise ExternalPackageError("package schema mismatch")
        if package["input_dossier_hash"] != expected_dossier_hash or package["input_manifest_hash"] != expected_manifest_hash:
            raise ExternalPackageError("package input hashes mismatch")
        if not isinstance(package["artifacts"], list):
            raise ExternalPackageError("package artifacts must be an array")
        expected_files = {"package.json"}
        validated: list[ValidatedExternalArtifact] = []
        seen_paths: set[str] = set()
        for value in package["artifacts"]:
            if not isinstance(value, dict) or set(value) != {"path", "sha256", "kind", "target_claim_id"}:
                raise ExternalPackageError("artifact entry schema mismatch")
            relative = value["path"]
            if not isinstance(relative, str) or "\\" in relative:
                raise ExternalPackageError("artifact path is invalid")
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts or pure.parts[0] != "artifacts":
                raise ExternalPackageError("artifact path traversal rejected")
            if relative in seen_paths:
                raise ExternalPackageError("duplicate artifact path")
            seen_paths.add(relative)
            expected_files.add(relative)
            path = output_dir.joinpath(*pure.parts)
            cursor = output_dir
            traverses_symlink = False
            for part in pure.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    traverses_symlink = True
                    break
            if traverses_symlink or not path.is_file():
                raise ExternalPackageError("artifact must be a regular in-directory file")
            try:
                path.resolve().relative_to(output_dir.resolve())
            except ValueError as error:
                raise ExternalPackageError("artifact resolved outside declared directory") from error
            content = path.read_bytes()
            observed = sha256_bytes(content)
            if value["sha256"] != observed:
                raise ExternalPackageError("artifact hash mismatch")
            if value["kind"] not in {"candidate_claim", "proof_attempt", "counterexample", "explicit_failure"}:
                raise ExternalPackageError("unsupported artifact kind")
            if value["target_claim_id"] not in valid_claim_ids:
                raise ExternalPackageError("artifact targets unknown claim")
            validated.append(
                ValidatedExternalArtifact(
                    path=relative, content=content, content_hash=observed,
                    kind=value["kind"], target_claim_id=OpaqueId(value["target_claim_id"]),
                )
            )
        observed_files = {
            path.relative_to(output_dir).as_posix()
            for path in output_dir.rglob("*") if path.is_file() or path.is_symlink()
        }
        if observed_files != expected_files:
            raise ExternalPackageError("unexpected or missing output files")
        return tuple(validated)


class ExternalBackendService:
    """Workflow-owned import of a validated external package as proposals."""

    def __init__(self, *, workspace: DurableWorkspace, artifacts: ArtifactStore, backend: FilesystemProcessBackend, now: Callable[[], str]) -> None:
        self.workspace = workspace
        self.artifacts = artifacts
        self.backend = backend
        self.now = now

    def run(
        self, *, run_id: OpaqueId, backend_run_id: OpaqueId,
        command: Sequence[str], timeout_milliseconds: int = 20_000,
        cancelled: Callable[[], bool] | None = None,
    ) -> BackendResult:
        run = self.workspace.get_run(run_id)
        dossier = self.workspace.load_dossier(run.dossier_id)
        now = self.now()
        job_id = OpaqueId(f"job.{run_id.value}.backend.{backend_run_id.value}")
        self.workspace.enqueue_job(
            job_id=job_id, run_id=run_id, kind="external_backend",
            idempotency_key=f"job:{run_id.value}:backend:{backend_run_id.value}",
            payload_hash=run.dossier_hash, max_attempts=1,
            deadline_at=_future(now, timeout_milliseconds + 5_000), now=now,
        )
        job = self.workspace.claim_job(
            run_id=run_id, kind="external_backend", worker_id="phase2.external-backend",
            lease_until=_future(now, timeout_milliseconds + 5_000), now=now,
        )
        if job is None:
            raise LateCommitRejected("external backend job is not runnable")
        input_manifest = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "run_id": run_id.value,
            "backend_run_id": backend_run_id.value,
            "disposition": "proposal",
            "allowed_output_kinds": ["candidate_claim", "proof_attempt", "counterexample", "explicit_failure"],
        }
        execution = self.backend.execute(
            backend_run_id=backend_run_id, dossier=dossier, manifest=input_manifest,
            command=command, timeout_milliseconds=timeout_milliseconds,
            cancelled=cancelled,
        )
        proposals: list[OpaqueId] = []
        if execution.status == "succeeded":
            for index, artifact in enumerate(execution.artifacts):
                reference = self.artifacts.put(artifact.content, media_type="application/vnd.adaivy.external-proposal+json")
                proposal = ProposalRecord(
                    proposal_id=OpaqueId(f"proposal.{run_id.value}.backend.{backend_run_id.value}.{index}"),
                    run_id=run_id, proposal_kind=artifact.kind,
                    artifact_hash=reference.content_hash, source_kind="external_backend",
                    source_id=backend_run_id.value, target_claim_id=artifact.target_claim_id,
                )
                committed = self.workspace.commit_proposal(
                    proposal, job_id=job.job_id, worker_id="phase2.external-backend",
                    now=self.now(), event_key=f"proposal:{run_id.value}:backend:{backend_run_id.value}:{index}",
                )
                proposals.append(committed.proposal_id)
            self.workspace.finish_job(
                job.job_id, worker_id="phase2.external-backend", status=JobStatus.SUCCEEDED.value,
                result_hash=execution.package_hash, now=self.now(),
                idempotency_key=f"job:{run_id.value}:backend:{backend_run_id.value}:succeeded",
            )
        else:
            status = JobStatus.TIMED_OUT if execution.status == "timeout" else JobStatus.FAILED
            try:
                self.workspace.finish_job(
                    job.job_id, worker_id="phase2.external-backend", status=status.value,
                    result_hash=execution.package_hash, now=self.now(),
                    idempotency_key=f"job:{run_id.value}:backend:{backend_run_id.value}:{status.value}",
                )
            except LateCommitRejected:
                pass
        result = BackendResult(
            backend_run_id=backend_run_id, status=execution.status,
            exit_status=execution.exit_status, stdout_hash=execution.stdout_hash,
            stderr_hash=execution.stderr_hash, environment_hash=execution.environment_hash,
            package_hash=execution.package_hash, proposal_ids=tuple(proposals), blocker=execution.blocker,
        )
        self.workspace.append_event(
            event_id=OpaqueId(f"event.{backend_run_id.value}.execution"),
            aggregate_id=run_id, event_type="backend_execution_recorded",
            payload_json=canonical_json({
                "backend_run_id": backend_run_id.value,
                "status": execution.status,
                "exit_status": execution.exit_status,
                "stdout_hash": execution.stdout_hash,
                "stderr_hash": execution.stderr_hash,
                "environment_hash": execution.environment_hash,
                "package_hash": execution.package_hash,
                "output_hashes": [item.content_hash for item in execution.artifacts],
                "proposal_ids": [item.value for item in proposals],
                "blocker": execution.blocker,
            }),
            now=self.now(), idempotency_key=f"backend:{run_id.value}:{backend_run_id.value}:recorded",
        )
        return result


def _future(now: str, milliseconds: int) -> str:
    from datetime import datetime, timedelta
    value = datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(milliseconds=milliseconds)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
