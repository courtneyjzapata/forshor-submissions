import TableGeneration.Policy

namespace TableGeneration.Submission.Policy

open Operations

/-!
Hand-derived optimal `k = 2` tables for both product modes.

Two registers start as the rows of `0` and `inf`, so the first layer is free.
A second layer needs every other row built and restored, so `2` arithmetic ops
(`PhaseProduct`) and `4` (`PhaseTripleProduct`) are lower bounds that these
programs meet.
-/

/-- `PhaseProduct` `k = 2`: 2 arithmetic ops, 2 layers, weighted 12. -/
def pointsPP2 : List Point :=
  [.int 0, .frac 0, .int 1]

def programPP2 : Prog 2 :=
  [.phaseProduct 0,
   .phaseProduct 1,
   .addScaled 0 1 false 0,
   .phaseProduct 0,
   .addScaled 0 1 true 0]

/-- `PhaseTripleProduct` `k = 2`: 4 arithmetic ops, 2 layers, weighted 14. -/
def pointsPTP2 : List Point :=
  [.int 0, .frac 0, .frac 2, .int 1]

def programPTP2 : Prog 2 :=
  [.phaseProduct 0,
   .phaseProduct 1,
   .addScaled 1 0 false 0,
   .addScaled 0 1 false 0,
   .phaseProduct 0,
   .phaseProduct 1,
   .addScaled 0 1 true 0,
   .addScaled 1 0 true 0]

def handles (mode : ProductMode) (k : Nat) : Bool :=
  match mode with
  | .PhaseProduct => decide (k = 2)
  | .PhaseTripleProduct => decide (k = 2)

def generatedPoints (mode : ProductMode) (k : Nat) : List Point :=
  match mode with
  | .PhaseProduct => if k = 2 then pointsPP2 else canonicalPoints mode k
  | .PhaseTripleProduct => if k = 2 then pointsPTP2 else canonicalPoints mode k

def generatePointsInOrder (mode : ProductMode) (k : Nat) (_hk : k >= 2) : List Point :=
  generatedPoints mode k

def generate (mode : ProductMode) (k : Nat) (hk : k >= 2) : Prog k :=
  match mode with
  | .PhaseProduct => if h : k = 2 then h.symm ▸ programPP2 else baselineGenerate mode k hk
  | .PhaseTripleProduct => if h : k = 2 then h.symm ▸ programPTP2 else baselineGenerate mode k hk

theorem generatedPoints_valid (mode : ProductMode) (k : Nat) (_hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointList mode k (generatedPoints mode k) := by
  cases mode with
  | PhaseProduct =>
    have hk' : k = 2 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · unfold ValidPointList; decide
  | PhaseTripleProduct =>
    have hk' : k = 2 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · unfold ValidPointList; decide

set_option maxHeartbeats 100000000 in
set_option maxRecDepth 100000 in
theorem generate_safe (mode : ProductMode) (k : Nat) (hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointOrder (generatedPoints mode k) (generatePointsInOrder mode k hk) ∧
      ProgConsumesPtsSafe (positive_of_ge_two hk) State.start_state
        (generate mode k hk) (generatePointsInOrder mode k hk) := by
  cases mode with
  | PhaseProduct =>
    have hk' : k = 2 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · obtain rfl : hk = (by decide) := Subsingleton.elim _ _
      exact ⟨List.Perm.refl _, progConsumesPtsSafe_of_checks (by decide) (by decide) (by decide)⟩
  | PhaseTripleProduct =>
    have hk' : k = 2 := by
      simpa [handles] using hhandles
    rcases hk' with rfl
    · obtain rfl : hk = (by decide) := Subsingleton.elim _ _
      exact ⟨List.Perm.refl _, progConsumesPtsSafe_of_checks (by decide) (by decide) (by decide)⟩

def implementation : TableGeneration.GeneratorPolicy where
  generatedPoints := generatedPoints
  handles := handles
  generatePointsInOrder := generatePointsInOrder
  generate := generate
  generatedPoints_valid := generatedPoints_valid
  generate_safe := generate_safe

end TableGeneration.Submission.Policy
