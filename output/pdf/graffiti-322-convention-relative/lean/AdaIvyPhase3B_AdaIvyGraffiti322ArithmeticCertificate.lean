import Mathlib.Data.Nat.Basic
set_option autoImplicit false
namespace AdaIvyPhase3B
theorem AdaIvyGraffiti322ArithmeticCertificate : (14 * 14 + 14 * 18 : Nat) = 448 ∧ (3 * 14 * 13 / 2 + 14 * 18 : Nat) = 525 ∧ (1 + 13 * 13 + 13 * 18 : Nat) = 404 ∧ (3 * 14 - 4 + 18 : Nat) = 56 ∧ (2 * 14 - 2 + 18 : Nat) = 44 ∧ (3 + 4 * 13 + (14 * 14 - 3 * 14 + 1) + 14 * 17 : Nat) = 448 ∧ (9 * 4444 : Nat) = 39996 ∧ (40049 - 39996 : Nat) = 53 ∧ ¬ ((40049 : Nat) ≤ 9 * 4444) := by decide
#print axioms AdaIvyPhase3B.AdaIvyGraffiti322ArithmeticCertificate
end AdaIvyPhase3B
