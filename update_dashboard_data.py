#!/usr/bin/env python3
"""
update_dashboard_data.py — refreshes the data inside house_power_dashboard.html.

Reads the CSV files in this folder (home_climate_log.csv + data/*.csv) and
regenerates the JavaScript data block between the ==HP_DATA_START== and
==HP_DATA_END== markers in house_power_dashboard.html. The dashboard's layout,
model coefficients, and logic are untouched — only the data snapshot changes.

Safe to run anytime:  python3 update_dashboard_data.py
Intended to run daily right after merge.py in the scheduled morning update.
"""

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "house_power_dashboard.html"
CLIMATE = ROOT / "home_climate_log.csv"
SETTINGS = ROOT / "data" / "settings_changelog.csv"
GAS = ROOT / "data" / "gas_monthly_billing_history.csv"

START = "// ==HP_DATA_START=="
END = "// ==HP_DATA_END=="

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ffloat(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_climate():
    """Aggregate home_climate_log.csv to daily records + sensor snapshot."""
    days = defaultdict(lambda: {"kwh": 0.0, "n_kwh": 0, "first": "99:99", "last": "00:00",
                                "temps": [], "hums": []})
    sensors = {}          # column -> (date, time, value)
    sensor_cols = ["MainFloor_Temp_F", "MainFloor_Humidity_pct",
                   "BasementSteps_Temp_F", "BasementSteps_Humidity_pct",
                   "MasterBedroom_Temp_F", "MasterBedroom_Humidity_pct",
                   "BedroomHomePod_Temp_F", "BedroomHomePod_Humidity_pct",
                   "CrawlSpace_Temp_F", "CrawlSpace_Humidity_pct",
                   "Fridge_Temp_F"]
    last_aep_date = None
    last_sensor_dt = None

    with open(CLIMATE, newline="") as f:
        for row in csv.DictReader(f):
            date, time = row["Date"], row["Time"]
            kwh = ffloat(row.get("AEP_kWh"))
            if kwh is not None:
                d = days[date]
                d["kwh"] += kwh
                d["n_kwh"] += 1
                d["first"] = min(d["first"], time)
                d["last"] = max(d["last"], time)
                if last_aep_date is None or date > last_aep_date:
                    last_aep_date = date
            t = ffloat(row.get("WX_Temp_F"))
            if t is not None:
                days[date]["temps"].append(t)
            h = ffloat(row.get("WX_Humidity_pct"))
            if h is not None:
                days[date]["hums"].append(h)
            for col in sensor_cols:
                v = ffloat(row.get(col))
                if v is not None:
                    sensors[col] = (date, time, v)
                    dt = date + " " + time
                    if last_sensor_dt is None or dt > last_sensor_dt:
                        last_sensor_dt = dt

    # Daily records: only days with (near-)complete AEP coverage and weather.
    # Coverage rule: metering must start by 02:00 and run past 22:00 — works for
    # both the old hourly data and the newer 15-minute data.
    daily = []
    for date in sorted(days):
        d = days[date]
        if d["n_kwh"] == 0 or not d["temps"] or not d["hums"]:
            continue
        if d["first"] > "02:00" or d["last"] < "22:00":
            continue
        daily.append([date,
                      round(sum(d["temps"]) / len(d["temps"]), 1),
                      round(sum(d["hums"]) / len(d["hums"]), 1),
                      round(d["kwh"], 2)])
    return daily, sensors, last_aep_date, last_sensor_dt


def read_settings():
    log = []
    with open(SETTINGS, newline="") as f:
        for row in csv.DictReader(f):
            log.append([row["Date"], row["MainThermostat_Set_F"], row["Notes"]])
    log.sort(key=lambda r: r[0])
    return log


def read_gas():
    """Return (per-month avg $/day pooled across years, last read date ISO)."""
    by_month = defaultdict(list)
    last_read = None
    with open(GAS, newline="") as f:
        for row in csv.DictReader(f):
            try:
                d = datetime.strptime(row["Read_Date"], "%m/%d/%Y")
            except ValueError:
                continue
            cost_day = ffloat(row.get("Avg_Cost_per_Day_USD"))
            if cost_day is not None:
                by_month[d.month].append(cost_day)
            iso = d.strftime("%Y-%m-%d")
            if last_read is None or iso > last_read:
                last_read = iso
    return by_month, last_read


def refit_model(daily):
    """Piecewise-linear refit: kwh ~ base + heat*(bal-T)+ + cool*(T-bal)+ + hum*coolside*(H-72).
    Grid-searches the balance point; pure python normal equations (no numpy)."""
    RATE = 0.1706

    def solve(A, b):
        n = len(A)
        M = [row[:] + [b[i]] for i, row in enumerate(A)]
        for c in range(n):
            p = max(range(c, n), key=lambda r: abs(M[r][c]))
            if abs(M[p][c]) < 1e-12:
                return None
            M[c], M[p] = M[p], M[c]
            for r in range(n):
                if r != c and M[r][c]:
                    f = M[r][c] / M[c][c]
                    for k in range(c, n + 1):
                        M[r][k] -= f * M[c][k]
        return [M[i][n] / M[i][i] for i in range(n)]

    best = None
    for bal in range(40, 61):
        rows, ys = [], []
        for _, t, h, k in daily:
            cool = max(t - bal, 0.0)
            heat = max(bal - t, 0.0)
            hum = (h - 72.0) if t >= bal else 0.0
            rows.append([1.0, heat, cool, hum])
            ys.append(k)
        m = len(rows[0])
        XtX = [[sum(r[i] * r[j] for r in rows) for j in range(m)] for i in range(m)]
        Xty = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(m)]
        beta = solve(XtX, Xty)
        if beta is None:
            continue
        errs = sorted(abs(sum(b * x for b, x in zip(beta, r)) - y) * RATE
                      for r, y in zip(rows, ys))
        mae = sum(errs) / len(errs)
        if best is None or mae < best["maeUsd"]:
            best = {
                "balance": bal,
                "vertexKwh": round(beta[0], 3),
                "heatSlope": round(beta[1], 4),
                "coolSlope": round(beta[2], 4),
                "humidityCoef": round(beta[3], 4),
                "humidityBaseline": 72,
                "fitDays": len(daily),
                "maeUsd": round(mae, 2),
                "medianMissUsd": round(errs[len(errs) // 2], 2),
                "p75MissUsd": round(errs[int(len(errs) * 0.75)], 2),
            }
    return best


def build_block(daily, sensors, settings, gas_by_month, last_aep, last_sensor_dt, last_gas):
    # Per-5°F-bin day counts (bins start at -10°F, 22 bins to 100°F)
    counts = [0] * 22
    for _, t, _, _ in daily:
        idx = int((t - (-10)) // 5)
        if 0 <= idx < len(counts):
            counts[idx] += 1

    # Monthly pooled records
    mon = defaultdict(lambda: {"t": [], "h": [], "k": []})
    for date, t, h, k in daily:
        m = int(date[5:7])
        mon[m]["t"].append(t)
        mon[m]["h"].append(h)
        mon[m]["k"].append(k)
    monthly = []
    for m in range(1, 13):
        d = mon[m]
        n = len(d["k"])
        gas_list = gas_by_month.get(m, [])
        gas_avg = round(sum(gas_list) / len(gas_list), 2) if gas_list else None
        if n:
            monthly.append([MONTH_NAMES[m - 1],
                            round(sum(d["t"]) / n, 1),
                            round(sum(d["h"]) / n, 1),
                            round(sum(d["k"]) / n, 1),
                            n, gas_avg, len(gas_list)])
        else:
            monthly.append([MONTH_NAMES[m - 1], None, None, None, 0, gas_avg, len(gas_list)])

    # Room snapshot from latest sensor readings
    room_defs = [("Main Floor", "MainFloor_Temp_F", "MainFloor_Humidity_pct"),
                 ("Basement Steps", "BasementSteps_Temp_F", "BasementSteps_Humidity_pct"),
                 ("Bedroom (Aqara)", "MasterBedroom_Temp_F", "MasterBedroom_Humidity_pct"),
                 ("Bedroom (HomePod)", "BedroomHomePod_Temp_F", "BedroomHomePod_Humidity_pct"),
                 ("Crawlspace", "CrawlSpace_Temp_F", "CrawlSpace_Humidity_pct"),
                 # Fridge probe added 7/5/2026 - single temp value, no humidity pair
                 ("Fridge", "Fridge_Temp_F", None)]
    rooms = []
    for name, tcol, hcol in room_defs:
        if tcol in sensors:
            rooms.append({"room": name,
                          "tempF": sensors[tcol][2],
                          "humidityPct": (sensors[hcol][2] if hcol and hcol in sensors else None)})

    # The most recent settings change that isn't the seasonal baseline —
    # used by the Model vs. Reality chart to color "new settings" days.
    change_date = settings[-1][0] if settings else "2026-06-28"
    for row in settings:
        if row[0] >= "2026-06-28":
            change_date = row[0]
            break

    js = lambda o: json.dumps(o, ensure_ascii=False)
    lines = [
        START,
        "// Everything between these markers is regenerated by update_dashboard_data.py",
        "// from the CSV files in this folder. Do not hand-edit; run the script instead.",
        f"// Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "// Real observed-day counts per 5°F bin, from home_climate_log.csv "
        f"({len(daily)} full metered days).",
        f"const ELECTRIC_DAY_COUNTS = {js(counts)};",
        "const ELECTRIC_BIN_START = -10, ELECTRIC_BIN_SIZE = 5;",
        "",
        "// Every real day with metered electric usage: [date, avgTempF, avgHumidityPct, actualKwh].",
        f"const DAILY_RECORDS = {js(daily)};",
        "",
        "// Real avg temp/humidity/usage by calendar month, pooled across years:",
        "// [monthName, avgTempF, avgHumidityPct, avgElecKwh, nElecDays, avgGasCostPerDay|null, nGasPeriods]",
        f"const MONTHLY_RECORDS = {js(monthly)};",
        "",
        "// First experiment date — days on/after this are colored as 'new settings' in charts.",
        f"const SETTINGS_CHANGE_DATE = {js(change_date)};",
        "",
        "// Mirrors data/settings_changelog.csv row for row: [date, thermostatSetF, notes].",
        f"const SETTINGS_LOG = {js(settings)};",
        "",
        "// Last real date seen in each source file at refresh time.",
        f"const LAST_DATA_DATES = {js({'aep': last_aep, 'sensors': (last_sensor_dt or '')[:10], 'gas': last_gas})};",
        "",
        "// Nightly refit of the electric model on all metered days (same piecewise",
        "// structure the dashboard has always used - only the coefficients update).",
        f"const MODEL_FIT = {js(refit_model(daily))};",
        "",
        "// Last real reading per indoor sensor — a display of latest known values, not a prediction.",
        f"const ROOM_SNAPSHOT = {js(rooms)};",
        f"const ROOM_SNAPSHOT_AS_OF = {js(last_sensor_dt or 'unknown')};",
        END,
    ]
    return "\n".join(lines)


def main():
    for p in (DASHBOARD, CLIMATE, SETTINGS, GAS):
        if not p.exists():
            sys.exit(f"Missing required file: {p}")

    daily, sensors, last_aep, last_sensor_dt = read_climate()
    if not daily:
        sys.exit("No complete metered days found in home_climate_log.csv — aborting, dashboard left untouched.")
    settings = read_settings()
    gas_by_month, last_gas = read_gas()

    block = build_block(daily, sensors, settings, gas_by_month, last_aep, last_sensor_dt, last_gas)

    html = DASHBOARD.read_text()
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pat.search(html):
        sys.exit("Data markers not found in dashboard HTML — is this the revamped dashboard?")
    DASHBOARD.write_text(pat.sub(lambda _: block, html))

    print(f"Dashboard data refreshed: {len(daily)} metered days "
          f"(through {last_aep}), sensors through {(last_sensor_dt or '?')[:10]}, "
          f"gas through {last_gas}.")


if __name__ == "__main__":
    main()
