#!/usr/bin/env python3
"""
publish_dashboard.py — publishes the dashboard to GitHub Pages.

Stateless publish: clones the repo shallowly into a temp dir, copies
house_power_dashboard.html (as index.html) plus everything in site/ into it,
commits, and pushes. No .git lives in the iCloud folder — iCloud sync and
git internals don't mix.

Needs publish_config.json next to this script:
  { "remote": "https://<TOKEN>@github.com/USER/REPO.git", "branch": "main" }

Run AFTER update_dashboard_data.py. Safe to run anytime.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
DASH = ROOT / "house_power_dashboard.html"
CONFIG = ROOT / "publish_config.json"


def run(cwd, *cmd, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd[:2])}...\n{r.stderr.strip()}")
    return r


def main():
    if not CONFIG.exists():
        sys.exit("publish_config.json not found — see GITHUB_SETUP.md.")
    if not DASH.exists():
        sys.exit("house_power_dashboard.html not found.")
    cfg = json.loads(CONFIG.read_text())
    remote, branch = cfg["remote"], cfg.get("branch", "main")

    tmp = Path(tempfile.mkdtemp(prefix="hp_publish_"))
    try:
        clone = run(None, "git", "clone", "--depth", "1", "--branch", branch,
                    remote, str(tmp), check=False)
        if clone.returncode != 0:
            # empty repo (no branch yet) — init fresh
            run(None, "git", "init", "-b", branch, str(tmp))
            run(tmp, "git", "remote", "add", "origin", remote)

        run(tmp, "git", "config", "user.name", "House Power Bot")
        run(tmp, "git", "config", "user.email", "housepower@localhost")

        # copy site assets + dashboard as index.html
        if SITE.exists():
            for f in SITE.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    shutil.copy(f, tmp / f.name)
        shutil.copy(DASH, tmp / "index.html")

        # Also push the SOURCE of truth (data + pipeline scripts), so the daily
        # GitHub Actions job is working from the same inputs we just used here.
        # Note: .github/ is deliberately left untouched — the workflow lives only
        # in the repo (a PAT without `workflow` scope cannot push changes to it).
        src_data = ROOT / "data"
        if src_data.exists():
            dst_data = tmp / "data"
            if dst_data.exists():
                shutil.rmtree(dst_data)
            shutil.copytree(
                src_data, dst_data,
                ignore=shutil.ignore_patterns(".DS_Store", "*.bak"),
            )
        for name in ("merge.py", "update_dashboard_data.py", "fetch_weather.py",
                     "publish_dashboard.py", "sync_from_repo.py",
                     "house_power_dashboard.html", ".gitignore"):
            f = ROOT / name
            if f.exists():
                shutil.copy(f, tmp / name)

        run(tmp, "git", "add", "-A")
        if run(tmp, "git", "diff", "--cached", "--quiet", check=False).returncode == 0:
            print("No changes to publish.")
            return
        run(tmp, "git", "commit", "-m", f"Data refresh {date.today().isoformat()}")
        run(tmp, "git", "push", "-u", "origin", branch)
        print("Published to GitHub Pages.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
