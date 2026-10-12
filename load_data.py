"""
Step 1: Load NOAA Storm Events data for Florida into SQLite.

Before running:
  1. Download a few years of "StormEvents_details" CSV files from
     https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
     (e.g. 2020-2025). They're .csv.gz -- no need to unzip.
  2. Put them in the same folder as this script.
  3. pip install pandas

Run:  python load_data.py
"""

import glob
import sqlite3

import pandas as pd

COLUMNS = [
    "EVENT_ID", "EPISODE_ID", "YEAR", "BEGIN_YEARMONTH", "BEGIN_DAY", "STATE",
    "CZ_TYPE", "CZ_NAME", "EVENT_TYPE",
    "INJURIES_DIRECT", "DEATHS_DIRECT",
    "DAMAGE_PROPERTY", "DAMAGE_CROPS",
    "BEGIN_LAT", "BEGIN_LON",
]


FL_COUNTIES = [
    "Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun",
    "Charlotte", "Citrus", "Clay", "Collier", "Columbia", "DeSoto", "Dixie",
    "Duval", "Escambia", "Flagler", "Franklin", "Gadsden", "Gilchrist",
    "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando", "Highlands",
    "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson",
    "Lafayette", "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison",
    "Manatee", "Marion", "Martin", "Miami-Dade", "Monroe", "Nassau",
    "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach", "Pasco",
    "Pinellas", "Polk", "Putnam", "St. Johns", "St. Lucie", "Santa Rosa",
    "Sarasota", "Seminole", "Sumter", "Suwannee", "Taylor", "Union",
    "Volusia", "Wakulla", "Walton", "Washington",
]
# Extra spellings NOAA sometimes uses
ALIASES = {
    "DADE": "Miami-Dade",
    "DE SOTO": "DeSoto",
    "PUTNUM": "Putnam",        # NOAA typo in "Eastern/Western Putnum"
    "TROUT RIVER": "Duval",    # Jacksonville-area forecast zone
}


def _norm(text):
    text = str(text).upper().replace(".", "")
    for ch in "-/":
        text = text.replace(ch, " ")
    return " " + text + " "


# Longest names first so "Indian River" wins before shorter matches
_PATTERNS = sorted(
    [(_norm(c), c) for c in FL_COUNTIES] + [(_norm(a), c) for a, c in ALIASES.items()],
    key=lambda p: -len(p[0]),
)


def to_county(area_name, area_type):
    """Map 'Coastal Lee', 'Inland Hillsborough', etc. to the real county."""
    if area_type == "marine" or pd.isna(area_name):
        return None
    name = _norm(area_name)
    for pattern, county in _PATTERNS:
        if pattern in name:
            return county
    return None


def parse_damage(value):
    """NOAA writes damage like '10.00K' or '2.5M'. Convert to dollars."""
    if pd.isna(value):
        return 0.0
    text = str(value).strip().upper()
    multipliers = {"K": 1e3, "M": 1e6, "B": 1e9}
    try:
        if text and text[-1] in multipliers:
            return float(text[:-1] or 0) * multipliers[text[-1]]
        return float(text)
    except ValueError:
        return 0.0


def main():
    files = sorted(glob.glob("StormEvents_details-*.csv*"))
    if not files:
        raise SystemExit("No StormEvents_details files found in this folder.")
    print(f"Loading {len(files)} file(s)...")

    df = pd.concat(
        (pd.read_csv(f, usecols=COLUMNS, low_memory=False) for f in files),
        ignore_index=True,
    )
    df = df[df["STATE"] == "FLORIDA"].copy()

    df["event_date"] = pd.to_datetime(
        df["BEGIN_YEARMONTH"].astype(str) + df["BEGIN_DAY"].astype(str).str.zfill(2),
        format="%Y%m%d",
        errors="coerce",
    ).dt.date.astype(str)

    clean = pd.DataFrame({
        "event_id": df["EVENT_ID"],
        "episode_id": df["EPISODE_ID"],
        "year": df["YEAR"],
        "event_date": df["event_date"],
        "area_type": df["CZ_TYPE"].map({"C": "county", "Z": "forecast_zone", "M": "marine"}),
        "area_name": df["CZ_NAME"].str.title(),
        "event_type": df["EVENT_TYPE"],
        "injuries": df["INJURIES_DIRECT"].fillna(0).astype(int),
        "deaths": df["DEATHS_DIRECT"].fillna(0).astype(int),
        "property_damage_usd": df["DAMAGE_PROPERTY"].map(parse_damage),
        "crop_damage_usd": df["DAMAGE_CROPS"].map(parse_damage),
        "lat": df["BEGIN_LAT"],
        "lon": df["BEGIN_LON"],
    })

    clean["county"] = [
        to_county(n, t) for n, t in zip(clean["area_name"], clean["area_type"])
    ]
    unmatched = clean.loc[
        clean["county"].isna() & (clean["area_type"] != "marine"), "area_name"
    ].unique()
    if len(unmatched):
        print("Couldn't map these areas to a county:", ", ".join(sorted(unmatched)))

    with sqlite3.connect("storms.db") as conn:
        clean.to_sql("storm_events", conn, if_exists="replace", index=False)

    print(f"Loaded {len(clean):,} Florida events into storms.db")
    print(clean.groupby("year").size().to_string())


if __name__ == "__main__":
    main()
