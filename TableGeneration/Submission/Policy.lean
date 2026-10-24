import TableGeneration.Policy

namespace TableGeneration.Submission.Policy

/-!
This is the editable submission entry point. Replace `implementation` with a
`GeneratorPolicy` for the targets handled by the submission; helper files may be
added as needed.
-/

/-- Intentionally invalid proof: the verifier must reject this integration test. -/
def implementation : TableGeneration.GeneratorPolicy :=
  by sorry

end TableGeneration.Submission.Policy
