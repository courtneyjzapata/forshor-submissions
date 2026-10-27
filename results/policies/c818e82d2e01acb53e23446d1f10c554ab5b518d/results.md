<!-- table-generation-submission-result -->
### Table generation benchmark

Status: **SUCCESS**

Submission: PR #27 · commit `c818e82d2e01`

Scoring: `weighted_cost = 1 * arithmetic_operation_count + 5 * parallel_phase_product_layer_count`.

Coverage: **30 of 30** targets.

| Target | Weighted cost | Arithmetic ops | Parallel layers | Phase products | Total ops | Generated points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `PhaseProduct` `k=2` | **14** | 4 | 2 | 3 | 7 | 3 |
| `PhaseTripleProduct` `k=2` | **20** | 10 | 2 | 4 | 14 | 4 |
| `PhaseProduct` `k=3` | **24** | 14 | 2 | 5 | 19 | 5 |
| `PhaseTripleProduct` `k=3` | **33** | 18 | 3 | 7 | 25 | 7 |
| `PhaseProduct` `k=4` | **45** | 30 | 3 | 7 | 37 | 7 |
| `PhaseTripleProduct` `k=4` | **68** | 48 | 4 | 10 | 58 | 10 |
| `PhaseProduct` `k=5` | **70** | 50 | 4 | 9 | 59 | 9 |
| `PhaseTripleProduct` `k=5` | **108** | 78 | 6 | 13 | 91 | 13 |
| `PhaseProduct` `k=6` | **99** | 74 | 5 | 11 | 85 | 11 |
| `PhaseTripleProduct` `k=6` | **147** | 112 | 7 | 16 | 128 | 16 |
| `PhaseProduct` `k=7` | **132** | 102 | 6 | 13 | 115 | 13 |
| `PhaseTripleProduct` `k=7` | **201** | 156 | 9 | 19 | 175 | 19 |
| `PhaseProduct` `k=8` | **169** | 134 | 7 | 15 | 149 | 15 |
| `PhaseTripleProduct` `k=8` | **250** | 200 | 10 | 22 | 222 | 22 |
| `PhaseProduct` `k=9` | **210** | 170 | 8 | 17 | 187 | 17 |
| `PhaseTripleProduct` `k=9` | **318** | 258 | 12 | 25 | 283 | 25 |
| `PhaseProduct` `k=10` | **255** | 210 | 9 | 19 | 229 | 19 |
| `PhaseTripleProduct` `k=10` | **377** | 312 | 13 | 28 | 340 | 28 |
| `PhaseProduct` `k=11` | **304** | 254 | 10 | 21 | 275 | 21 |
| `PhaseTripleProduct` `k=11` | **459** | 384 | 15 | 31 | 415 | 31 |
| `PhaseProduct` `k=12` | **357** | 302 | 11 | 23 | 325 | 23 |
| `PhaseTripleProduct` `k=12` | **528** | 448 | 16 | 34 | 482 | 34 |
| `PhaseProduct` `k=13` | **414** | 354 | 12 | 25 | 379 | 25 |
| `PhaseTripleProduct` `k=13` | **624** | 534 | 18 | 37 | 571 | 37 |
| `PhaseProduct` `k=14` | **475** | 410 | 13 | 27 | 437 | 27 |
| `PhaseTripleProduct` `k=14` | **703** | 608 | 19 | 40 | 648 | 40 |
| `PhaseProduct` `k=15` | **540** | 470 | 14 | 29 | 499 | 29 |
| `PhaseTripleProduct` `k=15` | **813** | 708 | 21 | 43 | 751 | 43 |
| `PhaseProduct` `k=16` | **609** | 534 | 15 | 31 | 565 | 31 |
| `PhaseTripleProduct` `k=16` | **902** | 792 | 22 | 46 | 838 | 46 |

All correctness and safety checks passed.
