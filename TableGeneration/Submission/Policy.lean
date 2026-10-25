import TableGeneration.Policy

namespace TableGeneration.Submission.Policy

open Operations

/-- A small k=2 candidate using 0, infinity, and 2.
    The accepted k=2 table uses 0, infinity, and +1. -/
def programK2 : Prog 2 :=
  [.phaseProduct 0,
   .phaseProduct 1,
   .addScaled 0 1 false 1,
   .phaseProduct 0,
   .addScaled 0 1 true 1]

def generatedPoints (_mode : ProductMode) (_k : Nat) : List Point :=
  [.int 0, .frac 0, .int 2]

def handles (mode : ProductMode) (k : Nat) : Bool :=
  match mode with
  | .PhaseProduct => decide (k = 2)
  | .PhaseTripleProduct => false

def generatePointsInOrder (mode : ProductMode) (k : Nat) (_hk : k >= 2) :=
  generatedPoints mode k

def generate (mode : ProductMode) (k : Nat) (hk : k >= 2) : Prog k :=
  if h : k = 2 then h.symm ▸ programK2
  else baselineGenerate mode k hk

theorem generatedPoints_valid (mode : ProductMode) (k : Nat) (_hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointList mode k (generatedPoints mode k) := by
  cases mode with
  | PhaseTripleProduct => simp [handles] at hhandles
  | PhaseProduct =>
    have h : k = 2 := by simpa [handles] using hhandles
    subst k
    unfold ValidPointList generatedPoints
    decide

theorem generate_safe (mode : ProductMode) (k : Nat) (hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointOrder (generatedPoints mode k) (generatePointsInOrder mode k hk) ∧
      ProgConsumesPtsSafe (positive_of_ge_two hk) State.start_state
        (generate mode k hk) (generatePointsInOrder mode k hk) := by
  cases mode with
  | PhaseTripleProduct => simp [handles] at hhandles
  | PhaseProduct =>
    have h : k = 2 := by simpa [handles] using hhandles
    subst k
    have hhk : hk = (by decide : 2 >= 2) := Subsingleton.elim _ _
    subst hk
    constructor
    · exact List.Perm.refl _
    · apply progConsumesPtsSafe_of_checks <;> decide

def implementation : GeneratorPolicy where
  generatedPoints := generatedPoints
  handles := handles
  generatePointsInOrder := generatePointsInOrder
  generate := generate
  generatedPoints_valid := generatedPoints_valid
  generate_safe := generate_safe

end TableGeneration.Submission.Policy
