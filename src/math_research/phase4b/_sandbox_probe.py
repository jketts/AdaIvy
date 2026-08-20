"""Standalone adversarial probe for the named Darwin parser sandbox.

This file is executed with ``-I -S`` and deliberately imports no AdaIvy code.
It is not a parser and never handles source content.
"""

from __future__ import annotations

import json
import os
import sys


def _attempt(action: str, target: str | None) -> dict[str, object]:
    try:
        if action == "baseline":
            return {"action": action, "allowed": True, "environment": sorted(os.environ)}
        if action == "network":
            import socket

            descriptor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                descriptor.sendto(b"probe", ("127.0.0.1", 9))
            finally:
                descriptor.close()
        elif action == "write":
            assert target is not None
            with open(target, "wb") as output:
                output.write(b"forbidden")
        elif action == "read":
            assert target is not None
            with open(target, "rb") as source:
                source.read(1)
        elif action == "process":
            import subprocess

            subprocess.run((sys.executable, "-I", "-S", "-c", "pass"), check=False)
        else:
            raise ValueError("unknown probe action")
    except BaseException as error:
        return {
            "action": action,
            "allowed": False,
            "error_type": type(error).__name__,
        }
    return {"action": action, "allowed": True}


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    request = json.loads(sys.argv[1])
    if not isinstance(request, dict) or set(request) != {"action", "target"}:
        return 2
    result = _attempt(request["action"], request["target"])
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
