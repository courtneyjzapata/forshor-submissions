import TableGeneration.Policy
import TableGeneration.Submission.Policy.GeneralParity

namespace TableGeneration.Submission.Policy

/-- The general parity policy: handles every `k` for which its checks pass. -/
def implementation : TableGeneration.GeneratorPolicy :=
  GeneralParity.implementation

end TableGeneration.Submission.Policy
