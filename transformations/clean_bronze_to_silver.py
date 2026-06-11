import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

# Add scrapers/ to path to import the shared storage_client module
SCRAPERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scrapers")
sys.path.insert(0, os.path.abspath(SCRAPERS_DIR))

from storage_client import (  # noqa: E402
    get_storage_client, read_json, upload_json,
    list_objects, move_object, object_exists,
)

BUCKET_BRONZE = "bronze"
BUCKET_SILVER = "silver"
PREFIX_RAW = "raw_news/"
PREFIX_ARCHIVED = "archived/raw_news/"


def clean_html_content(raw_content: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not raw_content:
        return ""
    soup = BeautifulSoup(raw_content, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


def run_transformation():
    print("=" * 55)
    print("  TRANSFORMATION — Bronze -> Silver")
    print("=" * 55)

    client = get_storage_client()
    raw_files = list_objects(client, BUCKET_BRONZE, PREFIX_RAW)

    if not raw_files:
        print("\n[INFO] Nothing to process in bronze/raw_news/")
        return

    files_processed = 0

    for file_path in raw_files:
        print(f"\n[File] {file_path}")
        silver_path = file_path.replace(PREFIX_RAW, "cleaned_news/")

        # Idempotency check: skip if Silver file already exists
        if object_exists(client, BUCKET_SILVER, silver_path):
            print("  [SKIP] Silver file already exists — archiving Bronze copy.")
            archived_path = file_path.replace(PREFIX_RAW, PREFIX_ARCHIVED)
            move_object(client, BUCKET_BRONZE, file_path, BUCKET_BRONZE, archived_path)
            continue

        articles = read_json(client, BUCKET_BRONZE, file_path)

        cleaned_articles = []
        for article in articles:
            article["content"] = clean_html_content(article.get("content", ""))
            article["processed_at"] = datetime.now().isoformat()
            article["processing_layer"] = "silver"
            cleaned_articles.append(article)

        print(f"  [Clean] {len(cleaned_articles)} article(s) processed")

        upload_json(client, BUCKET_SILVER, silver_path, cleaned_articles)
        print(f"  [Silver] Saved: s3://{BUCKET_SILVER}/{silver_path}")

        # Archive the Bronze file instead of deleting it
        archived_path = file_path.replace(PREFIX_RAW, PREFIX_ARCHIVED)
        move_object(client, BUCKET_BRONZE, file_path, BUCKET_BRONZE, archived_path)
        files_processed += 1

    print(f"\n[OK] Transformation complete — {files_processed} file(s) processed.")


if __name__ == "__main__":
    run_transformation()
