"""
backend/pipeline.py — the analysis pipeline, memory OFF or ON.

    clean → embed → cluster → label → score → brief
            ↑                  ↑       ↑       ↑
            │                  │       │       └─ recall: context, rejections, prefs
            │                  │       └──────── recall: prior scores → trend
            │                  └──────────────── recall: prior theme names
            └─ (nothing touches memory until labeling)

Every memory read/write goes through backend.memory so MEMORY_ENABLED is
the single switch. If memory.MEMORY_ENABLED is False, no recalls fire and
no retains happen — the pipeline runs identically.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from . import memory
from .llm import call_json, RateLimited, MODEL_FAST, MODEL_REASON, BadLLMOutput
from .embeddings import embed
from .models import (
    Theme, Recommendation, Brief, AnalysisResult, RecalledMemory,
)


THEME_KEYWORDS: dict[str, list[str]] = {
    "sync": ["sync", "synchroniz", "cross-device", "device", "conflict",
             "data loss", "offline", "delay"],
    "startup": ["startup", "slow", "cold start", "launch", "loading",
                "performance", "lag"],
    "pricing": ["pricing", "price", "subscription", "expensive",
                "overpriced", "cost", "billing", "paywall"],
    "dark_mode": ["dark mode", "dark theme", "theming", "theme",
                  "night mode"],
    "calendar": ["calendar", "schedule", "ics", "integration"],
    "search": ["search", "find", "filter"],
    "notifications": ["notification", "reminder"],
    "mobile": ["mobile", "iphone", "android", "phone", "tablet"],
    "onboarding": ["onboarding", "tutorial", "first-run"],
    "sharing": ["sharing", "collaboration", "guest"],
}

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))

# Aligned to the generated data window (batch week-end).
BATCH_DATES = {1: "2026-08-16", 2: "2026-09-06", 3: "2026-09-27"}


# ── IO ────────────────────────────────────────────────────────────────────

def _load_batch(batch: int) -> list[dict]:
    p = DATA_DIR / f"batch_{batch}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing. Run `python -m backend.generate_data` first."
        )
    return json.loads(p.read_text())


# ── clustering ────────────────────────────────────────────────────────────

def _cluster(X: np.ndarray, k: int) -> list[list[int]]:
    from sklearn.cluster import KMeans
    labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X)
    groups: list[list[int]] = [[] for _ in range(k)]
    for i, lab in enumerate(labels):
        groups[int(lab)].append(i)
    return [g for g in groups if g]


def _theme_id(name: str) -> str:
    return hashlib.sha1(name.lower().strip().encode()).hexdigest()[:10]


# ── labeling ──────────────────────────────────────────────────────────────

def _fallback_name(texts: list[str]) -> str:
    """Deterministic last-resort name from distinctive tokens.
    Never returns 'Unlabeled'."""
    STOP = {
        "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
        "to", "of", "in", "on", "at", "for", "with", "by", "from", "as",
        "it", "its", "this", "that", "these", "those", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "should",
        "can", "could", "may", "might", "must", "i", "you", "we", "they",
        "my", "your", "our", "their", "me", "us", "them", "so", "if", "not",
        "no", "yes", "just", "very", "really", "please", "app", "use", "used",
        "using", "like", "would", "love", "want", "need", "get", "got",
        "make", "makes", "made", "still", "even", "much", "many", "some",
        "any", "all", "more", "most", "than", "then", "now", "here", "there",
        "why", "what", "when", "where", "how", "which", "who", "when",
    }
    from collections import Counter
    import re as _re
    counts: Counter[str] = Counter()
    for t in texts:
        for w in _re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (t or "").lower()):
            if w in STOP or len(w) < 4:
                continue
            counts[w] += 1
    if not counts:
        return "General feedback"
    # One distinctive token only — multi-token joins read like nonsense
    # ("Sync Between Work issues") and, worse, collide across subclusters.
    top_word = counts.most_common(1)[0][0]
    return f"{top_word.capitalize()} issues"


def _fallback_name_v2(texts: list[str]) -> str:
    """Keyword-vote fallback that produces a name theme_key can match.
    Runs THEME_KEYWORDS over the evidence and picks the best-fitting theme.
    Falls back to the single-token heuristic only if no keyword fires."""
    blob = " ".join(texts).lower()
    votes: dict[str, int] = {}
    for key, kws in THEME_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in blob)
        if score:
            votes[key] = score
    if votes:
        best = max(votes, key=votes.get)
        return best.replace("_", " ").title() + " issues"
    return _fallback_name(texts)


def _label_cluster(reviews: list[dict], prior_names: list[str]) -> dict:
    sample = [r["text"] for r in reviews[:12]]
    example = (
        'Example of a valid reply:\n'
        '{"name": "Sync reliability issues", '
        '"summary": "Users report silent sync failures and lost edits.", '
        '"evidence": ["Sync failed silently and I did not notice.", '
        '"Lost a whole project because sync overwrote my edits.", '
        '"Changes on one device do not show up on another."]}'
    )
    sys = (
        "You name and summarize clusters of app reviews for a Product Manager.\n"
        "\n"
        "Output: a single JSON object with exactly these keys:\n"
        '  "name"     — 2 to 6 words, title-cased, describes the shared issue\n'
        '  "summary"  — one or two sentences, no bullet points\n'
        '  "evidence" — exactly 3 VERBATIM quotes copied from the input reviews\n'
        "\n"
        + example
    )
    if prior_names:
        sys += (
            "\n\nIMPORTANT: if this cluster is about the same issue as one of "
            "these previously-seen theme names, reuse that name EXACTLY "
            "(character-for-character):\n- " + "\n- ".join(prior_names[:20])
        )
    msgs = [
        {"role": "system", "content": sys},
        {"role": "user",
         "content": "Reviews to label:\n" + "\n".join(f"- {s}" for s in sample)},
    ]

    parsed: dict = {}
    try:
        parsed, _, _ = call_json(msgs, model=MODEL_FAST, max_tokens=600)
    except (RateLimited, BadLLMOutput) as e:
        print(f"[label] LLM call failed: {type(e).__name__}: {e}")

    if not isinstance(parsed, dict) or not parsed.get("name"):
        print(f"[label] JSON attempt produced no name; raw={parsed!r}")
        # Plain-text retry: REPLACE system prompt entirely (do not append).
        plain_msgs = [
            {"role": "system",
             "content": "You name clusters of app reviews. Reply with ONLY "
                        "the theme name — 2 to 6 words, title-cased, no JSON, "
                        "no quotes, no punctuation at the end."},
            {"role": "user",
             "content": "Reviews:\n" + "\n".join(f"- {s}" for s in sample[:8])},
        ]
        try:
            from .llm import _get_client
            r = _get_client().chat.completions.create(
                model=MODEL_FAST, messages=plain_msgs,
                temperature=0.2, max_tokens=30,
            )
            choices = getattr(r, "choices", None) or []
            content = (choices[0].message.content
                       if choices else "") or ""
            lines = content.strip().splitlines()
            nm = lines[0].strip().strip('"').strip("'").strip(".") if lines else ""
            if nm:
                parsed = {"name": nm[:60], "summary": "", "evidence": sample[:3]}
                print(f"[label] plain-text retry succeeded: {nm!r}")
            else:
                print("[label] plain-text retry returned empty")
        except Exception as e2:
            print(f"[label] plain-text retry failed: {type(e2).__name__}: {e2}")

    if not isinstance(parsed, dict) or not parsed.get("name"):
        fb = _fallback_name_v2(sample)
        print(f"[label] using deterministic fallback: {fb!r}")
        parsed = {"name": fb,
                  "summary": "Cluster of related feedback (LLM labeling failed).",
                  "evidence": sample[:3]}

    parsed.setdefault("summary", "")
    parsed.setdefault("evidence", sample[:3])
    if not isinstance(parsed.get("evidence"), list) or not parsed["evidence"]:
        parsed["evidence"] = sample[:3]
    return parsed


# ── scoring ───────────────────────────────────────────────────────────────

def _merge_duplicate_themes(
    themes: list[Theme],
    prior_freqs: dict[str, dict[int, int]] | None = None,
) -> list[Theme]:
    """Merge clusters that share a theme_key. Two clusters with different
    LLM names but the same keyword key ('sync') describe the same theme —
    treat them as one. After merging, recompute trend from the merged
    frequency, not from either subcluster."""
    by_key: dict[str, Theme] = {}
    for t in themes:
        key = theme_key(t.name, t.summary) or t.name.strip().lower()
        if key not in by_key:
            by_key[key] = t
            continue
        a = by_key[key]
        old_freq = a.frequency
        merged_freq = a.frequency + t.frequency
        merged_sent = (
            (a.sentiment_score * old_freq + t.sentiment_score * t.frequency)
            / max(1, merged_freq)
        )
        merged_evidence = list(dict.fromkeys(a.evidence + t.evidence))[:3]
        merged_bd = {
            k: round(
                (a.score_breakdown.get(k, 0) * old_freq
                 + t.score_breakdown.get(k, 0) * t.frequency)
                / max(1, merged_freq),
                3,
            )
            for k in set(a.score_breakdown) | set(t.score_breakdown)
        }
        a.frequency = merged_freq
        a.sentiment_score = round(merged_sent, 3)
        a.evidence = merged_evidence
        a.score_breakdown = merged_bd
        raw = (
            (a.score * old_freq + t.score * t.frequency)
            / max(1, merged_freq)
        )
        a.score = round(max(0.0, min(1.0, raw)), 3)
        # Keep the more informative summary
        if len(t.summary) > len(a.summary):
            a.summary = t.summary
        # If the first cluster's name is worse, adopt the second's
        if len(t.name) > len(a.name) and "issues" not in a.name.lower():
            a.name = t.name

    merged = list(by_key.values())

    # ── Recompute trend from MERGED frequency against prior batches ──
    if prior_freqs:
        for t in merged:
            key = theme_key(t.name, t.summary)
            prior = (prior_freqs.get(f"key:{key}")
                     or prior_freqs.get(t.name) or {})
            if not prior:
                lname = t.name.strip().lower()
                for cand, hist in prior_freqs.items():
                    if cand.strip().lower() == lname:
                        prior = hist
                        break
            t.trend = _compute_trend(t.frequency, prior)
            trend_score = {"up": 1.0, "stable": 0.5,
                           "down": 0.2, "new": 0.6}.get(t.trend, 0.5)
            t.score_breakdown["trend_component"] = round(trend_score, 3)
            freq_norm = t.score_breakdown.get("frequency_norm", 0)
            neg = t.score_breakdown.get("negativity", 0)
            t.score = round(max(0.0, min(1.0,
                0.55 * freq_norm + 0.25 * neg + 0.20 * trend_score)), 3)

    return merged



def theme_key(name: str, summary: str = "") -> str:
    """Reduce a theme to a stable keyword key so trend computation survives
    naming drift across batches. Falls back to the normalized first word."""
    blob = f"{name} {summary}".lower()
    scores: dict[str, int] = {}
    for key, kws in THEME_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in blob)
        if score:
            scores[key] = score
    if scores:
        return max(scores, key=scores.get)
    # no keyword hit — use the first nontrivial word
    for w in name.lower().split():
        if len(w) > 3 and w.isalpha():
            return w
    return name.lower().strip() or "general"


def _compute_trend(current_freq: int, prior: dict[int, int]) -> str:
    """Numeric trend from retained frequencies. Compares current frequency
    to the most recent prior batch using stable thresholds.
        >1.15x prior  → up
        <0.85x prior  → down
        else          → stable
    No prior data → new."""
    if not prior:
        return "new"
    last_batch = max(prior)
    prev = prior[last_batch]
    if prev <= 0:
        return "new"
    ratio = current_freq / prev
    if ratio > 1.15:
        return "up"
    if ratio < 0.85:
        return "down"
    return "stable"


def _score_theme(
    reviews: list[dict],
    label: dict,
    prior_recalls: list[dict],
    prior_freqs: dict[str, dict[int, int]],
) -> tuple[float, dict, str]:
    freq = len(reviews)
    ratings = [r.get("rating", 3) for r in reviews]
    mean_r = float(np.mean(ratings)) if ratings else 3.0
    negativity = max(0.0, (5.0 - mean_r) / 4.0)

    # Numeric trend — look up prior frequencies by KEYWORD key, then by
    # exact name, then by fuzzy name. Keyword first because it survives
    # naming drift across batches (which is the whole point of memory).
    name = label.get("name", "")
    key = theme_key(name, label.get("summary", ""))
    prior = prior_freqs.get(f"key:{key}") or prior_freqs.get(name) or {}
    if not prior:
        lname = name.strip().lower()
        for cand, hist in prior_freqs.items():
            if cand.strip().lower() == lname:
                prior = hist
                break
    trend = _compute_trend(freq, prior)

    # If numeric prior is missing but we have semantic recalls, ask the
    # LLM as a last resort (this is the previous path, kept as fallback).
    if not prior and prior_recalls:
        msgs = [
            {"role": "system", "content": (
                "Compare the current theme frequency to the prior context. "
                'Reply JSON only: {"trend": "up"|"down"|"stable"|"new", '
                '"reason": str}. "up" means growing/more urgent.'
            )},
            {"role": "user", "content":
                f"Current theme: {name}\nSummary: {label.get('summary','')}\n"
                f"Current frequency: {freq}\nMean rating: {mean_r:.2f}\n\n"
                "Prior context:\n"
                + "\n".join(f"- {(m.get('text') or '')[:300]}"
                            for m in prior_recalls[:8])},
        ]
        try:
            p, _, _ = call_json(msgs, model=MODEL_FAST, max_tokens=300)
            llm_trend = p.get("trend", "stable")
            trend = llm_trend
        except (RateLimited, BadLLMOutput):
            pass

    trend_score = {"up": 1.0, "stable": 0.5, "down": 0.2, "new": 0.6}.get(
        trend, 0.5
    )
    freq_norm = min(1.0, freq / 60.0)
    score = 0.55 * freq_norm + 0.25 * negativity + 0.20 * trend_score
    breakdown = {
        "frequency_norm": round(freq_norm, 3),
        "negativity": round(negativity, 3),
        "trend_component": round(trend_score, 3),
    }
    return round(score, 3), breakdown, trend


# ── brief ─────────────────────────────────────────────────────────────────

def _fmt_recall(m: dict) -> str:
    t = (m.get("text") or "").replace("\n", " ").strip()
    return t[:280] + ("…" if len(t) > 280 else "")


def _extract_suppress_keywords(shipped_texts, rejected_texts):
    """Theme keys to suppress: shipped or rejected topics."""
    suppressed = set()
    for txt in (shipped_texts or []) + (rejected_texts or []):
        k = theme_key(txt, "")
        if k and k != "general":
            suppressed.add(k)
    return suppressed


def _generate_brief(
    batch: int,
    themes: list[Theme],
    ctx: dict,
    memory_enabled: bool,
) -> Brief:
    shipped = [_fmt_recall(m) for m in ctx.get("shipped", [])]
    rejected = [_fmt_recall(m) for m in ctx.get("rejected", [])]
    prefs = [_fmt_recall(m) for m in ctx.get("preferences", [])]
    suppress_keys = (
        _extract_suppress_keywords(shipped, rejected)
        if memory_enabled else set()
    )

    sys = (
        "You write a 'what to build next' brief for a Product Manager. "
        'Reply JSON only: {"summary": str, "recommendations": ['
        '{"title": str, "action": str, "rationale": str, '
        '"evidence": [str], "source_theme_id": str, '
        '"memory_citations": [str]}]}. '
        "Rules: 3-5 ranked recommendations; do NOT re-recommend shipped "
        "features; do NOT re-surface rejected ideas without explicitly "
        "noting the rejection; cite specific memory fragments verbatim "
        "in memory_citations when you use them."
    )
    if memory_enabled and (shipped or rejected or prefs):
        sys += (
            "\n\nPRODUCT CONTEXT (from memory):\n"
            "Shipped / roadmap:\n"
            + "\n".join(f"- {s}" for s in shipped)
            + "\n\nRejected by PM:\n"
            + "\n".join(f"- {r}" for r in rejected)
            + "\n\nPM preferences:\n"
            + "\n".join(f"- {p}" for p in prefs)
        )
        if suppress_keys:
            sys += (
                "\n\nMANDATORY EXCLUSION: Do NOT recommend anything "
                "related to these already-shipped or previously-rejected "
                "topics: " + ", ".join(sorted(suppress_keys)) + "."
            )

    theme_payload = [
        {"id": t.id, "name": t.name, "score": t.score,
         "frequency": t.frequency, "trend": t.trend,
         "summary": t.summary, "evidence": t.evidence[:2]}
        for t in themes
    ]
    msgs = [
        {"role": "system", "content": sys},
        {"role": "user",
         "content": f"Batch {batch} themes:\n"
                    + json.dumps(theme_payload, indent=2)},
    ]
    parsed: dict | None = None
    brief_warning: str | None = None

    # Try the strong model first; fall back to the fast one on rate limit.
    for attempt_model in (MODEL_REASON, MODEL_FAST):
        try:
            parsed, _, warn = call_json(msgs, model=attempt_model,
                                        max_tokens=2000)
            if warn:
                brief_warning = warn
            if parsed and parsed.get("recommendations"):
                if attempt_model != MODEL_REASON:
                    brief_warning = (
                        f"brief used {attempt_model} "
                        f"({MODEL_REASON} rate-limited)"
                    )
                break
            parsed = None
        except (RateLimited, BadLLMOutput) as e:
            print(f"[brief] {attempt_model} failed: "
                  f"{type(e).__name__}: {e}")
            parsed = None

    if not parsed or not parsed.get("recommendations"):
        # Deterministic fallback: emit the top themes as recommendations
        # so the caller gets SOMETHING ranked, not an empty brief.
        print("[brief] all LLMs failed — using theme-based fallback")
        top = themes[:4]
        fallback_recs = [{
            "title": t.name,
            "action": (
                f"Address the '{t.name}' cluster — {t.frequency} reviews, "
                f"trend={t.trend}."
            ),
            "rationale": t.summary or "Top-scoring theme this batch.",
            "evidence": t.evidence[:3],
            "source_theme_id": t.id,
            "memory_citations": [],
        } for t in top]
        parsed = {
            "summary": ("LLM brief unavailable (rate limit or parse error) — "
                        "recommendations derived from top-ranked themes."),
            "recommendations": fallback_recs,
        }
        brief_warning = brief_warning or "brief fell back to theme ranking"

    by_id = {t.id: t for t in themes}
    by_name = {t.name.lower(): t for t in themes}
    recs: list[Recommendation] = []
    for i, r in enumerate(parsed.get("recommendations", [])):
        tid = r.get("source_theme_id")
        theme = by_id.get(tid) or by_name.get((r.get("title") or "").lower())
        if theme is None and themes:
            theme = themes[min(i, len(themes) - 1)]
        if theme is None:
            continue
        recs.append(Recommendation(
            id=f"b{batch}-r{i+1}",
            title=r.get("title") or theme.name,
            action=r.get("action", "Investigate"),
            rationale=r.get("rationale", ""),
            evidence=r.get("evidence", theme.evidence[:3]),
            score=theme.score,
            score_breakdown=theme.score_breakdown,
            source_theme_id=theme.id,
            theme_key=theme_key(theme.name, theme.summary),
            memory_citations=r.get("memory_citations", []) if memory_enabled else [],
        ))
    # Drop recommendations whose theme_key matches a suppressed topic.
    if memory_enabled and suppress_keys:
        before = len(recs)
        recs = [r for r in recs if r.theme_key not in suppress_keys]
        dropped = before - len(recs)
        if dropped:
            print(f"[brief] suppressed {dropped} rec(s) matching: "
                  f"{sorted(suppress_keys)}")

    # If we never gave the model any memory context, it can't have used
    # any. Clear citations so the UI doesn't display invented ones.
    if not memory_enabled or not (shipped or rejected or prefs):
        for rec in recs:
            rec.memory_citations = []

    recs.sort(key=lambda x: x.score, reverse=True)
    # Attach warning via a sentinel we pick up in run_pipeline
    brief = Brief(
        batch=batch,
        date=BATCH_DATES.get(batch, ""),
        summary=parsed.get("summary", ""),
        recommendations=recs[:5],
        generated_with_memory=memory_enabled,
        pm_preferences_applied=prefs[:3] if memory_enabled else [],
    )
    brief.__dict__["_brief_warning"] = brief_warning
    return brief


# ── orchestration ─────────────────────────────────────────────────────────

def run_pipeline(batch: int, memory_enabled: bool) -> AnalysisResult:
    """Run the full pipeline. memory_enabled forces memory.MEMORY_ENABLED
    for the duration of the run, then restores it."""
    prev = memory.MEMORY_ENABLED
    memory.MEMORY_ENABLED = bool(memory_enabled)
    log_offset = len(memory._read_logs())
    warning: str | None = None

    try:
        reviews = _load_batch(batch)
        X = embed([r["text"] for r in reviews])
        k = max(6, min(10, len(reviews) // 25))
        groups = _cluster(X, k=k)

        prior_names = memory.recall_past_theme_names(batch)
        prior_freqs = memory.get_prior_frequencies(batch)
        themes: list[Theme] = []
        for g in groups:
            cl = [reviews[i] for i in g]
            label = _label_cluster(cl, prior_names)
            prior_scores = memory.recall_prior_scores(batch) if \
                memory.MEMORY_ENABLED else []
            score, breakdown, trend = _score_theme(
                cl, label, prior_scores, prior_freqs,
            )
            themes.append(Theme(
                id=_theme_id(label["name"]),
                name=label["name"],
                summary=label["summary"],
                frequency=len(cl),
                sentiment_score=round(1 - 2 * breakdown["negativity"], 3),
                trend=trend,
                evidence=label["evidence"][:3],
                score=score,
                score_breakdown=breakdown,
            ))
        themes = _merge_duplicate_themes(themes, prior_freqs)
        themes.sort(key=lambda t: t.score, reverse=True)

        ctx = (
            memory.recall_context_for_brief(batch)
            if memory.MEMORY_ENABLED
            else {"shipped": [], "rejected": [], "preferences": []}
        )
        brief = _generate_brief(batch, themes, ctx, memory.MEMORY_ENABLED)

        if memory.MEMORY_ENABLED:
            memory.retain_analysis(
                batch=batch,
                date=BATCH_DATES.get(batch, ""),
                themes=[t.model_dump() for t in themes],
                brief=brief.model_dump(),
            )

        # Surface any brief warning
        bw = brief.__dict__.pop("_brief_warning", None)
        if bw and not warning:
            warning = bw

        new_logs = memory._read_logs()[log_offset:]
        recalled: list[RecalledMemory] = []
        for r in new_logs:
            for hit in r.get("results", []):
                if "error" in hit:
                    if not warning:
                        warning = f"recall error: {hit['error']}"
                    continue
                recalled.append(RecalledMemory(
                    purpose=r.get("purpose", ""),
                    query=r.get("query", ""),
                    text=hit.get("text", ""),
                    score=hit.get("score"),
                    metadata=hit.get("metadata"),
                ))

        return AnalysisResult(
            batch=batch,
            memory_enabled=memory.MEMORY_ENABLED,
            date=BATCH_DATES.get(batch, ""),
            themes=themes,
            brief=brief,
            recalled_memories=recalled,
            cached=False,
            warning=warning,
        )
    finally:
        memory.MEMORY_ENABLED = prev
