/*
  mart_top_authors.sql
  =====================
  Mart: top authors ranked by total number of articles published.
  Used by Metabase "Top 10 Auteurs" row chart.
*/

WITH base AS (
    SELECT * FROM {{ ref('stg_articles') }}
)

SELECT
    author,
    COUNT(*)                AS article_count,
    COUNT(DISTINCT source)  AS sources_written_for,
    MAX(published_at)       AS latest_article_date
FROM base
WHERE author IS NOT NULL
GROUP BY author
ORDER BY article_count DESC
LIMIT 20
