# Policy submission CI

The existing verification and trusted publication jobs serve both submission formats. `PolicySubmission` and `PTPPolicySubmission` select the complete-policy route; other files retain the older table-generator route.

Verification uses trusted base-branch code and full Git history. It builds the public ForShor pin and the in-repository STO targets in `evaluation/policy-trees.json`, then calls the existing verifier with `FORSHOR_TREE`, `STO_TREE`, `ENGINE_PYTHON`, and the GitHub PR author's login. Only the submitted Lean file reaches ForShor's disposable verification tree. No Google publication identity is available in this job.

## Environments and limits

`Warm policy verification environments` builds on trusted `main`, then saves separate ForShor, STO, and Python caches. PR jobs restore only; they never save these caches. The v2 Python environment is separate from the legacy estimator, and uses `evaluation/engine/requirements.txt` with vendored Qualtran. The publisher checkout must include full history so `engineRevision` is the actual last engine change, rather than the shallow checkout's tip.

`POLICY_RUNNER` may name a provisioned Linux runner label. The default is the existing `ubuntu-24.04` private runner. This has 8 GB physical RAM; on disposable GitHub-hosted Linux machines we reclaim unused SDK space, add 16 GB swap, and use `LEAN_NUM_THREADS=1`. **This does not satisfy a 16 GB physical RAM guarantee.** Hosted measurements must determine whether it is sufficient for the tested policies; larger policies may need a larger runner. Never perform that machine cleanup on a custom runner.

The verification job is bounded to 350 minutes; mirror stages are bounded separately. A resource timeout or exhausted memory is an infrastructure limit, not a mathematical verdict. Timings are retained in the `policy-bootstrap` artifact. The large disposable Lean tree is excluded from result artifacts; `verification.json`, identity, outcomes, and logs are retained.

## Trusted publication

After GitHub confirms the exact source run and PR files, the publisher checks the artifact's source/run metadata and compares the verification's Lean bytes and author with GitHub. For a policy it calls `intake_v2.py --publish-from` using the isolated v2 engine and short-lived Google identity. That call revalidates evidence, archives the policy on `submission-results`, calculates resource values, and publishes into the existing v2 epoch.

The archive carries a trusted verification receipt. Publisher retries may recover evidence from it if the original Actions artifact has expired. Evaluation identity stays bound to the original accepted verification run. Completed evaluations skip the engine and archive steps. Both PR checks remain attached to the source head, and successful publication closes the PR without merging it. Policy comments link to the v2 immutable snapshot and `results/policy-submissions/<head>` archive.

The policy archive is separate from the older `leaderboard/results.json` index. Model changes or any engine change require the epoch migration procedure; ordinary CI wiring must not alter scientific sources or the active model.

## Hosted rehearsal

First warm the policy environments on `main`. Open a PR containing only the supplied `seed_pp_S707dd51bf951.Policy.lean` as `TableGeneration/Submission/Policy.lean`. Confirm both PR checks, archived source and evidence, CLI status, and the PhaseProduct/full-board rows. Repeat with the supplied PhaseTripleProduct example. A published row remains in the ledger, so use a deliberate test handle. Test failed verification and publisher retry without replacing the valid snapshot.

Tracking: [QP-436](https://linear.app/zapata-quantum/issue/QP-436), [QP-437](https://linear.app/zapata-quantum/issue/QP-437).
