# Member 2: Star Schema & SQLite ELT

Main objective: convert the three validated datasets (Open Food Facts, Open Prices, World Bank
FPN + WDI) into a defensible dimensional warehouse, and document the full Extract, Load and
Transform process required by BUSINFO 702.

This builds directly on Member 1's feasibility findings: the 83.3 percent barcode match between
Open Food Facts and Open Prices, the 99.6 percent country match between Open Prices and the
World Bank data, and the 2017 to 2025 overlapping time window.

---

## Task A: Fact grain definitions

**FACT_PRICE**: one row represents one price observation, for one product, at one location, on
one date. Source: Open Prices, 304,936 raw rows, reduced to the subset with a valid product
match against Open Food Facts.

**FACT_COUNTRY_ECONOMIC**: one row represents one country's economic and diet affordability
snapshot for one year. Source: the pre-merged `country_context.csv`, 1,611 rows (country by
year).

These two facts sit at deliberately different grains, product/location/day versus country/year,
which is the second required attribute hierarchy and grain contrast for this assignment.

---

## Task B: Dimension design

**DIM_PRODUCT** (from `off_matched_clean.csv`)
- `product_key` (surrogate primary key)
- `barcode` (natural key, from `code`)
- `product_name` (from `product_name_final`)
- `brand` (from `brands`)
- `category_raw` (original full path string, kept for reference and auditing)
- `category_top` (Hierarchy 1, level 1, broadest)
- `category_sub` (Hierarchy 1, level 2, more specific)

**DIM_DATE** (built from distinct dates in Open Prices, the only dataset with genuine
transaction-level dates, per Member 1's Task C)
- `date_key` (surrogate, YYYYMMDD integer)
- `full_date`, `year`, `quarter`, `month`, `month_name`, `day`, `day_of_week`, `week_of_year`

**DIM_YEAR** (separate, lightweight dimension for the annual-grain fact, rather than forcing
country-year data down to a fabricated daily date)
- `year_key` (= year, surrogate not needed since year is already a natural integer key)
- `year`

**DIM_COUNTRY** (bridges Open Prices' 2-letter codes and World Bank's 3-letter codes, using the
ISO lookup table Member 1 already validated at a 99.6 percent match rate)
- `country_key` (surrogate primary key)
- `iso2`, `iso3`, `country_name`
- `income_group` (Hierarchy 2, derived, see decision below)

**DIM_LOCATION** (optional, from Open Prices' OpenStreetMap location fields, only populated
where available)
- `location_key`, `osm_id`, `latitude`, `longitude`, `location_type`, `country_key` (FK)

---

## Task C: Two documented decisions the team needs to sign off on

### Decision 1: Parsing `categories` into a two-level hierarchy

Member 1 confirmed `categories` is stored as one comma-separated string, broadest to most
specific (e.g. "Breakfasts, Spreads, Sweet spreads, Bee products, Farming products, Sweeteners,
Honeys"), with a variable number of levels per product and 46.6 percent of matched products
missing it entirely.

**Decision**: take only the first two comma-separated tokens.
- `category_top` = the first token (broadest)
- `category_sub` = the second token if it exists, otherwise `category_top` is repeated so no
  product has a NULL subcategory
- Products with no category string at all (46.6 percent) are assigned `'Uncategorised'` at both
  levels, rather than dropped, so they remain queryable but are clearly flagged as not
  contributing to category-level insight
- The literal string `"en:null"` found in one record is treated as equivalent to a missing
  category, not as a real category value, per Member 1's data-quality note

This keeps the hierarchy usable without inventing categories that are not in the source data.

### Decision 2: Deriving `income_group` for Hierarchy 2

The World Bank country-context table does not include an income classification column directly.
Rather than leaving Country as a flat dimension with only one hierarchy in the whole warehouse,
`income_group` is derived from `gdp_per_capita` using standard World Bank income thresholds
(low, lower-middle, upper-middle, high income).

**This is flagged as an approximation, not an official World Bank classification for the given
year.** The real classification changes annually and is not present in the extracted data. This
should be described in the final report exactly as it is here: a reasonable derived attribute,
not a source-verified field.

---

## Task D: Star schema diagram

See `star_schema.mmd`. Two fact tables, five dimensions, two documented hierarchies:
Product to Category_Sub to Category_Top, and Country to Income_Group.

---

## Task E: ELT implementation

**Extract**: the three cleaned files Member 1 already produced (`off_matched_clean.csv`,
`Open Prices.parquet`, `country_context.csv`) are read directly, no re-cleaning of raw multi-
gigabyte sources is needed since that step is already done.

**Load and Transform**: implemented in `build_warehouse.py`. DuckDB is used only to read the
Parquet file (SQLite cannot read Parquet natively); every dimension and fact table is created and
populated inside the SQLite database itself using standard SQL executed through Python's
`sqlite3` interface, which is the practical way to combine string-parsing logic (category
splitting) with SQL table creation in a single documented, rerunnable script. All SQL statements
executed are printed and logged so they can be copied directly into the report.

**Validation**: `validation_queries.sql` contains the standalone checks: duplicate keys, orphan
foreign keys, NULL checks on required fields, and row-count reconciliation against Member 1's
documented source counts.

---

## Definition of done

A team member can open `warehouse.db`, understand the star schema from the diagram, rerun
`build_warehouse.py` end to end, and see the validation queries pass with results matching the
counts documented here and in Member 1's report.

---

## Real data run: results (verified, not projected)

The script was executed against the actual uploaded files (`off_matched_clean.csv`,
`Open Prices.parquet`, `country_context.csv`, `countries_iso3166b.csv`) and every validation
query was run against the resulting `warehouse.db`. All numbers below are real, not estimates.

### Row counts

| Table | Row count |
|---|---|
| DIM_PRODUCT | 112,523 |
| DIM_DATE | 2,098 |
| DIM_YEAR | 9 |
| DIM_COUNTRY | 179 |
| DIM_LOCATION | 6,307 |
| FACT_PRICE | 264,042 |
| FACT_COUNTRY_ECONOMIC | 1,611 |

DIM_PRODUCT (112,523) and FACT_COUNTRY_ECONOMIC (1,611) match Member 1's documented counts
exactly. FACT_PRICE (264,042) is lower than Open Prices' full 304,936 rows because it excludes
rows with no barcode at all (raw/unbarcoded items, a known and already-documented split in the
source data) and rows whose barcode did not match a product in DIM_PRODUCT. Of the 294,847
barcoded, priced rows, 264,042 matched a product (89.6 percent of price *rows*), a higher rate
than the 83.3 percent match on distinct *barcodes* Member 1 documented, which is expected since
matched products tend to have more price observations recorded against them than unmatched ones.

### Data-quality checks: all clean

- Duplicate barcodes in DIM_PRODUCT after dedup: 0
- Duplicate iso3 codes in DIM_COUNTRY: 0
- Duplicate country-year rows in FACT_COUNTRY_ECONOMIC: 0
- NULL barcodes: 0
- Orphan foreign keys (FACT_PRICE to DIM_PRODUCT, DIM_DATE; FACT_COUNTRY_ECONOMIC to
  DIM_COUNTRY, DIM_YEAR): 0 in every case
- Time overlap confirmed: FACT_PRICE spans 2010 to 2026, FACT_COUNTRY_ECONOMIC spans 2017 to
  2025, so the full economic time series sits inside the price data's range

### Two new findings, not in Member 1's original report

**1. Six price observations have a price of exactly 0.00 (all in EUR).** This was not caught by
Member 1's original checks. It is a small number relative to 264,042 total price facts, but it
should be mentioned in the report as a known data-quality note. Recommendation: either exclude
these six rows from price-based analysis (they are likely free samples or a data entry artifact)
or flag them explicitly rather than silently including them in average price calculations.

**2. The `categories` field contains a second placeholder value not documented in Member 1's
report: the literal string `"undefined"` (654 products), in addition to `"en:null"` (1 product)
and genuinely empty values (52,475 products).** All three are now folded into `'Uncategorised'`
by the same rule. This raises the uncategorised share slightly from Member 1's documented 46.6
percent to 47.2 percent (53,138 of 112,523 products), which is worth a one-line update to Member
1's data-quality section for consistency.

**3. Fifteen countries end up with an `income_group` of `'Unknown'`** because their most recent
year of data has no `gdp_per_capita` value: Bahamas, South Sudan, Cayman Islands, Lebanon,
Bermuda, Turks and Caicos Islands, Aruba, British Virgin Islands, United Arab Emirates, Curacao,
Syrian Arab Republic, Bonaire, Taiwan, Anguilla, and Montserrat. This is a real gap in the World
Bank source data, not a join failure, all fifteen countries exist correctly in DIM_COUNTRY, they
simply have no GDP figure to classify against Hierarchy 2. Worth a one-line mention in the
report's limitations section.

### Category hierarchy, top values

The parsed `category_top` values confirm the hierarchy works as intended once uncategorised
products are set aside: leading real categories include Snacks (5,431 products), Plant-based
foods and beverages (5,346), Dairies (1,423 under the English label plus 2,461 more under the
French "Produits laitiers", a labelling inconsistency worth noting since Open Food Facts is
multi-language and category text was not translated during cleaning), and Beverages. This
multi-language category duplication (the same real category appearing under different language
labels) is a further data-quality nuance the team may want to address, either by translating
`category_top` values to a single language or by accepting it as a documented limitation.

### Files produced

- `warehouse.db`, the built SQLite warehouse, ready to query
- `elt_log.sql`, every CREATE TABLE, CREATE INDEX, and INSERT statement executed during the
  build, for the report's required "SQLite commands and SQL statements" section

