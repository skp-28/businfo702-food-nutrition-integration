# Food Prices, Nutrition and Socioeconomic Wellbeing
### A Global Data Integration Study, BUSINFO 702, University of Auckland

This project integrates three public datasets into a single SQLite data warehouse to examine how retail food prices, product characteristics, and country-level socioeconomic conditions relate to one another.

## Project Summary

The warehouse holds two fact tables at two different grains:

- **FACT_PRICE** (264,042 rows): one product/location/date price observation
- **FACT_COUNTRY_ECONOMIC** (1,611 rows): one country-year economic record

These grains are never merged directly; `FACT_PRICE` is aggregated to country-year before any joint analysis. Four validated research questions examine affordability across income groups, the GDP-affordability relationship, price volatility within France's retail market, and an integrated temporal pattern between diet costs and retail prices.

Full methodology, SQL, and findings are documented in `docs/` and the final report.

## Data Sources

| Source | Content | Format |
|---|---|---|
| [Open Food Facts](https://huggingface.co/datasets/openfoodfacts/product-database) | Product identity, brand, category | Parquet |
| [Open Prices](https://huggingface.co/datasets/openfoodfacts/open-prices) | Retail price observations | Parquet |
| [World Bank Food Prices for Nutrition + World Development Indicators](https://databank.worldbank.org/source/food-prices-for-nutrition) | Country-year affordability and economic indicators | CSV |

## Repository Structure

```
├── data/                # Cleaned datasets used to build the warehouse
│   └── LARGE_FILES.md   # Links to oversized source files hosted on Google Drive
├── scripts/             # Python ELT pipeline (extraction, transformation, loading)
│   └── build_warehouse.py
├── sql/                 # SQL used for warehouse construction and validation
│   ├── elt_log.sql
│   └── validation_queries.sql
├── docs/                # Star schema design and ELT documentation
│   ├── star_schema_and_elt.md
│   └── star_schema.mmd
├── warehouse/           # The built SQLite data warehouse
│   └── warehouse.db
├── dashboard/           # Visual analytics: charts and the script that generates them
│   ├── build_figures.py
│   └── Figure2 to Figure7 (PNG)
├── .gitignore
└── README.md
```

## Large Files

Two source files exceed GitHub's 100MB limit and are not stored in this repository. They are linked and documented in [`data/LARGE_FILES.md`](data/LARGE_FILES.md):

- `food.parquet` (7.29 GB)
- `off_matched.csv` (2.28 GB)

## Data Warehouse Design

A dimensional star schema with two fact tables sharing `DIM_COUNTRY`, seven dimension tables, and two documented attribute hierarchies:

- **Product hierarchy**: `DIM_PRODUCT` to `DIM_CATEGORY` (Category_Sub to Category_Top)
- **Geography/economic hierarchy**: `DIM_COUNTRY` to `DIM_INCOME_GROUP`

Both hierarchies are snowflaked into their own dimension tables rather than stored as flat text columns, so each is a real queryable table with its own key. Full design detail, including the reasoning behind this decision, is in [`docs/star_schema_and_elt.md`](docs/star_schema_and_elt.md) and the diagram in [`docs/star_schema.mmd`](docs/star_schema.mmd).

## Running the Pipeline

**Requirements:**
- Python 3.x with `pandas` and `sqlite3`
- [DuckDB](https://duckdb.org/) (used to read Parquet files directly, not bundled in this repo)

**Steps:**
1. Ensure the source files listed in `data/` (and the two large files linked in `LARGE_FILES.md`) are available locally.
2. Run `scripts/build_warehouse.py` to extract, transform, and load the data into `warehouse/warehouse.db`.
3. Run the checks in `sql/validation_queries.sql` to confirm referential integrity.
4. Run `dashboard/build_figures.py` to regenerate the Section 7 visual analytics charts.

## Team

| Name | Role |
|---|---|
| Courtenay Baker | Dataset Investigation & Integration Lead |
| Prasad Santhi Kumaresan | Star Schema & SQLite ELT Lead |
| Thuslimah Rahiman Sowkat Ali | Research Questions & SQL Analytics Lead |
| Mahadhir Sathik Batcha | Visual Storytelling Lead |

## Limitations

Key limitations, including France's 67.7% share of price observations and 47.2% of products lacking a usable category, are documented in full in the final report and should be read before drawing conclusions from the warehouse.