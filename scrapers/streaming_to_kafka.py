import os
import sys
import json
import time
from dotenv import load_dotenv
from kafka import KafkaProducer

# Fix d'import : même raison que dans batch_to_minio.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from article_scraper import GenericNewsScraper, RSS_SOURCES  # noqa: E402

load_dotenv()

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "news_articles_raw")

# Nombre d'articles à produire par run (configurable via env var)
# En prod on pourrait brancher ça sur un vrai flux en temps réel
ARTICLES_PER_RUN = int(os.getenv("STREAMING_ARTICLES_PER_RUN", "20"))
DELAY_BETWEEN_MESSAGES = float(os.getenv("STREAMING_DELAY_SEC", "0.5"))


def get_producer():
    """Crée et retourne un KafkaProducer connecté au broker."""
    return KafkaProducer(
        bootstrap_servers=[KAFKA_BROKER],
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",  # On veut la confirmation que le message est bien reçu
        retries=3,
    )


def run_streaming_ingestion():
    print("=" * 55)
    print("  STREAMING INGESTION — Kafka Producer")
    print(f"  Topic   : {KAFKA_TOPIC}")
    print(f"  Broker  : {KAFKA_BROKER}")
    print("=" * 55)

    try:
        producer = get_producer()
    except Exception as e:
        print(f"[ERREUR] Impossible de se connecter à Kafka : {e}")
        sys.exit(1)

    sent_count = 0

    try:
        # On tourne sur toutes les sources RSS et on envoie les articles un par un
        # pour simuler un flux d'événements en temps réel
        for source in RSS_SOURCES:
            if sent_count >= ARTICLES_PER_RUN:
                break

            scraper = GenericNewsScraper(
                source_name=source["name"],
                rss_url=source["rss_url"],
            )
            limit = min(ARTICLES_PER_RUN - sent_count, 10)
            articles = scraper.scrape_latest_articles(limit=limit)

            for article in articles:
                if sent_count >= ARTICLES_PER_RUN:
                    break

                future = producer.send(
                    topic=KAFKA_TOPIC,
                    key=article["source"],
                    value=article,
                )
                future.get(timeout=10)  # Attendre la confirmation d'envoi

                sent_count += 1
                print(f"  [Kafka] ({sent_count}/{ARTICLES_PER_RUN}) {article['title'][:65]}")

                # Petite pause pour simuler l'arrivée progressive des articles
                time.sleep(DELAY_BETWEEN_MESSAGES)

    except KeyboardInterrupt:
        print("\nArrêt manuel.")
    finally:
        producer.flush()
        producer.close()
        print(f"\n[OK] {sent_count} message(s) envoyés vers le topic '{KAFKA_TOPIC}'.")


if __name__ == "__main__":
    run_streaming_ingestion()
