# Policy submission CI

The existing verification and trusted publication jobs serve both submission formats. `PolicySubmission` and `PTPPolicySubmission` select the complete-policy route; other files retain the older table-generator route.

Verification uses trusted base-branch code and full Git history. It builds the public ForShor pin and the in-repository STO targets in `evaluation/policy-trees.json`, then calls the existing verifier with `FORSHOR_TREE`, `STO_TREE`, `ENGINE_PYTHON`, and the GitHub PR author's login. Only the submitted Lean file reaches ForShor's disposable verification tree. No Google publication identity is available in this job.

## Environments and limits

`Warm policy verification environments` builds on trusted `main`, then saves separate ForShor, STO, and Python caches. PR jobs restore only; they never save these caches. The v2 Python environment is separate from the legacy estimator, and uses `evaluation/engine/requirements.txt` with vendored Qualtran. The publisher checkout must include full history so `engineRevision` is the actual last engine change, rather than the shallow checkout's tip.

`POLICY_RUNNER` may name a provisioned Linux runner label. The default is the existing `ubuntu-24.04` private runner. This has 8 GB physical RAM; on disposable GitHub-hosted Linux machines we reclaim unused SDK space, add 8 GiB swap, and use `LEAN_NUM_THREADS=1`. **This does not satisfy a 16 GB physical RAM guarantee.** Hosted measurements must determine whether it is sufficient for the tested policies; larger policies may need a larger runner. Never perform that machine cleanup on a custom runner.

Bootstrap explicitly fetches the compiled `Mathlib` root. The cache tool does not traverse downstream ForShor/STO roots; requesting those roots silently omits the Mathlib artifacts and causes a source build. It suppresses the automatic whole-library fetch during Lake dependency updates. The two trusted trees share dependency directories only when their manifests pin the same Git source and revision. Relative links preserve this layout in the separate caches. On Linux, disposable verification trees copy project sources and their own build outputs while sharing the trusted job's dependency directory; they do not copy Mathlib again. Those trees and PR jobs never save dependency caches. Bootstrap stops its own build process if free disk falls below 3 GiB, retaining stage timings and available disk space before the runner's log writer fails.

The verification job is bounded to 350 minutes; mirror stages are bounded separately. A resource timeout or exhausted memory is an infrastructure limit, not a mathematical verdict. Timings are retained in the `policy-bootstrap` artifact. The large disposable Lean tree is excluded from result artifacts; `verification.json`, identity, outcomes, and logs are retained.

## Trusted publication

After GitHub confirms the exact source run and PR files, the publisher checks the artifact's source/run metadata and compares the verification's Lean bytes and author with GitHub. For a policy it calls `intake_v2.py --publish-from` using the isolated v2 engine and short-lived Google identity. That call revalidates evidence, archives the policy on `submission-results`, calculates resource values, and publishes into the existing v2 epoch.

The archive carries a trusted verification receipt. Publisher retries may recover evidence from it if the original Actions artifact has expired. Evaluation identity stays bound to the original accepted verification run. Completed evaluations skip the engine and archive steps. Both PR checks remain attached to the source head, and successful publication closes the PR without merging it. Policy comments link to the v2 immutable snapshot and `results/policy-submissions/<head>` archive.

The policy archive is separate from the older `leaderboard/results.json` index. Model changes or any engine change require the epoch migration procedure; ordinary CI wiring must not alter scientific sources or the active model.

## Hosted rehearsal

First warm the policy environments on `main`. Open a PR containing only the supplied `seed_pp_S707dd51bf951.Policy.lean` as `TableGeneration/Submission/Policy.lean`. Confirm both PR checks, archived source and evidence, CLI status, and the PhaseProduct/full-board rows. Repeat with the supplied PhaseTripleProduct example. A published row remains in the ledger, so use a deliberate test handle. Test failed verification and publisher retry without replacing the valid snapshot.

Tracking: [QP-436](https://linear.app/zapata-quantum/issue/QP-436), [QP-437](https://linear.app/zapata-quantum/issue/QP-437).

## Temporary cold-build fallback

`Temporary policy cache bootstrap` is manual-only and checks out trusted `main`. It uses the one-job `forshor-bootstrap-20261109` Linux/x64 runner to create the same cache keys as standard hosted verification. It cannot publish results. Ordinary PR verification continues on `ubuntu-24.04`; no repository runner variable changes.

The fallback VM has 8 vCPUs, 32 GiB RAM, a 100 GiB boot disk, no Google service account, and an administrative SSH rule restricted to Google IAP. Its runner registration is ephemeral, and the VM is configured to delete itself after at most two hours. Delete the VM immediately after its job, then remove its IAP firewall rule, dedicated subnet, and network. The workflow has a separate concurrency group so the original hosted bootstrap can complete independently; cancel the remaining bootstrap once one has saved both caches.

The temporary bootstrap uses four Lean threads and preserves trusted local `.lake` files when retrying an interrupted build. PR verification keeps one thread and clean checkouts. Both trees share the one compiled Mathlib download by matching their pinned manifests.

## Hosted results: November 9, 2026

Both supplied starter policies passed the CLI and both GitHub checks, were archived byte-for-byte, and were closed without merging:

* PhaseProduct: [PR #52](https://github.com/zapatacomputing/forshor-submissions/pull/52), head `de4a5a9935e2cd3605c9f6ca2df3b1e6418142fc`, published as `davidleocadio94_sub1` on PP/full.
* PhaseTripleProduct: [PR #53](https://github.com/zapatacomputing/forshor-submissions/pull/53), head `a18ffa70b4a8a74b0f173a66873f2c0b1b0451a9`, published as `davidleocadio94_sub2` on PTP.

Active epoch: `7a11b2b8b6d68718`. Two-submission snapshot: `9eb7cb213b599a33765e0b619ac9294af8858aa0f20a2db01c3420314d367925`.

The browser passed all 12 board/budget views, both submissions' details, refresh, desktop, and 390px mobile without page errors or horizontal overflow. Both queued submissions were retained. [PR #54](https://github.com/zapatacomputing/forshor-submissions/pull/54) passed structural preflight but failed the deliberately false Lean proof; publication was skipped. Re-running [PP publication](https://github.com/zapatacomputing/forshor-submissions/actions/runs/42716235736) succeeded without changing the snapshot or adding another submission. The ledger still has two completed evaluations and the next participant number is 3. v1 data is unchanged; all five reviewer logins work and anonymous access remains blocked.

### Measured compute

These are measured starter examples on the standard private Ubuntu x64 runner, using trusted caches and one Lean thread. They are not a bound for every k ≤ 8 policy.

| Example | Verification | Publication | Rounded job minutes | Gross CI estimate |
| --- | --- | --- | --- | --- |
| PP, one k=3 band | 9m 54s | 53s | 10 + 1 | $0.066 |
| PTP, one k=4 band | 9m 15s | 64s | 10 + 2 | $0.072 |

Calculated at [GitHub's Linux x64 rate](https://docs.github.com/en/billing/reference/actions-runner-pricing) of $0.006/minute, rounding each job separately. Queue time and the custom publication check consume no extra runner minutes. Estimates precede the organization's included usage, and exclude failed submissions, retries, storage, and one-off bootstrap/debug work. For a similar workload, 1,000 accepted policies imply about $66–72 gross CI compute. The private sprint currently runs one verifier at a time (roughly six of these verifications per hour); production concurrency is a separate setting.

The corrected cold bootstrap took 17m 44s on the temporary 8-vCPU/32-GiB VM with four threads. Warm checker preparation on the first ordinary runner spent 34s fetching/checking dependencies and 10s building ForShor, then 6s/4s for STO; restoring the cache and preparing the runner add time. The temporary VM, IAP rule, subnet, network, and task SSH key were removed. [Self-hosted GitHub compute is free](https://docs.github.com/en/billing/concepts/product-billing/github-actions); that temporary VM's Google charge is separate from the per-submission estimate.

### Public-release boundaries

The tested flow uses collaborators' branches in the company repository. The CLI currently requires that repository as both the base and head, so public fork submissions need a separate integration change. The v2 contract caps each board and the submission index at 2,000 rows; paginate before scaling beyond those caps. These constraints concern submission volume, independently of visitor traffic receiving shared JSON.
