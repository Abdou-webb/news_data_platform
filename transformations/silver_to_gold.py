import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

SCRAPERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scrapers")
sys.path.insert(0, os.path.abspath(SCRAPERS_DIR))

from storage_client import get_storage_client, read_json, list_objects  # noqa: E402

BUCKET_SILVER = "silver"
PREFIX_CLEANED = "cleaned_news/"

PG_HOST = os.getenv("PG_HOST", "postgres-dw")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER", "dw_user")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_DB = os.getenv("PG_DB", "datawarehouse")


def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DB,
    )


def run_silver_to_gold():
    # Loads cleaned articles from Silver into the Gold PostgreSQL table.
    # ON CONFLICT DO NOTHING makes this safe to re-run — no duplicates.
    # Silver files are kept after load for audit/replay purposes.
    print("=" * 55)
    print("  LOAD — Silver -> Gold (PostgreSQL)")
    print("=" * 55)

    client = get_storage_client()
    silver_files = list_objects(client, BUCKET_SILVER, PREFIX_CLEANED)

    if not silver_files:
        print("\n[INFO] Nothing to load in silver/cleaned_news/")
        return

    pg_conn = None
    try:
        pg_conn = get_pg_connection()
        cursor = pg_conn.cursor()
        print("[DB] Connected to PostgreSQL.")

        total_inserted = 0

        for file_path in silver_files:
            print(f"\n[File] {file_path}")
            articles = read_json(client, BUCKET_SILVER, file_path)

            if not articles:
                print("  [SKIP] Empty file.")
                continue

            rows = [
                (
                    art.get("id"),
                    art.get("title"),
                    art.get("author"),
                    art.get("category"),
                    art.get("content"),
                    art.get("source"),
                    art.get("url"),
                    art.get("date"),
                    art.get("processed_at"),
                    art.get("processing_layer"),
                )
                for art in articles
            ]

            insert_query = """
                INSERT INTO articles_gold (
                    id, title, author, category, content,
                    source, url, date, processed_at, processed_by
                )
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """
            execute_values(cursor, insert_query, rows)
            pg_conn.commit()

            inserted = max(cursor.rowcount, 0)
            total_inserted += inserted
            print(f"  [Gold] {len(rows)} processed, {inserted} inserted ({len(rows) - inserted} duplicates skipped).")

        print(f"\n[OK] Load complete — {total_inserted} new article(s) in the warehouse.")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        if pg_conn:
            pg_conn.rollback()
        raise
    finally:
        if pg_conn:
            cursor.close()
            pg_conn.close()


if __name__ == "__main__":
    run_silver_to_gold()
