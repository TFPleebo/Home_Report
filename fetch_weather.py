#!/usr/bin/env python3
"""
fetch_weather.py - append one day of hourly weather to data/weather_log.csv.

Usage:
    python3 fetch_weather.py            # fetches "yesterday" (local date)
    python3 fetch_weather.py 2026-08-28 # fetches a specific date
    python3 fetch_weather.py --backfill # fetches every missing day from the log's
                                        # last date through yesterday (max 60)

Idempotent: a date already present in weather_log.csv is skipped, so re-running
is always safe. Exits 0 with "nothing to do" if there is no gap to fill.

Source: Open-Meteo archive API (no key required). Coordinates are Mingo Junction,
OH. Times come back in America/New_York already, so no timezone math is needed.
"""
import csv
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "data", "weather_log.csv")

LAT, LON = 40.32, -80.61
TZ = "America/New_York"
MAX_BACKFILL_DAYS = 60

HEADER = ["Date", "Time", "Temp_F", "DewPoint_F", "Humidity_pct", "Wind_Dir",
          "Wind_Speed_mph", "Wind_Gust_mph", "Pressure_in", "Precip_in", "Condition"]

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

WMO = {0: "Fair", 1: "Fair", 2: "Partly Cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
       51: "Light Drizzle", 53: "Drizzle", 55: "Drizzle", 61: "Light Rain",
       63: "Rain", 65: "Heavy Rain", 73: "Light Snow", 80: "Rain Showers",
       81: "Rain Showers", 82: "Heavy Showers", 95: "Thunder"}


def existing_dates():
    if not os.path.exists(LOG):
        return set()
    with open(LOG, newline="", encoding="utf-8") as f:
        return {r["Date"] for r in csv.DictReader(f) if r.get("Date")}


def fetch(day):
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LAT}&longitude={LON}&start_date={day}&end_date={day}"
        "&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,wind_speed_10m,"
        "wind_gusts_10m,wind_direction_10m,surface_pressure,precipitation,weather_code"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
        f"&timezone={TZ.replace('/', '%2F')}"
    )
    last_err = None
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                return json.load(r)
        except Exception as e:                       # noqa: BLE001
            last_err = e
            if attempt < 3:
                import time
                time.sleep(3 * attempt)
    raise RuntimeError(f"weather fetch failed for {day} after 3 tries: {last_err}")


def rows_for(day, payload):
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    if not times:
        raise RuntimeError(f"no hourly data returned for {day}")

    def g(key, i):
        v = (h.get(key) or [None] * len(times))[i]
        return v

    out = []
    for i, iso in enumerate(times):
        stamp = datetime.fromisoformat(iso)
        if stamp.strftime("%Y-%m-%d") != day:
            continue
        deg = g("wind_direction_10m", i)
        wdir = COMPASS[int((deg / 22.5) + 0.5) % 16] if deg is not None else ""
        pres = g("surface_pressure", i)
        temp = g("temperature_2m", i)
        dewp = g("dew_point_2m", i)
        hum = g("relative_humidity_2m", i)
        wspd = g("wind_speed_10m", i)
        wgst = g("wind_gusts_10m", i)
        prcp = g("precipitation", i)
        code = g("weather_code", i)
        # a row with no temperature is not usable
        if temp is None:
            continue
        out.append([
            day,
            stamp.strftime("%-I:%M %p"),
            round(temp, 1),
            "" if dewp is None else round(dewp, 1),
            "" if hum is None else int(round(hum)),
            wdir,
            "" if wspd is None else round(wspd, 1),
            "" if wgst is None else round(wgst, 1),
            "" if pres is None else round(pres * 0.02953, 2),
            "" if prcp is None else f"{prcp:.3f}",
            WMO.get(int(code), "Cloudy") if code is not None else "Cloudy",
        ])
    if len(out) < 20:
        raise RuntimeError(f"only {len(out)} usable hourly rows for {day} - refusing partial day")
    return out


def append(rows):
    new_file = not os.path.exists(LOG) or os.path.getsize(LOG) == 0
    needs_nl = False
    if not new_file:
        with open(LOG, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_nl = f.read(1) != b"\n"
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        if needs_nl:
            f.write("\n")
        w = csv.writer(f)
        if new_file:
            w.writerow(HEADER)
        w.writerows(rows)


def targets(argv, have):
    yesterday = date.today() - timedelta(days=1)
    if "--backfill" in argv:
        if not have:
            return [yesterday.isoformat()]
        start = datetime.strptime(max(have), "%Y-%m-%d").date() + timedelta(days=1)
        days, d = [], start
        while d <= yesterday and len(days) < MAX_BACKFILL_DAYS:
            days.append(d.isoformat())
            d += timedelta(days=1)
        return days
    explicit = [a for a in argv if not a.startswith("-")]
    return explicit if explicit else [yesterday.isoformat()]


def main():
    have = existing_dates()
    wanted = [d for d in targets(sys.argv[1:], have) if d not in have]
    if not wanted:
        print("weather: nothing to do (log already current)")
        return 0
    total = 0
    for day in wanted:
        rows = rows_for(day, fetch(day))
        append(rows)
        total += len(rows)
        print(f"weather: +{len(rows)} rows for {day}")
    print(f"weather: appended {total} rows across {len(wanted)} day(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
