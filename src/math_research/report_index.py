"""Index a locally run report directory: hash every file, name the readable ones.

A directory of JSON and Markdown is not a report until a reader can tell what is
in it, which file to open first, and whether the bytes are the ones that were
produced. This writes both forms of that: ``index.json`` for a machine and
``INDEX.md`` for a person.

Two properties are deliberate.

**The index is a pure function of its inputs.** ``recorded_at`` is an argument,
never a clock read, exactly as the frozen instants in the Makefile are inputs.
Re-indexing the same directory at the same instant produces the same bytes, so a
changed index means changed contents.

**It hashes rather than summarises.** The index makes no claim about what a
report says. Restating a finding here would create a second, unbacked copy of it,
and the report's own provenance already carries the claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0.0"
INDEX_FILES = ("index.json", "INDEX.md")
MAX_FILES = 4096

#: Files a person should open first, and why. Anything not named here is still
#: indexed; it just does not get a pointer.
READABLE = {
    "paper.tex": "the rendered document (ADR-0036 projection; PDF is a separate gate)",
    "paper.pdf": "the typeset document, if the pinned toolchain has run",
    "confirmatory-report.md": "the Phase 6 confirmatory evaluation",
    "traceable-report.md": "an ID-traceable trust report",
    "report.md": "a rendered phase report",
    "release.json": "the Phase 6 release package",
    "MANIFEST.json": "a self-describing bundle manifest with per-file hashes",
    "INDEX.md": "this index",
}

_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ReportIndexError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _indexable(root: Path) -> list[Path]:
    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.name not in INDEX_FILES
        and "__pycache__" not in path.parts
        and not path.name.startswith(".")
    ]
    if not files:
        raise ReportIndexError(f"{root} holds no indexable file")
    if len(files) > MAX_FILES:
        raise ReportIndexError(f"{root} holds {len(files)} files, over the {MAX_FILES} bound")
    return files


def build_index(root: Path, recorded_at: str) -> dict[str, Any]:
    if not root.is_dir():
        raise ReportIndexError(f"{root} is not a directory")
    if not _INSTANT.match(recorded_at):
        raise ReportIndexError(f"recorded_at={recorded_at!r} must be YYYY-MM-DDTHH:MM:SSZ")
    files = _indexable(root)
    entries = [
        {
            "path": str(path.relative_to(root)),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    groups: dict[str, int] = {}
    for entry in entries:
        parts = Path(str(entry["path"])).parts
        groups[parts[0] if len(parts) > 1 else "."] = groups.get(
            parts[0] if len(parts) > 1 else ".", 0
        ) + 1
    highlights = [
        {"path": str(entry["path"]), "note": READABLE[Path(str(entry["path"])).name]}
        for entry in entries
        if Path(str(entry["path"])).name in READABLE
    ]
    index = {
        "schema_version": SCHEMA_VERSION,
        "report_root": root.name,
        "recorded_at": recorded_at,
        "file_count": len(entries),
        "total_bytes": sum(int(entry["bytes"]) for entry in entries),
        "groups": dict(sorted(groups.items())),
        "highlights": highlights,
        "files": entries,
        "committed": False,
        "note": (
            "A locally run report. reports/local/ is gitignored: this directory is not "
            "recorded evidence, and re-running the commands that produced it reproduces "
            "it, because every input is a frozen fixture at a frozen instant."
        ),
    }
    index["index_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {key: value for key, value in index.items() if key != "index_hash"},
            ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return index


def render_index(index: dict[str, Any]) -> str:
    lines = [
        f"# Report `{index['report_root']}`",
        "",
        f"- Recorded at `{index['recorded_at']}`",
        f"- Files `{index['file_count']}`, total `{index['total_bytes']}` bytes",
        f"- Index hash `{index['index_hash']}`",
        "- Committed: `false`. This is a local run under `reports/local/`, which is",
        "  gitignored. Recorded evidence lives elsewhere under `reports/` and is",
        "  committed deliberately.",
        "",
        "## Open these first",
        "",
    ]
    if index["highlights"]:
        for item in index["highlights"]:
            lines.append(f"- [`{item['path']}`]({item['path']}) -- {item['note']}")
    else:
        lines.append("- No file in this report is a recognised readable report.")
    lines.extend(["", "## Contents by group", "", "| Group | Files |", "|---|---|"])
    for group, count in index["groups"].items():
        lines.append(f"| `{group}` | {count} |")
    lines.extend([
        "",
        "## Every file",
        "",
        "Hashes, not summaries. This index makes no claim about what any report says;",
        "each report carries its own provenance and evidence class.",
        "",
        "| Path | Bytes | sha256 |",
        "|---|---|---|",
    ])
    for entry in index["files"]:
        lines.append(f"| `{entry['path']}` | {entry['bytes']} | `{entry['sha256']}` |")
    lines.append("")
    return "\n".join(lines)


def write_index(root: Path, recorded_at: str) -> dict[str, Any]:
    index = build_index(root, recorded_at)
    (root / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "INDEX.md").write_text(render_index(index), encoding="utf-8")
    return index


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index a locally run report directory")
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--recorded-at", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        index = write_index(args.report_dir, args.recorded_at)
    except ReportIndexError as error:
        print(json.dumps({"refused": True, "detail": str(error)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps({
        "report_root": index["report_root"],
        "recorded_at": index["recorded_at"],
        "file_count": index["file_count"],
        "total_bytes": index["total_bytes"],
        "index_hash": index["index_hash"],
        "highlights": [item["path"] for item in index["highlights"]],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
