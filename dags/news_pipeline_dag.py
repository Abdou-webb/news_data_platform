from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data_engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "news_pipeline_dag",
    default_args=default_args,
    description="Batch pipeline: RSS → Bronze → Silver → Gold → dbt models + tests",
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["news", "batch", "bronze", "silver", "gold", "dbt"],
) as dag:

    # Task 1 — Scrape RSS feeds and store raw JSON in Bronze (MinIO / S3)
    scrape_and_ingest = BashOperator(
        task_id="scrape_rss_to_bronze",
        bash_command="python /opt/airflow/scrapers/batch_to_minio.py",
        append_env=True,
    )

    # Task 2 — Strip HTML, deduplicate, write clean JSON to Silver
    clean_bronze_to_silver = BashOperator(
        task_id="clean_bronze_to_silver",
        bash_command="python /opt/airflow/transformations/clean_bronze_to_silver.py",
        append_env=True,
    )

    # Task 3 — Load Silver JSON into PostgreSQL Gold table
    load_silver_to_gold = BashOperator(
        task_id="load_silver_to_gold",
        bash_command="python /opt/airflow/transformations/silver_to_gold.py",
        append_env=True,
    )

    # Task 4 — Run dbt: transform Gold into staging + mart models, then test
    # dbt run  : executes all SQL models (stg_articles, mart_*)
    # dbt test : runs data quality checks (not_null, unique, accepted_values)
    dbt_run_and_test = BashOperator(
        task_id="dbt_run_and_test",
        bash_command=(
            "cd /opt/airflow/dbt_transform && "
            "dbt run --profiles-dir . && "
            "dbt test --profiles-dir ."
        ),
        append_env=True,
    )

    # Pipeline execution order
    scrape_and_ingest >> clean_bronze_to_silver >> load_silver_to_gold >> dbt_run_and_test
