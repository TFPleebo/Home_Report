import csv
import glob
import os
import re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
# Output lives at the top level of the project folder (not buried in data/)
# so it's easy to find among all the raw source files.
OUT = os.path.join(BASE, "home_climate_log.csv")

# Main thermostat setpoint history: loaded from data/settings_changelog.csv
# (columns: Date,MainThermostat_Set_F,Notes) instead of hardcoded here, so
# future setpoint/equipment changes just need a new row in that file - no
# code edits required. Each row's setpoint applies from its Date onward,
# until the next row's Date.
# NOTE: this only tracks the MAIN THERMOSTAT. Other equipment (e.g. the
# window AC's time-of-day schedule) is described in the Notes column but
# not represented as its own numeric column here.
def load_thermostat_changelog():
    changelog_path = os.path.join(BASE, "data", "settings_changelog.csv")
    entries = []
    if os.path.exists(changelog_path):
        with open(changelog_path) as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("Date") and r.get("MainThermostat_Set_F"):
                    entries.append((r["Date"].strip(), int(r["MainThermostat_Set_F"])))
    entries.sort(key=lambda e: e[0])
    return entries

THERMOSTAT_CHANGELOG = load_thermostat_changelog()

def main_thermostat_setpoint(date):
    setpoint = None
    for cutoff, value in THERMOSTAT_CHANGELOG:
        if date >= cutoff:
            setpoint = value
    return setpoint

rows = {}  # (date,time24) -> dict of fields

def ensure(date, time24):
    key = (date, time24)
    if key not in rows:
        rows[key] = {
            "AEP_kWh": "", "AEP_Cost": "",
            "WX_Temp_F": "", "WX_DewPoint_F": "", "WX_Humidity_pct": "",
            "WX_Wind_Dir": "", "WX_Wind_Speed_mph": "", "WX_Wind_Gust_mph": "",
            "WX_Pressure_in": "", "WX_Precip_in": "", "WX_Condition": "",
            "MasterBedroom_Temp_F": "", "MasterBedroom_Humidity_pct": "",
            "CrawlSpace_Temp_F": "", "CrawlSpace_Humidity_pct": "",
            "BasementSteps_Temp_F": "", "BasementSteps_Humidity_pct": "",
            "MainFloor_Temp_F": "", "MainFloor_Humidity_pct": "",
            # HomePod's built-in ambient sensor in the bedroom, kept alongside the
            # dedicated Aqara bedroom sensor (which is what MasterBedroom_Temp_F
            # represents) purely as a cross-check between the two devices.
            "BedroomHomePod_Temp_F": "", "BedroomHomePod_Humidity_pct": "",
            # Fridge temp probe added 7/5/2026 - single value, no humidity pair
            "Fridge_Temp_F": "",
        }
    return rows[key]

# --- AEP: single running log data/aep_interval_log.csv, plus any legacy
# data/aep_raw*.csv files still lying around (already 24-hr, 15-min intervals) ---
for aep_file in sorted(glob.glob(os.path.join(BASE, "data", "aep_interval_log.csv"))) + \
                sorted(glob.glob(os.path.join(BASE, "data", "aep_raw*.csv"))):
    with open(aep_file) as f:
        for r in csv.reader(f):
            if not r or not r[0]:
                continue
            _, date, start, end, kwh, cost = r[:6]
            d = ensure(date, start)
            d["AEP_kWh"] = kwh
            d["AEP_Cost"] = cost

# --- Weather: single running log data/weather_log.csv (Date,Time,... rows, 12-hr AM/PM times) ---
# One row gets appended per hour by the daily scheduled pull, instead of a
# new dated file each day, to keep the data folder from filling up with
# thousands of tiny files over months/years.
wx_log_path = os.path.join(BASE, "data", "weather_log.csv")
if os.path.exists(wx_log_path):
    with open(wx_log_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get("Date") or not r.get("Time"):
                continue
            date = r["Date"].strip()
            t24 = datetime.strptime(r["Time"].strip(), "%I:%M %p").strftime("%H:%M")
            d = ensure(date, t24)
            d["WX_Temp_F"] = r["Temp_F"]
            d["WX_DewPoint_F"] = r["DewPoint_F"]
            d["WX_Humidity_pct"] = r["Humidity_pct"]
            d["WX_Wind_Dir"] = r["Wind_Dir"]
            d["WX_Wind_Speed_mph"] = r["Wind_Speed_mph"]
            d["WX_Wind_Gust_mph"] = r["Wind_Gust_mph"]
            d["WX_Pressure_in"] = r["Pressure_in"]
            d["WX_Precip_in"] = r["Precip_in"]
            d["WX_Condition"] = r["Condition"]

# Backward compatibility: any leftover data/weather_daily/weather_YYYY-MM-DD.csv
# files (pre-consolidation) are still picked up if present.
for wx_file in sorted(glob.glob(os.path.join(BASE, "data", "weather_daily", "weather_*.csv"))):
    m = re.search(r"weather_(\d{4}-\d{2}-\d{2})\.csv$", wx_file)
    if not m:
        continue
    date = m.group(1)
    with open(wx_file) as f:
        reader = csv.DictReader(f)
        for r in reader:
            t24 = datetime.strptime(r["Time"], "%I:%M %p").strftime("%H:%M")
            d = ensure(date, t24)
            d["WX_Temp_F"] = r["Temp_F"]
            d["WX_DewPoint_F"] = r["DewPoint_F"]
            d["WX_Humidity_pct"] = r["Humidity_pct"]
            d["WX_Wind_Dir"] = r["Wind_Dir"]
            d["WX_Wind_Speed_mph"] = r["Wind_Speed_mph"]
            d["WX_Wind_Gust_mph"] = r["Wind_Gust_mph"]
            d["WX_Pressure_in"] = r["Pressure_in"]
            d["WX_Precip_in"] = r["Precip_in"]
            d["WX_Condition"] = r["Condition"]

# --- Aqara Master Bedroom Temp: data/aqara_masterbedroom_YYYY-MM-DD.csv ---
def load_aqara(pattern, field):
    for fpath in sorted(glob.glob(os.path.join(BASE, "data", pattern))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.csv$", fpath)
        if not m:
            continue
        date = m.group(1)
        with open(fpath) as f:
            reader = csv.DictReader(f)
            for r in reader:
                d = ensure(date, r["Time"])
                d[field] = r[list(r.keys())[1]]

load_aqara("aqara_masterbedroom_[0-9][0-9][0-9][0-9]-*.csv", "MasterBedroom_Temp_F")
load_aqara("aqara_masterbedroom_humidity_*.csv", "MasterBedroom_Humidity_pct")
load_aqara("aqara_basementsteps_temp_*.csv", "BasementSteps_Temp_F")
load_aqara("aqara_basementsteps_humidity_*.csv", "BasementSteps_Humidity_pct")
load_aqara("aqara_crawlspace_temp_*.csv", "CrawlSpace_Temp_F")
load_aqara("aqara_crawlspace_humidity_*.csv", "CrawlSpace_Humidity_pct")

# --- Main Floor / Living Room (Siri Shortcut, sent via text, 12-hr AM/PM times) ---
for mf_file in sorted(glob.glob(os.path.join(BASE, "data", "mainfloor_daily", "mainfloor_*.csv"))):
    m = re.search(r"mainfloor_(\d{4}-\d{2}-\d{2})\.csv$", mf_file)
    if not m:
        continue
    date = m.group(1)
    with open(mf_file) as f:
        reader = csv.DictReader(f)
        for r in reader:
            t24 = datetime.strptime(r["Time"], "%I:%M %p").strftime("%H:%M")
            d = ensure(date, t24)
            d["MainFloor_Temp_F"] = r["Temp_F"]
            d["MainFloor_Humidity_pct"] = r["Humidity_pct"]

# --- Main Floor / Living Room, LIVE Siri Shortcut feed ---
# The Shortcut appends one row per run directly to this single file (via the
# Shortcuts "Get File" + "Save File" append pattern) instead of texting the user.
# Current header: Date,Temp_F,Humidity_pct (no Time column - the shortcut only
# captures a date, via "Formatted Date" set to yyyy-MM-dd). Since there's no
# time-of-day to align to a specific AEP/weather 15-min row, these rows are
# bucketed under a sentinel time "--:--" so they sit on their own row per date
# instead of colliding with a real interval reading.
# Older 4-column format (Date,Time,Temp_F,Humidity_pct) is still supported for
# backward compatibility, in case the file ever has real per-reading times.
#
# Same "inbox" pattern is reused below for CrawlSpace, Basement Steps, and
# Master Bedroom now that the Shortcut reads all of them live via HomeKit on
# every run (confirmed 7/2026) - no more one-off manual transcription needed
# for those rooms; just point the Shortcut's extra Save-to-file blocks at
# these filenames and this loader picks them up automatically.
def clean_numeric(raw):
    # Shortcuts' "Measurement" variable type renders with its unit baked in
    # (e.g. "69.8°F") when dropped into a Text action, instead of a plain
    # number. That silently fails pd.to_numeric() downstream - confirmed this
    # broke 9 of the 46 real MainFloor rows (all the 7/2-7/3 live ones) before
    # this fix. Strip anything that isn't part of a leading number so this
    # can't happen again regardless of what unit suffix a sensor's Shortcut
    # variable happens to render with.
    if raw is None:
        return ""
    raw = raw.strip()
    if not raw:
        return ""
    m = re.match(r"-?\d+(\.\d+)?", raw)
    return m.group(0) if m else ""

def load_inbox(filename, temp_field, humidity_field):
    inbox_path = os.path.join(BASE, "data", filename)
    if not os.path.exists(inbox_path):
        return
    with open(inbox_path) as f:
        reader = csv.DictReader(f)
        has_time_col = reader.fieldnames and "Time" in reader.fieldnames
        for r in reader:
            if not r.get("Date"):
                continue
            date = r["Date"].strip()
            if not date:
                continue
            if has_time_col and r.get("Time", "").strip():
                time_raw = r["Time"].strip()
                try:
                    if "M" in time_raw.upper():
                        t24 = datetime.strptime(time_raw, "%I:%M %p").strftime("%H:%M")
                    else:
                        t24 = datetime.strptime(time_raw, "%H:%M").strftime("%H:%M")
                except ValueError:
                    continue
            else:
                t24 = "--:--"
            d = ensure(date, t24)
            d[temp_field] = clean_numeric(r.get("Temp_F", ""))
            d[humidity_field] = clean_numeric(r.get("Humidity_pct", ""))

# mainfloor_inbox.csv retired 7/3/2026 - all 9 of its historical rows were
# migrated into home_sensors_inbox.csv (Main_Temp_F/Main_Humidity_pct columns)
# so every sensor now flows through exactly one file, per Lee's request.
# load_inbox() is left defined above for reuse if a single-metric file is
# ever needed again, just not called for mainfloor anymore.

# --- Combined all-room inbox, single file/single Save action per Shortcut run ---
# Rather than one file per room (four Get-file/Save blocks), the Shortcut's
# existing "Text" action was widened to include every sensor it already reads
# live via HomeKit each run, all appended as one row. Column mapping:
#   Main_Temp_F/Main_Humidity_pct                -> Main Floor (MainFloor_*)
#   Basement_Temp_F/Basement_Humidity_pct         -> Basement Steps (BasementSteps_*)
#   BedroomAqara_Temp_F/BedroomAqara_Humidity_pct -> dedicated Aqara bedroom sensor (MasterBedroom_*)
#   BedroomHomePod_Temp_F/BedroomHomePod_Humidity_pct -> HomePod's built-in ambient sensor (cross-check only)
#   Crawlspace_Temp_F/Crawlspace_Humidity_pct     -> CrawlSpace_*
COMBINED_INBOX_COLUMNS = [
    ("Main_Temp_F", "Main_Humidity_pct", "MainFloor_Temp_F", "MainFloor_Humidity_pct"),
    ("Basement_Temp_F", "Basement_Humidity_pct", "BasementSteps_Temp_F", "BasementSteps_Humidity_pct"),
    ("BedroomAqara_Temp_F", "BedroomAqara_Humidity_pct", "MasterBedroom_Temp_F", "MasterBedroom_Humidity_pct"),
    ("BedroomHomePod_Temp_F", "BedroomHomePod_Humidity_pct", "BedroomHomePod_Temp_F", "BedroomHomePod_Humidity_pct"),
    ("Crawlspace_Temp_F", "Crawlspace_Humidity_pct", "CrawlSpace_Temp_F", "CrawlSpace_Humidity_pct"),
]

def load_combined_inbox(filename="home_sensors_inbox.csv"):
    inbox_path = os.path.join(BASE, "data", filename)
    if not os.path.exists(inbox_path):
        return
    with open(inbox_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get("Date"):
                continue
            date = r["Date"].strip()
            if not date:
                continue
            time_raw = (r.get("Time") or "").strip()
            if not time_raw:
                t24 = "--:--"
            else:
                try:
                    if "M" in time_raw.upper():
                        t24 = datetime.strptime(time_raw, "%I:%M %p").strftime("%H:%M")
                    else:
                        t24 = datetime.strptime(time_raw, "%H:%M").strftime("%H:%M")
                except ValueError:
                    t24 = "--:--"
            d = ensure(date, t24)
            for src_temp, src_hum, dst_temp, dst_hum in COMBINED_INBOX_COLUMNS:
                if src_temp in r:
                    d[dst_temp] = clean_numeric(r.get(src_temp, ""))
                if src_hum in r:
                    d[dst_hum] = clean_numeric(r.get(src_hum, ""))
            # Fridge temp probe - single value column, no humidity pair, added 7/5/2026
            if "Fridge_Temp_F" in r:
                d["Fridge_Temp_F"] = clean_numeric(r.get("Fridge_Temp_F", ""))

load_combined_inbox()

# NOTE: the original screenshot-transcribed Aqara files (aqara_masterbedroom_28.csv etc,
# using 2-digit day suffixes) predate this YYYY-MM-DD convention and are handled below
# for backward compatibility with the existing dataset.
LEGACY_AQARA = [
    ("aqara_masterbedroom_28.csv", "2026-06-28", "MasterBedroom_Temp_F"),
    ("aqara_masterbedroom_29.csv", "2026-06-29", "MasterBedroom_Temp_F"),
    ("aqara_masterbedroom_30.csv", "2026-06-30", "MasterBedroom_Temp_F"),
    ("aqara_masterbedroom_01.csv", "2026-07-01", "MasterBedroom_Temp_F"),
    ("aqara_masterbedroom_humidity_28.csv", "2026-06-28", "MasterBedroom_Humidity_pct"),
    ("aqara_masterbedroom_humidity_29.csv", "2026-06-29", "MasterBedroom_Humidity_pct"),
    ("aqara_masterbedroom_humidity_30.csv", "2026-06-30", "MasterBedroom_Humidity_pct"),
    ("aqara_masterbedroom_humidity_01.csv", "2026-07-01", "MasterBedroom_Humidity_pct"),
    ("aqara_basementsteps_temp_28.csv", "2026-06-28", "BasementSteps_Temp_F"),
    ("aqara_basementsteps_temp_29.csv", "2026-06-29", "BasementSteps_Temp_F"),
    ("aqara_basementsteps_temp_30.csv", "2026-06-30", "BasementSteps_Temp_F"),
    ("aqara_basementsteps_temp_01.csv", "2026-07-01", "BasementSteps_Temp_F"),
    ("aqara_basementsteps_humidity_28.csv", "2026-06-28", "BasementSteps_Humidity_pct"),
    ("aqara_basementsteps_humidity_29.csv", "2026-06-29", "BasementSteps_Humidity_pct"),
    ("aqara_basementsteps_humidity_30.csv", "2026-06-30", "BasementSteps_Humidity_pct"),
    ("aqara_basementsteps_humidity_01.csv", "2026-07-01", "BasementSteps_Humidity_pct"),
    ("aqara_crawlspace_temp_28.csv", "2026-06-28", "CrawlSpace_Temp_F"),
    ("aqara_crawlspace_temp_29.csv", "2026-06-29", "CrawlSpace_Temp_F"),
    ("aqara_crawlspace_temp_01.csv", "2026-07-01", "CrawlSpace_Temp_F"),
    ("aqara_crawlspace_humidity_28.csv", "2026-06-28", "CrawlSpace_Humidity_pct"),
    ("aqara_crawlspace_humidity_29.csv", "2026-06-29", "CrawlSpace_Humidity_pct"),
    ("aqara_crawlspace_humidity_01.csv", "2026-07-01", "CrawlSpace_Humidity_pct"),
]
for fname, date, field in LEGACY_AQARA:
    fpath = os.path.join(BASE, "data", fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath) as f:
        reader = csv.DictReader(f)
        for r in reader:
            d = ensure(date, r["Time"])
            d[field] = r[list(r.keys())[1]]

# --- Write merged CSV ---
fieldnames = ["Date", "Time", "MainThermostat_Set_F",
              "AEP_kWh", "AEP_Cost",
              "WX_Temp_F", "WX_DewPoint_F", "WX_Humidity_pct", "WX_Wind_Dir",
              "WX_Wind_Speed_mph", "WX_Wind_Gust_mph", "WX_Pressure_in", "WX_Precip_in", "WX_Condition",
              "MasterBedroom_Temp_F", "MasterBedroom_Humidity_pct",
              "BedroomHomePod_Temp_F", "BedroomHomePod_Humidity_pct",
              "CrawlSpace_Temp_F", "CrawlSpace_Humidity_pct",
              "BasementSteps_Temp_F", "BasementSteps_Humidity_pct",
              "MainFloor_Temp_F", "MainFloor_Humidity_pct",
              "Fridge_Temp_F"]

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for (date, time24) in sorted(rows.keys(), key=lambda k: (k[0], k[1])):
        row = {"Date": date, "Time": time24, "MainThermostat_Set_F": main_thermostat_setpoint(date)}
        row.update(rows[(date, time24)])
        w.writerow(row)

print("Wrote", len(rows), "rows to", OUT)
