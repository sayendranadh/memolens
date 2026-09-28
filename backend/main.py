"""backend/main.py — FastAPI surface for MemoLens."""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import memory
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
    batch: Literal[1, 2, 3]
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
    batch: Literal[1, 2, 3]


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


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "memory": memory.stats()}


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
