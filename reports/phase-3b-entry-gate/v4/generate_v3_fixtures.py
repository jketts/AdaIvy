#!/usr/bin/env python3
"""Materialize the exact fixture bytes used by the preserved v3 replay."""

from pathlib import Path


DIRECTORY = Path(__file__).with_name("fixtures")
FIXTURES = {
    "F01": """import Mathlib.Data.Nat.Basic
set_option autoImplicit false
theorem AdaIvyGateF01 (n : Nat) : n = n := by rfl
#print axioms AdaIvyGateF01
""",
    "F02": """set_option autoImplicit false
theorem AdaIvyGateF02 (n : Nat) : n = n := by sorry
#print axioms AdaIvyGateF02
""",
    "F03": """set_option autoImplicit false
theorem AdaIvyGateF03 (n : Nat) : n = n := by admit
#print axioms AdaIvyGateF03
""",
    "F04": """set_option autoImplicit false
theorem AdaIvyGateF04 : False := by exact True.intro
#print axioms AdaIvyGateF04
""",
    "F05": """set_option autoImplicit false
theorem AdaIvyGateF05 (n : Nat : n = n := by rfl
""",
    "F06": """import AdaIvyUnknownPackage
theorem AdaIvyGateF06 : True := by trivial
""",
    "F07": """set_option autoImplicit false
axiom AdaIvyGateAssumption : False
theorem AdaIvyGateF07 : False := AdaIvyGateAssumption
#print axioms AdaIvyGateF07
""",
    "F08": """set_option autoImplicit false
theorem AdaIvyGateF08 (p : Prop) : p ∨ ¬p := Classical.em p
#print axioms AdaIvyGateF08
""",
    "F09": """set_option autoImplicit false
set_option maxHeartbeats 1 in
theorem AdaIvyGateF09 : (1 : Nat) = 1 := by decide
""",
    "F10": """#eval IO.FS.readFile "/workspace/README.md"
""",
    "F11": """#eval IO.Process.run { cmd := "/bin/sh", args := #["-c", "wget https://example.invalid/"] }
""",
    "F12": "#check AdaIvy" + ("X" * 70000) + "\n",
}


def main() -> None:
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for fixture_id, source in FIXTURES.items():
        (DIRECTORY / f"{fixture_id}.lean").write_text(
            source, encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
