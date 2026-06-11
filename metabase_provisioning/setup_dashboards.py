"""
Metabase provisioning script.

Connects to the Metabase REST API and sets up the initial dashboard:
  - registers the PostgreSQL Gold warehouse as a data source
  - creates analytical questions (charts) on top of articles_gold
  - assembles everything into a single dashboard

Run this once after `docker compose up` and after the pipeline has loaded data.
Requires: pip install requests
"""

import os
import sys
import io
import time
import json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# When running inside Docker Compose, use the service name.
# Override with METABASE_URL env var if running from the host machine.
METABASE_URL = os.getenv("METABASE_URL", "http://metabase:3000")
METABASE_USER = "admin@newsdataplatform.com"
METABASE_PASSWORD = "Admin1234!"

# These must match the values in docker-compose.yml / .env
PG_HOST = "postgres-dw"
PG_PORT = 5432
PG_USER = "dw_user"
PG_PASSWORD = "dw_password"
PG_DB = "datawarehouse"

session = requests.Session()


def wait_for_metabase(max_retries=30, delay=10):
    print(f"Waiting for Metabase at {METABASE_URL} ...")
    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(f"{METABASE_URL}/api/health", timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print("Metabase is up.")
                return True
        except requests.exceptions.ConnectionError:
            pass
        print(f"  [{attempt}/{max_retries}] Not ready yet, retrying in {delay}s...")
        time.sleep(delay)
    raise TimeoutError("Metabase did not start in time.")


def setup_metabase_admin():
    print("\nChecking Metabase admin setup...")
    r = session.get(f"{METABASE_URL}/api/session/properties")
    props = r.json()

    if props.get("setup-token"):
        setup_token = props["setup-token"]
        payload = {
            "token": setup_token,
            "user": {
                "first_name": "News",
                "last_name": "Admin",
                "email": METABASE_USER,
                "password": METABASE_PASSWORD,
                "site_name": "News Data Platform",
            },
            "prefs": {
                "site_name": "News Data Platform",
                "allow_tracking": False,
            },
        }
        r = session.post(f"{METABASE_URL}/api/setup", json=payload)
        if r.status_code == 200:
            print("Admin account created.")
        else:
            print(f"Setup already done or error: {r.status_code}")
    else:
        print("Metabase already configured.")


def get_auth_token():
    print("\nAuthenticating...")
    payload = {"username": METABASE_USER, "password": METABASE_PASSWORD}
    r = session.post(f"{METABASE_URL}/api/session", json=payload)
    r.raise_for_status()
    token = r.json()["id"]
    session.headers.update({"X-Metabase-Session": token})
    print(f"Authenticated. Token: {token[:8]}...")
    return token


def add_postgres_database():
    print("\nRegistering PostgreSQL data warehouse...")

    r = session.get(f"{METABASE_URL}/api/database")
    for db in r.json().get("data", []):
        if db.get("name") == "News Data Warehouse (Gold)":
            print(f"Already registered (id={db['id']}), reusing.")
            return db["id"]

    payload = {
        "engine": "postgres",
        "name": "News Data Warehouse (Gold)",
        "details": {
            "host": PG_HOST,
            "port": PG_PORT,
            "dbname": PG_DB,
            "user": PG_USER,
            "password": PG_PASSWORD,
            "ssl": False,
        },
    }
    r = session.post(f"{METABASE_URL}/api/database", json=payload)
    r.raise_for_status()
    db_id = r.json()["id"]
    print(f"Database added (id={db_id}). Syncing schema (15s)...")
    session.post(f"{METABASE_URL}/api/database/{db_id}/sync_schema")
    time.sleep(15)
    return db_id


def get_table_id(db_id, table_name="articles_gold"):
    print(f"\nLooking up table '{table_name}'...")
    r = session.get(f"{METABASE_URL}/api/database/{db_id}/metadata")
    for table in r.json().get("tables", []):
        if table.get("name") == table_name:
            print(f"Found table (id={table['id']})")
            return table["id"]
    raise ValueError(f"Table '{table_name}' not found. Make sure data has been loaded first.")


def get_field_id(db_id, table_name, field_name):
    r = session.get(f"{METABASE_URL}/api/database/{db_id}/metadata")
    for table in r.json().get("tables", []):
        if table.get("name") == table_name:
            for field in table.get("fields", []):
                if field.get("name") == field_name:
                    return field["id"]
    return None


def create_all_questions(db_id, table_id):
    print("\nCreating dashboard charts...")
    cards = {}

    questions = [
        {
            "key": "total_articles",
            "name": "Total Articles Ingested",
            "description": "Total number of articles in the Gold layer",
            "query": {"source-table": table_id, "aggregation": [["count"]]},
            "display": "scalar",
            "viz_settings": {"scalar.field": "count"},
        },
        {
            "key": "by_category",
            "name": "Articles by Category",
            "description": "Article count broken down by editorial category",
            "query": {
                "source-table": table_id,
                "aggregation": [["count"]],
                "breakout": [["field", "category", {"base-type": "type/Text"}]],
            },
            "display": "bar",
            "viz_settings": {
                "graph.x_axis.title_text": "Category",
                "graph.y_axis.title_text": "Articles",
                "graph.colors": ["#7C3AED"],
            },
        },
        {
            "key": "by_source",
            "name": "Articles by Source",
            "description": "Share of articles per news source",
            "query": {
                "source-table": table_id,
                "aggregation": [["count"]],
                "breakout": [["field", "source", {"base-type": "type/Text"}]],
            },
            "display": "pie",
            "viz_settings": {},
        },
        {
            "key": "top_authors",
            "name": "Top 10 Authors",
            "description": "Authors with the highest article counts",
            "query": {
                "source-table": table_id,
                "aggregation": [["count"]],
                "breakout": [["field", "author", {"base-type": "type/Text"}]],
                "order-by": [["desc", ["aggregation", 0]]],
                "limit": 10,
            },
            "display": "row",
            "viz_settings": {
                "graph.x_axis.title_text": "Articles",
                "graph.y_axis.title_text": "Author",
            },
        },
        {
            "key": "over_time",
            "name": "Daily Article Volume",
            "description": "Number of articles ingested per day",
            "query": {
                "source-table": table_id,
                "aggregation": [["count"]],
                "breakout": [
                    ["field", "date", {"base-type": "type/DateTime", "temporal-unit": "day"}]
                ],
            },
            "display": "line",
            "viz_settings": {
                "graph.x_axis.title_text": "Date",
                "graph.y_axis.title_text": "Articles ingested",
                "graph.colors": ["#10B981"],
            },
        },
        {
            "key": "latest_articles",
            "name": "Recently Loaded Articles",
            "description": "The 20 most recently inserted articles",
            "query": {
                "source-table": table_id,
                "order-by": [["desc", ["field", "processed_at", {"base-type": "type/DateTime"}]]],
                "limit": 20,
            },
            "display": "table",
            "viz_settings": {
                "table.columns": [
                    {"name": "title", "enabled": True},
                    {"name": "author", "enabled": True},
                    {"name": "category", "enabled": True},
                    {"name": "source", "enabled": True},
                    {"name": "date", "enabled": True},
                ]
            },
        },
    ]

    for q in questions:
        payload = {
            "name": q["name"],
            "description": q["description"],
            "dataset_query": {
                "database": db_id,
                "type": "query",
                "query": q["query"],
            },
            "display": q["display"],
            "visualization_settings": q["viz_settings"],
        }
        r = session.post(f"{METABASE_URL}/api/card", json=payload)
        r.raise_for_status()
        cards[q["key"]] = r.json()["id"]
        print(f"  Created '{q['name']}' (id={cards[q['key']]})")

    return cards


def create_dashboard(cards):
    print("\nAssembling dashboard...")

    r = session.post(
        f"{METABASE_URL}/api/dashboard",
        json={
            "name": "News Data Platform - Analytics",
            "description": "Medallion pipeline overview — Gold layer (PostgreSQL).",
        },
    )
    r.raise_for_status()
    dashboard_id = r.json()["id"]

    layout = [
        {"id": -1, "card_id": cards["total_articles"], "col": 0,  "row": 0,  "size_x": 6,  "size_y": 4,  "parameter_mappings": [], "visualization_settings": {}},
        {"id": -2, "card_id": cards["over_time"],      "col": 6,  "row": 0,  "size_x": 18, "size_y": 8,  "parameter_mappings": [], "visualization_settings": {}},
        {"id": -3, "card_id": cards["by_source"],      "col": 0,  "row": 4,  "size_x": 6,  "size_y": 8,  "parameter_mappings": [], "visualization_settings": {}},
        {"id": -4, "card_id": cards["by_category"],    "col": 0,  "row": 12, "size_x": 12, "size_y": 8,  "parameter_mappings": [], "visualization_settings": {}},
        {"id": -5, "card_id": cards["top_authors"],    "col": 12, "row": 12, "size_x": 12, "size_y": 8,  "parameter_mappings": [], "visualization_settings": {}},
        {"id": -6, "card_id": cards["latest_articles"],"col": 0,  "row": 20, "size_x": 24, "size_y": 8,  "parameter_mappings": [], "visualization_settings": {}},
    ]

    r = session.put(f"{METABASE_URL}/api/dashboard/{dashboard_id}", json={"dashcards": layout})
    if r.status_code in (200, 202):
        print(f"Dashboard created with {len(layout)} cards (id={dashboard_id}).")
    else:
        # Fallback to the older per-card API (Metabase < 0.47)
        print(f"PUT failed ({r.status_code}), falling back to legacy card API...")
        for item in layout:
            old_payload = {
                "cardId": item["card_id"],
                "col": item["col"],
                "row": item["row"],
                "size_x": item["size_x"],
                "size_y": item["size_y"],
            }
            r2 = session.post(
                f"{METABASE_URL}/api/dashboard/{dashboard_id}/cards", json=old_payload
            )
            status = "OK" if r2.status_code in (200, 201) else f"ERROR {r2.status_code}"
            print(f"  [{status}] card {item['card_id']}")

    return dashboard_id


def main():
    print("=" * 55)
    print("  Metabase provisioning — News Data Platform")
    print("=" * 55)

    wait_for_metabase()
    setup_metabase_admin()
    get_auth_token()
    db_id = add_postgres_database()
    table_id = get_table_id(db_id, "articles_gold")
    cards = create_all_questions(db_id, table_id)
    dashboard_id = create_dashboard(cards)

    print("\n" + "=" * 55)
    print("  Done.")
    print(f"  Dashboard: {METABASE_URL}/dashboard/{dashboard_id}")
    print("=" * 55)


if __name__ == "__main__":
    main()
