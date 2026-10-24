-- Private QP-396 pipeline integration test invalid.
import TableGeneration.Policies.Accepted.P546fea33a7a4

namespace TableGeneration.Submission.Policy

theorem invalidProof : True := by sorry

/-!
This is the editable submission entry point. Replace `implementation` with a
`GeneratorPolicy` for the targets handled by the submission; helper files may be
added as needed.
-/

/-- Known-valid existing k=4 table, reused solely to test the private pipeline. -/
def implementation : TableGeneration.GeneratorPolicy :=
  TableGeneration.Policies.Accepted.P546fea33a7a4.implementation

end TableGeneration.Submission.Policy
