import TableGeneration.Policy

namespace TableGeneration.Submission.Policy

open Operations

/-!
Low-width `PhaseProduct` tables at `k = 4, 7, 8`, built for the recursive
planners rather than the per-target weighted score.

Each layer builds its rows from the identity and is then exactly undone. The
width scan never shrinks on an addition, so the point set, the layer order,
the accumulator registers, the order in which terms are added, and pre-shifts
later taken back off by `shiftR` were searched to keep the running width
maximum low. Every table uses the champion's layer count at its arity.

Child widths at 2048 bits: `k = 8` -> 289, `k = 7` -> 319. At about 290 bits
`k = 4` adds roughly 11 bits over `w / 4`. Together with the archive, the
publisher's 2048-bit plans become 2048 k8 -> 289 k4 -> 83 k2 -> 45 (T count)
and 2048 k7 -> 319 k3 -> 114 k2 -> 60 k2 -> 33 (gate count).
-/

/-- `PhaseProduct` `k = 4`: 34 arithmetic ops, 3 layers; child width 523 at 2048 bits. -/
def pointsK4 : List Point :=
  [.frac 0, .frac 2, .frac (-2), .int 0, .int 2, .int 1, .int (-1)]

def programK4 : Prog 4 :=
  [.shiftL 1 2,
   .addScaled 1 3 false 0,
   .shiftL 0 2,
   .addScaled 0 2 false 0,
   .shiftL 0 1,
   .addScaled 0 1 false 0,
   .shiftL 1 1,
   .addScaled 1 0 true 0,
   .phaseProduct 3,
   .phaseProduct 0,
   .phaseProduct 1,
   .addScaled 1 0 false 0,
   .shiftR 1 1,
   .addScaled 0 1 true 0,
   .shiftR 0 1,
   .addScaled 0 2 true 0,
   .shiftR 0 2,
   .addScaled 1 3 true 0,
   .shiftR 1 2,
   .shiftL 3 3,
   .addScaled 3 2 false 2,
   .addScaled 3 0 false 0,
   .addScaled 3 1 false 1,
   .phaseProduct 0,
   .phaseProduct 3,
   .addScaled 3 1 true 1,
   .addScaled 3 0 true 0,
   .addScaled 3 2 true 2,
   .shiftR 3 3,
   .addScaled 2 0 false 0,
   .addScaled 1 2 false 0,
   .addScaled 1 3 false 0,
   .shiftL 2 1,
   .addScaled 2 1 true 0,
   .phaseProduct 1,
   .phaseProduct 2,
   .addScaled 2 1 false 0,
   .shiftR 2 1,
   .addScaled 1 3 true 0,
   .addScaled 1 2 true 0,
   .addScaled 2 0 true 0]

/-- `PhaseProduct` `k = 7`: 128 arithmetic ops, 6 layers; child width 319 at 2048 bits. -/
def pointsK7 : List Point :=
  [.frac 0, .frac 2, .frac (-2), .frac 8, .frac (-8), .int 4, .int (-4), .int 2, .frac 4, .frac (-4), .int 0, .int 1, .int (-1)]

def programK7 : Prog 7 :=
  [.shiftL 2 4,
   .addScaled 2 4 false 2,
   .addScaled 2 6 false 0,
   .addScaled 2 0 false 6,
   .shiftL 3 2,
   .addScaled 3 5 false 0,
   .addScaled 3 1 false 4,
   .shiftL 3 1,
   .addScaled 3 2 false 0,
   .shiftL 2 1,
   .addScaled 2 3 true 0,
   .phaseProduct 6,
   .phaseProduct 3,
   .phaseProduct 2,
   .addScaled 2 3 false 0,
   .shiftR 2 1,
   .addScaled 3 2 true 0,
   .shiftR 3 1,
   .addScaled 3 1 true 4,
   .addScaled 3 5 true 0,
   .shiftR 3 2,
   .addScaled 2 0 true 6,
   .addScaled 2 6 true 0,
   .addScaled 2 4 true 2,
   .shiftR 2 4,
   .shiftL 0 18,
   .addScaled 0 6 false 0,
   .addScaled 0 4 false 6,
   .addScaled 0 2 false 12,
   .shiftL 1 14,
   .addScaled 1 5 false 2,
   .addScaled 1 3 false 8,
   .shiftL 1 1,
   .addScaled 1 0 false 0,
   .shiftL 0 1,
   .addScaled 0 1 true 0,
   .phaseProduct 1,
   .phaseProduct 0,
   .addScaled 0 1 false 0,
   .shiftR 0 1,
   .addScaled 1 0 true 0,
   .shiftR 1 1,
   .addScaled 1 3 true 8,
   .addScaled 1 5 true 2,
   .shiftR 1 14,
   .addScaled 0 2 true 12,
   .addScaled 0 4 true 6,
   .addScaled 0 6 true 0,
   .shiftR 0 18,
   .shiftL 4 8,
   .addScaled 4 0 false 0,
   .addScaled 4 2 false 4,
   .addScaled 4 6 false 12,
   .shiftL 5 4,
   .addScaled 5 3 false 0,
   .shiftL 5 4,
   .addScaled 5 1 false 0,
   .shiftL 5 2,
   .addScaled 5 4 false 0,
   .shiftL 4 1,
   .addScaled 4 5 true 0,
   .phaseProduct 5,
   .phaseProduct 4,
   .addScaled 4 5 false 0,
   .shiftR 4 1,
   .addScaled 5 4 true 0,
   .shiftR 5 2,
   .addScaled 5 1 true 0,
   .shiftR 5 4,
   .addScaled 5 3 true 0,
   .shiftR 5 4,
   .addScaled 4 6 true 12,
   .addScaled 4 2 true 4,
   .addScaled 4 0 true 0,
   .shiftR 4 8,
   .shiftL 6 6,
   .addScaled 6 0 false 0,
   .addScaled 6 2 false 2,
   .addScaled 6 1 false 1,
   .addScaled 6 3 false 3,
   .addScaled 6 5 false 5,
   .addScaled 6 4 false 4,
   .phaseProduct 6,
   .addScaled 6 4 true 4,
   .addScaled 6 5 true 5,
   .addScaled 6 3 true 3,
   .addScaled 6 1 true 1,
   .addScaled 6 2 true 2,
   .addScaled 6 0 true 0,
   .shiftR 6 6,
   .shiftL 0 4,
   .addScaled 0 2 false 0,
   .shiftL 0 4,
   .addScaled 0 4 false 0,
   .shiftL 0 4,
   .addScaled 0 6 false 0,
   .shiftL 1 4,
   .addScaled 1 3 false 0,
   .shiftL 1 4,
   .addScaled 1 5 false 0,
   .shiftL 1 1,
   .shiftL 1 1,
   .addScaled 1 0 false 0,
   .shiftL 0 1,
   .addScaled 0 1 true 0,
   .phaseProduct 1,
   .phaseProduct 0,
   .addScaled 0 1 false 0,
   .shiftR 0 1,
   .addScaled 1 0 true 0,
   .shiftR 1 1,
   .shiftR 1 1,
   .addScaled 1 5 true 0,
   .shiftR 1 4,
   .addScaled 1 3 true 0,
   .shiftR 1 4,
   .addScaled 0 6 true 0,
   .shiftR 0 4,
   .addScaled 0 4 true 0,
   .shiftR 0 4,
   .addScaled 0 2 true 0,
   .shiftR 0 4,
   .addScaled 4 0 false 0,
   .addScaled 4 2 false 0,
   .addScaled 4 6 false 0,
   .addScaled 1 3 false 0,
   .addScaled 1 5 false 0,
   .addScaled 1 4 false 0,
   .shiftL 4 1,
   .addScaled 4 1 true 0,
   .phaseProduct 0,
   .phaseProduct 1,
   .phaseProduct 4,
   .addScaled 4 1 false 0,
   .shiftR 4 1,
   .addScaled 1 4 true 0,
   .addScaled 1 5 true 0,
   .addScaled 1 3 true 0,
   .addScaled 4 6 true 0,
   .addScaled 4 2 true 0,
   .addScaled 4 0 true 0]

/-- `PhaseProduct` `k = 8`: 166 arithmetic ops, 7 layers; child width 289 at 2048 bits. -/
def pointsK8 : List Point :=
  [.frac 2, .frac (-2), .frac 8, .frac (-8), .int 0, .int 8, .int 4, .int (-4), .frac 4, .frac (-4), .frac 0, .int 1, .int (-1), .int 2, .int (-2)]

def programK8 : Prog 8 :=
  [.shiftL 3 4,
   .addScaled 3 5 false 2,
   .addScaled 3 7 false 0,
   .addScaled 3 1 false 6,
   .shiftL 4 2,
   .addScaled 4 6 false 0,
   .addScaled 4 2 false 4,
   .addScaled 4 0 false 6,
   .shiftL 4 1,
   .addScaled 4 3 false 0,
   .shiftL 3 1,
   .addScaled 3 4 true 0,
   .phaseProduct 4,
   .phaseProduct 3,
   .addScaled 3 4 false 0,
   .shiftR 3 1,
   .addScaled 4 3 true 0,
   .shiftR 4 1,
   .addScaled 4 0 true 6,
   .addScaled 4 2 true 4,
   .addScaled 4 6 true 0,
   .shiftR 4 2,
   .addScaled 3 1 true 6,
   .addScaled 3 7 true 0,
   .addScaled 3 5 true 2,
   .shiftR 3 4,
   .shiftL 1 18,
   .addScaled 1 7 false 0,
   .addScaled 1 5 false 6,
   .addScaled 1 3 false 12,
   .shiftL 2 13,
   .addScaled 2 6 false 1,
   .addScaled 2 4 false 7,
   .addScaled 2 0 false 19,
   .shiftL 2 2,
   .addScaled 2 1 false 0,
   .shiftL 1 1,
   .addScaled 1 2 true 0,
   .phaseProduct 2,
   .phaseProduct 1,
   .addScaled 1 2 false 0,
   .shiftR 1 1,
   .addScaled 2 1 true 0,
   .shiftR 2 2,
   .addScaled 2 0 true 19,
   .addScaled 2 4 true 7,
   .addScaled 2 6 true 1,
   .shiftR 2 13,
   .addScaled 1 3 true 12,
   .addScaled 1 5 true 6,
   .addScaled 1 7 true 0,
   .shiftR 1 18,
   .shiftL 5 15,
   .addScaled 5 0 false 0,
   .addScaled 5 1 false 3,
   .addScaled 5 3 false 9,
   .addScaled 5 6 false 18,
   .addScaled 5 2 false 6,
   .addScaled 5 4 false 12,
   .addScaled 5 7 false 21,
   .phaseProduct 0,
   .phaseProduct 5,
   .addScaled 5 7 true 21,
   .addScaled 5 4 true 12,
   .addScaled 5 2 true 6,
   .addScaled 5 6 true 18,
   .addScaled 5 3 true 9,
   .addScaled 5 1 true 3,
   .addScaled 5 0 true 0,
   .shiftR 5 15,
   .shiftL 6 4,
   .addScaled 6 4 false 0,
   .shiftL 6 4,
   .addScaled 6 2 false 0,
   .shiftL 6 4,
   .addScaled 6 0 false 0,
   .shiftL 7 14,
   .addScaled 7 6 false 0,
   .addScaled 7 1 false 2,
   .addScaled 7 3 false 6,
   .addScaled 7 5 false 10,
   .shiftL 6 1,
   .addScaled 6 7 true 0,
   .phaseProduct 7,
   .phaseProduct 6,
   .addScaled 6 7 false 0,
   .shiftR 6 1,
   .addScaled 7 5 true 10,
   .addScaled 7 3 true 6,
   .addScaled 7 1 true 2,
   .addScaled 7 6 true 0,
   .shiftR 7 14,
   .addScaled 6 0 true 0,
   .shiftR 6 4,
   .addScaled 6 2 true 0,
   .shiftR 6 4,
   .addScaled 6 4 true 0,
   .shiftR 6 4,
   .shiftL 1 4,
   .addScaled 1 3 false 0,
   .shiftL 1 4,
   .addScaled 1 5 false 0,
   .shiftL 1 4,
   .addScaled 1 7 false 0,
   .shiftL 0 12,
   .addScaled 0 4 false 4,
   .addScaled 0 2 false 8,
   .addScaled 0 6 false 0,
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
   .addScaled 0 6 true 0,
   .addScaled 0 2 true 8,
   .addScaled 0 4 true 4,
   .shiftR 0 12,
   .addScaled 1 7 true 0,
   .shiftR 1 4,
   .addScaled 1 5 true 0,
   .shiftR 1 4,
   .addScaled 1 3 true 0,
   .shiftR 1 4,
   .addScaled 0 2 false 0,
   .addScaled 0 4 false 0,
   .addScaled 0 6 false 0,
   .addScaled 1 3 false 0,
   .addScaled 1 5 false 0,
   .addScaled 1 7 false 0,
   .addScaled 1 0 false 0,
   .shiftL 0 1,
   .addScaled 0 1 true 0,
   .phaseProduct 7,
   .phaseProduct 1,
   .phaseProduct 0,
   .addScaled 0 1 false 0,
   .shiftR 0 1,
   .addScaled 1 0 true 0,
   .addScaled 1 7 true 0,
   .addScaled 1 5 true 0,
   .addScaled 1 3 true 0,
   .addScaled 0 6 true 0,
   .addScaled 0 4 true 0,
   .addScaled 0 2 true 0,
   .addScaled 4 6 false 2,
   .shiftL 4 2,
   .addScaled 4 2 false 0,
   .shiftL 4 2,
   .addScaled 4 0 false 0,
   .shiftL 7 2,
   .addScaled 7 5 false 0,
   .shiftL 7 2,
   .addScaled 7 3 false 0,
   .shiftL 7 2,
   .addScaled 7 1 false 0,
   .shiftL 7 1,
   .addScaled 7 4 false 0,
   .shiftL 4 1,
   .addScaled 4 7 true 0,
   .phaseProduct 7,
   .phaseProduct 4,
   .addScaled 4 7 false 0,
   .shiftR 4 1,
   .addScaled 7 4 true 0,
   .shiftR 7 1,
   .addScaled 7 1 true 0,
   .shiftR 7 2,
   .addScaled 7 3 true 0,
   .shiftR 7 2,
   .addScaled 7 5 true 0,
   .shiftR 7 2,
   .addScaled 4 0 true 0,
   .shiftR 4 2,
   .addScaled 4 2 true 0,
   .shiftR 4 2,
   .addScaled 4 6 true 2]

def handles (mode : ProductMode) (k : Nat) : Bool :=
  match mode with
  | .PhaseProduct => decide (k = 4) || (decide (k = 7) || decide (k = 8))
  | .PhaseTripleProduct => false

def generatedPoints (mode : ProductMode) (k : Nat) : List Point :=
  match mode with
  | .PhaseProduct => if k = 4 then pointsK4 else if k = 7 then pointsK7 else if k = 8 then pointsK8 else canonicalPoints mode k
  | .PhaseTripleProduct => canonicalPoints mode k

def generatePointsInOrder (mode : ProductMode) (k : Nat) (_hk : k >= 2) : List Point :=
  generatedPoints mode k

def generate (mode : ProductMode) (k : Nat) (hk : k >= 2) : Prog k :=
  match mode with
  | .PhaseProduct => if h : k = 4 then h.symm ▸ programK4 else if h : k = 7 then h.symm ▸ programK7 else if h : k = 8 then h.symm ▸ programK8 else baselineGenerate mode k hk
  | .PhaseTripleProduct => baselineGenerate mode k hk

theorem handles_cases {mode : ProductMode} {k : Nat} (h : handles mode k = true) :
    mode = .PhaseProduct ∧ (k = 4 ∨ k = 7 ∨ k = 8) := by
  cases mode with
  | PhaseProduct => exact ⟨rfl, by simpa [handles, Bool.or_eq_true, decide_eq_true_eq] using h⟩
  | PhaseTripleProduct => simp [handles] at h

set_option exponentiation.threshold 512 in
theorem generatedPoints_valid (mode : ProductMode) (k : Nat) (_hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointList mode k (generatedPoints mode k) := by
  obtain ⟨rfl, hk'⟩ := handles_cases hhandles
  rcases hk' with rfl | rfl | rfl <;> (unfold ValidPointList; decide)

set_option exponentiation.threshold 512 in
set_option maxHeartbeats 1000000000 in
set_option maxRecDepth 100000 in
theorem generate_safe (mode : ProductMode) (k : Nat) (hk : k >= 2)
    (hhandles : handles mode k = true) :
    ValidPointOrder (generatedPoints mode k) (generatePointsInOrder mode k hk) ∧
      ProgConsumesPtsSafe (positive_of_ge_two hk) State.start_state
        (generate mode k hk) (generatePointsInOrder mode k hk) := by
  obtain ⟨rfl, hk'⟩ := handles_cases hhandles
  rcases hk' with rfl | rfl | rfl <;>
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
