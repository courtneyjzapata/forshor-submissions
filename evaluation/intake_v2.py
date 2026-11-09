#!/usr/bin/env python3
"""One submission, end to end: a policy (the submitted Lean file `Policy.lean`, or its site policy JSON) through the Lean checks to the v2 publisher (and so onto the boards).

    python intake_v2.py (--lean-policy Policy.lean | --policy P.json) --login HANDLE --pull N --tree STO_TREE --publisher-url URL
                        [--forshor-tree FORSHOR_CHECKOUT] [--workdir DIR] [--head-sha SHA] [--run-id ID] [--stage-timeout S]

This is the whole of "everything after the participant's policy exists", in one command a workflow can call (GitHub CI supplies the PR's login, number
and head commit, the Lean trees and the publisher's URL and token; nothing else is needed). It never runs anything a participant wrote except Lean
on the policy's own data:

  1. reads the policy and normalises it to the policy the engine prices (a declared width ladder and any other extra key are dropped, never passed to Lean).
     With `--lean-policy` the submission is the Lean file itself: ForShor's lexical gate runs on it, ForShor builds it (needs `--forshor-tree`) and the document it
     prints is the policy (exact widths and the default negation only; 2 <= k <= 8 per band); the document's bands are what the mirror and the pricing use;
  2. refuses the reserved handle, and a publisher whose epoch was built for a different model than this checkout's, BEFORE any compute;
  3. runs the STO mirror (PhaseProduct) or the PhaseTripleProduct harness at exact widths in the Lean tree at the epoch's pins: an envelope that is not
     accepted ends the run, with the stage and reason;
  4. for a PhaseProduct policy whose k are all at most 8, and when a ForShor checkout is given: (JSON input) writes ForShor's PolicyTemplate for it into a disposable
     copy of the checkout and builds it, or (Lean input) uses the build of step 1; prints ForShor's document and requires its bands to be the submitted bands and its own
     IR to price to the same T as the policy. A check that was attempted and fails ends the run. Without a checkout, or for a PhaseTripleProduct policy, the row carries no
     ForShor record (a Lean submission always has one);
  5. prices the policy once, then publishes it through `publish_v2_with_recovery` (the CI client): a conflict or transport error re-reads the live state
     and refreshes only what depends on it.

Exit status: 0 published (or already published), 1 refused (the result says why), 2 the run could not complete (a tool failed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "starter" / "pack" / "harness"))

from publish import RetryPublication, request_json  # noqa: E402  (v1 helpers, unchanged)
from publish_v2 import ModelMismatch, ReservedHandle, policy_name, publish_v2_with_recovery  # noqa: E402

REPO = "zapatacomputing/forshor-submissions"
MAX_FORSHOR_K = 8           # a submission's bands take 2 <= k <= 8
MAX_LEAN_BYTES = 1_000_000  # the size limit of the submitted Lean file


class Refused(Exception):
    """The submission was examined and does not qualify. `stage` names the check, `reason` says why."""

    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage, self.reason = stage, reason


def normalise(policy_doc: Any) -> Dict[str, Any]:
    """The policy the engine prices, as site policy JSON: mode, name, bands (threshold, k, point_order, operations). Anything else is dropped."""
    from export_v2 import engine
    eng = engine.load()
    docs = eng.tables.policy_docs(policy_doc)
    if len(docs) != 1:
        raise Refused("format", f"expected one policy, found {len(docs)}")
    try:
        P = eng.tables.Policy.from_json(docs[0])
    except Exception as e:  # noqa: BLE001
        raise Refused("format", f"not an accepted policy: {e}")
    if not P.bands:
        raise Refused("format", "a policy needs at least one band (a bare leaf is not a submission; the Lean harness refuses it too)")
    return P.to_json()


def _point(p: Dict[str, Any]) -> str:
    """A ForShor point (`{"kind": "int", "z": z}` or a fraction with denominator m, 0 meaning infinity) in the site's spelling."""
    if p["kind"] == "int":
        return str(int(p["z"]))
    m = int(p["m"])
    return "inf" if m == 0 else f"{1 if m > 0 else -1}/{abs(m)}"


def policy_from_document(eng, doc: Dict[str, Any]):
    """The policy ForShor's printed document describes, as the engine's policy (its tables spelled as the site spells them)."""
    T = eng.tables
    return T.Policy(mode=T.PAIR, name="forshor-printed", bands=tuple(
        T.Band(int(b["threshold"]), T.Table.from_json({"mode": T.PAIR, "k": int(b["k"]), "point_order": [_point(p) for p in b["points"]],
                                                       "operations": b["ops"]})) for b in doc["bands"]))


def policy_from_ptp_document(eng, doc: Dict[str, Any]):
    """The PhaseTripleProduct policy ForShor's PTP executable printed, as the engine's policy (same spelling of points and operations as the PhaseProduct document)."""
    T = eng.tables
    return T.Policy(mode=T.TRIPLE, name="forshor-printed-ptp", bands=tuple(
        T.Band(int(b["threshold"]), T.Table.from_json({"mode": T.TRIPLE, "k": int(b["k"]), "point_order": [_point(p) for p in b["points"]],
                                                       "operations": b["ops"]})) for b in doc["bands"]))


def forshor_record(eng, P, doc: Dict[str, Any], pin: str) -> Dict[str, Any]:
    """`verification.forshorPolicy` for a PhaseProduct policy, from ForShor's printed document: its bands are the submitted bands and its own IR
    prices to the same single-run T as the policy does (the site's two agreement checks). Raises Refused when either fails."""
    from export_v2.evidence import FORSHOR_CLAIM
    sys.path.insert(0, str(eng.engine_dir))
    from site_engine import DEFAULT_DELTA
    from site_engine import fullalg as fa
    printed = policy_from_document(eng, doc)
    bands_agree = [(b.threshold, b.table.k, b.table.digest) for b in printed.bands] == [(b.threshold, b.table.k, b.table.digest) for b in P.bands]
    rule = fa.doc_width_rule(doc)
    t_document = float(fa.price_document(doc, 2048, DEFAULT_DELTA)["T"])
    t_policy = float(fa.price_full(P, 2048, DEFAULT_DELTA, detail=False, rule=rule)["T"])
    ir_agrees = t_document == t_policy
    if not bands_agree:
        raise Refused("forshor", "the bands ForShor printed are not the submitted bands")
    if not ir_agrees:
        raise Refused("forshor", f"ForShor's own IR prices to {t_document!r} T, the policy to {t_policy!r} T")
    return {"verified": True, "bandsAgree": True, "irPriceAgrees": True, "claim": FORSHOR_CLAIM, "forshorCommit": pin}


#: What ForShor builds for each kind of Lean submission: the file's name in ForShor's tree, the targets, the executable and its arguments.
#: PhaseProduct: `PolicyTemplate.lean`, document printed under `--balanced`. PhaseTripleProduct: `PTPPolicyTemplate.lean`, no IR.
FORSHOR_KINDS = {
    "pp": ("PolicyTemplate.lean", ["PolicySubmission", "forshor_policy_submission"], ["forshor_policy_submission", "--balanced"]),
    "ptp": ("PTPPolicyTemplate.lean", ["PTPPolicySubmission", "forshor_ptp_policy_submission"], ["forshor_ptp_policy_submission"]),
}


def lean_kind(lean_text: str) -> str:
    """`"pp"` or `"ptp"`: the board a submitted `Policy.lean` is for, from the namespace it declares (exactly one of the two)."""
    pp = re.search(r"^\s*namespace\s+PolicySubmission\b", lean_text, re.M)
    ptp = re.search(r"^\s*namespace\s+PTPPolicySubmission\b", lean_text, re.M)
    if bool(pp) == bool(ptp):
        raise Refused("format", "the Lean file must declare exactly one of `namespace PolicySubmission` (PhaseProduct) and `namespace PTPPolicySubmission` (PhaseTripleProduct)")
    return "ptp" if ptp else "pp"


def forshor_build(forshor_tree: Path, template: str, workdir: Path, timeout: int = 7200, kind: str = "pp") -> Dict[str, Any]:
    """The Lean file as ForShor's template (`kind`: `pp` or `ptp`), in a disposable copy of the checkout: ForShor's lexical gate, its build, then the document its
    executable prints. Raises `Refused` at stage `lexical` or `forshor`; the file is only ever compiled, never run by us."""
    filename, targets, exe = FORSHOR_KINDS[kind]
    tree = workdir / "forshor-tree"
    if tree.exists():
        shutil.rmtree(tree)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tree_copy import copy_lean_tree
    copy_lean_tree(forshor_tree, tree)
    target = tree / "ForShor" / "ShorVerification" / "Submission" / filename
    if not target.parent.is_dir() or (kind == "ptp" and not (target.parent / "PTPPolicyCheck.lean").exists()):
        raise RuntimeError(f"the ForShor checkout has no {'PhaseTripleProduct' if kind == 'ptp' else 'policy'} submission files (it needs ForShor's PTPPolicyCheck and PTPPolicyMain)")
    target.write_text(template)
    gate = subprocess.run(["bash", "scripts/check_template_lexical.sh", str(target)], cwd=tree, capture_output=True, text=True)
    if gate.returncode != 0:
        raise Refused("lexical", "ForShor's lexical gate refused the file: " + (gate.stdout + gate.stderr)[-500:].strip())
    log = workdir / "forshor.log"
    with open(log, "w") as out:
        built = subprocess.run(["lake", "build", *targets], cwd=tree, stdout=out, stderr=subprocess.STDOUT, timeout=timeout)
    if built.returncode != 0:
        text = log.read_text()
        errors = [line for line in text.splitlines() if "error" in line.lower()]          # Lean's own error lines, not the tail of a long build log
        raise Refused("forshor", "ForShor's build of the policy template failed: " + ("\n".join(errors[:6]) or text[-500:])[:900])
    printed = subprocess.run(["lake", "exe", *exe], cwd=tree, capture_output=True, text=True, timeout=timeout)
    if printed.returncode != 0:
        raise Refused("forshor", "ForShor's check refused the policy: " + (printed.stderr or printed.stdout)[-500:])
    return json.loads(printed.stdout)


def forshor_check(eng, P, forshor_tree: Path, workdir: Path, pin: str, timeout: int = 7200) -> Dict[str, Any]:
    """ForShor's build of the policy's template in a disposable copy of the checkout, then its printed document, then `forshor_record`."""
    import policy_to_template as ptt
    return forshor_record(eng, P, forshor_build(forshor_tree, ptt.template_text(P, "ForShor"), workdir, timeout), pin)


def policy_from_lean(eng, lean_text: str, forshor_tree: Optional[Path], workdir: Path, timeout: int = 7200):
    """A submitted `Policy.lean` (ForShor's PolicyTemplate format for PhaseProduct, its PTPPolicyTemplate format for PhaseTripleProduct, told apart by the namespace it
    declares) to (the policy as site policy JSON, ForShor's printed document). ForShor builds the file, so the document is the policy it kernel-checked; the boards then
    check the same tables in the STO mirror and price them. Only exact widths and the default negation are priced, so a file that asks for anything else is refused
    rather than priced as something it is not."""
    if len(lean_text.encode()) > MAX_LEAN_BYTES:
        raise Refused("format", f"the Lean file is larger than {MAX_LEAN_BYTES} bytes")
    kind = lean_kind(lean_text)
    if forshor_tree is None:
        raise RuntimeError("a Lean policy needs ForShor's build, and no ForShor checkout was given (--forshor-tree)")
    doc = forshor_build(forshor_tree, lean_text, workdir, timeout, kind=kind)
    if doc.get("negation", "oneQubit") != "oneQubit":
        raise Refused("format", f"the policy asks for negation {doc.get('negation')!r}; the boards price oneQubit only")
    if kind == "pp":
        from site_engine import fullalg as fa
        if fa.doc_width_rule(doc) != "exact":
            raise Refused("format", "the policy does not use exact widths; the boards price at exact widths")
        P = policy_from_document(eng, doc)
    else:
        P = policy_from_ptp_document(eng, doc)
    if not P.bands or any(not 2 <= b.table.k <= MAX_FORSHOR_K for b in P.bands):
        raise Refused("format", f"every band takes 2 <= k <= {MAX_FORSHOR_K}")
    return P.to_json(), doc


def _published_archive_commit(url: str, token: str) -> str:
    """The archive commit the live snapshot records, read from the published dashboard (`/results/v2/dashboard.json`, which a local publisher serves and
    staging serves from the bucket mount). `/v2/state` does not carry it. Without it, pass `archive_commit` (or `--archive`)."""
    try:
        return request_json(url.rstrip("/") + "/results/v2/dashboard.json", token)["publication"]["archiveCommit"]
    except (RetryPublication, RuntimeError, KeyError) as e:
        raise RuntimeError("the archive commit is not in /v2/state: pass --archive-commit (or --archive); "
                           f"reading it from the published dashboard failed ({type(e).__name__})") from None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


VERIFICATION_SCHEMA = "forshor.policy-verification/v1"
PUBLICATION_SCHEMA = "forshor.publication/v2"


def verify_submission(policy_doc: Any, *, lean_policy: Optional[str] = None, login: str, url: Optional[str] = None, token: str = "local", tree: Path, workdir: Path,
                      forshor_tree: Optional[Path] = None, stage_timeout: Optional[int] = None, mirror_timeout: int = 7200,
                      run_mirror_fn: Optional[Callable[..., Dict[str, Any]]] = None, python: str = sys.executable,
                      log: Callable[[str], None] = lambda s: print(s, flush=True)) -> Dict[str, Any]:
    """Everything up to the publish: the reserved handle and (when a publisher URL is given) the epoch, then ForShor's gate and build (a Lean submission), the STO mirror
    and ForShor's check. Returns the verification: the policy, ForShor's printed document, the mirror's envelope and the model it was verified under, as data a trusted
    job can publish from (`publish_verification`). Nothing is priced and nothing leaves the machine. Raises `Refused`, `ReservedHandle`, `ModelMismatch`."""
    from export_v2 import engine, epoch
    from export_v2.canon import policy_digest
    from export_v2.evidence import EvidenceStore, run_mirror
    from publish_v2 import HOUSE_HANDLE
    eng = engine.load()
    model = epoch.model_of()
    if login.lower() == HOUSE_HANDLE:                           # the reserved handle, before any compute (also offline)
        raise ReservedHandle(f"the handle {HOUSE_HANDLE} is reserved for planner policies")
    if url:
        state = request_json(url.rstrip("/") + "/v2/state", token)
        policy_name(state, login)
        if state["model"] != model:
            raise ModelMismatch(f"live epoch {state['epoch']} was built for a different model than this checkout's; not publishing")

    workdir.mkdir(parents=True, exist_ok=True)
    printed = None
    if lean_policy is not None:                                 # a Lean submission: ForShor builds it, its printed document is the policy
        log("ForShor's lexical gate, build and printed document (the submitted Lean file) ...")
        policy_doc, printed = policy_from_lean(eng, lean_policy, forshor_tree, workdir)
    policy_json = normalise(policy_doc)
    digest = policy_digest(policy_json)
    board = "ptp" if policy_json["mode"] == eng.tables.TRIPLE else "pp"
    log(f"policy {digest[:12]} ({policy_json['mode']}, {len(policy_json['bands'])} bands): the Lean mirror at exact widths ...")
    envelope = (run_mirror_fn or run_mirror)(policy_json, board, tree, workdir / "evidence", timeout=mirror_timeout, python=python, stage_timeout=stage_timeout, fast=True)   # `fast`: PhaseTripleProduct only, see run_mirror
    mirror, why = EvidenceStore(workdir / "evidence").stomirror(policy_json, model, board)
    if mirror is None:
        rec = envelope.get("record", {})
        rej = rec.get("rejection") or {}
        raise Refused(rej.get("stage") or "mirror", f"{rej.get('reason') or why}: {str(rej.get('detail') or '')[:400]}".strip(": "))
    log("  accepted by the STO mirror")

    P = eng.tables.Policy.from_json(policy_json)
    if printed is not None and str(printed.get("schema", "")).startswith("forshor.ptp-"):
        log("  ForShor kernel-checked the PhaseTripleProduct policy (it has no IR, so the row carries no ForShor record)")
        forshor = None
    elif printed is not None:
        forshor = forshor_record(eng, P, printed, model["forshor"]["pin"])
        log("  ForShor policy-verified")
    elif forshor_tree and P.mode == eng.tables.PAIR and max(b.table.k for b in P.bands) <= MAX_FORSHOR_K:
        log("ForShor's build and printed document ...")
        import policy_to_template as ptt
        printed = forshor_build(Path(forshor_tree), ptt.template_text(P, "ForShor"), workdir)
        forshor = forshor_record(eng, P, printed, model["forshor"]["pin"])
        log("  ForShor policy-verified")
    else:
        forshor = None
        log("no ForShor check (" + ("PhaseTripleProduct" if P.mode != eng.tables.PAIR else "no ForShor checkout given" if not forshor_tree else f"k above {MAX_FORSHOR_K}") + ")")
    out = {"schema": VERIFICATION_SCHEMA, "digest": digest, "mode": policy_json["mode"], "board": board, "policy": policy_json, "printed": printed,
           "envelope": envelope, "forshor": forshor, "model": model, "login": login, "createdAt": _now()}
    if lean_policy is not None:                                 # what the archive stores; the publish job compares it with the file at the PR's head commit
        out.update(leanSource=lean_policy, leanSha256=hashlib.sha256(lean_policy.encode()).hexdigest())
    return out


def publish_verification(v: Dict[str, Any], *, login: str, pull: int, url: str, token: str, workdir: Path, head_sha: Optional[str] = None, run_id: Optional[str] = None,
                         archive_commit: Optional[str] = None, archive_view: Optional[Callable[[], Any]] = None,
                         archive_write: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                         log: Callable[[str], None] = lambda s: print(s, flush=True)) -> Dict[str, Any]:
    """Price and publish a verification (`verify_submission`'s output, possibly produced by another job). No Lean runs here and nothing in `v` is trusted: the policy's digest, the
    mirror's envelope (against this checkout's model and the policy), the printed document and ForShor's record are all checked again, and the handle and epoch against the live
    publisher. Raises `Refused`, `ReservedHandle`, `ModelMismatch`."""
    from export_v2 import engine, epoch, request
    from export_v2.canon import policy_digest
    from export_v2.evidence import EvidenceStore
    eng = engine.load()
    model = epoch.model_of()
    if v.get("schema") != VERIFICATION_SCHEMA:
        raise Refused("format", "not a policy verification")
    if v.get("login") != login:
        raise Refused("format", "the verification was made for another handle")
    if v.get("model") != model:
        raise ModelMismatch("the verification was made under another model than this checkout's")
    state_of = lambda: request_json(url.rstrip("/") + "/v2/state", token)
    state = state_of()
    policy_name(state, login)                                   # the reserved handle
    if state["model"] != model:
        raise ModelMismatch(f"live epoch {state['epoch']} was built for a different model than this checkout's; not publishing")

    policy_json = normalise(v["policy"])
    digest = policy_digest(policy_json)
    if digest != v.get("digest"):
        raise Refused("format", "the verification's policy does not match its digest")
    board = "ptp" if policy_json["mode"] == eng.tables.TRIPLE else "pp"
    # the mirror's envelope goes back where the engine reads evidence from, byte for byte as the harness wrote the policy file
    ev = workdir / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / f"{digest[:16]}.policy.json").write_text(json.dumps(policy_json, indent=1, ensure_ascii=False))
    (ev / f"{digest[:16]}.evidence.json").write_text(json.dumps(v["envelope"], indent=1, ensure_ascii=False))
    store = EvidenceStore(ev)
    mirror, why = store.stomirror(policy_json, model, board)
    if mirror is None:
        raise Refused("mirror", f"the mirror evidence does not hold for this policy: {why}")
    P = eng.tables.Policy.from_json(policy_json)
    printed = v.get("printed")
    forshor = None
    if printed is not None and not str(printed.get("schema", "")).startswith("forshor.ptp-"):
        forshor = forshor_record(eng, P, printed, model["forshor"]["pin"])
    elif printed is not None:
        if [(b.threshold, b.table.k) for b in policy_from_ptp_document(eng, printed).bands] != [(b.threshold, b.table.k) for b in P.bands]:
            raise Refused("forshor", "the bands ForShor printed are not the submitted bands")
    head_sha = head_sha or hashlib.sha1(digest.encode()).hexdigest()
    run_id = run_id or str(int(dt.datetime.now(dt.timezone.utc).timestamp()))
    submitted_at = _now()
    pr_url = f"https://github.com/{REPO}/pull/{pull}"
    evaluation_key = hashlib.sha256(f"{head_sha}:{run_id}:{pull}".encode()).hexdigest()
    metadata = {"headSha": head_sha, "pullRequestUrl": pr_url, "githubLogin": login, "runId": run_id, "submittedAt": submitted_at, "evaluationKey": evaluation_key}

    # Production: the accepted ids and the archive commit are the `submission-results` branch's (`archive_view`, as publish_v2 reads it). A local
    # rehearsal has no such branch: the accepted ids are the publisher's own ledger plus this submission.
    archive = archive_commit or (archive_view()[1] if archive_view else _published_archive_commit(url, token))
    accepted_now = archive_view or (lambda: (sorted(set(state_of().get("submissionIds", [])) | {head_sha}), archive))

    def price() -> Dict[str, Any]:
        return request.build_request(policy_json, model=model, store=store, head_sha=head_sha, pull_number=pull, github_login=login, run_id=run_id,
                                     submitted_at=submitted_at, evaluated_at=submitted_at, archive_commit=archive, accepted_ids=[head_sha], number=0,
                                     evaluation_key=evaluation_key, base_generation="", forshor=forshor, log=log)

    sent: Dict[str, Any] = {}

    def send(payload: Dict[str, Any]) -> Dict[str, Any]:
        sent["payload"] = payload                              # the last attempt is the one that was accepted
        return request_json(url.rstrip("/") + "/v2/publish", token, payload)

    archived = None
    if archive_write is not None:                               # the policy joins the archive first: the publisher wants its head among the accepted ids
        archived = archive_write(v)
        log(f"archived {archived['path']} on submission-results ({archived['commit'][:12]})" if archived["added"] else f"already archived: {archived['path']}")
    result = publish_v2_with_recovery(metadata, model, state_of, price, accepted_now, send)
    if archived is not None:
        result["archive"] = archived
    result["policy"] = {"digest": digest, "headSha": head_sha, "login": login, "pull": pull, "mode": policy_json["mode"],
                        "stoMirror": True, "forshorPolicy": bool(forshor)}
    # The publication record the trusted publish job uploads as `publication-result.json` (`./forshor status` and `watch` read it): which snapshot, which row, which boards.
    priced = (sent.get("payload") or {}).get("priced") or []
    result.update({"schema": PUBLICATION_SCHEMA, "kind": "policy", "name": (priced[0]["row"]["name"] if priced else None),
                   "boards": sorted({p["board"] for p in priced})})
    return result


def run_intake(policy_doc: Any, *, lean_policy: Optional[str] = None, login: str, pull: int, url: str, token: str, tree: Path, workdir: Path,
               head_sha: Optional[str] = None, run_id: Optional[str] = None, forshor_tree: Optional[Path] = None,
               stage_timeout: Optional[int] = None, mirror_timeout: int = 7200, archive_commit: Optional[str] = None,
               archive_view: Optional[Callable[[], Any]] = None,
               run_mirror_fn: Optional[Callable[..., Dict[str, Any]]] = None, python: str = sys.executable,
               log: Callable[[str], None] = lambda s: print(s, flush=True)) -> Dict[str, Any]:
    """The pipeline above, verify then publish in one call. Returns the publisher's result. Raises `Refused`, `ReservedHandle`, `ModelMismatch`."""
    v = verify_submission(policy_doc, lean_policy=lean_policy, login=login, url=url, token=token, tree=tree, workdir=workdir, forshor_tree=forshor_tree,
                          stage_timeout=stage_timeout, mirror_timeout=mirror_timeout, run_mirror_fn=run_mirror_fn, python=python, log=log)
    return publish_verification(v, login=login, pull=pull, url=url, token=token, workdir=workdir, head_sha=head_sha, run_id=run_id,
                                archive_commit=archive_commit, archive_view=archive_view, log=log)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", type=Path, help="a policy as site policy JSON (the pack's format)")
    ap.add_argument("--lean-policy", type=Path, help="a submitted Policy.lean (ForShor's PolicyTemplate format); needs --forshor-tree. Exactly one of --policy, --lean-policy and --publish-from")
    ap.add_argument("--no-publish", action="store_true",
                    help="verify only (the reserved handle, ForShor's gate and build, the STO mirror, ForShor's check) and write a verification file; nothing is priced, nothing is "
                         "sent, no publisher or token is needed. This is `./forshor check`, and the untrusted half of CI")
    ap.add_argument("--verification-out", type=Path, help="with --no-publish: where to write the verification (default: WORKDIR/verification.json)")
    ap.add_argument("--publish-from", type=Path, help="price and publish a verification written by --no-publish (the trusted half of CI): no Lean runs, and everything in it is checked again")
    ap.add_argument("--login", required=True, help="the submitter's GitHub handle (the PR author)")
    ap.add_argument("--pull", type=int, help="the pull request number (not needed with --no-publish)")
    ap.add_argument("--head-sha", help="the PR head commit (40 hex); default: derived from the policy")
    ap.add_argument("--run-id")
    ap.add_argument("--tree", type=Path, help="the built Lean tree for the STO mirror, at the epoch's pins (not needed with --publish-from)")
    ap.add_argument("--forshor-tree", type=Path, help="a built ForShor checkout (copied per run); omit to skip the ForShor check of a JSON policy; required for a Lean policy")
    ap.add_argument("--publisher-url", default=os.environ.get("PUBLISHER_URL"), help="with --no-publish: optional, checks the handle and the epoch against the live publisher first")
    ap.add_argument("--workdir", type=Path, default=Path("intake-work"))
    ap.add_argument("--archive", type=Path, help="a checkout of the `submission-results` branch (as publish_v2.py reads it; needs GH_TOKEN); omit for a local rehearsal. With --publish-from "
                    "the policy is first archived there (Policy.lean, policy.json, verification.json, index entry; pushed to the branch) and then published")
    ap.add_argument("--archive-commit", help="the submission-results commit to record (default: the live snapshot's, read from the published dashboard)")
    ap.add_argument("--stage-timeout", type=int)
    ap.add_argument("--mirror-timeout", type=int, default=7200)
    ap.add_argument("--out", type=Path, help="write the result JSON here")
    a = ap.parse_args(argv)
    modes = [a.policy is not None, a.lean_policy is not None, a.publish_from is not None]
    if sum(modes) != 1:
        ap.error("give exactly one of --policy, --lean-policy and --publish-from")
    if a.publish_from is not None:
        if a.no_publish:
            ap.error("--publish-from publishes: it cannot be combined with --no-publish")
        if not a.publisher_url or a.pull is None:
            ap.error("--publish-from needs --publisher-url (or PUBLISHER_URL) and --pull")
    else:
        if a.tree is None:
            ap.error("--tree is required to verify")
        if not a.no_publish and (not a.publisher_url or a.pull is None):
            ap.error("publishing needs --publisher-url (or PUBLISHER_URL) and --pull; use --no-publish to verify only")
    token = os.environ.get("PUBLISHER_TOKEN", "local")
    archive_view = (lambda: __import__("publish_v2")._archive_view(a.archive)) if a.archive else None
    archive_write = None
    if a.archive and a.publish_from is not None:
        def archive_write(v):
            import archive_policy as ap_
            if a.head_sha is None or a.run_id is None:
                raise ap_.ArchiveRefused("archiving needs --head-sha and --run-id")
            token_gh = os.environ["GH_TOKEN"]
            source = ap_.github_source(a.head_sha, token_gh, __import__("publish").request_json)
            return ap_.archive_policy(a.archive, v, login=a.login, pull=a.pull, head_sha=a.head_sha, run_id=a.run_id, source=source, token=token_gh)
    try:
        if a.publish_from is not None:
            result = publish_verification(json.loads(a.publish_from.read_text()), login=a.login, pull=a.pull, url=a.publisher_url, token=token, workdir=a.workdir,
                                          head_sha=a.head_sha, run_id=a.run_id, archive_commit=a.archive_commit, archive_view=archive_view,
                                          archive_write=archive_write)
        elif a.no_publish:
            v = verify_submission(json.loads(a.policy.read_text()) if a.policy else None, lean_policy=a.lean_policy.read_text() if a.lean_policy else None, login=a.login,
                                  url=a.publisher_url, token=token, tree=a.tree, workdir=a.workdir, forshor_tree=a.forshor_tree, stage_timeout=a.stage_timeout,
                                  mirror_timeout=a.mirror_timeout)
            path = a.verification_out or (a.workdir / "verification.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(v) + "\n")
            result = {"verified": True, "verification": str(path), "policy": {"digest": v["digest"], "mode": v["mode"], "bands": len(v["policy"]["bands"]),
                      "stoMirror": True, "forshorPolicy": bool(v["forshor"]), "forshorChecked": v["printed"] is not None}}
        else:
            result = run_intake(json.loads(a.policy.read_text()) if a.policy else None, lean_policy=a.lean_policy.read_text() if a.lean_policy else None, login=a.login,
                                pull=a.pull, url=a.publisher_url, token=token, tree=a.tree, workdir=a.workdir, head_sha=a.head_sha, run_id=a.run_id, forshor_tree=a.forshor_tree,
                                stage_timeout=a.stage_timeout, mirror_timeout=a.mirror_timeout, archive_commit=a.archive_commit, archive_view=archive_view)
        code = 0
    except (Refused, ReservedHandle, ModelMismatch) as e:
        result, code = {"refused": True, "stage": getattr(e, "stage", type(e).__name__), "reason": getattr(e, "reason", str(e))}, 1
    except __import__("archive_policy").ArchiveRefused as e:
        result, code = {"refused": True, "stage": "archive", "reason": str(e)}, 1
    except (RetryPublication, RuntimeError, subprocess.SubprocessError, OSError, ValueError, KeyError) as e:
        result, code = {"failed": True, "error": f"{type(e).__name__}: {e}"[:600]}, 2
    text = json.dumps(result, indent=1)
    print(text)
    if a.out:
        a.out.write_text(text + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
