"""Recoverable publication of one evaluated policy to the contract-v2 publisher (`/v2/state`, `/v2/publish`).

Same shape as `publish.py` (v1, untouched): read state, skip work already done, price once, send, and on a conflict or transport
error re-read state and send again. Never runs submitted Lean. The trusted workflow calls this recovery loop through `intake_v2.py --publish-from`.

What is different from v1:
* The request is priced ONCE. A retry only refreshes the three things that depend on the live state: `baseGeneration`,
  `evaluation.evaluatedAt` (must be later than the live snapshot's time), the policy name (`<PR author's handle>_sub<N>`, N being that
  handle's next number from the publisher's ledger), and the archive view (`archive.acceptedIds` and
  `evaluation.archiveCommit`, re-fetched like v1 does).
* The epoch's model is checked before any compute. A changed model is not publishable into the live epoch (design D5), and
  retrying cannot fix it, so it is an error, never a retry.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Tuple

from publish import RetryPublication, request_json, refresh_archive  # same directory; v1 helpers are unchanged


HOUSE_HANDLE = "forshor"   # the planner's handle; a submission can never carry it


class ReservedHandle(Exception):
    """The PR author's GitHub handle is the house handle, which is reserved for planner policies (it would impersonate one)."""


class ModelMismatch(Exception):
    """The live epoch was built for a different model than this checkout's; re-pricing under a new epoch is a separate protocol."""


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def already_published(state: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    done = state.get("completedEvaluations", {}).get(metadata["evaluationKey"])
    if done and (done["headSha"] != metadata["headSha"] or str(done["runId"]) != str(metadata["runId"])):
        raise ValueError("Evaluation identity collision")
    return bool(done)


def policy_name(state: Dict[str, Any], login: str) -> str:
    """`<github handle>_sub<N>`: the PR author's handle and that handle's next number, as the publisher's ledger counts them."""
    if login.lower() == HOUSE_HANDLE:
        raise ReservedHandle(f"the handle {HOUSE_HANDLE} is reserved for planner policies")
    return f"{login}_sub{state.get('nextNumbers', {}).get(login.lower(), 1)}"


def check_model(state: Dict[str, Any], model: Dict[str, Any]) -> None:
    if state["model"] != model:
        raise ModelMismatch(f"live epoch {state['epoch']} was built for a different model than this checkout's; not publishing")


def publish_v2_with_recovery(metadata: Dict[str, Any], model: Dict[str, Any], fetch_state: Callable[[], Dict[str, Any]],
                             price: Callable[[], Dict[str, Any]], refresh: Callable[[], Tuple[List[str], str]],
                             send: Callable[[Dict[str, Any]], Dict[str, Any]], sleep=time.sleep,
                             now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc), attempts: int = 4):
    """`price()` returns a complete `forshor.publish/v2` request for this policy; it is called at most once, after the checks pass."""
    key = metadata["evaluationKey"]
    template = None
    for attempt in range(attempts):
        try:
            state = fetch_state()
            if already_published(state, metadata):
                return {"alreadyPublished": True, "evaluationKey": key}
            policy_name(state, metadata["githubLogin"])   # refuses the reserved handle before any compute
            check_model(state, model)
            if template is None:
                template = price()
            request = copy.deepcopy(template)
            at = max(now(), _parse(state["publication"]["updatedAt"]) + dt.timedelta(milliseconds=1))
            request["evaluationKey"] = key
            request["baseGeneration"] = state["baseGeneration"]
            request["evaluation"]["evaluatedAt"] = _iso(at)
            request["archive"]["acceptedIds"], request["evaluation"]["archiveCommit"] = refresh()
            for priced in request["priced"]:   # the publisher assigns the name: the next number after everything already stored
                priced["row"]["name"] = policy_name(state, metadata["githubLogin"])
            return send(request)
        except RetryPublication:
            if attempt == attempts - 1:
                raise
            sleep(2 ** attempt)
    raise AssertionError("Unreachable")


def _archive_view(path: Path) -> Tuple[List[str], str]:
    archive, revision = refresh_archive(path)
    index = json.loads((archive / "leaderboard/results.json").read_text())
    from archive_policy import policy_ids   # policy submissions are archived beside the table-generation entries, in their own index
    return sorted({p["policy_id"] for p in index["policies"]} | set(policy_ids(archive))), revision


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report whether this evaluation is already published")
    ap.add_argument("--policy", help="the accepted policy JSON file (required unless --check)")
    ap.add_argument("--evidence-dir", help="STO mirror evidence for the policy (required unless --check)")
    ap.add_argument("--archive", default="archive")
    a = ap.parse_args(argv)
    metadata = json.loads(Path("evaluation-metadata.json").read_text())
    url = os.environ["PUBLISHER_URL"].rstrip("/")
    token = os.environ["PUBLISHER_TOKEN"]
    state_of = lambda: request_json(url + "/v2/state", token)

    if a.check:
        done = already_published(state_of(), metadata)
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"complete={'true' if done else 'false'}\n")
        return 0
    if not (a.policy and a.evidence_dir):
        ap.error("--policy and --evidence-dir are required to publish")

    from export_v2 import epoch, request
    from export_v2.evidence import EvidenceStore
    model = epoch.model_of()
    revision = _archive_view(Path(a.archive))[1]

    def price():
        # the evaluated-at, base generation, accepted ids and policy number here are placeholders; the recovery loop sets the live values
        return request.build_request(
            json.loads(Path(a.policy).read_text()), model=model, store=EvidenceStore(Path(a.evidence_dir)),
            head_sha=metadata["headSha"], pull_number=int(metadata["pullRequestUrl"].rsplit("/", 1)[1]),
            github_login=metadata["githubLogin"], run_id=str(metadata["runId"]), submitted_at=metadata["submittedAt"],
            evaluated_at=metadata["submittedAt"], archive_commit=revision, accepted_ids=[], number=0,
            evaluation_key=metadata["evaluationKey"], base_generation="", log=lambda s: print(s, flush=True))

    result = publish_v2_with_recovery(metadata, model, state_of, price, lambda: _archive_view(Path(a.archive)),
                                      lambda payload: request_json(url + "/v2/publish", token, payload))
    print(json.dumps(result))
    Path("publication-result.json").write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
