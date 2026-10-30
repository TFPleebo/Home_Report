#!/usr/bin/env python3
"""Sync data files between the iCloud folder and this repo clone, in the right direction.

Direction matters:
  weather_log.csv        repo -> local   (GitHub Action is authoritative)
  everything else        local -> repo   (Shortcut / uploads / Claude write there)

Prints a LOUD warning if a local->repo file would LOSE rows, and refuses to shrink it.
"""
import sys, os, shutil

SRC = sys.argv[1] if len(sys.argv) > 1 else None
if not SRC: sys.exit("usage: sync_local.py <path-to-iCloud-House-Power>")
L, R = os.path.join(SRC, "data"), "data"

FROM_REPO = ["weather_log.csv"]
TO_REPO   = ["home_sensors_inbox.csv", "settings_changelog.csv", "appliance_inventory.csv",
             "aep_interval_log.csv", "gas_monthly_billing_history.csv"]

def rows(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f: return sum(1 for _ in f)
    except Exception: return -1

problems = []
for n in FROM_REPO:
    a, b = os.path.join(R, n), os.path.join(L, n)
    if rows(a) > 0:
        shutil.copy(a, b); print("  repo -> local  %-32s %d rows" % (n, rows(b)))

for n in TO_REPO:
    a, b = os.path.join(L, n), os.path.join(R, n)
    ra, rb = rows(a), rows(b)
    if ra < 0:
        print("  SKIP (unreadable locally)        %-20s" % n); continue
    if ra < rb:
        problems.append("%s: local has %d rows but repo has %d - NOT copying, repo would lose %d"
                        % (n, ra, rb, rb - ra))
        continue
    gained = ra - rb
    shutil.copy(a, b)
    print("  local -> repo  %-32s %d rows%s" % (n, ra, "  (+%d new)" % gained if gained else ""))

if problems:
    print("\n*** WARNING - files NOT synced because the copy would shrink: ***")
    for p in problems: print("   ", p)
    sys.exit(1)
