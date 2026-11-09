"""Prepare the trusted policy checkers; never read or execute submitted source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def configuration(root):
    config = json.loads((root / "evaluation/policy-trees.json").read_text())
    if config["forshor"]["repo"] != "https://github.com/VerifiedQC/ForShor" or not re.fullmatch(r"[a-f0-9]{40}", config["forshor"]["ref"]):
        raise ValueError("Expected the pinned public ForShor checkout")
    if config["sto"].get("repo") != "self":
        raise ValueError("STO must be the trusted verifier checkout")
    for key in ("sto_build", "forshor_build"):
        if not config[key] or any(not re.fullmatch(r"[A-Za-z0-9_.]+", x) for x in config[key]):
            raise ValueError("Invalid Lean build targets")
    return config


def cache_keys(root):
    config = configuration(root)
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", "TableGeneration", "TableGeneration.lean",
                                    "lean-toolchain", "lakefile.lean", "lake-manifest.json", "evaluation/policy-trees.json"], cwd=root)
    return {"forshor_ref": config["forshor"]["ref"], "sto_hash": hashlib.sha256(tree).hexdigest(),
            "forshor_hash": hashlib.sha256(json.dumps([config["forshor"], config["forshor_build"]], sort_keys=True).encode()).hexdigest()}


def build(root, forshor, log):
    config = configuration(root)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=forshor, text=True).strip()
    if actual != config["forshor"]["ref"]:
        raise ValueError("ForShor checkout does not match the trusted pin")
    environment = {**os.environ, "LEAN_NUM_THREADS": "1"}
    environment.pop("ELAN_TOOLCHAIN", None)
    timings = []
    try:
        for name, path, targets in (("ForShor", forshor, config["forshor_build"]), ("STO", root, config["sto_build"])):
            for stage, cmd in (("dependencies", ["lake", "exe", "cache", "get"]), ("build", ["lake", "build", *targets])):
                start = time.monotonic()
                print(f"::group::{name} {stage}", flush=True)
                run = subprocess.run(cmd, cwd=path, env=environment)
                print("::endgroup::", flush=True)
                timings.append({"tree": name, "stage": stage, "seconds": round(time.monotonic() - start, 2), "exitCode": run.returncode})
                run.check_returncode()
    finally:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(timings, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("config", "build"))
    parser.add_argument("--root", type=Path, default=Path("verifier"))
    parser.add_argument("--forshor", type=Path, default=Path("policy-forshor"))
    parser.add_argument("--log", type=Path, default=Path("policy-bootstrap.json"))
    args = parser.parse_args()
    if args.action == "config":
        for key, value in cache_keys(args.root.resolve()).items():
            print(f"{key}={value}")
    else:
        build(args.root.resolve(), args.forshor.resolve(), args.log)
