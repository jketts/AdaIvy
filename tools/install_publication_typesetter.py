#!/usr/bin/env python3
"""Install the hash-pinned BasicTeX publication toolchain under work/.

The script deliberately does not run a system installer. It asks Homebrew for
the cached cask artifact (fetching only during this explicit setup command),
verifies the package bytes, expands the package into a temporary directory,
and copies the TeX Live tree into the gitignored local toolchain directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path("config/publication-typeset-dependency-v1.json"),
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if platform.system() != "Darwin":
        raise SystemExit("this dependency descriptor is for darwin-universal")

    destination = Path(config["install_root"])
    engine = destination / config["engine_relative_path"]
    receipt = destination / "adaivy-install.json"
    if engine.is_file() and receipt.is_file():
        installed = json.loads(receipt.read_text(encoding="utf-8"))
        if installed.get("artifact_sha256") == config["artifact_sha256"]:
            print(engine)
            return 0
        raise SystemExit(f"existing toolchain receipt does not match {args.config}")
    if destination.exists():
        raise SystemExit(f"refusing nonempty or partial destination: {destination}")

    brew = shutil.which("brew")
    pkgutil = shutil.which("pkgutil")
    if brew is None or pkgutil is None:
        raise SystemExit("setup requires Homebrew and macOS pkgutil")
    artifact_text = _run([brew, "--cache", "--cask", str(config["homebrew_cask"])])
    artifact = Path(artifact_text)
    if not artifact.is_file():
        _run([brew, "fetch", "--cask", str(config["homebrew_cask"])])
        artifact = Path(_run([brew, "--cache", "--cask", str(config["homebrew_cask"])]))
    observed = _sha256(artifact)
    if observed != config["artifact_sha256"]:
        raise SystemExit(f"artifact hash mismatch: expected {config['artifact_sha256']}, got {observed}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adaivy-basictex-") as temporary:
        expanded = Path(temporary) / "package"
        subprocess.run([pkgutil, "--expand-full", str(artifact), str(expanded)], check=True)
        suffix = Path(config["extracted_distribution_path"])
        candidates = [path for path in expanded.rglob(suffix.name) if path.as_posix().endswith(suffix.as_posix())]
        if len(candidates) != 1:
            raise SystemExit(f"expected one extracted TeX Live root, found {len(candidates)}")
        shutil.copytree(candidates[0], destination, symlinks=True)
    if not engine.is_file():
        raise SystemExit(f"verified artifact did not contain {config['engine_relative_path']}")
    receipt.write_text(
        json.dumps({
            "dependency_id": config["dependency_id"],
            "version": config["version"],
            "artifact_sha256": observed,
            "engine_relative_path": config["engine_relative_path"],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
