import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv
from kafka import KafkaConsumer

load_dotenv()

SCRAPERS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRAPERS_DIR)

from storage_client import get_storage_client, upload_json  # noqa: E402

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "news_articles_raw")
KAFKA_GROUP_ID = "news-minio-consumer-group"
CONSUMER_TIMEOUT_MS = int(os.getenv("CONSUMER_TIMEOUT_MS", "30000"))

BUCKET_NAME = "bronze"


def run_kafka_to_storage():
    """
    Consumes messages from the Kafka topic and saves them to the data lake.
    Stops automatically after CONSUMER_TIMEOUT_MS without new messages
    — important for Airflow tasks (they must terminate).
    Works with both MinIO (local) and AWS S3 (cloud) via storage_client.
    """
    print("=" * 55)
    print("  KAFKA CONSUMER — Bronze Layer")
    print(f"  Topic   : {KAFKA_TOPIC}")
    print(f"  Timeout : {CONSUMER_TIMEOUT_MS / 1000}s without messages")
    print("=" * 55)

    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=[KAFKA_BROKER],
            group_id=KAFKA_GROUP_ID,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=CONSUMER_TIMEOUT_MS,
        )
    except Exception as e:
        print(f"[ERROR] Cannot connect to Kafka: {e}")
        sys.exit(1)

    client = get_storage_client()
    articles = []

    print("\nConsuming messages...")
    for message in consumer:
        article = message.value
        articles.append(article)
        print(f"  [IN] {article.get('title', 'N/A')[:70]}")

    consumer.close()

    if not articles:
        print("\n[WARN] No messages consumed from Kafka.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    object_key = f"raw_news/streaming_{timestamp}.json"

    upload_json(client, bucket=BUCKET_NAME, key=object_key, data=articles)

    print(f"\n[OK] {len(articles)} articles saved to s3://{BUCKET_NAME}/{object_key}")


if __name__ == "__main__":
    run_kafka_to_storage()
