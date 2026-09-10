CREATE TABLE DIM_CATEGORY (
            category_key  INTEGER PRIMARY KEY AUTOINCREMENT,
            category_top  TEXT NOT NULL,
            category_sub  TEXT NOT NULL,
            UNIQUE(category_top, category_sub)
        );

CREATE TABLE DIM_PRODUCT (
            product_key   INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode       TEXT UNIQUE NOT NULL,
            product_name  TEXT,
            brand         TEXT,
            category_raw  TEXT,
            category_key  INTEGER NOT NULL REFERENCES DIM_CATEGORY(category_key)
        );

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
        );

CREATE TABLE DIM_YEAR (
            year_key INTEGER PRIMARY KEY
        );

CREATE TABLE DIM_INCOME_GROUP (
            income_group_key  INTEGER PRIMARY KEY AUTOINCREMENT,
            label             TEXT UNIQUE NOT NULL,
            gdp_lower_bound   REAL,
            gdp_upper_bound   REAL
        );

CREATE TABLE DIM_COUNTRY (
            country_key       INTEGER PRIMARY KEY AUTOINCREMENT,
            iso2              TEXT,
            iso3              TEXT UNIQUE,
            country_name      TEXT,
            income_group_key  INTEGER REFERENCES DIM_INCOME_GROUP(income_group_key)
        );

CREATE TABLE DIM_LOCATION (
            location_key   INTEGER PRIMARY KEY AUTOINCREMENT,
            osm_id         TEXT,
            latitude       REAL,
            longitude      REAL,
            location_type  TEXT,
            country_key    INTEGER REFERENCES DIM_COUNTRY(country_key)
        );

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
        );

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
        );

CREATE INDEX idx_fact_price_product ON FACT_PRICE(product_key);

CREATE INDEX idx_fact_price_date ON FACT_PRICE(date_key);

CREATE INDEX idx_fact_price_country ON FACT_PRICE(country_key);

CREATE INDEX idx_fact_econ_country ON FACT_COUNTRY_ECONOMIC(country_key);

CREATE INDEX idx_product_category ON DIM_PRODUCT(category_key);

CREATE INDEX idx_country_income_group ON DIM_COUNTRY(income_group_key);

INSERT INTO DIM_INCOME_GROUP (label, gdp_lower_bound, gdp_upper_bound)
        VALUES (?, ?, ?);  -- (executemany, batch load)

SELECT label, income_group_key FROM DIM_INCOME_GROUP;

INSERT INTO DIM_CATEGORY (category_top, category_sub)
        VALUES (?, ?);  -- (executemany, batch load)

SELECT category_top, category_sub, category_key FROM DIM_CATEGORY;

INSERT INTO DIM_PRODUCT (barcode, product_name, brand, category_raw, category_key)
        VALUES (?, ?, ?, ?, ?);  -- (executemany, batch load)

INSERT INTO DIM_COUNTRY (iso2, iso3, country_name, income_group_key)
        VALUES (?, ?, ?, ?);  -- (executemany, batch load)

SELECT iso3, country_key FROM DIM_COUNTRY;

SELECT iso2, country_key FROM DIM_COUNTRY WHERE iso2 IS NOT NULL;

INSERT INTO DIM_YEAR (year_key) VALUES (?);  -- (executemany, batch load)

INSERT OR IGNORE INTO FACT_COUNTRY_ECONOMIC
            (country_key, year_key, cost_healthy_diet_ppp, affordability_ratio,
             pct_cannot_afford_healthy_diet, veg_cost_share, population,
             gdp_per_capita, poverty_headcount_pct, food_insecurity_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);  -- (executemany, batch load)

INSERT OR IGNORE INTO DIM_DATE
            (date_key, full_date, year, quarter, month, month_name, day, day_of_week, week_of_year)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);  -- (executemany, batch load)

INSERT INTO DIM_LOCATION (osm_id, latitude, longitude, location_type, country_key)
        VALUES (?, ?, ?, ?, ?);  -- (executemany, batch load)

SELECT osm_id, location_key FROM DIM_LOCATION;

SELECT barcode, product_key FROM DIM_PRODUCT;

INSERT INTO FACT_PRICE
            (product_key, date_key, location_key, country_key, price,
             price_without_discount, currency, is_discounted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);  -- (executemany, batch load)

