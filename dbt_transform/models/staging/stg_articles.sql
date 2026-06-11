/*
  stg_articles.sql
  ================
  Staging model: cleans and standardises raw articles from the Gold source table.

  Transformations applied:
  - Rename columns to snake_case conventions
  - Cast date strings to proper TIMESTAMP
  - Trim whitespace from text fields
  - Filter out records missing id, title or content
  - Deduplicate on article id (keep latest processed_at)
*/

WITH source AS (

    SELECT * FROM {{ source('gold', 'articles_gold') }}

),

deduplicated AS (

    -- Some articles may have been re-ingested; keep only the latest version
    SELECT DISTINCT ON (id)
        id,
        title,
        author,
        category,
        content,
        source,
        url,
        date,
        processed_at,
        processed_by
    FROM source
    ORDER BY id, processed_at DESC

),

cleaned AS (

    SELECT
        id                                          AS article_id,
        TRIM(title)                                 AS title,
        TRIM(LOWER(author))                         AS author,
        COALESCE(NULLIF(TRIM(category), ''), 'General') AS category,
        TRIM(content)                               AS content,
        source,
        url,
        -- date column is stored as TIMESTAMP; cast to TEXT for regex, then back
        CASE
            WHEN date::TEXT ~ '^\d{4}-\d{2}-\d{2}' THEN date::TIMESTAMP
            ELSE processed_at::TIMESTAMP
        END                                         AS published_at,
        processed_at::TIMESTAMP                     AS ingested_at
    FROM deduplicated
    WHERE
        id      IS NOT NULL
        AND title   IS NOT NULL
        AND content IS NOT NULL
        AND LENGTH(TRIM(content)) > 10  -- filter out near-empty content

)

SELECT * FROM cleaned
