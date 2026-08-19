def Even (n : Int) : Prop := ∃ k, n = 2 * k

theorem even_sum {a b : Int} (ha : Even a) (hb : Even b) : Even (a + b) := by
  rcases ha with ⟨k, rfl⟩
  rcases hb with ⟨l, rfl⟩
  exact ⟨k + l, (Int.mul_add 2 k l).symm⟩
