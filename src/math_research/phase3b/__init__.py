"""Bounded Phase 3B Lean formal-checking vertical slice."""

SCHEMA_VERSION = "1.0.0"
HASH_PROFILE = "phase3b-semantic-v1"
POLICY_VERSION = "phase3b-lean-restricted-v1"
RUNTIME_IMAGE = "adaivy-phase3b-gate-v5:lean-v4.32.1"
RUNTIME_DIGEST = "sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f"
RUNTIME_REFERENCE = f"{RUNTIME_IMAGE}@{RUNTIME_DIGEST}"
FIXED_INPUT_PATH = "/tmp/adaivy-input.lean"
MAX_STDIN_BYTES = 262_144
APPROVED_STANDARD_AXIOMS = ("Classical.choice", "Quot.sound", "propext")
