#!/usr/bin/env python3
"""
sync_from_repo.py - pull the GitHub repo's data/ back down into this folder.

Why this exists: a GitHub Actions job now appends the daily weather to
data/weather_log.csv IN THE REPO every morning, with no laptop involved. That
makes the repo the freshest copy. Run this BEFORE doing local work (e.g. adding
an AEP export) so you don't rebuild from a stale weather log and then publish
over the top of the Action's commits.

Usage:
    python3 sync_from_repo.py            # sync weather_log.csv only (default)
    python3 sync_from_repo.py --all      # sync the whole data/ folder

Safe: never deletes local-only files, and prints exactly what changed.
"""
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "publish_config.json"
DEFAULT_FILES = ["weather_log.csv"]


def main():
    if not CONFIG.exists():
        sys.exit("publish_config.json not found - cannot locate the repo.")
    cfg = json.loads(CONFIG.read_text())
    remote, branch = cfg["remote"], cfg.get("branch", "main")

    tmp = Path(tempfile.mkdtemp(prefix="hp_sync_"))
    try:
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, remote, str(tmp)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            # scrub any token that may appear in the error text
            err = r.stderr
            if "@" in err:
                err = "(clone failed; error text suppressed as it may contain the token)"
            sys.exit(f"clone failed: {err.strip()}")

        repo_data = tmp / "data"
        if not repo_data.exists():
            sys.exit("repo has no data/ folder yet - nothing to sync.")

        if "--all" in sys.argv:
            names = sorted(f.name for f in repo_data.iterdir() if f.is_file())
        else:
            names = DEFAULT_FILES

        changed = 0
        for name in names:
            src, dst = repo_data / name, ROOT / "data" / name
            if not src.exists():
                print(f"  skip {name} (not in repo)")
                continue
            if dst.exists() and filecmp.cmp(src, dst, shallow=False):
                print(f"  same {name}")
                continue
            before = sum(1 for _ in dst.open(encoding='utf-8', errors='replace')) if dst.exists() else 0
            shutil.copy(src, dst)
            after = sum(1 for _ in dst.open(encoding='utf-8', errors='replace'))
            print(f"  UPDATED {name}  ({before} -> {after} lines)")
            changed += 1

        print(f"\n{changed} file(s) updated from the repo."
              if changed else "\nAlready up to date with the repo.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
