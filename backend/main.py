"""backend/main.py — FastAPI surface for MemoLens."""
from __future__ import annotations

import csv
import io
import json
import os
import uuid
from typing import Any, Literal

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import memory
from . import uploads
from .pipeline import run_pipeline
from .models import AnalysisResult

app = FastAPI(title="MemoLens", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeReq(BaseModel):
    batch: int | str
    memory: bool = True


class FeedbackReq(BaseModel):
    recommendation_id: str
    decision: Literal["accepted", "rejected", "edited"]
    reason: str
    batch: int = 0


class ContextReq(BaseModel):
    text: str
    category: Literal["shipped", "roadmap", "constraint",
                      "target_user", "preference"] = "roadmap"


class CompareReq(BaseModel):
    batch: int | str


class OkResp(BaseModel):
    ok: bool = True
    memory_id: str | None = None
    message: str | None = None


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "MemoLens",
        "version": "0.1.0",
        "memory_enabled": memory.MEMORY_ENABLED,
        "bank_id": memory.BANK_ID,
    }


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Fast, side-effect-free health check. Never calls external services —
    HF Spaces' proxy has a short timeout and a slow health check shows up
    as a 502."""
    return {
        "ok": True,
        "bank_id": memory.BANK_ID,
        "memory_enabled": memory.MEMORY_ENABLED,
    }




class UploadResp(BaseModel):
    upload_id: str
    n_reviews: int
    preview: list[dict]


@app.post("/upload", response_model=UploadResp)
async def upload_reviews(file: UploadFile = File(...)) -> UploadResp:
    """Accept .json, .jsonl, or .csv. Normalize to pipeline schema:
    {id, text, rating, date, ground_truth_theme}."""
    raw = await file.read()
    name = (file.filename or "").lower()

    try:
        if name.endswith(".json"):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("JSON must be an array of reviews")
            items = parsed
        elif name.endswith(".jsonl"):
            items = [
                json.loads(line)
                for line in raw.decode("utf-8", "replace").splitlines()
                if line.strip()
            ]
        elif name.endswith(".csv"):
            items = list(csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))))
        else:
            raise HTTPException(400, "Unsupported file type. Use .json, .jsonl, or .csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Parse error: {type(e).__name__}: {e}")

    reviews: list[dict] = []
    for i, r in enumerate(items):
        if not isinstance(r, dict):
            continue
        text = (r.get("text") or r.get("review") or r.get("body")
                or r.get("content") or "")
        if not str(text).strip():
            continue
        try:
            rating = int(r.get("rating") or r.get("stars") or r.get("score") or 3)
        except (ValueError, TypeError):
            rating = 3
        rating = max(1, min(5, rating))
        reviews.append({
            "id": str(r.get("id") or f"up-{i:04d}"),
            "text": str(text)[:2000],
            "rating": rating,
            "date": str(r.get("date") or "2026-09-29")[:10],
            "ground_truth_theme": str(r.get("ground_truth_theme") or "unknown"),
        })

    if not reviews:
        raise HTTPException(400, "No valid reviews found in file")

    upload_id = uuid.uuid4().hex[:10]
    uploads.put(upload_id, reviews)
    return UploadResp(
        upload_id=upload_id,
        n_reviews=len(reviews),
        preview=reviews[:3],
    )


@app.get("/uploads")
def list_uploads() -> dict:
    return {"uploads": uploads.list_ids()}


@app.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str) -> dict:
    return {"ok": uploads.delete(upload_id)}

@app.post("/analyze", response_model=AnalysisResult)
def analyze(req: AnalyzeReq) -> AnalysisResult:
    try:
        return run_pipeline(batch=req.batch, memory_enabled=req.memory)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.post("/compare")
def compare(req: CompareReq) -> dict[str, Any]:
    try:
        off = run_pipeline(batch=req.batch, memory_enabled=False)
        on = run_pipeline(batch=req.batch, memory_enabled=True)
        return {"memory_off": off, "memory_on": on}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.post("/feedback", response_model=OkResp)
def feedback(req: FeedbackReq) -> OkResp:
    if not req.reason.strip():
        raise HTTPException(400, "reason is required")
    mid = memory.retain_pm_decision(
        recommendation=req.recommendation_id,
        decision=req.decision,
        reason=req.reason.strip(),
        batch=req.batch,
    )
    return OkResp(ok=True, memory_id=mid)


@app.post("/context", response_model=OkResp)
def context(req: ContextReq) -> OkResp:
    if not req.text.strip():
        raise HTTPException(400, "text is required")
    mid = memory.retain_product_context(req.text.strip(), req.category)
    return OkResp(ok=True, memory_id=mid)


@app.get("/memory/profile")
def memory_profile() -> dict[str, Any]:
    return {"profile": memory.reflect_profile()}


@app.get("/memory/timeline")
def memory_timeline(limit: int = 100) -> dict[str, Any]:
    return {"items": memory.list_all(limit=limit), "stats": memory.stats()}


@app.get("/memory/recalls")
def memory_recalls(limit: int = 30) -> dict[str, Any]:
    return {"recalls": memory.recent_recalls(limit=limit)}


@app.get("/memory/stats")
def memory_stats() -> dict[str, Any]:
    return memory.stats()


@app.post("/reset", response_model=OkResp)
def reset(x_confirm_reset: str | None = Header(default=None)) -> OkResp:
    if os.getenv("ALLOW_RESET", "false").lower() != "true":
        raise HTTPException(403, "Reset disabled. Set ALLOW_RESET=true in .env.")
    if x_confirm_reset != "yes":
        raise HTTPException(400, "Send header `X-Confirm-Reset: yes`.")
    try:
        result = memory.delete_bank()
        if not result.get("ok"):
            raise HTTPException(500, f"delete_bank failed: {result}")
        memory.ensure_bank()
        if memory.LOG_PATH.exists():
            memory.LOG_PATH.unlink()
        return OkResp(ok=True, message=f"Bank {memory.BANK_ID} cleared")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.on_event("shutdown")
def _shutdown() -> None:
    memory.close_client()
