/*
  mart_daily_volume.sql
  ======================
  Mart: number of articles published per calendar day.
  Used by Metabase "Évolution du Volume d'Articles" line chart.
*/

WITH base AS (
    SELECT * FROM {{ ref('stg_articles') }}
)

SELECT
    DATE_TRUNC('day', published_at)::DATE   AS published_date,
    COUNT(*)                                AS article_count,
    COUNT(DISTINCT source)                  AS active_sources
FROM base
WHERE published_at IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC
