/*
  mart_articles_by_category.sql
  ==============================
  Mart: article count grouped by editorial category.
  Used by Metabase "Articles par Catégorie" bar chart.
*/

WITH base AS (
    SELECT * FROM {{ ref('stg_articles') }}
)

SELECT
    category,
    COUNT(*)                AS article_count,
    COUNT(DISTINCT source)  AS source_count,
    MAX(ingested_at)        AS last_ingested_at
FROM base
GROUP BY category
ORDER BY article_count DESC
