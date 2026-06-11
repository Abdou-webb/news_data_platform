/*
  mart_articles_by_source.sql
  ============================
  Mart: total articles per RSS source with latest ingestion timestamp.
  Used by Metabase "Répartition par Source" pie chart.
*/

WITH base AS (
    SELECT * FROM {{ ref('stg_articles') }}
)

SELECT
    source,
    COUNT(*)                AS article_count,
    MAX(ingested_at)        AS last_ingested_at,
    MIN(published_at)       AS first_article_date,
    MAX(published_at)       AS last_article_date
FROM base
GROUP BY source
ORDER BY article_count DESC
