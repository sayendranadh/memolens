"""
backend/memory.py — the ONLY module that touches Hindsight.

Written against the real signatures returned by tools/probe_hindsight.py:

    Hindsight(base_url, api_key=None, timeout=300.0, ...)
    retain(bank_id, content, timestamp=None, context=None, document_id=None,
           metadata=None, entities=None, resolve_entities=None, tags=None,
           update_mode=None, retain_async=False, operation_id=None)
    recall(bank_id, query, types=None, max_tokens=4096, budget='mid', ...,
           tags=None, tags_match='any', prefer_observations=False, ...)
    reflect(bank_id, query, budget='low', context=None, response_schema=None,
            tags=None, tags_match='any', ...)
    list_memories(bank_id, type=None, search_query=None, limit=100, offset=0)
    create_bank(bank_id, name=None, mission=None, ...)
    delete_bank(bank_id)

Design:
  - MEMORY_ENABLED is a module-level flag. backend/pipeline.py flips it per
    run so the SAME code path runs with memory OFF or ON.
  - Every read/write goes through _retain / _recall_raw so logging is
    centralized and the UI can render recalls live.
  - metadata values are stringified — the Hindsight client types them as
    dict[str, str] and will reject ints at the transport layer.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────

MEMORY_ENABLED: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
BANK_ID: str = os.getenv("HINDSIGHT_BANK_ID", "taskflow-pm")
BASE_URL: str = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
API_KEY: str | None = os.getenv("HINDSIGHT_API_KEY")
LOG_PATH = Path(os.getenv("MEMORY_LOG", "./data/memory_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── models ────────────────────────────────────────────────────────────────

class RecallLog(BaseModel):
    ts: str
    purpose: str
    query: str
    bank_id: str
    result_count: int
    latency_ms: float
    results: list[dict[str, Any]]


ContextCategory = Literal[
    "shipped", "roadmap", "constraint", "target_user", "preference"
]
DecisionKind = Literal["accepted", "rejected", "edited"]


# ── lazy client ───────────────────────────────────────────────────────────

# ── worker thread with its own event loop ────────────────────────────────
#
# The Hindsight client uses aiohttp under the hood. Its sync methods work
# from a plain Python script but fail inside FastAPI's threadpool workers
# with: RuntimeError: Timeout context manager should be used inside a task.
# Fix: own a dedicated worker thread with its own event loop. All sync
# memory calls hop onto that loop and use the client's async methods.

import asyncio
import threading

_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_thread: threading.Thread | None = None
_worker_client = None
_worker_lock = threading.Lock()
_WORKER_TIMEOUT = 25.0


def _start_worker() -> None:
    global _worker_loop, _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        ready = threading.Event()

        def run() -> None:
            global _worker_loop
            _worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_worker_loop)
            ready.set()
            _worker_loop.run_forever()

        _worker_thread = threading.Thread(
            target=run, daemon=True, name="hindsight-loop",
        )
        _worker_thread.start()
        if not ready.wait(timeout=5):
            raise RuntimeError("hindsight worker loop failed to start")


async def _get_async_client():
    """Construct the Hindsight client inside the worker loop on first use.
    aiohttp sessions are loop-bound; they must not cross loops."""
    global _worker_client
    if _worker_client is None:
        from hindsight_client import Hindsight
        if not API_KEY or API_KEY.endswith("replace_me"):
            raise RuntimeError(
                "HINDSIGHT_API_KEY not set. Add it to .env or set "
                "MEMORY_ENABLED=false to run without memory."
            )
        _worker_client = Hindsight(base_url=BASE_URL, api_key=API_KEY)
    return _worker_client


def _call_async(async_method: str, **kwargs):
    """Invoke an async Hindsight client method on the worker loop and
    block until it completes. Raises whatever the method raises."""
    _start_worker()
    async def _go():
        client = await _get_async_client()
        return await getattr(client, async_method)(**kwargs)
    fut = asyncio.run_coroutine_threadsafe(_go(), _worker_loop)
    return fut.result(timeout=_WORKER_TIMEOUT)


def _get_client():
    """Deprecated — kept only so accidental callers fail loudly."""
    raise RuntimeError(
        "Use _call_async('arecall'|'aretain'|'areflect'|..., ...) instead."
    )


def close_client() -> None:
    """Close the client and stop the worker loop cleanly."""
    global _worker_client, _worker_loop, _worker_thread
    if _worker_client is not None and _worker_loop is not None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                _worker_client.aclose(), _worker_loop,
            )
            fut.result(timeout=5)
        except Exception:
            pass
        _worker_client = None
    if _worker_loop is not None:
        try:
            _worker_loop.call_soon_threadsafe(_worker_loop.stop)
        except Exception:
            pass
    _worker_loop = None
    _worker_thread = None


# ── bank lifecycle ────────────────────────────────────────────────────────

def ensure_bank(create: bool = True) -> dict:
    """Ensure the demo bank exists. Safe to call repeatedly. Returns a small
    dict describing what happened."""
    if not MEMORY_ENABLED:
        return {"ok": False, "reason": "memory disabled"}
    try:
        cfg = _call_async("aget_bank_config", bank_id=BANK_ID)
        return {"ok": True, "created": False, "config_keys": list(cfg)[:6]}
    except Exception as e:
        if not create:
            return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
        try:
            _call_async(
                "acreate_bank",
                bank_id=BANK_ID,
                name="TaskFlow PM workspace",
                mission=(
                    "Track product feedback, PM decisions, and shipped features "
                    "for the TaskFlow productivity app so briefs stay consistent "
                    "and do not re-recommend rejected or already-shipped items."
                ),
                enable_temporal_retrieval=True,
                enable_observations=True,
            )
            return {"ok": True, "created": True}
        except Exception as e2:
            return {"ok": False, "reason": f"{type(e2).__name__}: {e2}"}


def delete_bank() -> dict:
    if not MEMORY_ENABLED:
        return {"ok": False, "reason": "memory disabled"}
    try:
        _call_async("adelete_bank", bank_id=BANK_ID)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


# ── internal retain ───────────────────────────────────────────────────────

def _stringify_metadata(meta: dict[str, Any] | None) -> dict[str, str]:
    """The client types metadata as dict[str,str]. Coerce safely."""
    if not meta:
        return {}
    out: dict[str, str] = {}
    for k, v in meta.items():
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, (int, float, bool)):
            out[k] = str(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out


def _retain(
    content: str,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    context: str | None = None,
    timestamp: datetime | None = None,
    document_id: str | None = None,
) -> str | None:
    """Single choke-point for all writes. Never raises — a memory write
    failure must not kill the pipeline."""
    if not MEMORY_ENABLED:
        return None
    kwargs: dict[str, Any] = {
        "bank_id": BANK_ID,
        "content": content,
        "metadata": _stringify_metadata(metadata),
        "timestamp": timestamp or datetime.now(timezone.utc),
    }
    if tags:
        kwargs["tags"] = tags
    if context:
        kwargs["context"] = context
    if document_id:
        kwargs["document_id"] = document_id

    try:
        result = _call_async("aretain", **kwargs)
    except Exception as exc:
        print(f"[memory] retain failed: {type(exc).__name__}: {exc}")
        return None

    return (
        getattr(result, "id", None)
        or getattr(result, "memory_id", None)
        or getattr(result, "document_id", None)
        or "ok"
    )


# ── WRITE: A. analysis memory ─────────────────────────────────────────────

def retain_analysis(
    batch: int,
    date: str,
    themes: list[dict[str, Any]],
    brief: dict[str, Any],
) -> dict[str, str | None]:
    """Retain two memories for a batch:
       1. Full analysis blob (JSON) — rich context for reflect().
       2. Compact "theme names" memory — parseable, with metadata, so
          recall_past_theme_names() can reconstruct the theme list
          without relying on JSON surviving Hindsight's extraction.
    Returns {"analysis_id": ..., "names_id": ...}."""
    full = {
        "type": "analysis",
        "batch": batch,
        "date": date,
        "themes": themes,
        "brief": brief,
    }
    analysis_id = _retain(
        json.dumps(full, indent=2, default=str),
        tags=[f"batch:{batch}", "analysis"],
        metadata={"kind": "analysis", "batch": batch, "date": date},
        context=f"TaskFlow feedback analysis for batch {batch} ({date})",
        document_id=f"analysis-batch-{batch}",
    )

    names = [t.get("name", "") for t in themes if t.get("name")]
    names_csv = "|".join(names)
    names_sentence = (
        f"Batch {batch} (analyzed on {date}) used these theme names: "
        + ", ".join(names)
        + "."
    )
    names_id = _retain(
        names_sentence,
        tags=[f"batch:{batch}", "analysis_names"],
        metadata={
            "kind": "analysis_names",
            "batch": batch,
            "date": date,
            "names_csv": names_csv,
        },
        context=f"Theme names chosen for batch {batch}",
        document_id=f"theme-names-batch-{batch}",
    )

    # Structured stats: BOTH the exact theme name AND a stable keyword
    # key, so trend lookup survives naming drift between batches.
    from .pipeline import theme_key as _theme_key
    freqs: dict[str, int] = {}
    for t in themes:
        n = t.get("name", "")
        f = int(t.get("frequency", 0))
        if not n:
            continue
        freqs[n] = f  # exact-name key
        k = f"key:{_theme_key(n, t.get('summary', ''))}"
        freqs[k] = max(freqs.get(k, 0), f)  # sum? take max — one batch
    stats_sentence = (
        f"Batch {batch} theme frequencies (review counts): "
        + ", ".join(f"{n}={f}" for n, f in freqs.items())
        + "."
    )
    stats_id = _retain(
        stats_sentence,
        tags=[f"batch:{batch}", "analysis_stats"],
        metadata={
            "kind": "analysis_stats",
            "batch": batch,
            "date": date,
            "freqs_json": json.dumps(freqs),
        },
        context=f"Theme frequencies for batch {batch}",
        document_id=f"theme-stats-batch-{batch}",
    )

    return {"analysis_id": analysis_id, "names_id": names_id,
            "stats_id": stats_id}


# ── WRITE: B. product context ─────────────────────────────────────────────

def retain_product_context(fact: str, category: ContextCategory) -> str | None:
    """Retain a fact the PM tells the agent about the product."""
    payload = {
        "type": "product_context",
        "fact": fact,
        "category": category,
        "date": datetime.now(timezone.utc).date().isoformat(),
    }
    return _retain(
        json.dumps(payload, indent=2),
        tags=["product_context", category],
        metadata={"kind": "product_context", "category": category},
        context="Product context supplied by the PM",
    )


# ── WRITE: C. PM decision ─────────────────────────────────────────────────

def retain_pm_decision(
    recommendation: str,
    decision: DecisionKind,
    reason: str,
    batch: int,
) -> str | None:
    """Retain a PM's reaction to a recommendation."""
    payload = {
        "type": "pm_decision",
        "recommendation": recommendation,
        "decision": decision,
        "reason": reason,
        "batch": batch,
        "date": datetime.now(timezone.utc).date().isoformat(),
    }
    return _retain(
        json.dumps(payload, indent=2),
        tags=["pm_decision", decision, f"batch:{batch}"],
        metadata={"kind": "pm_decision", "decision": decision, "batch": batch},
        context="PM decision on a recommended action",
    )


# ── internal recall ───────────────────────────────────────────────────────

def _normalize_result(r: Any) -> dict[str, Any]:
    """Coerce whatever the SDK returns into a plain dict. Defensive because
    we did not have the RecallResult schema up front."""
    text = (
        getattr(r, "text", None)
        or getattr(r, "content", None)
        or (r if isinstance(r, str) else None)
        or ""
    )
    return {
        "text": text,
        "type": getattr(r, "type", None),
        "score": getattr(r, "score", None),
        "metadata": getattr(r, "metadata", None) or getattr(r, "meta", None),
    }


def _recall_raw(
    query: str,
    *,
    purpose: str,
    types: list[str] | None = None,
    budget: Literal["low", "mid", "high"] = "mid",
    tags: list[str] | None = None,
    tags_match: Literal["any", "all", "any_strict", "all_strict", "exact"] = "any",
    prefer_observations: bool = False,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Single choke-point for all reads. Logs every call to MEMORY_LOG."""
    if not MEMORY_ENABLED:
        return []

    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    error: str | None = None

    try:
        kwargs: dict[str, Any] = {
            "bank_id": BANK_ID,
            "query": query,
            "types": types or ["world", "observation", "experience"],
            "budget": budget,
            "max_tokens": 4096,
            "prefer_observations": prefer_observations,
        }
        if tags:
            kwargs["tags"] = tags
            kwargs["tags_match"] = tags_match
        resp = _call_async("arecall", **kwargs)

        raw = getattr(resp, "results", None)
        if raw is None:
            raw = getattr(resp, "memories", None) or []
        for r in list(raw)[:max_results]:
            results.append(_normalize_result(r))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        print(f"[memory] recall failed ({purpose}): {error}")

    log = RecallLog(
        ts=datetime.now(timezone.utc).isoformat(),
        purpose=purpose,
        query=query,
        bank_id=BANK_ID,
        result_count=len(results),
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        results=results if not error else [{"error": error}],
    )
    _append_log(log)
    return results


def _append_log(log: RecallLog) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except Exception as exc:
        print(f"[memory] log write failed: {exc}")


def _read_logs() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ── READ HOOK 1: theme labeling ───────────────────────────────────────────

_NAME_SPLIT = re.compile(r"[|,]\s*")


def recall_past_theme_names(batch: int) -> list[str]:
    """Before labeling a new batch's clusters, recall theme names from
    previous batches so the same issue keeps a consistent name.

    Primary signal: metadata.names_csv on analysis_names memories
    (survives Hindsight's prose extraction). Fallback: parse the prose
    sentence prefix "Batch N ... used these theme names: A, B, C."
    """
    results = _recall_raw(
        f"What theme names were used in analyses of batches before batch {batch}? "
        f"List the exact theme names.",
        purpose="theme_labeling",
        types=["world"],
        tags=["analysis_names"],
        tags_match="any",
        max_results=30,
    )
    names: list[str] = []
    for r in results:
        meta = r.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("kind") == "analysis_names":
            csv = meta.get("names_csv") or ""
            if isinstance(csv, str) and csv:
                for n in csv.split("|"):
                    n = n.strip()
                    if n and n not in names:
                        names.append(n)
                continue
        text = r.get("text", "")
        if "theme names" in text:
            try:
                tail = text.split("theme names", 1)[1]
                tail = tail.split(":", 1)[1] if ":" in tail else tail
                tail = tail.split(".")[0]
                for n in _NAME_SPLIT.split(tail):
                    n = n.strip()
                    if n and n not in names:
                        names.append(n)
            except Exception:
                pass
    return names


# ── READ HOOK 2: scoring / trends ─────────────────────────────────────────

def recall_prior_scores(batch: int) -> list[dict[str, Any]]:
    """Before scoring this batch, recall prior theme scores so trends can
    be computed against real history."""
    return _recall_raw(
        f"What were the theme scores, frequencies, and trends in batch "
        f"{batch - 1} and earlier? Include sentiment and frequency.",
        purpose="scoring_trends",
        types=["world", "observation"],
        tags=["analysis"],
        max_results=20,
    )


# ── READ HOOK 2b: prior frequencies (numeric trend) ──────────────────────

def get_prior_frequencies(current_batch: int) -> dict[str, dict[int, int]]:
    """Return {theme_name: {batch: frequency}} for all batches < current_batch.
    Reads from analysis_stats metadata (survives Hindsight extraction)."""
    if not MEMORY_ENABLED:
        return {}
    results = _recall_raw(
        f"Theme frequencies from batches before batch {current_batch}",
        purpose="prior_frequencies",
        types=["world"],
        tags=["analysis_stats"],
        max_results=20,
    )
    out: dict[str, dict[int, int]] = {}
    for r in results:
        meta = r.get("metadata") or {}
        if not isinstance(meta, dict) or meta.get("kind") != "analysis_stats":
            continue
        try:
            b = int(meta.get("batch", 0))
        except (ValueError, TypeError):
            continue
        if b == 0 or b >= current_batch:
            continue
        try:
            freqs = json.loads(meta.get("freqs_json") or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(freqs, dict):
            continue
        for name, freq in freqs.items():
            try:
                out.setdefault(name, {})[b] = int(freq)
            except (ValueError, TypeError):
                continue
    return out


# ── READ HOOK 3: brief generation ─────────────────────────────────────────

def recall_context_for_brief(batch: int) -> dict[str, list[dict[str, Any]]]:
    """Before generating the brief, recall three things:
       shipped features, rejected recommendations, and PM preferences."""
    shipped = _recall_raw(
        "What features have been shipped, fixed, or are on the roadmap? "
        "What constraints or target-user facts has the PM given?",
        purpose="brief_shipped_and_context",
        types=["world"],
        tags=["product_context"],
        max_results=15,
    )
    rejected_raw = _recall_raw(
        "What recommendations were rejected by the PM, and why? "
        "What reason was given?",
        purpose="brief_rejected_ideas",
        types=["experience", "observation", "world"],
        tags=["pm_decision"],
        max_results=15,
    )
    # Keep only actual rejections — accepted/edited decisions must NOT
    # suppress a theme. Metadata is authoritative when present; fall
    # back to keyword scan of the extracted text when it was stripped.
    def _is_rejection(hit: dict) -> bool:
        meta = hit.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("decision"):
            return meta.get("decision") == "rejected"
        text = (hit.get("text") or "").lower()
        return ("reject" in text) and ("accept" not in text)

    rejected = [h for h in rejected_raw if _is_rejection(h)]
    preferences = _recall_raw(
        "What are the PM's stated preferences for how recommendations "
        "should be ranked, formatted, scoped, or justified?",
        purpose="brief_pm_preferences",
        types=["observation", "world"],
        tags=["product_context"],
        max_results=10,
    )
    return {"shipped": shipped, "rejected": rejected, "preferences": preferences}


# ── READ: reflect profile ─────────────────────────────────────────────────

def reflect_profile(
    query: str = (
        "Summarize what you have learned about this product manager and the "
        "TaskFlow product: their priorities, what they have rejected and why, "
        "what has shipped, and how they like briefs structured. Be concrete."
    ),
) -> str:
    if not MEMORY_ENABLED:
        return "[memory disabled]"
    try:
        answer = _call_async(
            "areflect", bank_id=BANK_ID, query=query, budget="mid",
        )
        # SDK returns ReflectResponse — try .text then .answer then str()
        return (
            getattr(answer, "text", None)
            or getattr(answer, "answer", None)
            or str(answer)
        )
    except Exception as exc:
        return f"[reflect failed: {type(exc).__name__}: {exc}]"


# ── INSPECT ───────────────────────────────────────────────────────────────

def stats() -> dict[str, Any]:
    logs = _read_logs()
    base = {
        "enabled": MEMORY_ENABLED,
        "bank_id": BANK_ID,
        "recall_count": len(logs),
        "memory_count": 0,
    }
    if not MEMORY_ENABLED:
        return base
    try:
        resp = _call_async("alist_memories", bank_id=BANK_ID, limit=1000)
        items = getattr(resp, "items", None)
        if items is None:
            items = getattr(resp, "memories", None) or []
        base["memory_count"] = len(list(items))
    except Exception as exc:
        base["memory_count"] = -1
        base["error"] = f"{type(exc).__name__}: {exc}"
    return base


def recent_recalls(limit: int = 20) -> list[dict[str, Any]]:
    return _read_logs()[-limit:]


_WHEN_RE = re.compile(r"\|\s*When:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def extract_when(text: str) -> str | None:
    """Hindsight appends '| When: YYYY-MM-DD' to extracted facts. Return the
    date so the UI can show 'recalled from 3 weeks ago'."""
    m = _WHEN_RE.search(text or "")
    return m.group(1) if m else None


def list_all(limit: int = 200) -> list[dict[str, Any]]:
    """Return retained memories as {id, date, type, snippet} for the UI."""
    if not MEMORY_ENABLED:
        return []
    try:
        resp = _call_async("alist_memories", bank_id=BANK_ID, limit=limit)
        items = getattr(resp, "items", None)
        if items is None:
            items = getattr(resp, "memories", None) or []
        out = []
        for m in items:
            text = (
                getattr(m, "text", None)
                or getattr(m, "content", None)
                or ""
            )
            meta = getattr(m, "metadata", None) or {}
            out.append({
                "id": getattr(m, "id", None) or getattr(m, "memory_id", None),
                "date": str(
                    getattr(m, "created_at", None)
                    or meta.get("date", "")
                ),
                "type": meta.get("kind", "unknown"),
                "snippet": (text[:200] + "…") if len(text) > 200 else text,
            })
        return out
    except Exception as exc:
        print(f"[memory] list_all failed: {type(exc).__name__}: {exc}")
        return []
