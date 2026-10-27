<!-- table-generation-submission-result -->
### Table generation benchmark

Status: **SUCCESS**

Submission: PR #18 · commit `4b165565fcac`

Scoring: `weighted_cost = 1 * arithmetic_operation_count + 5 * parallel_phase_product_layer_count`.

Coverage: **6 of 30** targets.

| Target | Weighted cost | Arithmetic ops | Parallel layers | Phase products | Total ops | Generated points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `PhaseProduct` `k=4` | **40** | 25 | 3 | 7 | 32 | 7 |
| `PhaseProduct` `k=5` | **62** | 42 | 4 | 9 | 51 | 9 |
| `PhaseTripleProduct` `k=5` | **95** | 65 | 6 | 13 | 78 | 13 |
| `PhaseProduct` `k=6` | **90** | 65 | 5 | 11 | 76 | 11 |
| `PhaseTripleProduct` `k=6` | **129** | 94 | 7 | 16 | 110 | 16 |
| `PhaseTripleProduct` `k=7` | **184** | 139 | 9 | 19 | 158 | 19 |

All correctness and safety checks passed.
