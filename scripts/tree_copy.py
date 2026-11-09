"""Isolate writable Lean sources/build outputs without duplicating immutable dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys


def copy_lean_tree(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.is_relative_to(source):
        raise ValueError("The disposable tree must be outside its source")
    if sys.platform == "darwin":
        subprocess.run(["cp", "-cR", str(source), str(destination)], check=True)
        return
    # Ordinary Linux filesystems may not support reflinks. Copy writable project
    # files/build outputs, but reference the trusted dependency cache in this job.
    shutil.copytree(source, destination, symlinks=True,
                    ignore=lambda path, names: [".lake"] if Path(path) == source else [])
    lake = source / ".lake"
    if lake.is_dir():
        shutil.copytree(lake, destination / ".lake", symlinks=True,
                        ignore=lambda path, names: ["packages"] if Path(path) == lake else [])
        packages = lake / "packages"
        if packages.exists():
            (destination / ".lake/packages").symlink_to(packages.resolve(), target_is_directory=True)
