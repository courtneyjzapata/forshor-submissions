"""Identity and read-only reuse of trusted, archived verification receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

REPOSITORY = "zapatacomputing/forshor-submissions"
SHA = re.compile(r"[a-f0-9]{40}")
# These are the actual verification inputs. CI/deployment edits do not change
# mathematical acceptance, but contract, dependency or scoring edits do.
INPUTS = ["TableGeneration", "TableGeneration.lean", "scripts/verifier.py",
          "scripts/leaderboard.py", "scripts/ci/export_benchmark_config.py",
          "leaderboard/config.json", "lakefile.lean", "lake-manifest.json", "lean-toolchain",
          "scripts/policy_verifier.py", "scripts/trusted", "scripts/check_banded_policy.py",
          "scripts/check_ptp_policy.py", "scripts/exact_width.py", "scripts/ptp_exact_width.py",
          "scripts/memcap.py", "scripts/PTPPolicyReport.lean", "scripts/BandedPolicyReport.lean",
          "scripts/policy_json_to_lean.py", "scripts/ptp_policy_json_to_lean.py",
          "evaluation/policy-trees.json", "evaluation/intake_v2.py", "evaluation/export_v2", "evaluation/engine"]


def identity(root: Path, head: str) -> dict:
    if not SHA.fullmatch(head):
        raise ValueError("Invalid submission commit")
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", *INPUTS], cwd=root)
    if not tree:
        raise ValueError("Verification inputs are missing")
    fingerprint = hashlib.sha256(tree).hexdigest()
    key = hashlib.sha256(f"forshor-verification/v1\n{head}\n{fingerprint}".encode()).hexdigest()
    return {"schema": "forshor-verification/v1", "key": key, "headSha": head,
            "fingerprint": fingerprint}


def valid_receipt(receipt: dict, expected: dict) -> bool:
    return (all(receipt.get(k) == v for k, v in expected.items())
            and re.fullmatch(r"[1-9][0-9]*", str(receipt.get("runId", ""))) is not None
            and isinstance(receipt.get("runAttempt"), int) and receipt["runAttempt"] > 0
            and isinstance(receipt.get("pullRequest"), int) and receipt["pullRequest"] > 0)


def reuse(root: Path, head: str, out: Path) -> bool:
    expected = identity(root, head)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification-identity.json").write_text(json.dumps(expected))
    url = (f"https://api.github.com/repos/{REPOSITORY}/contents/"
           f"results/evaluations/{expected['key']}.json?ref=submission-results")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                                  "Accept": "application/vnd.github.raw+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            receipt = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise  # API outages and rate limits must not silently become cache misses.
    if not valid_receipt(receipt, expected):
        raise ValueError("Invalid trusted verification receipt")
    index_request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/contents/leaderboard/results.json?ref=submission-results",
        headers=dict(request.header_items()))
    with urllib.request.urlopen(index_request, timeout=30) as response:
        index = json.load(response)
    policy = next((p for p in index['policies'] if p['policy_id'] == head), None)
    if not policy or policy['source'].get('run_id') != receipt['runId']:
        return False
    (out / "reused-verification.json").write_text(json.dumps(receipt))
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--reuse", type=Path)
    args = parser.parse_args()
    if args.reuse:
        reused = reuse(args.root, args.head, args.reuse)
        print(f"reused={'true' if reused else 'false'}")
    else:
        print(json.dumps(identity(args.root, args.head)))
