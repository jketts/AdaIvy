#!/usr/bin/env python3
"""Scan persisted v5 gate/project evidence without printing credential values."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name("credential-scan-v5.json")
TOKEN_PATTERNS = (
    re.compile(rb"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"Bearer[ \t]+[A-Za-z0-9._-]{24,}"),
)


def allowed_credential() -> bytes | None:
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return None
    for raw_line in env_file.read_bytes().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(b"#") or b"=" not in line:
            continue
        key, value = line.split(b"=", 1)
        if key.strip() == b"OPENAI_API_KEY":
            value = value.strip().strip(b"'\"")
            return value or None
    return None


def main() -> int:
    files = sorted(path for path in (ROOT / "reports").rglob("*") if path.is_file())
    credential = allowed_credential()
    exact_matches = []
    token_matches = []
    for path in files:
        data = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        if credential and credential in data:
            exact_matches.append(relative)
        if any(pattern.search(data) for pattern in TOKEN_PATTERNS):
            token_matches.append(relative)
    report = {
        "schema_version": "adaivy.credential-scan.v5",
        "status": "passed" if not exact_matches and not token_matches else "blocked",
        "allowed_local_credential_present": credential is not None,
        "allowed_credential_source": ".env" if credential is not None else None,
        "persisted_scope": "reports/**",
        "persisted_files_scanned": len(files),
        "exact_credential_match_count": len(exact_matches),
        "exact_credential_match_files": exact_matches,
        "token_pattern_match_count": len(token_matches),
        "token_pattern_match_files": token_matches,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
