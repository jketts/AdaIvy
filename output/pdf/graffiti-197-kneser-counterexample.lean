import Mathlib.Data.Nat.Basic
set_option autoImplicit false
namespace AdaIvyPhase3B
theorem AdaIvyGraffiti197ArithmeticCertificate : (7 * 6 / 2 : Nat) = 21 ∧ (5 * 4 / 2 : Nat) = 10 ∧ (3 * 2 / 2 : Nat) = 3 ∧ (4 * 3 / 2 : Nat) = 6 ∧ (5 * ((10 : Int) + 21 - 1) = 2 * 75) ∧ (5 * ((1 : Int) - 1) = 2 * 0) ∧ (5 * ((-4 : Int) - 1) = -25) ∧ ¬ ((4 : Nat) ≤ 3) := by decide
#print axioms AdaIvyPhase3B.AdaIvyGraffiti197ArithmeticCertificate
end AdaIvyPhase3B
