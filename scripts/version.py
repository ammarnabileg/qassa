#!/usr/bin/env python3
"""Single source of version truth.

  release build : X.Y.Z on a commit tagged vX.Y.Z (VERSION holds the last release)
  debug build   : next minor + -dev.<commits since last release tag>+<short sha> (e.g. 0.2.0-dev.3+abc1234)

Usage: version.py            → prints the version for the current checkout
       version.py --channel  → prints "release" or "debug"
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def compute():
    base = (ROOT / "VERSION").read_text().strip()
    # a commit tagged vX.Y.Z is that release, even if VERSION was bumped in a later commit
    for tag in git("tag", "--points-at", "HEAD", "--list", "v*").split():
        if re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            return tag[1:], "release"
    major, minor, _ = (int(x) for x in base.split("."))
    sha = git("rev-parse", "--short", "HEAD") or os.environ.get("SOURCE_COMMIT", "")[:7] or "nogit"
    last_tag = git("describe", "--tags", "--abbrev=0", "--match", "v*")
    count = git("rev-list", "--count", f"{last_tag}..HEAD") if last_tag else git("rev-list", "--count", "HEAD")
    return f"{major}.{minor + 1}.0-dev.{count or 0}+{sha}", "debug"


if __name__ == "__main__":
    v, ch = compute()
    print(ch if "--channel" in sys.argv else v)
