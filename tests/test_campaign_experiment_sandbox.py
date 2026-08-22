"""ADR-0066 enforcement probes for the campaign experiment sandbox.

Every test in this file except the last class runs offline: no container
runtime, no image, no network, no subprocess, no socket.  Each named control
carries a single-field falsifiability probe -- a named mutation of its own
fixture that must produce the forbidden verdict -- and the probe tables assert
``flipped == total`` because a control that cannot be made to fail proves
nothing.

The honest separation this file maintains:

* An OFFLINE probe proves request admission, envelope closure, image-lock
  closure, command construction, refusal semantics, and content-addressed I/O.
* A KERNEL claim (no-network namespace, read-only root, noexec tmpfs, cgroup
  memory/cpu/pids, RLIMIT nofile/fsize) is NOT proven here.  It is asserted
  only by :class:`ContainerGateTests`, which SKIPS unless the repository owner
  has pinned the image digest and configured a reviewed runtime.  The offline
  tests instead assert the complement: on every offline path each kernel
  enforcement flag is ``False``.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import ast
import sys
import unittest
from pathlib import Path

from math_research.campaign.experiment_sandbox import (
    ACTIVATION_ACKNOWLEDGEMENT,
    ADAPTER_ID,
    ALLOWED_IMPORT_MODULES,
    BOOTSTRAP_SHA256,
    CONTAINER_CONTROLS,
    CONTAINER_ENVIRONMENT,
    ENVELOPE_SCHEMA,
    EVIDENCE_SCHEMA,
    EXPERIMENT_PROFILE,
    IMAGE_LOCK_SCHEMA,
    KERNEL_ENFORCEMENT_FIELDS,
    PHASE4B_PARSER_IMAGE_DIGEST,
    RESPONSE_FIELDS,
    RESPONSE_SCHEMA,
    RUNTIME_SCHEMA,
    SANDBOX_CONTRACT_VERSION,
    CampaignExperimentSandbox,
    ExperimentImageLock,
    ExperimentRefusal,
    ExperimentRuntimeIdentity,
    ExperimentSandboxActivation,
    ExperimentSandboxProfile,
    ExperimentSandboxRefusal,
    _BOOTSTRAP,
    build_default_experiment_sandbox,
    build_run_command,
    build_stdin_envelope,
    load_experiment_image_lock,
    parse_experiment_image_lock,
    parse_stdin_envelope,
    validate_experiment_request,
)
from math_research.experiment_oci_launcher import (
    LAUNCHER_ID,
    OciExperimentLauncher,
)
from math_research.campaign.records import RecordStatus, UsageSource, canonical_hash
from math_research.campaign.runner import (
    CampaignRunnerPolicy,
    ExperimentRequest,
    PlannerResponse,
    ResourceLimits,
    SequentialCampaignRunner,
)


ROOT = Path(__file__).resolve().parents[1]
IMAGE_LOCK_PATH = ROOT / "config/campaign-experiment-oci-image-linux-arm64-v1.json"
PHASE4B_LOCK_PATH = ROOT / "config/phase4b-oci-image-linux-arm64-v1.json"
MODULE_PATH = ROOT / "src/math_research/campaign/experiment_sandbox.py"


# ---------------------------------------------------------------------------
# Process/socket audit observer
# ---------------------------------------------------------------------------

#: CPython's own audit-event names. `socket.socket` is NOT an audit event, so
#: listing it observes nothing; the real socket-construction event is
#: `socket.__new__`.
_WATCHED_EVENTS = frozenset({
    "subprocess.Popen", "socket.__new__", "socket.connect", "socket.bind",
    "socket.sendto", "socket.getaddrinfo", "socket.gethostbyname",
    "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
    "os.system", "pty.spawn",
})
_OBSERVED: list[str] = []
_ACTIVE = False


def _audit(event: str, _args: object) -> None:
    if _ACTIVE and event in _WATCHED_EVENTS:
        _OBSERVED.append(event)


sys.addaudithook(_audit)


@contextlib.contextmanager
def no_process_or_socket():
    """Fail if the enclosed code creates a process or a socket.

    This is a CPython audit hook, so it observes the real interpreter events
    rather than a patched module attribute.
    """

    global _ACTIVE
    _OBSERVED.clear()
    _ACTIVE = True
    try:
        yield _OBSERVED
    finally:
        _ACTIVE = False


# ---------------------------------------------------------------------------
# Fixtures. Every bound comes from ADR-0066 and the module profile; nothing
# below was chosen after observing a result.
# ---------------------------------------------------------------------------

PROGRAM = (
    "import json\n"
    "import sys\n"
    "from fractions import Fraction\n"
    "payload = json.loads(sys.stdin.read())\n"
    "bound = int(payload['arguments'][0].split('=')[1])\n"
    "total = sum(Fraction(1, k) for k in range(1, bound + 1))\n"
    "print(json.dumps(\n"
    "    {'bound': bound, 'harmonic': [total.numerator, total.denominator]},\n"
    "    sort_keys=True, separators=(',', ':'),\n"
    "))\n"
).encode("utf-8")
INPUT_BYTES = b'{"seed":3}'


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def limits(**updates: int) -> ResourceLimits:
    value = {
        "cpu_milliseconds": 60_000,
        "wall_milliseconds": 60_000,
        "memory_bytes": 268_435_456,
        "output_bytes": 65_536,
        "process_count": 1,
    }
    value.update(updates)
    return ResourceLimits(**value)


def request(**updates: object) -> ExperimentRequest:
    value: dict[str, object] = {
        "campaign_id": "campaign.erdos-probe",
        "action_id": "action.4",
        "tool_id": "exact_python_search",
        "program_artifact_hash": digest(PROGRAM),
        "program_source": PROGRAM,
        "input_artifacts": ((digest(INPUT_BYTES), INPUT_BYTES),),
        "arguments": ("bound=8",),
        "resource_limits": limits(),
        "network": "none",
    }
    value.update(updates)
    return ExperimentRequest(**value)  # type: ignore[arg-type]


def program(body: str) -> dict[str, object]:
    raw = body.encode("utf-8")
    return {"program_source": raw, "program_artifact_hash": digest(raw)}


def raw_program(raw: bytes) -> dict[str, object]:
    return {"program_source": raw, "program_artifact_hash": digest(raw)}


def runtime(reference: str | None = None) -> ExperimentRuntimeIdentity:
    """A synthetic runtime identity record.

    Constructing this record measures nothing and authorizes nothing: it exists
    so the offline suite can inspect the command vector without a container.
    """

    reference = reference or ("docker.io/library/python@sha256:" + "a" * 64)
    preimage = {
        "daemon_host": "unix:///tmp/reviewed-docker.sock",
        "docker_executable": "/opt/reviewed/docker",
        "docker_executable_sha256": "sha256:" + "b" * 64,
        "docker_server_sha256": "sha256:" + "c" * 64,
        "image_architecture": "arm64",
        "image_descriptor_digest": "sha256:" + reference.rsplit(":", 1)[1],
        "image_id": "sha256:" + "d" * 64,
        "image_layers": ["sha256:" + "e" * 64],
        "image_os": "linux",
        "image_reference": reference,
        "platform": "linux/arm64",
        "schema_version": RUNTIME_SCHEMA,
    }
    return ExperimentRuntimeIdentity(
        schema_version=RUNTIME_SCHEMA,
        docker_executable=preimage["docker_executable"],
        docker_executable_sha256=preimage["docker_executable_sha256"],
        daemon_host=preimage["daemon_host"], platform="linux/arm64",
        image_reference=reference,
        image_descriptor_digest=preimage["image_descriptor_digest"],
        image_id=preimage["image_id"], image_os="linux",
        image_architecture="arm64",
        image_layers=("sha256:" + "e" * 64,),
        docker_server_sha256=preimage["docker_server_sha256"],
        environment_sha256=canonical_hash(preimage),
    )


def shipped_lock_document() -> dict[str, object]:
    return json.loads(IMAGE_LOCK_PATH.read_text("utf-8"))


def pinned_lock_document(digest_value: str | None = None) -> dict[str, object]:
    """The shipped pin with a HYPOTHETICAL digest, used only by probes.

    No such image has been pulled, built, or run.  This document exists so the
    mismatch, reuse, and activation refusals can be exercised offline.
    """

    value = shipped_lock_document()
    digest_value = digest_value or ("sha256:" + "a" * 64)
    value["digest_status"] = "pinned"
    value["image_digest"] = digest_value
    value["image_reference"] = f"{value['image_repository']}@{digest_value}"
    value["authorization_status"] = "authorized_for_bounded_generated_code_execution"
    return value


def pinned_lock() -> ExperimentImageLock:
    return parse_experiment_image_lock(
        json.dumps(pinned_lock_document()).encode("utf-8")
    )


def activation(lock: ExperimentImageLock) -> ExperimentSandboxActivation:
    sandbox = CampaignExperimentSandbox(lock=lock)
    return ExperimentSandboxActivation(
        status="authorized", authorized_by="human.repository-owner",
        acknowledgement=ACTIVATION_ACKNOWLEDGEMENT,
        image_lock_hash=sandbox.image_lock_sha256,
        policy_hash=sandbox.policy_sha256,
        probe_report_hash="sha256:" + "f" * 64,
    )


class RecordingLauncher:
    """A launcher that records calls and never creates a process.

    It stands in for the production `OciExperimentLauncher` so the offline suite
    can prove the ORDER of the gates without a container engine.
    """

    launcher_id = "test_recording_launcher"
    docker_executable = "/opt/reviewed/docker"
    daemon_host = "unix:///tmp/reviewed-docker.sock"

    def __init__(self) -> None:
        self.controls: list[tuple[str, ...]] = []
        self.executions: list[tuple[str, ...]] = []

    def control(self, command: tuple[str, ...]) -> bytes:
        self.controls.append(command)
        raise ExperimentSandboxRefusal(
            ExperimentRefusal.RUNTIME_UNAVAILABLE, detail="test_launcher",
        )

    def execute(self, command: tuple[str, ...], **_kwargs: object) -> object:
        self.executions.append(command)
        raise AssertionError("the offline suite must never launch a container")


# ---------------------------------------------------------------------------
# Probe tables. Each entry is (probe name, single-field mutation, reason, field).
# ---------------------------------------------------------------------------

REQUEST_PROBES: tuple[tuple[str, dict[str, object], ExperimentRefusal, str | None], ...] = (
    ("campaign_identifier_grammar", {"campaign_id": "campaign one"},
     ExperimentRefusal.IDENTIFIER_FORBIDDEN, "campaign_id"),
    ("action_identifier_grammar", {"action_id": "action/4"},
     ExperimentRefusal.IDENTIFIER_FORBIDDEN, "action_id"),
    ("shell_adapter_bash", {"tool_id": "bash_search"},
     ExperimentRefusal.SHELL_ADAPTER_FORBIDDEN, "bash_search"),
    ("shell_adapter_subprocess", {"tool_id": "subprocess_runner"},
     ExperimentRefusal.SHELL_ADAPTER_FORBIDDEN, "subprocess_runner"),
    ("unknown_adapter", {"tool_id": "unlisted_search"},
     ExperimentRefusal.UNKNOWN_TOOL_ADAPTER, "unlisted_search"),
    ("adapter_grammar", {"tool_id": "Exact_Python"},
     ExperimentRefusal.UNKNOWN_TOOL_ADAPTER, "tool_id"),
    ("network_bridge", {"network": "bridge"},
     ExperimentRefusal.NETWORK_FORBIDDEN, "network"),
    ("network_host", {"network": "host"},
     ExperimentRefusal.NETWORK_FORBIDDEN, "network"),
    ("network_target_url", {"arguments": ("target=https://example.org",)},
     ExperimentRefusal.HOST_PATH_FORBIDDEN, "target=https://example.org"),
    ("host_path_argument", {"arguments": ("path=/etc/passwd",)},
     ExperimentRefusal.HOST_PATH_FORBIDDEN, "path=/etc/passwd"),
    ("path_traversal_argument", {"arguments": ("data=..",)},
     ExperimentRefusal.HOST_PATH_FORBIDDEN, "data=.."),
    ("command_flag_argument", {"arguments": ("--memory=99",)},
     ExperimentRefusal.ARGUMENT_FORBIDDEN, "--memory=99"),
    ("shell_metacharacter_argument", {"arguments": ("bound=$(id)",)},
     ExperimentRefusal.ARGUMENT_FORBIDDEN, "bound=$(id)"),
    ("argument_count_bound",
     {"arguments": tuple(f"k{index}=1" for index in range(17))},
     ExperimentRefusal.ARGUMENT_COUNT_EXCEEDS_BOUND, "arguments"),
    ("program_content_address",
     {"program_source": PROGRAM + b"# tampered\n"},
     ExperimentRefusal.PROGRAM_HASH_MISMATCH, "program_source"),
    ("program_hash_grammar", {"program_artifact_hash": "sha1:deadbeef"},
     ExperimentRefusal.PROGRAM_HASH_MISMATCH, "program_artifact_hash"),
    ("program_byte_bound", raw_program(b"x = 1\n" * 60_000),
     ExperimentRefusal.PROGRAM_BYTES_EXCEED_BOUND, "program_source"),
    ("program_network_import", program("import socket\n"),
     ExperimentRefusal.PROGRAM_NETWORK_IMPORT_FORBIDDEN, "socket"),
    ("program_network_submodule_import", program("import urllib.request\n"),
     ExperimentRefusal.PROGRAM_NETWORK_IMPORT_FORBIDDEN, "urllib.request"),
    ("program_process_import", program("import subprocess\n"),
     ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, "subprocess"),
    ("program_os_import", program("import os\n"),
     ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, "os"),
    ("program_filesystem_import", program("from pathlib import Path\n"),
     ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, "pathlib"),
    ("program_relative_import", program("from . import helper\n"),
     ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, "relative_import"),
    ("program_star_import", program("from json import *\n"),
     ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, "star_import"),
    ("program_dynamic_eval", program("value = eval('1 + 1')\n"),
     ExperimentRefusal.PROGRAM_DYNAMIC_EXECUTION_FORBIDDEN, "eval"),
    ("program_dynamic_import", program("mod = __import__('os')\n"),
     ExperimentRefusal.PROGRAM_DYNAMIC_EXECUTION_FORBIDDEN, "__import__"),
    ("program_filesystem_open", program("handle = open('/etc/passwd')\n"),
     ExperimentRefusal.PROGRAM_FILESYSTEM_ACCESS_FORBIDDEN, "open"),
    ("program_reflection_class", program("kinds = ().__class__\n"),
     ExperimentRefusal.PROGRAM_REFLECTION_FORBIDDEN, "__class__"),
    ("program_reflection_bases", program("kinds = tuple.__bases__\n"),
     ExperimentRefusal.PROGRAM_REFLECTION_FORBIDDEN, "__bases__"),
    ("program_reflection_globals",
     program("def f():\n    pass\nscope = f.__globals__\n"),
     ExperimentRefusal.PROGRAM_REFLECTION_FORBIDDEN, "__globals__"),
    ("program_syntax", program("def broken(:\n"),
     ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, None),
    ("program_encoding", raw_program(b"\xff\xfe not utf-8"),
     ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, None),
    ("input_count_bound",
     {"input_artifacts": tuple(
         (digest(str(index).encode()), str(index).encode()) for index in range(9)
     )},
     ExperimentRefusal.INPUT_COUNT_EXCEEDS_BOUND, "input_artifacts"),
    ("input_content_address",
     {"input_artifacts": ((digest(INPUT_BYTES), b'{"seed":4}'),)},
     ExperimentRefusal.INPUT_HASH_MISMATCH, digest(INPUT_BYTES)),
    ("input_duplicate_hash",
     {"input_artifacts": (
         (digest(INPUT_BYTES), INPUT_BYTES), (digest(INPUT_BYTES), INPUT_BYTES),
     )},
     ExperimentRefusal.INPUT_DUPLICATE_HASH, digest(INPUT_BYTES)),
    ("input_byte_bound",
     {"input_artifacts": ((digest(b"z" * 1_048_577), b"z" * 1_048_577),)},
     ExperimentRefusal.INPUT_BYTES_EXCEED_BOUND, digest(b"z" * 1_048_577)),
    ("cpu_ceiling", {"resource_limits": limits(cpu_milliseconds=120_001)},
     ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, "cpu_milliseconds"),
    ("wall_ceiling", {"resource_limits": limits(wall_milliseconds=120_001)},
     ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, "wall_milliseconds"),
    ("memory_ceiling", {"resource_limits": limits(memory_bytes=1_073_741_825)},
     ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, "memory_bytes"),
    ("output_ceiling", {"resource_limits": limits(output_bytes=1_048_577)},
     ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, "output_bytes"),
    ("process_ceiling", {"resource_limits": limits(process_count=5)},
     ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, "process_count"),
    ("cpu_floor", {"resource_limits": limits(cpu_milliseconds=100)},
     ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, "cpu_milliseconds"),
    ("wall_floor", {"resource_limits": limits(wall_milliseconds=100)},
     ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, "wall_milliseconds"),
    ("memory_floor", {"resource_limits": limits(memory_bytes=4_096)},
     ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, "memory_bytes"),
    ("output_floor", {"resource_limits": limits(output_bytes=10)},
     ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, "output_bytes"),
    ("process_floor", {"resource_limits": limits(process_count=0)},
     ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, "process_count"),
    ("resource_limit_type", {"resource_limits": None},
     ExperimentRefusal.RESOURCE_LIMIT_MALFORMED, "resource_limits"),
    ("resource_limit_boolean",
     {"resource_limits": limits(cpu_milliseconds=True)},
     ExperimentRefusal.RESOURCE_LIMIT_MALFORMED, "cpu_milliseconds"),
)


def envelope_document() -> dict[str, object]:
    admitted = validate_experiment_request(request())
    return json.loads(build_stdin_envelope(admitted).decode("utf-8"))


ENVELOPE_PROBES: tuple[tuple[str, dict[str, object], ExperimentRefusal, str | None], ...] = (
    ("environment_field_environment", {"environment": {"SECRET": "x"}},
     ExperimentRefusal.ENVIRONMENT_FIELD_FORBIDDEN, "environment"),
    ("environment_field_env", {"env": {"AWS_SECRET_ACCESS_KEY": "x"}},
     ExperimentRefusal.ENVIRONMENT_FIELD_FORBIDDEN, "env"),
    ("environment_field_environ", {"environ": {}},
     ExperimentRefusal.ENVIRONMENT_FIELD_FORBIDDEN, "environ"),
    ("unknown_field", {"mounts": ["/etc"]},
     ExperimentRefusal.ENVELOPE_UNKNOWN_FIELD, "mounts"),
    ("schema_version", {"schema_version": "adaivy.something-else.v9"},
     ExperimentRefusal.ENVELOPE_SCHEMA_VERSION_UNKNOWN, "schema_version"),
    ("program_content_address", {"program_sha256": "0" * 64},
     ExperimentRefusal.PROGRAM_HASH_MISMATCH, "program_sha256"),
    ("host_path_argument", {"arguments": ["path=/etc/passwd"]},
     ExperimentRefusal.HOST_PATH_FORBIDDEN, "arguments"),
    ("argument_grammar", {"arguments": ["bound=$(id)"]},
     ExperimentRefusal.ARGUMENT_FORBIDDEN, "arguments"),
)


class ProfileTests(unittest.TestCase):
    def test_declared_profile_matches_the_shipped_pin_declaration(self) -> None:
        document = shipped_lock_document()
        self.assertEqual(EXPERIMENT_PROFILE.to_record(), document["resource_profile"])
        self.assertEqual(sorted(ALLOWED_IMPORT_MODULES), document["allowed_import_modules"])

    def test_profile_cannot_be_loosened_past_the_adr_ceiling(self) -> None:
        for name, value in (
            ("max_cpu_milliseconds", 120_001),
            ("max_wall_milliseconds", 120_001),
            ("max_memory_bytes", 1_073_741_825),
            ("max_output_bytes", 1_048_577),
            ("max_process_count", 5),
            ("max_open_files", 65),
            ("max_program_bytes", 262_145),
            ("max_stdin_envelope_bytes", 4_194_305),
            ("max_input_artifacts", 9),
            ("max_arguments", 17),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ExperimentSandboxRefusal) as caught:
                    ExperimentSandboxProfile(**{name: value})
                self.assertEqual(
                    ExperimentRefusal.PROFILE_OUTSIDE_ADR_ENVELOPE, caught.exception.reason,
                )
                self.assertEqual(name, caught.exception.field)

    def test_profile_cannot_be_tightened_below_the_container_floor(self) -> None:
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            ExperimentSandboxProfile(max_memory_bytes=4_096)
        self.assertEqual(
            ExperimentRefusal.PROFILE_OUTSIDE_ADR_ENVELOPE, caught.exception.reason,
        )
        self.assertEqual("max_memory_bytes", caught.exception.field)


class RequestAdmissionProbeTests(unittest.TestCase):
    """ADR-0057 acceptance gate 2, proven offline with one probe per control."""

    def test_baseline_fixture_is_admitted(self) -> None:
        with no_process_or_socket() as observed:
            admitted = validate_experiment_request(request())
        self.assertEqual([], observed)
        self.assertEqual("exact_python_search", admitted.tool_id)
        self.assertEqual(digest(PROGRAM), admitted.program_artifact_hash)
        self.assertEqual(limits(), admitted.declared_limits)
        # A declaration may only tighten; it never reaches the profile ceiling.
        self.assertEqual(limits(), admitted.effective_limits)
        self.assertLessEqual(
            admitted.effective_limits.memory_bytes, EXPERIMENT_PROFILE.max_memory_bytes,
        )

    def test_every_named_probe_flips_its_own_control(self) -> None:
        flipped = 0
        names = set()
        for name, mutation, reason, field in REQUEST_PROBES:
            with self.subTest(probe=name):
                self.assertNotIn(name, names, "probe names must be unique")
                names.add(name)
                with no_process_or_socket() as observed:
                    with self.assertRaises(ExperimentSandboxRefusal) as caught:
                        validate_experiment_request(request(**mutation))
                self.assertEqual([], observed, "admission must open no process")
                self.assertEqual(reason, caught.exception.reason)
                if field is not None:
                    self.assertEqual(field, caught.exception.field)
                flipped += 1
        self.assertEqual(len(REQUEST_PROBES), flipped)
        self.assertGreaterEqual(flipped, 45)

    def test_refusal_reasons_are_a_closed_deterministic_vocabulary(self) -> None:
        for _name, mutation, reason, _field in REQUEST_PROBES:
            with self.assertRaises(ExperimentSandboxRefusal) as caught:
                validate_experiment_request(request(**mutation))
            record = caught.exception.record()
            self.assertEqual(SANDBOX_CONTRACT_VERSION, record["schema_version"])
            self.assertEqual("refused_before_execution", record["verdict"])
            self.assertFalse(record["epistemic_warrant_created"])
            self.assertEqual("untrusted_observation", record["trust_effect"])
            self.assertEqual(reason.value, record["reason"])
            self.assertEqual(record, caught.exception.record())

    def test_the_admitted_language_surface_is_narrow_and_declared(self) -> None:
        self.assertEqual(18, len(ALLOWED_IMPORT_MODULES))
        for forbidden in (
            "os", "subprocess", "shutil", "pathlib", "socket", "ssl", "ctypes",
            "importlib", "multiprocessing", "threading", "pickle", "tempfile",
            "urllib", "http", "random", "secrets", "sqlite3",
        ):
            self.assertNotIn(forbidden, ALLOWED_IMPORT_MODULES)


class EnvelopeProbeTests(unittest.TestCase):
    def test_baseline_envelope_round_trips_and_is_byte_deterministic(self) -> None:
        admitted = validate_experiment_request(request())
        with no_process_or_socket() as observed:
            first = build_stdin_envelope(admitted)
            second = build_stdin_envelope(validate_experiment_request(request()))
            parsed = parse_stdin_envelope(first)
        self.assertEqual([], observed)
        self.assertEqual(first, second)
        self.assertEqual(ENVELOPE_SCHEMA, parsed["schema_version"])
        self.assertLessEqual(len(first), EXPERIMENT_PROFILE.max_stdin_envelope_bytes)

    def test_every_named_envelope_probe_flips_its_own_control(self) -> None:
        flipped = 0
        for name, mutation, reason, field in ENVELOPE_PROBES:
            with self.subTest(probe=name):
                document = envelope_document()
                document.update(mutation)
                raw = json.dumps(document, sort_keys=True).encode("utf-8")
                with self.assertRaises(ExperimentSandboxRefusal) as caught:
                    parse_stdin_envelope(raw)
                self.assertEqual(reason, caught.exception.reason)
                if field is not None:
                    self.assertEqual(field, caught.exception.field)
                flipped += 1
        self.assertEqual(len(ENVELOPE_PROBES), flipped)

    def test_duplicate_key_malformed_json_and_missing_field_all_refuse(self) -> None:
        document = envelope_document()
        body = json.dumps(document, sort_keys=True)
        duplicated = "{" + '"arguments":[],' + body[1:]
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_stdin_envelope(duplicated.encode("utf-8"))
        self.assertEqual(
            ExperimentRefusal.ENVELOPE_DUPLICATE_KEY, caught.exception.reason,
        )

        for raw, reason in (
            (b"{not json", ExperimentRefusal.ENVELOPE_MALFORMED),
            (b"[]", ExperimentRefusal.ENVELOPE_MALFORMED),
            (b"\xff\xfe", ExperimentRefusal.ENVELOPE_MALFORMED),
        ):
            with self.assertRaises(ExperimentSandboxRefusal) as caught:
                parse_stdin_envelope(raw)
            self.assertEqual(reason, caught.exception.reason)

        missing = envelope_document()
        del missing["arguments"]
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_stdin_envelope(json.dumps(missing).encode("utf-8"))
        self.assertEqual(ExperimentRefusal.ENVELOPE_MALFORMED, caught.exception.reason)

    def test_envelope_byte_bound_refuses_before_parsing(self) -> None:
        oversize = b"{" + b" " * (EXPERIMENT_PROFILE.max_stdin_envelope_bytes + 1)
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_stdin_envelope(oversize)
        self.assertEqual(
            ExperimentRefusal.STDIN_ENVELOPE_EXCEEDS_BOUND, caught.exception.reason,
        )


class BootstrapContractTests(unittest.TestCase):
    """The stdin/stdout contract, proven in-process without a container.

    This is a PROTOCOL contract test, not a containment proof.  It executes a
    project-authored fixture program inside the test interpreter to show the
    envelope, the content addresses, and the response envelope agree.  It says
    nothing about kernel isolation.
    """

    def _run(self, raw: bytes) -> str:
        stdin, stdout = sys.stdin, sys.stdout
        buffer = io.StringIO()

        class Stdin:
            def __init__(self, data: bytes) -> None:
                self.buffer = io.BytesIO(data)

        try:
            sys.stdin = Stdin(raw)  # type: ignore[assignment]
            sys.stdout = buffer
            exec(  # noqa: S102 - fixture protocol contract, see class docstring
                compile(_BOOTSTRAP, "<adaivy-bootstrap-contract>", "exec"),
                {"__name__": "__main__"},
            )
        finally:
            sys.stdin, sys.stdout = stdin, stdout
        return buffer.getvalue()

    def test_bootstrap_is_valid_python_and_hash_pinned(self) -> None:
        compile(_BOOTSTRAP, "<adaivy-bootstrap>", "exec")
        self.assertEqual(
            "sha256:" + hashlib.sha256(_BOOTSTRAP.encode("utf-8")).hexdigest(),
            BOOTSTRAP_SHA256,
        )
        self.assertIn(ENVELOPE_SCHEMA, _BOOTSTRAP)
        self.assertIn(RESPONSE_SCHEMA, _BOOTSTRAP)

    def test_result_is_content_addressed_end_to_end(self) -> None:
        admitted = validate_experiment_request(request())
        with no_process_or_socket() as observed:
            output = self._run(build_stdin_envelope(admitted))
        self.assertEqual([], observed)
        response = json.loads(output)
        self.assertEqual(RESPONSE_FIELDS, frozenset(response))
        self.assertEqual(RESPONSE_SCHEMA, response["schema_version"])
        self.assertEqual("completed", response["status"])
        import base64

        result = base64.b64decode(response["result_base64"], validate=True)
        self.assertEqual(digest(result), response["result_sha256"])
        self.assertEqual(
            {"bound": 8, "harmonic": [761, 280]}, json.loads(result.decode("utf-8")),
        )

    def test_each_bootstrap_tamper_probe_exits_with_its_named_code(self) -> None:
        probes = (
            ("duplicate_key", 91),
            ("unknown_field", 92),
            ("schema_version", 93),
            ("empty_program", 94),
            ("program_hash", 95),
            ("input_artifact_fields", 96),
            ("input_hash", 97),
        )
        admitted = validate_experiment_request(request())
        base = json.loads(build_stdin_envelope(admitted).decode("utf-8"))
        flipped = 0
        for name, code in probes:
            with self.subTest(probe=name):
                document = copy.deepcopy(base)
                if name == "duplicate_key":
                    body = json.dumps(document, sort_keys=True)
                    raw = ("{" + '"arguments":[],' + body[1:]).encode("utf-8")
                else:
                    if name == "unknown_field":
                        document["environment"] = {"SECRET": "x"}
                    elif name == "schema_version":
                        document["schema_version"] = "other.v1"
                    elif name == "empty_program":
                        document["program_source"] = ""
                    elif name == "program_hash":
                        document["program_sha256"] = "0" * 64
                    elif name == "input_artifact_fields":
                        document["input_artifacts"][0]["extra"] = 1
                    elif name == "input_hash":
                        document["input_artifacts"][0]["content_hash"] = (
                            "sha256:" + "0" * 64
                        )
                    raw = json.dumps(document, sort_keys=True).encode("utf-8")
                with self.assertRaises(SystemExit) as caught:
                    self._run(raw)
                self.assertEqual(code, caught.exception.code)
                flipped += 1
        self.assertEqual(len(probes), flipped)


class ImageLockTests(unittest.TestCase):
    def test_shipped_pin_is_unresolved_and_refuses_with_the_named_reason(self) -> None:
        with no_process_or_socket() as observed:
            lock = load_experiment_image_lock(IMAGE_LOCK_PATH)
        self.assertEqual([], observed)
        self.assertEqual("unresolved", lock.digest_status)
        self.assertFalse(lock.pinned)
        self.assertIsNone(lock.image_digest)
        self.assertIsNone(lock.image_reference)
        self.assertEqual("unresolved_pending_owner_pin", lock.authorization_status)
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            lock.require_pin()
        self.assertEqual(
            ExperimentRefusal.IMAGE_DIGEST_UNRESOLVED, caught.exception.reason,
        )
        self.assertEqual("image_digest", caught.exception.field)

    def test_parser_image_digest_constant_tracks_the_phase4b_pin(self) -> None:
        phase4b = json.loads(PHASE4B_LOCK_PATH.read_text("utf-8"))
        self.assertEqual(PHASE4B_PARSER_IMAGE_DIGEST, phase4b["oci_index_digest"])
        self.assertIn(
            PHASE4B_PARSER_IMAGE_DIGEST,
            shipped_lock_document()["forbidden_reuse_digests"],
        )
        self.assertNotEqual(
            phase4b["authorization"]["runtime_role"],
            shipped_lock_document()["runtime_role"],
        )

    def test_pinning_the_parser_image_is_itself_a_refusal(self) -> None:
        document = pinned_lock_document(PHASE4B_PARSER_IMAGE_DIGEST)
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_experiment_image_lock(json.dumps(document).encode("utf-8"))
        self.assertEqual(
            ExperimentRefusal.PARSER_IMAGE_REUSE_FORBIDDEN, caught.exception.reason,
        )
        identity_digest = PHASE4B_PARSER_IMAGE_DIGEST
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            runtime(f"docker.io/library/python@{identity_digest}")
        self.assertEqual(
            ExperimentRefusal.PARSER_IMAGE_REUSE_FORBIDDEN, caught.exception.reason,
        )

    def test_every_named_lock_probe_flips_its_own_control(self) -> None:
        def mutate(**updates: object) -> dict[str, object]:
            value = pinned_lock_document()
            value.update(updates)
            return value

        modules = sorted(ALLOWED_IMPORT_MODULES) + ["os"]
        loose_profile = dict(EXPERIMENT_PROFILE.to_record())
        loose_profile["max_memory_bytes"] = 2_147_483_648
        probes: tuple[tuple[str, dict[str, object], ExperimentRefusal, str | None], ...] = (
            ("reference_digest_mismatch",
             mutate(image_reference="docker.io/library/python@sha256:" + "b" * 64),
             ExperimentRefusal.IMAGE_DIGEST_MISMATCH, "image_reference"),
            ("pinned_without_digest", mutate(image_digest=None),
             ExperimentRefusal.IMAGE_DIGEST_UNRESOLVED, "image_digest"),
            ("pinned_digest_grammar", mutate(image_digest="sha256:xyz"),
             ExperimentRefusal.IMAGE_DIGEST_UNRESOLVED, "image_digest"),
            ("runtime_role", mutate(runtime_role="phase4b_parser_sandbox_only"),
             ExperimentRefusal.IMAGE_ROLE_NOT_GENERATED_CODE, "runtime_role"),
            ("unknown_field", mutate(offline_archive={"sha256": "x"}),
             ExperimentRefusal.IMAGE_LOCK_UNKNOWN_FIELD, "offline_archive"),
            ("schema_version", mutate(schema_version="adaivy.other.v1"),
             ExperimentRefusal.IMAGE_LOCK_SCHEMA_VERSION_UNKNOWN, "schema_version"),
            ("digest_status_vocabulary", mutate(digest_status="latest"),
             ExperimentRefusal.IMAGE_LOCK_MALFORMED, "digest_status"),
            ("network_default", mutate(network_default="bridge"),
             ExperimentRefusal.NETWORK_FORBIDDEN, "network_default"),
            ("pull_policy", mutate(pull_policy="always"),
             ExperimentRefusal.IMAGE_LOCK_MALFORMED, "pull_policy"),
            ("platform", mutate(platform="windows/amd64"),
             ExperimentRefusal.IMAGE_LOCK_MALFORMED, "platform"),
            ("resource_profile_declaration", mutate(resource_profile=loose_profile),
             ExperimentRefusal.PROFILE_DECLARATION_MISMATCH, "resource_profile"),
            ("language_surface_declaration", mutate(allowed_import_modules=modules),
             ExperimentRefusal.LANGUAGE_SURFACE_DECLARATION_MISMATCH,
             "allowed_import_modules"),
            ("forbidden_reuse_declaration", mutate(forbidden_reuse_digests=[]),
             ExperimentRefusal.IMAGE_LOCK_MALFORMED, "forbidden_reuse_digests"),
            ("pinned_authorization_status",
             mutate(authorization_status="unresolved_pending_owner_pin"),
             ExperimentRefusal.IMAGE_LOCK_MALFORMED, "authorization_status"),
        )
        flipped = 0
        for name, document, reason, field in probes:
            with self.subTest(probe=name):
                with self.assertRaises(ExperimentSandboxRefusal) as caught:
                    parse_experiment_image_lock(json.dumps(document).encode("utf-8"))
                self.assertEqual(reason, caught.exception.reason)
                self.assertEqual(field, caught.exception.field)
                flipped += 1

        unresolved = shipped_lock_document()
        unresolved["image_digest"] = "sha256:" + "a" * 64
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_experiment_image_lock(json.dumps(unresolved).encode("utf-8"))
        self.assertEqual(ExperimentRefusal.IMAGE_LOCK_MALFORMED, caught.exception.reason)
        self.assertEqual("image_digest", caught.exception.field)
        flipped += 1

        missing = shipped_lock_document()
        del missing["platform"]
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_experiment_image_lock(json.dumps(missing).encode("utf-8"))
        self.assertEqual(ExperimentRefusal.IMAGE_LOCK_MALFORMED, caught.exception.reason)
        flipped += 1

        body = json.dumps(shipped_lock_document(), sort_keys=True)
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            parse_experiment_image_lock(
                ("{" + '"platform":"linux/arm64",' + body[1:]).encode("utf-8")
            )
        self.assertEqual(
            ExperimentRefusal.IMAGE_LOCK_DUPLICATE_KEY, caught.exception.reason,
        )
        flipped += 1
        self.assertEqual(len(probes) + 3, flipped)


class CommandConstructionTests(unittest.TestCase):
    """Offline proof that the invocation names every control.

    Presence of a flag is NOT proof that the kernel enforced it; that claim
    belongs to :class:`ContainerGateTests`.  What is proven here is that the
    command carries every control, contains no mount and no in-container host
    path, and derives nothing from the model beyond tightened resource values.
    """

    def command(self, **updates: int) -> tuple[str, ...]:
        return build_run_command(
            runtime=runtime(), profile=EXPERIMENT_PROFILE,
            effective=limits(**updates), cidfile=Path("/tmp/adaivy-cid/cid"),
        )

    def test_command_carries_every_declared_control_flag(self) -> None:
        with no_process_or_socket() as observed:
            command = self.command()
        self.assertEqual([], observed, "building a command must open no process")
        for control in CONTAINER_CONTROLS:
            for evidence in control.command_evidence:
                with self.subTest(control=control.name, evidence=evidence):
                    self.assertTrue(
                        any(item.startswith(evidence) for item in command),
                        f"{control.name} lost its command evidence {evidence}",
                    )

    def test_command_names_the_exact_hard_bounds(self) -> None:
        command = self.command()
        expected = {
            "--interactive", "--pull=never", "--platform=linux/arm64",
            "--network=none", "--read-only", "--memory=268435456",
            "--memory-swap=268435456", "--pids-limit=1",
            "--ulimit=nofile=64:64", "--ulimit=fsize=8388608:8388608",
            "--ulimit=cpu=60:60", "--ulimit=core=0:0", "--cpus=1.0",
            "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
            "--user=65534:65534", "--workdir=/work", "--entrypoint=python3",
        }
        self.assertTrue(expected <= set(command), expected - set(command))
        self.assertTrue(any(
            item.startswith(
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8388608,nr_inodes=64,"
            )
            for item in command
        ))
        self.assertTrue(any(
            item.startswith(
                "--tmpfs=/work:rw,noexec,nosuid,nodev,size=8388608,nr_inodes=64,"
            )
            for item in command
        ))
        self.assertEqual(runtime().image_reference, command[-4])
        self.assertEqual(("-S", "-c"), command[-3:-1])

    def test_command_mounts_no_host_path_and_names_no_shell(self) -> None:
        command = self.command()
        self.assertFalse([
            item for item in command
            if item.startswith(("--mount", "--volume", "-v", "--privileged"))
        ])
        self.assertFalse([
            item for item in command
            if item.startswith(("--cap-add", "--device", "--pid=", "--ipc=", "--userns"))
        ])
        for shell in ("sh", "bash", "/bin/sh", "-c sh", "sudo"):
            self.assertNotIn(shell, command[:-1])
        # The only absolute host paths are the client binary and the
        # client-written cidfile. Neither is visible inside the container.
        absolute = [
            item for item in command
            if item.startswith("/") or "=/" in item and not item.startswith(
                ("--tmpfs=", "--workdir=", "--env=")
            )
        ]
        self.assertEqual(
            ["/opt/reviewed/docker", "--cidfile=/tmp/adaivy-cid/cid"], absolute,
        )

    def test_container_environment_is_fixed_and_complete(self) -> None:
        command = self.command()
        supplied = sorted(
            item.removeprefix("--env=") for item in command if item.startswith("--env=")
        )
        self.assertEqual(
            sorted(f"{key}={value}" for key, value in CONTAINER_ENVIRONMENT.items()),
            supplied,
        )
        for secret in ("AWS", "AZURE", "OPENAI", "TOKEN", "SECRET", "KEY", "DOCKER_"):
            self.assertFalse([item for item in supplied if secret in item])

    def test_program_source_never_reaches_the_command_line(self) -> None:
        command = self.command()
        self.assertNotIn(PROGRAM.decode("utf-8"), command)
        for item in command:
            self.assertNotIn("harmonic", item)

    def test_declared_resource_values_only_tighten_the_command(self) -> None:
        tight = self.command(memory_bytes=67_108_864, cpu_milliseconds=1_000)
        self.assertIn("--memory=67108864", tight)
        self.assertIn("--ulimit=cpu=1:1", tight)
        self.assertNotIn(f"--memory={EXPERIMENT_PROFILE.max_memory_bytes}", tight)


class CommandFalsifiabilityTests(unittest.TestCase):
    """One named single-field probe per command-carried control.

    A coverage assertion that cannot fail proves nothing, so each probe removes
    exactly one control's evidence from its own argv fixture and requires the
    coverage check to reject it, or mutates exactly one bound and requires the
    argv to change with it.
    """

    def command(self, *, profile=EXPERIMENT_PROFILE, **updates: int) -> tuple[str, ...]:
        return build_run_command(
            runtime=runtime(), profile=profile, effective=limits(**updates),
            cidfile=Path("/tmp/adaivy-cid/cid"),
        )

    @staticmethod
    def covers(command: tuple[str, ...], evidence: str) -> bool:
        return any(item.startswith(evidence) for item in command)

    def test_removing_one_control_flag_is_detected(self) -> None:
        baseline = self.command()
        flipped = 0
        for control in CONTAINER_CONTROLS:
            for evidence in control.command_evidence:
                with self.subTest(control=control.name, evidence=evidence):
                    self.assertTrue(self.covers(baseline, evidence))
                    mutated = tuple(
                        item for item in baseline if not item.startswith(evidence)
                    )
                    self.assertFalse(self.covers(mutated, evidence))
                    self.assertEqual(
                        len(baseline) - 1, len(mutated),
                        "a control flag must appear exactly once",
                    )
                    flipped += 1
        self.assertEqual(
            sum(len(control.command_evidence) for control in CONTAINER_CONTROLS),
            flipped,
        )
        self.assertGreaterEqual(flipped, 9, "the evidence table must not be emptied")

    def test_each_kernel_bound_probe_moves_its_own_flag(self) -> None:
        probes = (
            ("memory_limit", {"memory_bytes": 67_108_864},
             "--memory=268435456", "--memory=67108864"),
            ("memory_limit_swap", {"memory_bytes": 67_108_864},
             "--memory-swap=268435456", "--memory-swap=67108864"),
            ("process_limit", {"process_count": 4},
             "--pids-limit=1", "--pids-limit=4"),
            ("cpu_limit", {"cpu_milliseconds": 2_000},
             "--ulimit=cpu=60:60", "--ulimit=cpu=2:2"),
        )
        baseline = self.command()
        flipped = 0
        for name, mutation, before, after in probes:
            with self.subTest(probe=name):
                self.assertIn(before, baseline)
                mutated = self.command(**mutation)
                self.assertIn(after, mutated)
                self.assertNotIn(before, mutated)
                flipped += 1
        self.assertEqual(len(probes), flipped)

    def test_each_profile_bound_probe_moves_its_own_flag(self) -> None:
        probes = (
            ("file_count_limit", {"max_open_files": 32},
             "--ulimit=nofile=64:64", "--ulimit=nofile=32:32"),
            ("file_size_limit", {"max_file_bytes": 1_048_576},
             "--ulimit=fsize=8388608:8388608", "--ulimit=fsize=1048576:1048576"),
        )
        baseline = self.command()
        flipped = 0
        for name, mutation, before, after in probes:
            with self.subTest(probe=name):
                self.assertIn(before, baseline)
                mutated = self.command(profile=ExperimentSandboxProfile(**mutation))
                self.assertIn(after, mutated)
                self.assertNotIn(before, mutated)
                flipped += 1
        tightened = self.command(
            profile=ExperimentSandboxProfile(max_temp_inodes=16, max_temp_bytes=1_048_576)
        )
        self.assertTrue(any(
            item.startswith(
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=1048576,nr_inodes=16,"
            )
            for item in tightened
        ))
        flipped += 1
        self.assertEqual(len(probes) + 1, flipped)

    def test_wall_and_stream_truncation_remain_parent_side_and_unproven(self) -> None:
        """The wall deadline and stream truncation are not argv-visible.

        They are enforced by the launcher against a monotonic deadline and a byte
        counter, so no offline command-construction probe can establish them.
        This test records that honestly rather than implying coverage.
        """

        command = self.command()
        self.assertFalse([item for item in command if item.startswith("--stop-timeout")])
        self.assertFalse([item for item in command if "wall" in item])
        pending = {
            control.name: control.proof for control in CONTAINER_CONTROLS
            if control.name in {"wall_limit", "bounded_json_streams"}
        }
        for name, proof in pending.items():
            self.assertIn("pending_container_gate", proof, name)


class ControlCoverageTests(unittest.TestCase):
    def test_every_adr_0057_section_2_control_is_named(self) -> None:
        self.assertEqual(
            {
                "digest_pinned_image", "no_network", "read_only_root",
                "noexec_empty_temporary", "no_inherited_credentials",
                "fresh_work_directory", "bounded_json_streams", "wall_limit",
                "cpu_limit", "memory_limit", "process_limit", "file_count_limit",
                "file_size_limit", "content_addressed_io",
                "no_model_chosen_invocation",
            },
            {control.name for control in CONTAINER_CONTROLS},
        )
        self.assertEqual(15, len(CONTAINER_CONTROLS))

    def test_container_dependent_claims_are_labelled_as_pending(self) -> None:
        pending = {
            control.name for control in CONTAINER_CONTROLS
            if "pending_container_gate" in control.proof
        }
        self.assertEqual(
            {
                "no_network", "read_only_root", "noexec_empty_temporary",
                "no_inherited_credentials", "fresh_work_directory",
                "bounded_json_streams", "wall_limit", "cpu_limit", "memory_limit",
                "process_limit", "file_count_limit", "file_size_limit",
            },
            pending,
        )
        offline = {
            control.name for control in CONTAINER_CONTROLS
            if "pending_container_gate" not in control.proof
        }
        self.assertEqual(
            {"digest_pinned_image", "content_addressed_io", "no_model_chosen_invocation"},
            offline,
        )


class SandboxRefusalTests(unittest.TestCase):
    def test_unpinned_digest_refuses_with_the_named_reason_and_no_process(self) -> None:
        sandbox = CampaignExperimentSandbox(
            lock=load_experiment_image_lock(IMAGE_LOCK_PATH)
        )
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        self.assertIs(RecordStatus.FAILED, result.status)
        self.assertEqual(ADAPTER_ID, result.adapter_id)
        self.assertIs(UsageSource.UNAVAILABLE, result.measurement_source)
        self.assertIsNone(result.wall_milliseconds)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("image_digest_unresolved", body["refusal"]["reason"])
        self.assertFalse(body["refusal"]["epistemic_warrant_created"])
        self.assertIn(b"image_digest_unresolved", result.stderr)
        evidence = sandbox.last_evidence
        assert evidence is not None
        self.assertEqual(EVIDENCE_SCHEMA, evidence.schema_version)
        self.assertFalse(evidence.container_launched)
        self.assertFalse(evidence.image_digest_pinned)
        self.assertFalse(evidence.epistemic_warrant_created)
        for name in KERNEL_ENFORCEMENT_FIELDS:
            self.assertFalse(getattr(evidence, name), name)

    def test_refusal_bytes_are_deterministic_across_calls(self) -> None:
        sandbox = CampaignExperimentSandbox(
            lock=load_experiment_image_lock(IMAGE_LOCK_PATH)
        )
        first = sandbox(request())
        first_hash = sandbox.last_evidence.content_hash()  # type: ignore[union-attr]
        second = sandbox(request())
        self.assertEqual(first.result, second.result)
        self.assertEqual(first.stderr, second.stderr)
        self.assertEqual(
            first_hash, sandbox.last_evidence.content_hash(),  # type: ignore[union-attr]
        )

    def test_request_admission_precedes_the_digest_gate(self) -> None:
        sandbox = CampaignExperimentSandbox(
            lock=load_experiment_image_lock(IMAGE_LOCK_PATH)
        )
        with no_process_or_socket() as observed:
            result = sandbox(request(tool_id="bash_search"))
        self.assertEqual([], observed)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("shell_adapter_forbidden", body["refusal"]["reason"])
        self.assertIsNone(body["request"])

    def test_pinned_digest_without_activation_still_refuses(self) -> None:
        sandbox = CampaignExperimentSandbox(lock=pinned_lock())
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("activation_not_authorized", body["refusal"]["reason"])
        self.assertEqual("activation", body["refusal"]["field"])
        self.assertIsNotNone(body["request"])

    def test_activation_bound_to_a_different_lock_refuses(self) -> None:
        lock = pinned_lock()
        other = load_experiment_image_lock(IMAGE_LOCK_PATH)
        sandbox = CampaignExperimentSandbox(lock=lock, activation=activation(other))
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("activation_not_authorized", body["refusal"]["reason"])
        self.assertEqual("image_lock_hash", body["refusal"]["field"])

    def test_activated_pin_without_a_launcher_refuses(self) -> None:
        lock = pinned_lock()
        sandbox = CampaignExperimentSandbox(lock=lock, activation=activation(lock))
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("launcher_unavailable", body["refusal"]["reason"])
        self.assertEqual("launcher", body["refusal"]["field"])

    def test_activated_pin_with_a_launcher_but_no_runtime_refuses(self) -> None:
        lock = pinned_lock()
        sandbox = CampaignExperimentSandbox(
            lock=lock, activation=activation(lock), launcher=RecordingLauncher(),
        )
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        body = json.loads(result.result.decode("utf-8"))
        self.assertEqual("runtime_unavailable", body["refusal"]["reason"])
        self.assertEqual("runtime", body["refusal"]["field"])

    def test_default_construction_from_the_shipped_pin_refuses(self) -> None:
        sandbox = build_default_experiment_sandbox(image_lock_path=IMAGE_LOCK_PATH)
        self.assertIsNone(sandbox.launcher)
        self.assertIsNone(sandbox.activation)
        self.assertIsNone(sandbox.runtime)
        with no_process_or_socket() as observed:
            result = sandbox(request())
        self.assertEqual([], observed)
        self.assertIs(RecordStatus.FAILED, result.status)
        self.assertEqual(
            "image_digest_unresolved",
            json.loads(result.result.decode("utf-8"))["refusal"]["reason"],
        )

    def test_activation_record_itself_fails_closed(self) -> None:
        lock = pinned_lock()
        base = activation(lock).to_record()
        for name, value in (
            ("status", "pending"),
            ("authorized_by", ""),
            ("acknowledgement", "sure"),
            ("policy_hash", "nope"),
            ("probe_report_hash", "sha1:x"),
        ):
            with self.subTest(field=name):
                fields = {
                    key: item for key, item in base.items() if key != "schema_version"
                }
                fields[name] = value
                with self.assertRaises(ExperimentSandboxRefusal) as caught:
                    ExperimentSandboxActivation(**fields)
                self.assertEqual(
                    ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, caught.exception.reason,
                )
                self.assertEqual(name, caught.exception.field)


class CampaignLedgerIntegrationTests(unittest.TestCase):
    """The refusal is retained in the campaign ledger, not lost to an exception."""

    def test_refused_run_program_is_recorded_as_a_failed_tool_run(self) -> None:
        target = digest(b"target")
        configuration = digest(b"configuration")
        live = digest(b"live")
        pricing = digest(b"pricing")
        source = PROGRAM.decode("utf-8")

        def action(kind: str, **updates: object) -> bytes:
            value: dict[str, object] = {
                "schema_version": "1.0.0",
                "action_type": kind,
                "branch_id": "branch.main",
                "rationale": f"Perform {kind} inside the frozen campaign.",
                "artifact_text": None,
                "program_source": None,
                "tool_request": None,
                "selected_candidate_hash": None,
                "selected_tool_artifact_hashes": [],
                "report_text": None,
            }
            value.update(updates)
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

        class Artifacts:
            def __init__(self) -> None:
                self.values: dict[str, bytes] = {}

            def put(self, content: bytes, *, media_type: str) -> str:
                content_hash = digest(content)
                self.values[content_hash] = content
                return content_hash

            def get(self, content_hash: str) -> bytes:
                return self.values[content_hash]

        def planner_response(raw: bytes) -> PlannerResponse:
            return PlannerResponse(
                action_json=raw, provider="scripted", model_identifier="scripted-lead",
                status=RecordStatus.COMPLETED, usage_source=UsageSource.UNAVAILABLE,
                input_tokens=0, output_tokens=0, estimated_cost_microusd=None,
                provider_request_id=None,
            )

        steps = [
            action("write_program", program_source=source),
            lambda context: action("run_program", tool_request={
                "tool_id": "exact_python_search",
                "program_artifact_hash": context.recorded_program_hashes[0],
                "input_artifact_hashes": [],
                "arguments": ["bound=8"],
                "resource_limits": {
                    "cpu_milliseconds": 60_000, "wall_milliseconds": 60_000,
                    "memory_bytes": 268_435_456, "output_bytes": 65_536,
                    "process_count": 1,
                },
                "network": "none",
            }),
            action("report", report_text="The sandbox refused; no result exists."),
        ]

        class Planner:
            def __init__(self) -> None:
                self.steps = list(steps)

            def __call__(self, context: object) -> PlannerResponse:
                step = self.steps.pop(0)
                return planner_response(step(context) if callable(step) else step)

        def refuse_verification(_request: object) -> None:  # pragma: no cover
            raise AssertionError("the verifier must not be reached")

        sandbox = CampaignExperimentSandbox(
            lock=load_experiment_image_lock(IMAGE_LOCK_PATH)
        )
        runner = SequentialCampaignRunner(
            campaign_id="campaign.sandbox-refusal", target_hash=target,
            configuration_hash=configuration, live_configuration_hash=live,
            pricing_snapshot_hash=pricing, planner_actor_id="model.scripted",
            planner=Planner(), experiment_runner=sandbox, artifacts=Artifacts(),
            verifier=refuse_verification,  # type: ignore[arg-type]
            policy=CampaignRunnerPolicy(
                allowed_tools=frozenset({"exact_python_search"}), max_actions=6,
                max_tool_runs=2, max_program_bytes=262_144,
                max_artifact_bytes=1_048_576, max_cpu_milliseconds=120_000,
                max_wall_milliseconds=120_000, max_memory_bytes=1_073_741_824,
                max_output_bytes=1_048_576, max_process_count=4,
            ),
            recorded_at=lambda: "2026-08-22T00:00:00Z",
        )
        with no_process_or_socket() as observed:
            run = runner.run()
        self.assertEqual([], observed)
        self.assertEqual("reported", run.terminal_reason)
        self.assertFalse(run.epistemic_warrant_created)
        self.assertEqual(1, len(run.tool_runs))
        record = run.tool_runs[0]
        self.assertEqual(ADAPTER_ID, record.adapter_id)
        self.assertIs(RecordStatus.FAILED, record.status)
        self.assertIsNone(record.wall_milliseconds)
        self.assertIsNone(run.selected_candidate_hash)


class RepositoryInvariantTests(unittest.TestCase):
    def test_module_imports_no_network_module_at_module_scope(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text("utf-8"), filename=str(MODULE_PATH))
        module_scope: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_scope.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_scope.add(node.module)
        for forbidden in (
            "selectors", "socket", "ssl", "asyncio", "urllib.request",
            "http.client", "requests", "httpx", "subprocess", "multiprocessing",
        ):
            self.assertNotIn(forbidden, module_scope)
        # The campaign package contains NO process or socket code at all, at any
        # nesting level. `tests/test_campaign_provenance.py` asserts the same
        # property textually for the whole package; this asserts it structurally
        # for the new module.
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                self.assertNotIn(
                    name.split(".", 1)[0],
                    {"subprocess", "selectors", "socket", "ssl", "multiprocessing"},
                )

    def test_launcher_module_loads_selectors_lazily_and_nothing_third_party(self) -> None:
        path = ROOT / "src/math_research/experiment_oci_launcher.py"
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        module_scope: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_scope.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_scope.add(node.module)
        self.assertIn("subprocess", module_scope)
        self.assertNotIn("selectors", module_scope)
        lazy = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            and any(alias.name == "selectors" for alias in node.names)
        ]
        self.assertEqual(1, len(lazy), "selectors must load lazily exactly once")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                self.assertIn(
                    name.split(".", 1)[0],
                    sys.stdlib_module_names | {"math_research"},
                )

    def test_importing_the_launcher_module_creates_no_process(self) -> None:
        import importlib

        with no_process_or_socket() as observed:
            importlib.reload(
                importlib.import_module("math_research.experiment_oci_launcher")
            )
        self.assertEqual([], observed)

    def test_launcher_refuses_a_relative_client_or_non_unix_daemon(self) -> None:
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            OciExperimentLauncher(
                docker_executable=Path("docker"),
                daemon_host="unix:///tmp/reviewed-docker.sock",
            )
        self.assertEqual(
            ExperimentRefusal.RUNTIME_UNAVAILABLE, caught.exception.reason,
        )
        with self.assertRaises(ExperimentSandboxRefusal) as caught:
            OciExperimentLauncher(
                docker_executable=Path("/usr/bin/env"),
                daemon_host="tcp://127.0.0.1:2375",
            )
        self.assertEqual(
            ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, caught.exception.reason,
        )

    def test_module_declares_no_third_party_import(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text("utf-8"), filename=str(MODULE_PATH))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".", 1)[0]
                self.assertIn(
                    root,
                    sys.stdlib_module_names | {"math_research"},
                    f"{name} is not standard library",
                )


class LauncherBoundaryTests(unittest.TestCase):
    """The launcher's own closed surface, proven without launching anything.

    Constructing an `OciExperimentLauncher` performs no engine call: it only
    resolves and permission-checks the client path. `/usr/bin/env` stands in for
    a reviewed client here precisely because no engine call is made.
    """

    def launcher(self) -> OciExperimentLauncher:
        client = Path("/usr/bin/env")
        if not client.is_file():
            self.skipTest("no stand-in executable for the client path check")
        with no_process_or_socket() as observed:
            built = OciExperimentLauncher(
                docker_executable=client,
                daemon_host="unix:///var/run/reviewed-docker.sock",
            )
        self.assertEqual([], observed, "constructing a launcher must open nothing")
        return built

    def test_client_environment_is_closed_and_inherits_no_credential(self) -> None:
        environment = self.launcher().client_environment()
        self.assertEqual(
            {"DOCKER_HOST", "LANG", "LC_ALL", "PATH"}, set(environment),
        )
        self.assertEqual(
            "unix:///var/run/reviewed-docker.sock", environment["DOCKER_HOST"],
        )
        # An ambient credential in the parent environment must not appear.
        os.environ["ADAIVY_PROBE_FAKE_SECRET"] = "must-not-propagate"
        try:
            leaked = self.launcher().client_environment()
        finally:
            del os.environ["ADAIVY_PROBE_FAKE_SECRET"]
        self.assertNotIn("ADAIVY_PROBE_FAKE_SECRET", leaked)
        for name, value in leaked.items():
            self.assertNotIn("must-not-propagate", value, name)

    def test_launcher_refuses_a_command_that_is_not_the_reviewed_client(self) -> None:
        launcher = self.launcher()
        with no_process_or_socket() as observed:
            with self.assertRaises(ExperimentSandboxRefusal) as caught:
                launcher.control(("/bin/sh", "-c", "id"))
            self.assertEqual(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, caught.exception.reason,
            )
            with self.assertRaises(ExperimentSandboxRefusal) as caught:
                launcher.execute(
                    ("/bin/sh", "-c", "id"), input_bytes=b"{}", wall_seconds=1.0,
                    stdout_limit=1_024, stderr_limit=1_024,
                )
            self.assertEqual(
                ExperimentRefusal.LAUNCH_FAILED, caught.exception.reason,
            )
            with self.assertRaises(ExperimentSandboxRefusal) as caught:
                launcher.execute(
                    (launcher.docker_executable, "run"), input_bytes=b"{}",
                    wall_seconds=0.0, stdout_limit=1_024, stderr_limit=1_024,
                )
            self.assertEqual(
                ExperimentRefusal.LAUNCH_FAILED, caught.exception.reason,
            )
            self.assertEqual("bounds", caught.exception.field)
        self.assertEqual([], observed, "a refused launch must open no process")


class ContainerGateTests(unittest.TestCase):
    """Kernel enforcement. SKIPS unless the owner has pinned and configured it.

    Nothing in this class has ever executed in this repository: no image has
    been pulled, built, or run for the campaign experiment role, and the shipped
    pin carries `digest_status: unresolved`.  A skip here is NOT a pass.
    """

    def test_pinned_image_executes_and_the_kernel_rejects_a_memory_overage(self) -> None:
        lock_path = os.environ.get("ADAIVY_CAMPAIGN_EXPERIMENT_OCI_LOCK")
        docker = os.environ.get("ADAIVY_CAMPAIGN_EXPERIMENT_OCI_DOCKER")
        daemon = os.environ.get("ADAIVY_CAMPAIGN_EXPERIMENT_OCI_DAEMON")
        if not lock_path or not docker or not daemon:
            self.skipTest(
                "owner-pinned campaign experiment image and reviewed runtime "
                "are not configured; kernel enforcement is UNPROVEN"
            )
        lock = load_experiment_image_lock(Path(lock_path))
        self.assertTrue(lock.pinned, "the configured lock must carry a pinned digest")
        launcher = OciExperimentLauncher(
            docker_executable=Path(docker), daemon_host=daemon,
        )
        self.assertEqual(LAUNCHER_ID, launcher.launcher_id)
        measured = ExperimentRuntimeIdentity.measure(launcher=launcher, lock=lock)
        sandbox = CampaignExperimentSandbox(
            lock=lock, activation=activation(lock), runtime=measured,
            launcher=launcher,
        )
        result = sandbox(request())
        self.assertIs(RecordStatus.COMPLETED, result.status, result.stderr)
        self.assertEqual(
            {"bound": 8, "harmonic": [761, 280]},
            json.loads(result.result.decode("utf-8")),
        )
        evidence = sandbox.last_evidence
        assert evidence is not None
        self.assertTrue(evidence.container_launched)
        for name in KERNEL_ENFORCEMENT_FIELDS:
            self.assertTrue(getattr(evidence, name), name)

        hungry = (
            "import sys\n"
            "block = bytearray(400_000_000)\n"
            "sys.stdout.write(str(len(block)))\n"
        ).encode("utf-8")
        overage = sandbox(request(
            program_source=hungry, program_artifact_hash=digest(hungry),
            resource_limits=limits(memory_bytes=67_108_864, wall_milliseconds=30_000),
        ))
        self.assertIs(RecordStatus.FAILED, overage.status)
        body = json.loads(overage.result.decode("utf-8"))
        self.assertIn(
            body.get("bound_enforced"),
            {"memory_limit_exceeded", "worker_failed"},
        )
        memory_evidence = sandbox.last_evidence
        assert memory_evidence is not None
        self.assertTrue(memory_evidence.kernel_memory_enforcement)

        walker = (
            "total = 0\n"
            "while True:\n"
            "    total += 1\n"
        ).encode("utf-8")
        stalled = sandbox(request(
            program_source=walker, program_artifact_hash=digest(walker),
            resource_limits=limits(wall_milliseconds=5_000, cpu_milliseconds=3_000),
        ))
        self.assertIs(RecordStatus.FAILED, stalled.status)
        self.assertIn(
            json.loads(stalled.result.decode("utf-8")).get("bound_enforced"),
            {"wall_limit_exceeded", "cpu_limit_exceeded"},
        )


if __name__ == "__main__":
    unittest.main()
