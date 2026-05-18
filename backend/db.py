"""MongoDB connection helpers."""

from __future__ import annotations

import os

from gridfs import GridFS
from pymongo import MongoClient
from pymongo.database import Database

MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_DB = os.environ.get("MONGODB_DB", "mouthsync").strip() or "mouthsync"

_client: MongoClient | None = None


def mongo_enabled() -> bool:
    return bool(MONGODB_URI)


def get_client() -> MongoClient:
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not set")
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db() -> Database:
    return get_client()[MONGODB_DB]


def get_gridfs() -> GridFS:
    return GridFS(get_db(), collection="generation_files")


def ping() -> bool:
    if not mongo_enabled():
        return False
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def ensure_indexes() -> None:
    db = get_db()
    db.generations.create_index([("client_id", 1), ("created_at", -1)])
    db.generations.create_index("id", unique=True)
    db.user_configs.create_index("client_id", unique=True)
