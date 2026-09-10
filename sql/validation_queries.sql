-- ============================================================
-- BUSINFO 702 - Warehouse validation queries
-- Run against warehouse.db after build_warehouse.py completes.
-- These correspond to Member 2's Task F (data-quality validation).
-- ============================================================

-- 1. Row counts, compare against Member 1's documented source counts
--    Expect: DIM_PRODUCT ~112,522 (112,523 minus 1 documented duplicate)
--            DIM_COUNTRY ~190
--            FACT_COUNTRY_ECONOMIC ~1,611 (minus any unmatched country codes)
SELECT 'DIM_PRODUCT' AS table_name, COUNT(*) AS row_count FROM DIM_PRODUCT
UNION ALL
SELECT 'DIM_DATE', COUNT(*) FROM DIM_DATE
UNION ALL
SELECT 'DIM_YEAR', COUNT(*) FROM DIM_YEAR
UNION ALL
SELECT 'DIM_COUNTRY', COUNT(*) FROM DIM_COUNTRY
UNION ALL
SELECT 'DIM_LOCATION', COUNT(*) FROM DIM_LOCATION
UNION ALL
SELECT 'FACT_PRICE', COUNT(*) FROM FACT_PRICE
UNION ALL
SELECT 'FACT_COUNTRY_ECONOMIC', COUNT(*) FROM FACT_COUNTRY_ECONOMIC;

-- 2. Duplicate primary keys (should return 0 rows for every table)
SELECT barcode, COUNT(*) FROM DIM_PRODUCT GROUP BY barcode HAVING COUNT(*) > 1;
SELECT iso3, COUNT(*) FROM DIM_COUNTRY GROUP BY iso3 HAVING COUNT(*) > 1;
SELECT country_key, year_key, COUNT(*) FROM FACT_COUNTRY_ECONOMIC
  GROUP BY country_key, year_key HAVING COUNT(*) > 1;

-- 3. NULL checks on required fields (should return 0 for all)
SELECT COUNT(*) AS null_barcodes FROM DIM_PRODUCT WHERE barcode IS NULL;
SELECT COUNT(*) AS null_product_fk FROM FACT_PRICE WHERE product_key IS NULL;
SELECT COUNT(*) AS null_date_fk FROM FACT_PRICE WHERE date_key IS NULL;
SELECT COUNT(*) AS null_country_fk_econ FROM FACT_COUNTRY_ECONOMIC WHERE country_key IS NULL;
SELECT COUNT(*) AS null_year_fk FROM FACT_COUNTRY_ECONOMIC WHERE year_key IS NULL;

-- 4. Orphan foreign keys (rows in a fact table with no matching dimension row;
--    should return 0 for all)
SELECT COUNT(*) AS orphan_product
FROM FACT_PRICE f LEFT JOIN DIM_PRODUCT d ON f.product_key = d.product_key
WHERE d.product_key IS NULL;

SELECT COUNT(*) AS orphan_date
FROM FACT_PRICE f LEFT JOIN DIM_DATE d ON f.date_key = d.date_key
WHERE d.date_key IS NULL;

SELECT COUNT(*) AS orphan_country_econ
FROM FACT_COUNTRY_ECONOMIC f LEFT JOIN DIM_COUNTRY d ON f.country_key = d.country_key
WHERE d.country_key IS NULL;

SELECT COUNT(*) AS orphan_year
FROM FACT_COUNTRY_ECONOMIC f LEFT JOIN DIM_YEAR d ON f.year_key = d.year_key
WHERE d.year_key IS NULL;

-- 5. Invalid values: negative or zero prices, implausible values
SELECT COUNT(*) AS non_positive_prices FROM FACT_PRICE WHERE price <= 0;

-- 6. Hierarchy sanity check: how many products fell back to "Uncategorised"
--    (expected to be 47.2% per the real-data run documented in
--    Member2_Star_Schema_and_ELT.md)
SELECT
    dcat.category_top,
    COUNT(*) AS product_count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM DIM_PRODUCT), 1) AS pct_of_total
FROM DIM_PRODUCT dp
JOIN DIM_CATEGORY dcat ON dp.category_key = dcat.category_key
GROUP BY dcat.category_top
ORDER BY product_count DESC
LIMIT 10;

-- 7. Income group distribution (sanity check on the derived Hierarchy 2)
SELECT ig.label AS income_group, COUNT(*) AS country_count
FROM DIM_COUNTRY dc
JOIN DIM_INCOME_GROUP ig ON dc.income_group_key = ig.income_group_key
GROUP BY ig.label
ORDER BY country_count DESC;

-- 9. Orphan check: every product must resolve to a real category
--    (Variation 3: snowflaked DIM_CATEGORY)
SELECT COUNT(*) AS orphan_product_category
FROM DIM_PRODUCT p
LEFT JOIN DIM_CATEGORY c ON p.category_key = c.category_key
WHERE c.category_key IS NULL;

-- 10. Orphan check: every country must resolve to a real income group
--     (Variation 3: snowflaked DIM_INCOME_GROUP)
SELECT COUNT(*) AS orphan_country_income_group
FROM DIM_COUNTRY co
LEFT JOIN DIM_INCOME_GROUP ig ON co.income_group_key = ig.income_group_key
WHERE co.income_group_key IS NULL;

-- 11. Duplicate check: no duplicate (category_top, category_sub) pairs
SELECT category_top, category_sub, COUNT(*) AS n
FROM DIM_CATEGORY
GROUP BY category_top, category_sub
HAVING COUNT(*) > 1;

-- 12. DIM_INCOME_GROUP should have exactly 5 bands
SELECT COUNT(*) AS income_group_band_count FROM DIM_INCOME_GROUP;

-- 8. Time coverage check: confirm FACT_PRICE and FACT_COUNTRY_ECONOMIC
--    actually overlap in the 2017-2025 window Member 1 identified
SELECT MIN(year) AS min_year, MAX(year) AS max_year FROM DIM_DATE
WHERE date_key IN (SELECT DISTINCT date_key FROM FACT_PRICE);

SELECT MIN(year_key) AS min_year, MAX(year_key) AS max_year FROM FACT_COUNTRY_ECONOMIC;
