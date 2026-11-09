#!/usr/bin/env python3
"""The verifier for a policy submission: `TableGeneration/Submission/Policy.lean` holding a ForShor policy (PhaseProduct or PhaseTripleProduct).

`scripts/verifier.py` hands over to this module when the submitted `Policy.lean` declares `namespace PolicySubmission` or `namespace PTPPolicySubmission`; any other file is
the older table-generator submission and goes through the older checks, unchanged. It is trusted code: it runs from the base checkout (`./forshor check` and the pull-request
job both run it from a checkout of the base commit with the submitted file copied in) and it never executes anything the submitter wrote, only compiles it with Lean.

What it does (all of it in `evaluation/intake_v2.py --no-publish`, which this file calls):

  * only `TableGeneration/Submission/Policy.lean` may change (no helper files);
  * the file is checked by ForShor's lexical gate, built by ForShor (`PolicySubmission` or `PTPPolicySubmission`), and the document ForShor prints is the policy;
  * the policy is checked by the STO mirror at exact widths (and, for PhaseProduct, ForShor's printed document must price to the same T as the policy);
  * nothing is priced and nothing is published: the output is `verification.json`, which the trusted publish step (`intake_v2.py --publish-from`) prices and publishes.

It writes `table-generation-submission-result.json` (`status`, `phase: "full"`, the checks, the policy's digest) and `table-generation-summary.md` in the output directory, in the
shape `./forshor check` reads, plus `verification.json`, `intake-result.json` and `policy-verifier.log`.

Environment: FORSHOR_TREE (a built ForShor checkout at or after 349849e; required), STO_TREE (a built STO tree at the epoch's pins; default: the repository itself),
ENGINE_PYTHON (a Python with `evaluation/engine/requirements.txt`; default: this interpreter), TABLE_GEN_LOGIN (the submitter's handle for the reserved-handle check; default:
`local-check`), POLICY_STAGE_TIMEOUT and POLICY_MIRROR_TIMEOUT (seconds).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SUBMISSION = "TableGeneration/Submission/Policy.lean"
HERE = Path(__file__).resolve().parent
CHALLENGE = "forshor-policy"

_NAMESPACES = (re.compile(r"^\s*namespace\s+PolicySubmission\b", re.M), re.compile(r"^\s*namespace\s+PTPPolicySubmission\b", re.M))


def is_policy_file(text: str) -> bool:
    """True when the file declares one of the two policy namespaces: the new format. (The older `Policy.lean` declares `TableGeneration.Submission.Policy`.)"""
    return any(p.search(text) for p in _NAMESPACES)


def applies(repo: Path) -> bool:
    path = Path(repo) / SUBMISSION
    return path.is_file() and is_policy_file(path.read_text(errors="replace"))


def check(name: str, ok: bool, details: str) -> Dict[str, str]:
    return {"name": name, "status": "success" if ok else "failure", "details": details}


def changed_files_check(get_changed_files: Callable[[Path], Tuple[bool, List[str], str]], repo: Path) -> Dict[str, str]:
    """Only the submission file may change. An unavailable comparison is a failure, never a pass; a skipped one (a local run with no base) says so."""
    ok, files, detail = get_changed_files(repo)
    if not ok:
        return check("changed files", False, detail)
    extra = sorted(f for f in files if f != SUBMISSION)
    if extra:
        return check("changed files", False, f"only {SUBMISSION} may change; also changed: " + ", ".join(extra))
    return check("changed files", True, detail if files else f"{detail} (no file list)")


def summary(result: Dict[str, Any]) -> str:
    lines = [f"# Policy submission verification", "", f"Status: **{result['status'].upper()}**", ""]
    pol = result.get("policy")
    if pol:
        lines += [f"Policy `{pol['digest'][:12]}`: {pol['mode']}, {pol['bands']} band(s). STO mirror: accepted. ForShor: "
                  + ("policy-verified (its printed document prices to the same T)" if pol.get("forshorPolicy") else "kernel-checked (no IR for this board)"), ""]
    for c in result["checks"]:
        lines.append(f"- **{c['name']}**: {c['status']}. {c['details']}")
    return "\n".join(lines) + "\n"


def run(repo: Path, out_dir: Path, *, get_changed_files: Callable[[Path], Tuple[bool, List[str], str]],
        env: Optional[Dict[str, str]] = None, intake: Optional[List[str]] = None, preflight: bool = False) -> int:
    """Verify the policy file in `repo`, write the artifacts, return 0 on success. `preflight`: the structural check only (which files changed), no Lean; the result's phase is
    then `preflight`. `intake` replaces the command for tests."""
    env = dict(os.environ if env is None else env)
    repo, out_dir = Path(repo).resolve(), Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checks: List[Dict[str, str]] = [changed_files_check(get_changed_files, repo)]
    policy = None
    if checks[0]["status"] == "success" and not preflight:
        forshor = env.get("FORSHOR_TREE")
        sto = env.get("STO_TREE") or str(repo)
        if not forshor or not Path(forshor).is_dir():
            checks.append(check("trees", False, "FORSHOR_TREE must name a built ForShor checkout (the trusted environment is not prepared)"))
        else:
            cmd = intake or [env.get("ENGINE_PYTHON") or sys.executable, str(HERE.parent / "evaluation" / "intake_v2.py")]
            cmd = cmd + ["--lean-policy", str(repo / SUBMISSION), "--login", env.get("TABLE_GEN_LOGIN") or "local-check", "--no-publish", "--tree", sto, "--forshor-tree", forshor,
                         "--workdir", str(out_dir / "work"), "--verification-out", str(out_dir / "verification.json"), "--out", str(out_dir / "intake-result.json")]
            if env.get("POLICY_STAGE_TIMEOUT"):
                cmd += ["--stage-timeout", env["POLICY_STAGE_TIMEOUT"]]
            if env.get("POLICY_MIRROR_TIMEOUT"):
                cmd += ["--mirror-timeout", env["POLICY_MIRROR_TIMEOUT"]]
            with open(out_dir / "policy-verifier.log", "w") as log:
                proc = subprocess.run(cmd, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                got = json.loads((out_dir / "intake-result.json").read_text())
            except (OSError, ValueError):
                got = {"failed": True, "error": f"the intake wrote no result (exit {proc.returncode}); see policy-verifier.log"}
            if got.get("verified"):
                policy = got["policy"]
                checks.append(check("policy", True, f"ForShor's gate and build, the STO mirror at exact widths: accepted ({policy['mode']}, {policy['bands']} band(s))"))
            elif got.get("refused"):
                checks.append(check(str(got.get("stage") or "refused"), False, str(got.get("reason") or "refused")[:900]))
            else:
                checks.append(check("verification", False, "the verification could not complete (a tool failed, not a verdict on the policy): " + str(got.get("error") or "")[:900]))
    ok = all(c["status"] == "success" for c in checks)
    result = {"schema_version": 1, "challenge": CHALLENGE, "kind": "policy", "phase": "preflight" if preflight else "full", "status": "success" if ok else "failure", "checks": checks,
              "policy": policy, "verification": "verification.json" if ok and not preflight else None}
    # Bind the same source/run fields as the older verifier. The trusted publisher
    # checks these against GitHub, never uses them to choose a PR or commit.
    result["metadata"] = {key: env.get(variable, "") for key, variable in {
        "repository": "GITHUB_REPOSITORY", "run_id": "GITHUB_RUN_ID", "run_attempt": "GITHUB_RUN_ATTEMPT",
        "pr_number": "TABLE_GEN_PR_NUMBER", "head_sha": "TABLE_GEN_HEAD_SHA", "base_sha": "TABLE_GEN_BASE_SHA",
    }.items()}
    (out_dir / "table-generation-submission-result.json").write_text(json.dumps(result, indent=2) + "\n")
    (out_dir / "table-generation-summary.md").write_text(summary(result))
    print(f"policy verifier: {result['status']}")
    return 0 if ok else 1
