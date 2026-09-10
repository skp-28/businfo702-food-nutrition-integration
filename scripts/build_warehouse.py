"""
BUSINFO 702 - Food Prices, Nutrition and Socioeconomic Wellbeing
Member 2: Star Schema & SQLite ELT

Builds warehouse.db from the three files Member 1 already validated:
  - off_matched_clean.csv   (Open Food Facts, filtered to products that also
                              appear in Open Prices; 112,523 rows expected)
  - Open Prices.parquet     (304,936 rows expected)
  - country_context.csv     (World Bank FPN + WDI merged; 1,611 rows expected)

Usage:
    pip install duckdb --break-system-packages
    python build_warehouse.py

Place this script in the same folder as the three input files, or edit the
paths in the CONFIG section below. Every SQL statement executed against
SQLite is printed to the console (and to elt_log.sql) so it can be copied
directly into the project report's "SQLite commands and SQL statements" section.
"""

import sqlite3
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import duckdb
except ImportError:
    sys.exit(
        "This script needs DuckDB to read the Open Prices Parquet file.\n"
        "Install it with: pip install duckdb --break-system-packages"
    )

try:
    import pandas as pd
except ImportError:
    sys.exit(
        "This script needs pandas.\n"
        "Install it with: pip install pandas --break-system-packages"
    )

# ---------------------------------------------------------------------------
# CONFIG - edit these paths if your files are named or located differently
# ---------------------------------------------------------------------------
OFF_MATCHED_CSV = "off_matched_clean.csv"
OPEN_PRICES_PARQUET = "Open_Prices.parquet"
COUNTRY_CONTEXT_CSV = "country_context.csv"
ISO_LOOKUP_CSV = "countries_iso3166b.csv"   # iso2,iso3 lookup Member 1 already used
DB_PATH = "warehouse.db"
SQL_LOG_PATH = "elt_log.sql"

# World Bank income group thresholds (GNI/GDP per capita, USD).
# NOTE: this is a documented approximation, not an official World Bank
# income classification for a specific fiscal year - see design doc.
INCOME_THRESHOLDS = [
    (1145, "Low income"),
    (4515, "Lower-middle income"),
    (14005, "Upper-middle income"),
    (float("inf"), "High income"),
]


def classify_income(gdp_per_capita):
    if gdp_per_capita is None:
        return "Unknown"
    for threshold, label in INCOME_THRESHOLDS:
        if gdp_per_capita <= threshold:
            return label
    return "Unknown"


# Income band bounds for DIM_INCOME_GROUP (Variation 3: snowflaked hierarchy).
# (label, lower_bound, upper_bound) - bounds are None where open-ended.
INCOME_GROUP_BANDS = [
    ("Low income", None, 1145),
    ("Lower-middle income", 1145, 4515),
    ("Upper-middle income", 4515, 14005),
    ("High income", 14005, None),
    ("Unknown", None, None),
]


def split_categories(categories_raw):
    """Return (category_top, category_sub) from a comma-separated hierarchy
    string, treating missing values, the literal 'en:null', and the literal
    'undefined' as 'Uncategorised' at both levels, per the documented Task C
    decision (the 'undefined' variant was found during the real-data run and
    was not in Member 1's original documented list, but is the same kind of
    source-system artifact as 'en:null')."""
    if categories_raw is None:
        return "Uncategorised", "Uncategorised"
    cleaned = categories_raw.strip()
    if cleaned == "" or cleaned.lower() in ("en:null", "undefined", "null"):
        return "Uncategorised", "Uncategorised"
    parts = [p.strip() for p in categories_raw.split(",") if p.strip()]
    if not parts:
        return "Uncategorised", "Uncategorised"
    top = parts[0]
    sub = parts[1] if len(parts) > 1 else parts[0]
    return top, sub


def safe_dictreader_rows(path):
    """Read a CSV file as a list of dict rows, skipping any individual line
    that fails UTF-8 decoding rather than crashing the whole import. Member 1
    documented exactly this kind of encoding issue in the ISO lookup table
    (Curacao and Cote d'Ivoire, both containing accented characters), so
    dropping the malformed row and continuing is the same decision already
    made for that file, applied consistently to every CSV input."""
    good_lines = []
    skipped = 0
    with open(path, "rb") as f:
        for raw_line in f:
            try:
                good_lines.append(raw_line.decode("utf-8"))
            except UnicodeDecodeError:
                skipped += 1
    if skipped:
        print(f"  (skipped {skipped} line(s) in {path} due to a UTF-8 encoding error)")
    reader = csv.DictReader(good_lines)
    return list(reader)


def clean_val(v):
    """Convert pandas/numpy NaN, NaT, and pd.NA into a plain Python None so
    sqlite3 can bind the value; leave everything else untouched."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


class SqlLogger:
    """Wraps a sqlite3 connection so every executed statement is printed
    and appended to a log file, satisfying the assignment's requirement to
    preserve all SQLite commands used."""

    def __init__(self, conn, log_path):
        self.conn = conn
        self.log_file = open(log_path, "w", encoding="utf-8")

    def execute(self, sql, params=None):
        self.log_file.write(sql.strip() + ";\n\n")
        print(sql.strip()[:120].replace("\n", " ") + (" ..." if len(sql) > 120 else ""))
        if params is not None:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def executemany(self, sql, seq_of_params):
        self.log_file.write(sql.strip() + ";  -- (executemany, batch load)\n\n")
        print(sql.strip()[:120].replace("\n", " ") + " ... (batch)")
        return self.conn.executemany(sql, seq_of_params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.log_file.close()
        self.conn.close()


def main():
    for required in [OFF_MATCHED_CSV, OPEN_PRICES_PARQUET, COUNTRY_CONTEXT_CSV, ISO_LOOKUP_CSV]:
        if not Path(required).exists():
            print(f"WARNING: expected input file not found: {required}")
            print("Edit the CONFIG section at the top of this script if your filenames differ.\n")

    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()

    conn = sqlite3.connect(DB_PATH)
    db = SqlLogger(conn, SQL_LOG_PATH)

    # =======================================================================
    # SCHEMA (DDL)
    # =======================================================================
    print("\n=== Creating schema ===")

    db.execute("""
        CREATE TABLE DIM_CATEGORY (
            category_key  INTEGER PRIMARY KEY AUTOINCREMENT,
            category_top  TEXT NOT NULL,
            category_sub  TEXT NOT NULL,
            UNIQUE(category_top, category_sub)
        )
    """)

    db.execute("""
        CREATE TABLE DIM_PRODUCT (
            product_key   INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode       TEXT UNIQUE NOT NULL,
            product_name  TEXT,
            brand         TEXT,
            category_raw  TEXT,
            category_key  INTEGER NOT NULL REFERENCES DIM_CATEGORY(category_key)
        )
    """)

    db.execute("""
        CREATE TABLE DIM_DATE (
            date_key      INTEGER PRIMARY KEY,
            full_date     TEXT NOT NULL,
            year          INTEGER NOT NULL,
            quarter       INTEGER NOT NULL,
            month         INTEGER NOT NULL,
            month_name    TEXT NOT NULL,
            day           INTEGER NOT NULL,
            day_of_week   TEXT NOT NULL,
            week_of_year  INTEGER NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE DIM_YEAR (
            year_key INTEGER PRIMARY KEY
        )
    """)

    db.execute("""
        CREATE TABLE DIM_INCOME_GROUP (
            income_group_key  INTEGER PRIMARY KEY AUTOINCREMENT,
            label             TEXT UNIQUE NOT NULL,
            gdp_lower_bound   REAL,
            gdp_upper_bound   REAL
        )
    """)

    db.execute("""
        CREATE TABLE DIM_COUNTRY (
            country_key       INTEGER PRIMARY KEY AUTOINCREMENT,
            iso2              TEXT,
            iso3              TEXT UNIQUE,
            country_name      TEXT,
            income_group_key  INTEGER REFERENCES DIM_INCOME_GROUP(income_group_key)
        )
    """)

    db.execute("""
        CREATE TABLE DIM_LOCATION (
            location_key   INTEGER PRIMARY KEY AUTOINCREMENT,
            osm_id         TEXT,
            latitude       REAL,
            longitude      REAL,
            location_type  TEXT,
            country_key    INTEGER REFERENCES DIM_COUNTRY(country_key)
        )
    """)

    db.execute("""
        CREATE TABLE FACT_PRICE (
            price_key                INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key               INTEGER NOT NULL REFERENCES DIM_PRODUCT(product_key),
            date_key                  INTEGER NOT NULL REFERENCES DIM_DATE(date_key),
            location_key              INTEGER REFERENCES DIM_LOCATION(location_key),
            country_key               INTEGER REFERENCES DIM_COUNTRY(country_key),
            price                     REAL,
            price_without_discount    REAL,
            currency                  TEXT,
            is_discounted             INTEGER
        )
    """)

    db.execute("""
        CREATE TABLE FACT_COUNTRY_ECONOMIC (
            economic_key                    INTEGER PRIMARY KEY AUTOINCREMENT,
            country_key                     INTEGER NOT NULL REFERENCES DIM_COUNTRY(country_key),
            year_key                        INTEGER NOT NULL REFERENCES DIM_YEAR(year_key),
            cost_healthy_diet_ppp           REAL,
            affordability_ratio             REAL,
            pct_cannot_afford_healthy_diet  REAL,
            veg_cost_share                  REAL,
            population                      REAL,
            gdp_per_capita                  REAL,
            poverty_headcount_pct           REAL,
            food_insecurity_pct             REAL,
            UNIQUE(country_key, year_key)
        )
    """)

    db.execute("CREATE INDEX idx_fact_price_product ON FACT_PRICE(product_key)")
    db.execute("CREATE INDEX idx_fact_price_date ON FACT_PRICE(date_key)")
    db.execute("CREATE INDEX idx_fact_price_country ON FACT_PRICE(country_key)")
    db.execute("CREATE INDEX idx_fact_econ_country ON FACT_COUNTRY_ECONOMIC(country_key)")
    db.execute("CREATE INDEX idx_product_category ON DIM_PRODUCT(category_key)")
    db.execute("CREATE INDEX idx_country_income_group ON DIM_COUNTRY(income_group_key)")
    db.commit()

    # =======================================================================
    # LOAD: DIM_INCOME_GROUP (Variation 3: snowflaked income hierarchy)
    # =======================================================================
    print("\n=== Loading DIM_INCOME_GROUP ===")
    db.executemany("""
        INSERT INTO DIM_INCOME_GROUP (label, gdp_lower_bound, gdp_upper_bound)
        VALUES (?, ?, ?)
    """, INCOME_GROUP_BANDS)
    db.commit()
    income_group_key_by_label = dict(
        db.execute("SELECT label, income_group_key FROM DIM_INCOME_GROUP").fetchall()
    )
    print(f"Loaded {len(INCOME_GROUP_BANDS)} income group bands")

    # =======================================================================
    # LOAD + TRANSFORM: DIM_CATEGORY, then DIM_PRODUCT
    # (from off_matched_clean.csv; Variation 3: snowflaked category hierarchy)
    # =======================================================================
    print("\n=== Loading DIM_PRODUCT ===")
    product_rows = []
    for row in safe_dictreader_rows(OFF_MATCHED_CSV):
        barcode = row.get("code")
        if not barcode:
            continue
        category_raw = row.get("categories", "")
        category_top, category_sub = split_categories(category_raw)
        product_rows.append((
            barcode,
            row.get("product_name_final") or None,
            row.get("brands") or None,
            category_raw or None,
            category_top,
            category_sub,
        ))

    # de-duplicate on barcode, keeping the first occurrence
    # (Member 1 documented exactly 1 duplicate barcode in this file)
    seen = set()
    deduped = []
    for r in product_rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        deduped.append(r)

    # build DIM_CATEGORY from the distinct (category_top, category_sub) pairs
    # found across all products, then insert products against category_key
    distinct_categories = sorted(set((r[4], r[5]) for r in deduped))
    db.executemany("""
        INSERT INTO DIM_CATEGORY (category_top, category_sub)
        VALUES (?, ?)
    """, distinct_categories)
    db.commit()
    category_key_by_pair = dict(
        (
            (top, sub), key
        ) for top, sub, key in db.execute(
            "SELECT category_top, category_sub, category_key FROM DIM_CATEGORY"
        ).fetchall()
    )
    print(f"Loaded {len(distinct_categories)} distinct categories")

    product_insert_rows = [
        (r[0], r[1], r[2], r[3], category_key_by_pair[(r[4], r[5])])
        for r in deduped
    ]
    db.executemany("""
        INSERT INTO DIM_PRODUCT (barcode, product_name, brand, category_raw, category_key)
        VALUES (?, ?, ?, ?, ?)
    """, product_insert_rows)
    db.commit()
    print(f"Loaded {len(deduped)} products ({len(product_rows) - len(deduped)} duplicate barcode(s) skipped)")

    # =======================================================================
    # LOAD + TRANSFORM: DIM_COUNTRY (from country_context.csv + ISO lookup)
    # =======================================================================
    print("\n=== Loading DIM_COUNTRY ===")

    iso_lookup = {}  # iso3 -> iso2
    for row in safe_dictreader_rows(ISO_LOOKUP_CSV):
        iso3 = row.get("iso3")
        iso2 = row.get("iso2")
        if iso3 and iso2:
            iso_lookup[iso3] = iso2

    # gather one representative row per country (most recent year) to
    # derive income_group and country_name; keep the full country_context
    # rows for the fact table load below
    country_context_rows = safe_dictreader_rows(COUNTRY_CONTEXT_CSV)

    latest_by_country = {}
    for row in country_context_rows:
        code = row.get("country_code")
        if not code:
            continue
        year = int(row["year"]) if row.get("year") else None
        if code not in latest_by_country or (year and year > latest_by_country[code]["year"]):
            latest_by_country[code] = {**row, "year": year}

    country_rows = []
    for iso3, row in latest_by_country.items():
        gdp = float(row["gdp_per_capita"]) if row.get("gdp_per_capita") else None
        income_label = classify_income(gdp)
        country_rows.append((
            iso_lookup.get(iso3),
            iso3,
            row.get("country_name"),
            income_group_key_by_label[income_label],
        ))

    db.executemany("""
        INSERT INTO DIM_COUNTRY (iso2, iso3, country_name, income_group_key)
        VALUES (?, ?, ?, ?)
    """, country_rows)
    db.commit()
    print(f"Loaded {len(country_rows)} countries")

    country_key_by_iso3 = dict(
        db.execute("SELECT iso3, country_key FROM DIM_COUNTRY").fetchall()
    )
    country_key_by_iso2 = {
        r[0]: r[1] for r in db.execute(
            "SELECT iso2, country_key FROM DIM_COUNTRY WHERE iso2 IS NOT NULL"
        ).fetchall()
    }

    # =======================================================================
    # LOAD: DIM_YEAR
    # =======================================================================
    print("\n=== Loading DIM_YEAR ===")
    years = sorted(set(int(r["year"]) for r in country_context_rows if r.get("year")))
    db.executemany("INSERT INTO DIM_YEAR (year_key) VALUES (?)", [(y,) for y in years])
    db.commit()
    print(f"Loaded {len(years)} years: {years[0]}-{years[-1]}" if years else "No years found")

    # =======================================================================
    # LOAD + TRANSFORM: FACT_COUNTRY_ECONOMIC
    # =======================================================================
    print("\n=== Loading FACT_COUNTRY_ECONOMIC ===")
    econ_rows = []
    for row in country_context_rows:
        iso3 = row.get("country_code")
        year = row.get("year")
        if not iso3 or not year or iso3 not in country_key_by_iso3:
            continue

        def f(field):
            v = row.get(field)
            return float(v) if v not in (None, "") else None

        econ_rows.append((
            country_key_by_iso3[iso3],
            int(year),
            f("cost_healthy_diet_ppp"),
            f("affordability_ratio"),
            f("pct_cannot_afford_healthy_diet"),
            f("veg_cost_share"),
            f("population"),
            f("gdp_per_capita"),
            f("poverty_headcount_pct"),
            f("food_insecurity_pct"),
        ))

    db.executemany("""
        INSERT OR IGNORE INTO FACT_COUNTRY_ECONOMIC
            (country_key, year_key, cost_healthy_diet_ppp, affordability_ratio,
             pct_cannot_afford_healthy_diet, veg_cost_share, population,
             gdp_per_capita, poverty_headcount_pct, food_insecurity_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, econ_rows)
    db.commit()
    print(f"Loaded {len(econ_rows)} country-year economic rows")

    # =======================================================================
    # EXTRACT (via DuckDB) + LOAD + TRANSFORM: DIM_DATE, DIM_LOCATION, FACT_PRICE
    # =======================================================================
    print("\n=== Reading Open Prices via DuckDB ===")
    duck = duckdb.connect()
    price_df = duck.execute(f"""
        SELECT
            product_code,
            price,
            price_without_discount,
            currency,
            price_is_discounted,
            date,
            location_osm_id,
            location_osm_address_country_code,
            location_osm_lat,
            location_osm_lon,
            location_type
        FROM '{OPEN_PRICES_PARQUET}'
        WHERE product_code IS NOT NULL AND date IS NOT NULL
    """).fetchdf()
    print(f"Read {len(price_df)} priced, barcoded rows from Open Prices")

    print("\n=== Loading DIM_DATE ===")
    distinct_dates = sorted(set(price_df["date"].astype(str)))
    date_rows = []
    for d in distinct_dates:
        try:
            dt = datetime.strptime(d[:10], "%Y-%m-%d")
        except ValueError:
            continue
        date_key = int(dt.strftime("%Y%m%d"))
        date_rows.append((
            date_key, dt.strftime("%Y-%m-%d"), dt.year,
            (dt.month - 1) // 3 + 1, dt.month, dt.strftime("%B"),
            dt.day, dt.strftime("%A"), int(dt.strftime("%W")),
        ))
    db.executemany("""
        INSERT OR IGNORE INTO DIM_DATE
            (date_key, full_date, year, quarter, month, month_name, day, day_of_week, week_of_year)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, date_rows)
    db.commit()
    print(f"Loaded {len(date_rows)} distinct dates")

    print("\n=== Loading DIM_LOCATION ===")
    loc_seen = {}
    location_rows = []
    for _, r in price_df.drop_duplicates(subset=["location_osm_id"]).iterrows():
        osm_id = clean_val(r["location_osm_id"])
        iso2 = clean_val(r["location_osm_address_country_code"])
        country_key = country_key_by_iso2.get(iso2)
        location_rows.append((
            osm_id, clean_val(r["location_osm_lat"]), clean_val(r["location_osm_lon"]),
            clean_val(r["location_type"]), country_key
        ))
    db.executemany("""
        INSERT INTO DIM_LOCATION (osm_id, latitude, longitude, location_type, country_key)
        VALUES (?, ?, ?, ?, ?)
    """, location_rows)
    db.commit()
    location_key_by_osm = dict(
        db.execute("SELECT osm_id, location_key FROM DIM_LOCATION").fetchall()
    )
    print(f"Loaded {len(location_rows)} locations")

    print("\n=== Loading FACT_PRICE ===")
    product_key_by_barcode = dict(
        db.execute("SELECT barcode, product_key FROM DIM_PRODUCT").fetchall()
    )

    fact_rows = []
    skipped_no_product = 0
    for _, r in price_df.iterrows():
        barcode = clean_val(r["product_code"])
        product_key = product_key_by_barcode.get(barcode)
        if product_key is None:
            skipped_no_product += 1
            continue
        try:
            dt = datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
            date_key = int(dt.strftime("%Y%m%d"))
        except ValueError:
            continue
        location_key = location_key_by_osm.get(clean_val(r["location_osm_id"]))
        country_key = country_key_by_iso2.get(clean_val(r["location_osm_address_country_code"]))
        fact_rows.append((
            product_key, date_key, location_key, country_key,
            clean_val(r["price"]), clean_val(r["price_without_discount"]), clean_val(r["currency"]),
            1 if clean_val(r["price_is_discounted"]) else 0,
        ))

    db.executemany("""
        INSERT INTO FACT_PRICE
            (product_key, date_key, location_key, country_key, price,
             price_without_discount, currency, is_discounted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, fact_rows)
    db.commit()
    print(f"Loaded {len(fact_rows)} price facts ({skipped_no_product} rows skipped: barcode not in DIM_PRODUCT)")

    db.close()
    print(f"\nDone. Warehouse written to {DB_PATH}. SQL log written to {SQL_LOG_PATH}.")
    print("Next step: run validation_queries.sql against warehouse.db")


if __name__ == "__main__":
    main()
