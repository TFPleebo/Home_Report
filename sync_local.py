#!/usr/bin/env python3
"""Sync data files between the iCloud folder and this repo clone, in the right direction.

Direction matters:
  weather_log.csv        repo -> local   (GitHub Action is authoritative)
  everything else        local -> repo   (Shortcut / uploads / Claude write there)

Prints a LOUD warning if a local->repo file would LOSE rows, and refuses to shrink it.
"""
import sys, os, shutil, time

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
locked = []

def safe_copy(a, b, n):
    """iCloud intermittently refuses writes/reads with EDEADLK ('Resource deadlock
    avoided'). Retry a few times; if it is still locked, record it and CARRY ON -
    one locked file must never abort the whole sync (it used to, silently starving
    the sensor inbox for four days in Nov 2026)."""
    for i in range(5):
        try:
            shutil.copy(a, b); return True
        except OSError as e:
            last = e; time.sleep(3)
    locked.append("%s: %s" % (n, last)); return False

for n in FROM_REPO:
    a, b = os.path.join(R, n), os.path.join(L, n)
    if rows(a) > 0:
        if safe_copy(a, b, n): print("  repo -> local  %-32s %d rows" % (n, rows(b)))

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
    if safe_copy(a, b, n):
        print("  local -> repo  %-32s %d rows%s" % (n, ra, "  (+%d new)" % gained if gained else ""))

if locked:
    print("\n*** iCloud LOCKED these files - skipped this run, retry later: ***")
    for p in locked: print("   ", p)
if problems:
    print("\n*** WARNING - files NOT synced because the copy would shrink: ***")
    for p in problems: print("   ", p)
if problems or locked:
    sys.exit(1)
