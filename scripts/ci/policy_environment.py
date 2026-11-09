"""Prepare the trusted policy checkers; never read or execute submitted source."""
from __future__ import annotations

import argparse
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

FORSHOR_ROOTS = [
    "ForShor.ShorVerification.Submission.PolicyCheck",
    "ForShor.ShorVerification.Submission.PolicyMain",
    "ForShor.ShorVerification.Submission.PTPPolicyCheck",
    "ForShor.ShorVerification.Submission.PTPPolicyMain",
]


def run_with_disk_budget(command, path, environment):
    process = subprocess.Popen(command, cwd=path, env=environment, start_new_session=True)
    while process.poll() is None:
        if shutil.disk_usage(path).free < 3 * (1 << 30):
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RuntimeError("Less than 3 GiB disk space remains; stopped before the runner loses its logs")
        time.sleep(2)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)


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


def share_matching_dependencies(root, forshor):
    """Reuse only dependencies whose trusted manifests pin identical sources."""
    source_manifest = json.loads((forshor / "lake-manifest.json").read_text())
    destination_manifest = json.loads((root / "lake-manifest.json").read_text())
    source_packages = {p["name"]: p for p in source_manifest["packages"]}
    identity = ("type", "url", "rev", "subDir", "configFile", "manifestFile")
    for package in destination_manifest["packages"]:
        name = package["name"]
        other = source_packages.get(name)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or package.get("type") != "git" or not other:
            continue
        if not package.get("rev") or any(package.get(k) != other.get(k) for k in identity):
            continue
        source = forshor / ".lake/packages" / name
        destination = root / ".lake/packages" / name
        if not source.is_dir():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists():
            shutil.rmtree(destination)
        destination.symlink_to(os.path.relpath(source, destination.parent), target_is_directory=True)
        print(f"Sharing identically pinned dependency: {name}", flush=True)


def build(root, forshor, log):
    config = configuration(root)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=forshor, text=True).strip()
    if actual != config["forshor"]["ref"]:
        raise ValueError("ForShor checkout does not match the trusted pin")
    environment = {**os.environ, "LEAN_NUM_THREADS": "1", "MATHLIB_NO_CACHE_ON_UPDATE": "1"}
    environment.pop("ELAN_TOOLCHAIN", None)
    timings = []
    try:
        for name, path, targets in (("ForShor", forshor, config["forshor_build"]), ("STO", root, config["sto_build"])):
            if name == "STO":
                share_matching_dependencies(root, forshor)
            roots = FORSHOR_ROOTS if name == "ForShor" else targets
            for stage, cmd in (("dependencies", ["lake", "exe", "cache", "get", *roots]), ("build", ["lake", "build", *targets])):
                start = time.monotonic()
                print(f"::group::{name} {stage}", flush=True)
                passed = False
                try:
                    run_with_disk_budget(cmd, path, environment)
                    passed = True
                finally:
                    print("::endgroup::", flush=True)
                    timings.append({"tree": name, "stage": stage, "seconds": round(time.monotonic() - start, 2), "success": passed,
                                    "diskFreeGiB": round(shutil.disk_usage(path).free / (1 << 30), 2)})
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
