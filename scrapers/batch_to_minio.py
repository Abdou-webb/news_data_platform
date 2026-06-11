import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# sys.path fix: ensures article_scraper and storage_client are importable
# regardless of which directory Airflow calls this script from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from article_scraper import GenericNewsScraper, RSS_SOURCES  # noqa: E402
from storage_client import get_storage_client, upload_json   # noqa: E402

load_dotenv()

BUCKET_NAME = "bronze"


def run_batch_ingestion():
    print("=" * 55)
    print("  BATCH INGESTION — Bronze Layer")
    print("=" * 55)

    client = get_storage_client()
    all_articles = []

    for source in RSS_SOURCES:
        scraper = GenericNewsScraper(
            source_name=source["name"],
            rss_url=source["rss_url"],
        )
        articles = scraper.scrape_latest_articles(limit=10)
        all_articles.extend(articles)
        print(f"  => {len(articles)} article(s) from '{source['name']}'")

    if not all_articles:
        print("\n[WARN] No articles retrieved. Check network connectivity.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    object_key = f"raw_news/batch_{timestamp}.json"

    upload_json(client, bucket=BUCKET_NAME, key=object_key, data=all_articles)

    print(f"\n[OK] {len(all_articles)} articles saved to s3://{BUCKET_NAME}/{object_key}")


if __name__ == "__main__":
    run_batch_ingestion()
