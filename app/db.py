from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.models import ProductRecord, utc_now_iso


class Database:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This release supports sqlite:/// URLs only")
        self.path = Path(database_url.removeprefix("sqlite:///"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS products (
                    asin TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asin TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    seller_sku TEXT NOT NULL,
                    external_id TEXT,
                    status TEXT NOT NULL,
                    target_price INTEGER,
                    target_stock INTEGER,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(channel, seller_sku)
                );
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                """
            )

    def upsert_product(self, product: ProductRecord) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO products(asin, payload, fetched_at) VALUES(?, ?, ?)
                ON CONFLICT(asin) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at""",
                (product.asin, product.model_dump_json(), product.fetched_at),
            )

    def get_product(self, asin: str) -> ProductRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload FROM products WHERE asin=?", (asin,)).fetchone()
        return ProductRecord.model_validate_json(row["payload"]) if row else None

    def list_products(self) -> list[ProductRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT payload FROM products ORDER BY fetched_at DESC").fetchall()
        return [ProductRecord.model_validate_json(row["payload"]) for row in rows]

    def upsert_listing(self, *, asin: str, channel: str, seller_sku: str, external_id: str | None, status: str, target_price: int, target_stock: int, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO listings(asin, channel, seller_sku, external_id, status, target_price, target_stock, payload, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel, seller_sku) DO UPDATE SET asin=excluded.asin, external_id=COALESCE(excluded.external_id, listings.external_id), status=excluded.status, target_price=excluded.target_price, target_stock=excluded.target_stock, payload=excluded.payload, updated_at=excluded.updated_at""",
                (asin, channel, seller_sku, external_id, status, target_price, target_stock, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
            )

    def list_listings(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM listings ORDER BY updated_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def start_sync(self) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("INSERT INTO sync_runs(started_at, status, detail) VALUES(?, 'running', '{}')", (utc_now_iso(),))
            return int(cursor.lastrowid)

    def finish_sync(self, run_id: int, status: str, detail: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("UPDATE sync_runs SET finished_at=?, status=?, detail=? WHERE id=?", (utc_now_iso(), status, json.dumps(detail, ensure_ascii=False), run_id))
