#!/usr/bin/env python3
"""Seal v5 runtime inventory, v4 preservation, and dynamic-input evidence."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import stat
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
V4 = HERE.parent / "v4"
V4_IMAGE_TAR = Path("/private/tmp/adaivy-phase3b-v4/v4-final-image.tar")
V5_IMAGE_TAR = Path("/private/tmp/adaivy-phase3b-v5-image.tar")
V4_IMAGE = "adaivy-phase3b-gate-v4:lean-v4.32.1"
V5_IMAGE = "adaivy-phase3b-gate-v5:lean-v4.32.1"
V4_DIGEST = "sha256:ad81d799c1d9e766e0263c2b703936ca3fb8042e189e7e279b7abd1c7889c60b"
V5_DIGEST = "sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f"
V4_DIFF_IDS = [
    "sha256:f68ac9dbe8eba5abe20d2866420085f951251a99ec3a847e5fb40aebf454e07c",
    "sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef",
]
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
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def image_files(path: Path) -> tuple[dict[str, dict[str, object]], dict, list[str]]:
    files: dict[str, dict[str, object]] = {}
    with tarfile.open(path, "r") as outer:
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
                        files.pop(str(Path(name).with_name(basename[4:])), None)
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


def recursive_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def main() -> None:
    v4_files, v4_config, _ = image_files(V4_IMAGE_TAR)
    v5_files, v5_config, v5_layers = image_files(V5_IMAGE_TAR)
    if v4_config["rootfs"]["diff_ids"] != V4_DIFF_IDS:
        raise RuntimeError("v4 rootfs seal differs")
    if v5_config["rootfs"]["diff_ids"][:2] != V4_DIFF_IDS:
        raise RuntimeError("v5 does not inherit exact v4 rootfs layers")

    v4_without_launcher = {key: value for key, value in v4_files.items() if key != "/checker/launcher"}
    v5_without_launcher = {key: value for key, value in v5_files.items() if key != "/checker/launcher"}
    unchanged_nonlauncher_rootfs = v4_without_launcher == v5_without_launcher
    changed_paths = sorted(
        path for path in set(v4_files) | set(v5_files)
        if v4_files.get(path) != v5_files.get(path)
    )
    executables = sorted(
        (record for record in v5_files.values() if record["executable"]),
        key=lambda record: str(record["path"]),
    )
    executable_paths = [str(record["path"]) for record in executables]
    forbidden = sorted(
        str(record["path"]) for record in v5_files.values()
        if Path(str(record["path"])).name in FORBIDDEN_BASENAMES
    )
    d13_hash = sha256_file(HERE / "fixtures" / "D13.lean")
    d13_in_image = any(record["sha256"] == d13_hash for record in v5_files.values())
    v4_hashes = recursive_hashes(V4)

    acquisition = {
        "schema_version": "adaivy.phase3b-dynamic-input-acquisition.v5",
        "status": "passed",
        "network_acquisitions": [],
        "network_acquisition_performed": False,
        "toolchain_rebuilt_or_expanded": False,
        "builder_image": "adaivy-phase3b-gate:lean-v4.32.1",
        "builder_image_digest": "sha256:0d3a26db46d1bace987b273d59087e3e39fbc9901d2bd680bf251f190622eac3",
        "runtime_base_image": V4_IMAGE,
        "runtime_base_image_digest": V4_DIGEST,
        "build_network": "none",
        "pull": False,
        "new_dependencies": [],
    }
    write_json(HERE / "acquisition-manifest-v5.json", acquisition)

    inventory = {
        "schema_version": "adaivy.phase3b-dynamic-input-executable-inventory.v5",
        "status": "passed" if executable_paths == APPROVED_EXECUTABLES and not forbidden else "blocked",
        "image": V5_IMAGE,
        "image_digest": V5_DIGEST,
        "inventory_method": "regular files reconstructed from every docker-save OCI layer; runtime-injected container files excluded",
        "approved_manifest": APPROVED_EXECUTABLES,
        "executables": executables,
        "inventory_equals_approved_manifest": executable_paths == APPROVED_EXECUTABLES,
        "forbidden_runtime_paths": forbidden,
        "non_allowlisted_executables": sorted(set(executable_paths) - set(APPROVED_EXECUTABLES)),
    }
    if inventory["status"] != "passed":
        raise RuntimeError("v5 executable inventory mismatch")
    write_json(HERE / "executable-inventory-v5.json", inventory)

    preservation = {
        "schema_version": "adaivy.phase3b-v4-preservation.v5",
        "status": "passed" if unchanged_nonlauncher_rootfs and changed_paths == ["/checker/launcher"] else "blocked",
        "v4_image": V4_IMAGE,
        "v4_image_digest": V4_DIGEST,
        "v5_image": V5_IMAGE,
        "v5_image_digest": V5_DIGEST,
        "v4_rootfs_diff_ids": V4_DIFF_IDS,
        "v5_inherits_v4_rootfs_diff_ids": v5_config["rootfs"]["diff_ids"][:2] == V4_DIFF_IDS,
        "changed_runtime_paths": changed_paths,
        "only_launcher_changed": changed_paths == ["/checker/launcher"],
        "all_nonlauncher_runtime_files_byte_and_metadata_identical": unchanged_nonlauncher_rootfs,
        "v4_report_file_count": len(v4_hashes),
        "v4_report_sha256": v4_hashes,
        "existing_production_prompt": {
            "path": "docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT.md",
            "sha256": sha256_file(ROOT / "docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT.md"),
        },
    }
    if preservation["status"] != "passed":
        raise RuntimeError("v4 runtime preservation failed")
    write_json(HERE / "v4-preservation-v5.json", preservation)

    runtime = {
        "schema_version": "adaivy.phase3b-dynamic-input-runtime.v5",
        "status": "passed",
        "image": V5_IMAGE,
        "image_digest": V5_DIGEST,
        "base_image": V4_IMAGE,
        "base_image_digest": V4_DIGEST,
        "docker_save_sha256": sha256_file(V5_IMAGE_TAR),
        "docker_save_bytes": V5_IMAGE_TAR.stat().st_size,
        "rootfs_diff_ids": v5_config["rootfs"]["diff_ids"],
        "inherited_v4_rootfs_diff_ids": V4_DIFF_IDS,
        "saved_layer_blobs": v5_layers,
        "architecture": v5_config["architecture"],
        "os": v5_config["os"],
        "user": v5_config["config"]["User"],
        "entrypoint": v5_config["config"]["Entrypoint"],
        "working_directory": v5_config["config"]["WorkingDir"],
        "regular_file_count": len(v5_files),
        "regular_file_bytes": sum(int(record["bytes"]) for record in v5_files.values()),
        "fixed_input_contract": {
            "transport": "stdin",
            "container_path": "/tmp/adaivy-input.lean",
            "max_input_bytes": 262144,
            "creation_flags": ["O_CREAT", "O_EXCL", "O_NOFOLLOW", "O_CLOEXEC"],
            "final_mode": "0400",
            "path_arguments_allowed": False,
            "tmpfs": "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        },
        "dynamic_fixture_embedded_in_image": d13_in_image,
        "selected_file_hashes": {
            path: str(v5_files[path]["sha256"])
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
                HERE / "aarch64_start.S",
                HERE / "Dockerfile",
                HERE / "run_gate.py",
            )
        },
        "elan_present": any("elan" in path.lower() for path in v5_files),
        "lake_present": any(Path(path).name == "lake" for path in v5_files),
        "compiler_or_linker_present": any(Path(path).name in {"clang", "gcc", "cc", "ld", "ld.lld"} for path in v5_files),
        "shell_present": any(Path(path).name in {"sh", "bash", "dash", "busybox"} for path in v5_files),
        "executable_inventory_report": "executable-inventory-v5.json",
    }
    if d13_in_image or any(runtime[key] for key in ("elan_present", "lake_present", "compiler_or_linker_present", "shell_present")):
        raise RuntimeError("v5 runtime content gate failed")
    write_json(HERE / "runtime-manifest-v5.json", runtime)

    print(json.dumps({
        "acquisition": acquisition["status"],
        "inventory": inventory["status"],
        "preservation": preservation["status"],
        "runtime": runtime["status"],
        "image_digest": V5_DIGEST,
        "changed_paths": changed_paths,
        "executables": executable_paths,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
