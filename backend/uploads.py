"""
backend/uploads.py — in-memory store for uploaded review batches.

Caveats (honest, and documented in the README):
- In-memory only. Lost on container restart or HF Space rebuild.
- Not shared across workers. Fine for a single-container demo.
- For real durability, retain uploads to Hindsight under a
  `raw_reviews:{upload_id}` tag or write to external storage.

Interface is intentionally tiny so it can be swapped for a real store
without touching call sites.
"""
from __future__ import annotations

from datetime import datetime, timezone

_uploads: dict[str, dict] = {}


def put(upload_id: str, reviews: list[dict]) -> dict:
    _uploads[upload_id] = {
        "reviews": reviews,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_reviews": len(reviews),
    }
    return _uploads[upload_id]


def get(upload_id: str) -> list[dict] | None:
    entry = _uploads.get(upload_id)
    return entry["reviews"] if entry else None


def info(upload_id: str) -> dict | None:
    entry = _uploads.get(upload_id)
    if not entry:
        return None
    return {
        "upload_id": upload_id,
        "n_reviews": entry["n_reviews"],
        "created_at": entry["created_at"],
    }


def list_ids() -> list[dict]:
    return [
        {
            "upload_id": k,
            "n_reviews": v["n_reviews"],
            "created_at": v["created_at"],
        }
        for k, v in _uploads.items()
    ]


def delete(upload_id: str) -> bool:
    return _uploads.pop(upload_id, None) is not None


def clear() -> None:
    _uploads.clear()
