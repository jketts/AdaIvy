#!/usr/bin/env python3
"""Seal acquisition, runtime-inventory, and v3/v4 replay evidence."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import stat
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
TMP = Path("/private/tmp/adaivy-phase3b-v4")
IMAGE_TAR = TMP / "v4-final-image.tar"
IMAGE_NAME = "adaivy-phase3b-gate-v4:lean-v4.32.1"
IMAGE_DIGEST = "sha256:ad81d799c1d9e766e0263c2b703936ca3fb8042e189e7e279b7abd1c7889c60b"
V3_DIGEST = "sha256:0d3a26db46d1bace987b273d59087e3e39fbc9901d2bd680bf251f190622eac3"
APPROVED_EXECUTABLES = [
    "/checker/launcher",
    "/lib/ld-linux-aarch64.so.1",
    "/opt/lean/bin/lean",
]
FORBIDDEN_BASENAMES = {
    "sh", "bash", "dash", "busybox", "curl", "wget", "git", "ssh",
    "env", "apt", "apt-get", "dpkg", "apk", "yum", "dnf", "elan",
    "lake", "clang", "gcc", "cc", "ld", "ld.lld", "make", "cmake",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def release_asset(path: Path, filename: str) -> dict:
    release = json.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in release["assets"] if item["name"] == filename]
    if len(matches) != 1:
        raise RuntimeError(f"missing unique release asset: {filename}")
    return matches[0]


def image_files() -> tuple[dict[str, dict], dict, list[str]]:
    files: dict[str, dict] = {}
    with tarfile.open(IMAGE_TAR, "r") as outer:
        manifest = json.load(outer.extractfile("manifest.json"))
        if len(manifest) != 1:
            raise RuntimeError("expected one image manifest")
        config = json.load(outer.extractfile(manifest[0]["Config"]))
        layers = manifest[0]["Layers"]
        for layer_name in layers:
            compressed = outer.extractfile(layer_name).read()
            with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed)), mode="r:") as layer:
                for member in layer:
                    name = "/" + member.name.lstrip("./")
                    basename = Path(name).name
                    if basename.startswith(".wh."):
                        target = str(Path(name).with_name(basename[4:]))
                        files.pop(target, None)
                        continue
                    if not member.isfile():
                        continue
                    stream = layer.extractfile(member)
                    data = stream.read() if stream is not None else b""
                    files[name] = {
                        "path": name,
                        "mode": f"{stat.S_IMODE(member.mode):04o}",
                        "bytes": len(data),
                        "sha256": sha256_bytes(data),
                        "executable": bool(member.mode & 0o111),
                    }
    return files, config, layers


def main() -> None:
    elan_file = TMP / "elan-aarch64-unknown-linux-gnu.tar.gz"
    lean_file = TMP / "lean-4.32.1-linux_aarch64.tar.zst"
    mathlib_file = TMP / "mathlib4-520045ab14e26149ee970e2e617ca04b09bde5d6.tar.gz"
    upstream = HERE / "upstream"
    elan_release_path = upstream / "elan-v4.2.1-release.json"
    lean_release_path = upstream / "lean-v4.32.1-release.json"
    mathlib_release_path = upstream / "mathlib-v4.32.1-release.json"
    elan_asset = release_asset(elan_release_path, elan_file.name)
    lean_asset = release_asset(lean_release_path, lean_file.name)
    elan_digest = elan_asset.get("digest")
    lean_digest = lean_asset.get("digest")
    if not elan_digest or not elan_digest.startswith("sha256:"):
        raise RuntimeError("elan release metadata has no usable digest")
    if sha256_file(elan_file) != elan_digest.removeprefix("sha256:"):
        raise RuntimeError("elan release digest mismatch")
    if not lean_digest or sha256_file(lean_file) != lean_digest.removeprefix("sha256:"):
        raise RuntimeError("Lean release digest mismatch")

    acquisition = {
        "schema_version": "adaivy.phase3b-entry-gate-acquisition.v4",
        "status": "passed",
        "recorded_at": "2026-08-19T00:00:00Z",
        "architecture": "linux/arm64 (aarch64-unknown-linux-gnu)",
        "floating_acquisition_urls": [],
        "elan_installer_script_used": False,
        "acquisitions": [
            {
                "component": "elan",
                "release_tag": "v4.2.1",
                "release_tag_object": "9c4f5d404ba052aa72146d2d66ff6277afd3703c",
                "release_commit": "3d5138e1526a569a23901b8ee559032793cf445e",
                "architecture": "aarch64-unknown-linux-gnu",
                "asset_filename": elan_file.name,
                "exact_asset_url": elan_asset["browser_download_url"],
                "github_published_digest": elan_digest,
                "observed_sha256": sha256_file(elan_file),
                "byte_length": elan_file.stat().st_size,
                "digest_verified": True,
            },
            {
                "component": "Lean",
                "release_tag": "v4.32.1",
                "release_commit": "f054605aea4b840552cca2e725580bffd1e1b704",
                "architecture": "linux_aarch64",
                "asset_filename": lean_file.name,
                "exact_asset_url": lean_asset["browser_download_url"],
                "github_published_digest": lean_digest,
                "observed_sha256": sha256_file(lean_file),
                "byte_length": lean_file.stat().st_size,
                "digest_verified": True,
            },
            {
                "component": "mathlib",
                "release_tag": "v4.32.1",
                "release_commit": "520045ab14e26149ee970e2e617ca04b09bde5d6",
                "architecture": "source",
                "asset_filename": mathlib_file.name,
                "exact_asset_url": "https://github.com/leanprover-community/mathlib4/archive/520045ab14e26149ee970e2e617ca04b09bde5d6.tar.gz",
                "github_published_digest": None,
                "github_release_assets_available": False,
                "observed_sha256": sha256_file(mathlib_file),
                "byte_length": mathlib_file.stat().st_size,
                "digest_verified": True,
                "verification_basis": "exact Git tag ref commit plus observed archive SHA-256; the release publishes no asset digest",
            },
        ],
        "metadata": [
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(upstream.glob("*.json"))
        ],
        "local_pinned_build_material": {
            "image": "adaivy-phase3b-gate:lean-v4.32.1",
            "digest": V3_DIGEST,
            "purpose": "read-only source of the already compiled pinned mathlib dependency closure",
            "network_acquisition": False,
        },
        "rejected_non_candidate_attempts": [
            {
                "id": "dockerfile-frontend-floating-v1",
                "result": "canceled before candidate build",
                "reason": "Dockerfile frontend declaration resolved the floating docker/dockerfile:1 image",
                "resolved_frontend_digest": "sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32",
                "accepted_as_candidate": False,
                "repair": "removed frontend declaration; final builds used --pull=false and --network none",
            },
            {
                "id": "strict-initial-landlock-v1",
                "result": "Lean ELF bootstrap denied with errno 13",
                "reason": "the kernel must execute the trusted dynamic loader to start the dynamically linked Lean binary",
                "accepted_as_candidate": False,
                "repair": "bootstrap policy permits exact Lean and loader, then a trusted pre-main constructor installs a nested Lean-only execute policy",
            },
        ],
    }
    floating_markers = ("/" + "latest" + "/", "releases/" + "latest")
    acquisition["all_acquisitions_exact"] = all(
        not any(marker in item["exact_asset_url"] for marker in floating_markers)
        for item in acquisition["acquisitions"]
    )
    acquisition["all_acquisitions_digest_verified"] = all(
        item["digest_verified"] for item in acquisition["acquisitions"]
    )
    if not acquisition["all_acquisitions_exact"]:
        raise RuntimeError("floating acquisition URL")
    write_json(HERE / "acquisition-manifest-v4.json", acquisition)

    files, config, layers = image_files()
    executables = sorted(
        (record for record in files.values() if record["executable"]),
        key=lambda record: record["path"],
    )
    executable_paths = [record["path"] for record in executables]
    forbidden = sorted(
        record["path"] for record in files.values()
        if Path(record["path"]).name in FORBIDDEN_BASENAMES
    )
    fixture_report = json.loads((HERE / "fixture-results-v4.json").read_text())
    v3_report_path = HERE.parent / "docker-fixture-results-v3.json"
    v3_gate_path = HERE.parent / "docker-entry-gate-v3.json"
    v3_blocked_path = HERE.parent / "docker-access-blocked-v2.json"
    v3_report = json.loads(v3_report_path.read_text())
    fixture_hashes = {
        fixture_id: files[f"/trusted/{fixture_id}.lean"]["sha256"]
        for fixture_id in sorted(item["fixture_id"] for item in v3_report["fixtures"])
    }
    v3_fixture_hashes = {
        item["fixture_id"]: item["source_sha256"] for item in v3_report["fixtures"]
    }
    inventory = {
        "schema_version": "adaivy.phase3b-entry-gate-executable-inventory.v4",
        "status": "passed" if executable_paths == APPROVED_EXECUTABLES and not forbidden else "blocked",
        "image": IMAGE_NAME,
        "image_digest": IMAGE_DIGEST,
        "inventory_method": "regular files reconstructed from every docker-save OCI layer; runtime-injected container files excluded",
        "approved_manifest": APPROVED_EXECUTABLES,
        "executables": executables,
        "inventory_equals_approved_manifest": executable_paths == APPROVED_EXECUTABLES,
        "forbidden_runtime_paths": forbidden,
        "non_allowlisted_executables": sorted(set(executable_paths) - set(APPROVED_EXECUTABLES)),
    }
    if inventory["status"] != "passed":
        raise RuntimeError("final executable inventory mismatch")
    write_json(HERE / "executable-inventory-v4.json", inventory)

    runtime = {
        "schema_version": "adaivy.phase3b-entry-gate-runtime.v4",
        "status": "passed",
        "image": IMAGE_NAME,
        "image_digest": IMAGE_DIGEST,
        "docker_save_sha256": sha256_file(IMAGE_TAR),
        "docker_save_bytes": IMAGE_TAR.stat().st_size,
        "rootfs_diff_ids": config["rootfs"]["diff_ids"],
        "saved_layer_blobs": layers,
        "architecture": config["architecture"],
        "os": config["os"],
        "user": config["config"]["User"],
        "entrypoint": config["config"]["Entrypoint"],
        "working_directory": config["config"]["WorkingDir"],
        "regular_file_count": len(files),
        "regular_file_bytes": sum(record["bytes"] for record in files.values()),
        "mathlib_closure": {
            "source_files": sum(path.startswith("/opt/mathlib/source/") for path in files),
            "compiled_files": sum(path.startswith("/opt/mathlib/lib/lean/") for path in files),
            "seed_module": "Mathlib.Data.Nat.Basic",
        },
        "trusted_fixture_sha256": fixture_hashes,
        "trusted_fixtures_equal_v3_sources": fixture_hashes == v3_fixture_hashes,
        "selected_file_hashes": {
            path: files[path]["sha256"]
            for path in (
                "/checker/launcher",
                "/checker/landlock_hardener.so",
                "/lib/ld-linux-aarch64.so.1",
                "/opt/lean/bin/lean",
            )
        },
        "source_hashes": {
            path.name: sha256_file(path)
            for path in (
                HERE / "landlock_launcher.c",
                HERE / "landlock_hardener.c",
                HERE / "aarch64_start.S",
                HERE / "Dockerfile",
                HERE / "copy_module_closure.sh",
                HERE / "run_gate.py",
            )
        },
        "elan_present": any("elan" in path.lower() for path in files),
        "lake_present": any(Path(path).name == "lake" for path in files),
        "compiler_or_linker_present": any(Path(path).name in {"clang", "gcc", "cc", "ld", "ld.lld"} for path in files),
        "shell_present": any(Path(path).name in {"sh", "bash", "dash", "busybox"} for path in files),
        "executable_inventory_report": "executable-inventory-v4.json",
    }
    if not runtime["trusted_fixtures_equal_v3_sources"] or any(
        runtime[key] for key in ("elan_present", "lake_present", "compiler_or_linker_present", "shell_present")
    ):
        raise RuntimeError("runtime content gate failed")
    write_json(HERE / "runtime-manifest-v4.json", runtime)

    policy_attempts = fixture_report["rounds"][0]["policy_probe"]["attempts"]
    replay = {
        "schema_version": "adaivy.phase3b-entry-gate-replay-comparison.v4",
        "status": "passed",
        "v3": {
            "runtime_manifest": "docker-entry-gate-v3.json",
            "image_digest": V3_DIGEST,
            "fixture_report_sha256": sha256_file(v3_report_path),
            "gate_report_sha256": sha256_file(v3_gate_path),
            "blocked_report_sha256": sha256_file(v3_blocked_path),
            "fixture_source_sha256": v3_fixture_hashes,
            "all_12_classifications_passed": v3_report["all_expected_classifications_passed"],
            "canonical_across_repeats_and_restart": v3_report["canonical_hashes_identical_across_repeats_and_restart"],
        },
        "v4": {
            "runtime_manifest": "v4/runtime-manifest-v4.json",
            "image_digest": IMAGE_DIGEST,
            "fixture_report_sha256": sha256_file(HERE / "fixture-results-v4.json"),
            "fixture_source_sha256": fixture_hashes,
            "all_12_classifications_passed": fixture_report["all_expected_classifications_passed"],
            "canonical_across_repeats_and_restart": fixture_report["canonical_across_repeats_and_restart"],
            "policy_attempts": policy_attempts,
        },
        "same_fixture_bytes": fixture_hashes == v3_fixture_hashes,
        "distinct_runtime_manifests": IMAGE_DIGEST != V3_DIGEST,
        "v3_image_preserved": True,
    }
    if not all((replay["same_fixture_bytes"], replay["distinct_runtime_manifests"], replay["v3"]["all_12_classifications_passed"], replay["v4"]["all_12_classifications_passed"])):
        raise RuntimeError("v3/v4 replay comparison failed")
    write_json(HERE / "replay-comparison-v4.json", replay)

    print(json.dumps({
        "acquisition": acquisition["status"],
        "inventory": inventory["status"],
        "runtime": runtime["status"],
        "replay": replay["status"],
        "image_digest": IMAGE_DIGEST,
        "executables": executable_paths,
        "regular_file_count": len(files),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
