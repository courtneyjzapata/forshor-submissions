import TableGeneration.Policy

namespace TableGeneration.Submission.Policy

open Operations

/-!
Low-width `PhaseProduct` `k = 6` table for the recursive gate-count planner.

Every layer is built from the identity and exactly undone, and the planner's
width scan never shrinks on an addition, so the layer order, the registers each
layer accumulates in, and pre-shifts later removed by `shiftR` were chosen by
search to keep the running width maximum low. The points mix integer and
reciprocal powers of two (`±1/8` is cheap here because its large shifts are
taken back off by `shiftR`). It uses the minimal five layers.

At 2048 bits the child width is 363 against 369 for the table the published
plan uses at this arity, which lowers the planner's total from 4,343,539 to
4,331,707 gates. It does not beat the per-target champion's weighted cost.
-/

/-- `PhaseProduct` `k = 6`: 84 arithmetic ops, 5 layers, weighted 109. -/
def pointsPP6 : List Point :=
  [.int 0, .frac 0, .int 1, .int (-1), .frac 8, .frac (-8), .int 4, .frac 2, .frac (-2), .int 2, .int (-2)]

def programPP6 : Prog 6 :=
  [.addScaled 2 0 false 0,
   .addScaled 2 4 false 0,
   .addScaled 3 1 false 0,
   .addScaled 3 5 false 0,
   .addScaled 3 2 false 0,
   .shiftL 2 1,
   .addScaled 2 3 true 0,
   .phaseProduct 0,
   .phaseProduct 5,
   .phaseProduct 3,
   .phaseProduct 2,
   .addScaled 2 3 false 0,
   .shiftR 2 1,
   .addScaled 3 2 true 0,
   .addScaled 3 5 true 0,
   .addScaled 3 1 true 0,
   .addScaled 2 4 true 0,
   .addScaled 2 0 true 0,
   .shiftL 1 12,
   .addScaled 1 5 false 0,
   .addScaled 1 3 false 6,
   .shiftL 0 13,
   .addScaled 0 4 false 1,
   .addScaled 0 2 false 7,
   .shiftL 0 2,
   .addScaled 0 1 false 0,
   .shiftL 1 1,
   .addScaled 1 0 true 0,
   .phaseProduct 0,
   .phaseProduct 1,
   .addScaled 1 0 false 0,
   .shiftR 1 1,
   .addScaled 0 1 true 0,
   .shiftR 0 2,
   .addScaled 0 2 true 7,
   .addScaled 0 4 true 1,
   .shiftR 0 13,
   .addScaled 1 3 true 6,
   .addScaled 1 5 true 0,
   .shiftR 1 12,
   .shiftL 4 8,
   .addScaled 4 0 false 0,
   .addScaled 4 1 false 2,
   .addScaled 4 2 false 4,
   .addScaled 4 5 false 10,
   .addScaled 4 3 false 6,
   .phaseProduct 4,
   .addScaled 4 3 true 6,
   .addScaled 4 5 true 10,
   .addScaled 4 2 true 4,
   .addScaled 4 1 true 2,
   .addScaled 4 0 true 0,
   .shiftR 4 8,
   .shiftL 1 4,
   .addScaled 1 5 false 0,
   .addScaled 1 3 false 2,
   .shiftL 0 4,
   .addScaled 0 2 false 2,
   .addScaled 0 4 false 0,
   .shiftL 0 1,
   .addScaled 0 1 false 0,
   .shiftL 1 1,
   .addScaled 1 0 true 0,
   .phaseProduct 0,
   .phaseProduct 1,
   .addScaled 1 0 false 0,
   .shiftR 1 1,
   .addScaled 0 1 true 0,
   .shiftR 0 1,
   .addScaled 0 4 true 0,
   .addScaled 0 2 true 2,
   .shiftR 0 4,
   .addScaled 1 3 true 2,
   .addScaled 1 5 true 0,
   .shiftR 1 4,
   .addScaled 0 2 false 2,
   .addScaled 0 4 false 4,
   .shiftL 5 4,
   .addScaled 5 3 false 2,
   .addScaled 5 1 false 0,
   .shiftL 5 1,
   .addScaled 5 0 false 0,
   .shiftL 0 1,
   .addScaled 0 5 true 0,
   .phaseProduct 5,
   .phaseProduct 0,
   .addScaled 0 5 false 0,
   .shiftR 0 1,
   .addScaled 5 0 true 0,
   .shiftR 5 1,
   .addScaled 5 1 true 0,
   .addScaled 5 3 true 2,
   .shiftR 5 4,
   .addScaled 0 4 true 4,
   .addScaled 0 2 true 2]

def handles (mode : ProductMode) (k : Nat) : Bool :=
  match mode with
  | .PhaseProduct => decide (k = 6)
  | .PhaseTripleProduct => false

def generatedPoints (mode : ProductMode) (k : Nat) : List Point :=
  match mode with
  | .PhaseProduct => if k = 6 then pointsPP6 else canonicalPoints mode k
  | .PhaseTripleProduct => canonicalPoints mode k

def generatePointsInOrder (mode : ProductMode) (k : Nat) (_hk : k >= 2) : List Point :=
  generatedPoints mode k

def generate (mode : ProductMode) (k : Nat) (hk : k >= 2) : Prog k :=
  match mode with
  | .PhaseProduct => if h : k = 6 then h.symm ▸ programPP6 else baselineGenerate mode k hk
  | .PhaseTripleProduct => baselineGenerate mode k hk

theorem generatedPoints_valid (mode : ProductMode) (k : Nat) (_hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointList mode k (generatedPoints mode k) := by
  cases mode with
  | PhaseProduct =>
    have hk' : k = 6 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · unfold ValidPointList; decide
  | PhaseTripleProduct => simp [handles] at hhandles

set_option maxHeartbeats 100000000 in
set_option maxRecDepth 100000 in
theorem generate_safe (mode : ProductMode) (k : Nat) (hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointOrder (generatedPoints mode k) (generatePointsInOrder mode k hk) ∧
      ProgConsumesPtsSafe (positive_of_ge_two hk) State.start_state
        (generate mode k hk) (generatePointsInOrder mode k hk) := by
  cases mode with
  | PhaseProduct =>
    have hk' : k = 6 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · obtain rfl : hk = (by decide) := Subsingleton.elim _ _
      exact ⟨List.Perm.refl _, progConsumesPtsSafe_of_checks (by decide) (by decide) (by decide)⟩
  | PhaseTripleProduct => simp [handles] at hhandles

def implementation : TableGeneration.GeneratorPolicy where
  generatedPoints := generatedPoints
  handles := handles
  generatePointsInOrder := generatePointsInOrder
  generate := generate
  generatedPoints_valid := generatedPoints_valid
  generate_safe := generate_safe

end TableGeneration.Submission.Policy
