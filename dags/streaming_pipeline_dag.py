from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

# DAG séparé pour le pipeline streaming via Kafka.
# Il est conçu pour tourner plus fréquemment que le batch (toutes les heures).
#
# Flow :
#   streaming_to_kafka.py  -->  Kafka topic  -->  kafka_to_minio.py
#   --> Bronze  -->  Silver  -->  Gold (PostgreSQL)

default_args = {
    "owner": "data_engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    "streaming_pipeline_dag",
    default_args=default_args,
    description="Pipeline streaming : RSS -> Kafka -> Bronze -> Silver -> Gold",
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["news", "streaming", "kafka", "bronze", "silver", "gold"],
) as dag:

    # Tâche 1 — Scraping RSS et envoi dans Kafka (producer)
    produce_to_kafka = BashOperator(
        task_id="produce_rss_to_kafka",
        bash_command="python /opt/airflow/scrapers/streaming_to_kafka.py",
        append_env=True,
    )

    # Tâche 2 — Consommation depuis Kafka et sauvegarde dans Bronze (MinIO)
    # Le consumer s'arrête automatiquement après 30s sans message
    consume_to_bronze = BashOperator(
        task_id="consume_kafka_to_bronze",
        bash_command="python /opt/airflow/scrapers/kafka_to_minio.py",
        append_env=True,
    )

    # Tâche 3 — Nettoyage HTML (Bronze -> Silver)
    clean_bronze_to_silver = BashOperator(
        task_id="clean_bronze_to_silver",
        bash_command="python /opt/airflow/transformations/clean_bronze_to_silver.py",
        append_env=True,
    )

    # Tâche 4 — Chargement dans PostgreSQL (Silver -> Gold)
    load_silver_to_gold = BashOperator(
        task_id="load_silver_to_gold",
        bash_command="python /opt/airflow/transformations/silver_to_gold.py",
        append_env=True,
    )

    produce_to_kafka >> consume_to_bronze >> clean_bronze_to_silver >> load_silver_to_gold
