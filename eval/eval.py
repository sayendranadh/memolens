"""
eval/eval.py — honest measurement of memory impact.

    python -m eval.eval               # reset bank, run both conditions
    python -m eval.eval --no-reset    # keep bank state

Outputs: eval/results/{metrics.json, metrics.md, ui.json}
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend import memory  # noqa: E402
from backend.pipeline import run_pipeline  # noqa: E402
from backend.embeddings import embed  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.metrics import adjusted_rand_score  # noqa: E402

DATA = REPO / "data"
OUT = Path(__file__).resolve().parent / "results"
GOLDEN = Path(__file__).resolve().parent / "golden_labels.json"
OUT.mkdir(parents=True, exist_ok=True)

# ── planted story ────────────────────────────────────────────────────────
SEED_CONTEXT = [
    ("Shipped startup speed fix in v2.3 on 2026-09-01", "shipped"),
    ("Enterprise customers only — theming is a distraction", "preference"),
]
SEED_DECISIONS = [
    ("Add dark mode", "rejected",
     "Enterprise customers only — theming is a distraction", 1),
    ("Fix sync bugs", "accepted", "Top complaint from paying users", 1),
]
SUPPRESS_TERMS = [
    "dark mode", "dark theme", "theming",
    "startup speed", "slow startup", "cold start", "load time",
]
GT_TRENDS = {
    ("sync_bugs", 2): "up",
    ("sync_bugs", 3): "up",
    ("slow_startup", 2): "down",
    ("slow_startup", 3): "down",
    ("calendar_integration", 3): "new",
}
GT_KEYWORDS = {
    "sync_bugs": ["sync", "synchroniz", "cross-device", "data loss",
                  "device", "conflict", "offline", "delay"],
    "slow_startup": ["startup", "slow", "launch", "load time",
                     "cold start", "performance", "lag", "loading"],
    "dark_mode": ["dark mode", "dark theme", "theming", "theme",
                  "night mode"],
    "pricing": ["pricing", "price", "subscription", "expensive",
                "cost", "billing", "paywall", "overpriced"],
    "calendar_integration": ["calendar", "schedule", "ics",
                             "google cal", "integrat"],
}


# ── helpers ──────────────────────────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _load_batch(n: int) -> list[dict]:
    return json.loads((DATA / f"batch_{n}.json").read_text())


def _cluster_reviews(reviews: list[dict]) -> tuple[list[int], int]:
    X = embed([r["text"] for r in reviews])
    k = max(6, min(10, len(reviews) // 25))
    labels = KMeans(n_clusters=k, n_init=10, random_state=42) \
        .fit_predict(X).tolist()
    return labels, k


def _theme_to_gt(theme: dict, reviews: list[dict]) -> str | None:
    """Map a pipeline theme to its ground-truth label. Evidence first
    (verbatim quotes → source review → GT), keywords second."""
    votes: Counter[str] = Counter()
    for q in theme.get("evidence", []):
        best_i, best_s = None, 0.0
        for i, r in enumerate(reviews):
            s = _sim(q, r["text"])
            if s > best_s:
                best_i, best_s = i, s
        if best_i is not None and best_s > 0.5:
            votes[reviews[best_i]["ground_truth_theme"]] += 2
    name = (theme.get("name") or "").lower()
    for gt, kws in GT_KEYWORDS.items():
        for kw in kws:
            if kw in name:
                votes[gt] += 1
    return votes.most_common(1)[0][0] if votes else None


# ── cluster quality (memory-independent) ────────────────────────────────

def cluster_quality(batch: int) -> dict:
    reviews = _load_batch(batch)
    labels, k = _cluster_reviews(reviews)
    gt = [r["ground_truth_theme"] for r in reviews]
    ari = float(adjusted_rand_score(gt, labels))
    correct = 0
    for cid in set(labels):
        members = [gt[i] for i in range(len(reviews)) if labels[i] == cid]
        if members:
            correct += Counter(members).most_common(1)[0][1]
    return {"purity": round(correct / len(reviews), 3),
            "ari": round(ari, 3), "k": k, "n": len(reviews)}


def ensure_golden(n: int = 50) -> tuple[list[dict], bool]:
    if GOLDEN.exists():
        return json.loads(GOLDEN.read_text()), False
    rng = random.Random(1337)
    all_rev = [{"review_id": r["id"], "batch": b,
                "expected_theme": r["ground_truth_theme"], "text": r["text"]}
               for b in (1, 2, 3) for r in _load_batch(b)]
    sample = rng.sample(all_rev, min(n, len(all_rev)))
    GOLDEN.write_text(json.dumps(sample, indent=2))
    return sample, True


def subset_label_accuracy(golden: list[dict],
                          batches: tuple[int, ...] = (1, 2, 3)) -> float:
    by_batch: dict[int, list[dict]] = {}
    for g in golden:
        if g["batch"] in batches:
            by_batch.setdefault(g["batch"], []).append(g)
    correct = total = 0
    for batch, entries in by_batch.items():
        reviews = _load_batch(batch)
        id_to_idx = {r["id"]: i for i, r in enumerate(reviews)}
        labels, _ = _cluster_reviews(reviews)
        cluster_gt: dict[int, str] = {}
        for cid in set(labels):
            gts = [reviews[i]["ground_truth_theme"]
                   for i in range(len(reviews)) if labels[i] == cid]
            cluster_gt[cid] = Counter(gts).most_common(1)[0][0]
        for g in entries:
            idx = id_to_idx.get(g["review_id"])
            if idx is None:
                continue
            pred = cluster_gt.get(labels[idx])
            total += 1
            if pred == g["expected_theme"]:
                correct += 1
    return round(correct / total, 3) if total else 0.0


# ── run both conditions ─────────────────────────────────────────────────

def _reset_bank() -> bool:
    if not memory.MEMORY_ENABLED:
        return False
    try:
        memory.delete_bank()
        memory.ensure_bank()
        return True
    except Exception as e:
        print(f"[eval] reset failed: {type(e).__name__}: {e}")
        return False


def _run_condition(label: str, with_memory: bool,
                   batches=(1, 2, 3)) -> dict[tuple[str, int], dict]:
    print(f"\n[eval] running condition: {label}")
    if with_memory:
        memory.MEMORY_ENABLED = True
        _reset_bank()
        # pre-seed context & decisions BEFORE batch 1 so batch 2 sees them
        for text, cat in SEED_CONTEXT:
            memory.retain_product_context(text, cat)
        for rec, dec, reason, b in SEED_DECISIONS:
            memory.retain_pm_decision(rec, dec, reason, b)
        print(f"[eval]   seeded {len(SEED_CONTEXT)} context + "
              f"{len(SEED_DECISIONS)} decisions")
        time.sleep(8)

    out: dict[tuple[str, int], dict] = {}
    for b in batches:
        r = run_pipeline(batch=b, memory_enabled=with_memory)
        out[(label, b)] = r.model_dump()
        print(f"[eval]   {label} batch {b}: {len(r.themes)} themes, "
              f"{len(r.recalled_memories)} recalled")
        if with_memory and b < max(batches):
            time.sleep(6)
    return out


# ── metrics ──────────────────────────────────────────────────────────────

def theme_name_consistency(runs, cond: str, batches=(1, 2, 3)) -> tuple:
    names_per_gt: dict[str, list[str]] = {}
    for b in batches:
        run = runs.get((cond, b))
        if not run:
            continue
        reviews = _load_batch(b)
        for t in run["themes"]:
            gt = _theme_to_gt(t, reviews)
            if gt:
                names_per_gt.setdefault(gt, []).append(t["name"])
    scores, detail = [], {}
    for gt, names in names_per_gt.items():
        if len(names) < 2:
            continue
        top = Counter(names).most_common(1)[0][1]
        s = top / len(names)
        scores.append(s)
        detail[gt] = {"names": names, "score": round(s, 3)}
    return (round(sum(scores) / len(scores), 3) if scores else 0.0), detail


def trend_accuracy(runs, cond: str):
    correct = total = 0
    detail = {}
    for (gt_theme, batch), expected in GT_TRENDS.items():
        run = runs.get((cond, batch))
        if not run:
            continue
        reviews = _load_batch(batch)
        found = None
        for t in run["themes"]:
            if _theme_to_gt(t, reviews) == gt_theme:
                found = t
                break
        total += 1
        got = (found or {}).get("trend") or "NOT_FOUND"
        if got == expected:
            correct += 1
        detail[f"{gt_theme}@b{batch}"] = {"expected": expected, "got": got}
    return (round(correct / total, 3) if total else 0.0), detail


def repeat_recommendation_rate(runs, cond: str, batches=(2, 3)):
    rates, detail = [], {}
    for b in batches:
        run = runs.get((cond, b))
        if not run:
            continue
        recs = run["brief"]["recommendations"]
        if not recs:
            continue
        repeats = []
        for r in recs:
            blob = (r["title"] + " " + r["action"]).lower()
            if any(term in blob for term in SUPPRESS_TERMS):
                repeats.append(r["title"])
        rate = len(repeats) / len(recs)
        rates.append(rate)
        detail[f"batch_{b}"] = {"n": len(recs), "repeats": repeats,
                                "rate": round(rate, 3)}
    return (round(sum(rates) / len(rates), 3) if rates else 0.0), detail


def preference_adherence(runs, cond: str, batches=(2, 3)):
    passes, detail = [], {}
    for b in batches:
        run = runs.get((cond, b))
        if not run:
            continue
        recs = run["brief"]["recommendations"]
        blob = " ".join((r["title"] + " " + r["action"]).lower() for r in recs)
        p1 = not any(t in blob for t in
                     ["dark mode", "dark theme", "theming"])
        p2 = not any(t in blob for t in
                     ["startup speed", "slow startup", "cold start",
                      "load time", "startup time"])
        prefs = run["brief"].get("pm_preferences_applied") or []
        cites = sum(len(r.get("memory_citations") or []) for r in recs)
        p3 = bool(prefs) or cites > 0
        passes.append((int(p1) + int(p2) + int(p3)) / 3)
        detail[f"batch_{b}"] = {"no_dark_mode": p1, "no_startup": p2,
                                "acknowledges_context": p3}
    return (round(sum(passes) / len(passes), 3) if passes else 0.0), detail


# ── orchestration ───────────────────────────────────────────────────────

@dataclass
class ConditionResult:
    condition: str
    theme_name_consistency: float
    trend_accuracy: float
    repeat_recommendation_rate: float
    preference_adherence: float
    details: dict


def _winner(off: float, on: float, lower_is_better: bool = False) -> str:
    if abs(on - off) < 1e-6:
        return "tie"
    return ("ON" if on < off else "OFF") if lower_is_better \
        else ("ON" if on > off else "OFF")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-reset", action="store_true")
    p.add_argument("--batches", default="1,2,3",
                   help="comma-separated batch numbers, e.g. 1,2")
    p.add_argument("--no-cache", action="store_true",
                   help="ignore disk cache (fresh LLM calls)")
    args = p.parse_args()
    batches = tuple(int(x) for x in args.batches.split(","))

    if args.no_cache:
        import backend.llm as _llm
        _orig = _llm.call_json
        def _wrap(*a, **k):
            k["use_cache"] = False
            return _orig(*a, **k)
        _llm.call_json = _wrap
        # also re-export so pipeline picks up the wrapper
        import backend.pipeline as _pl
        _pl.call_json = _wrap

    if not memory.API_KEY or memory.API_KEY.endswith("replace_me"):
        print("[eval] HINDSIGHT_API_KEY not set — cannot run memory ON.")
        sys.exit(1)

    # ── memory OFF first (so ON sees clean state) ────────────────────
    memory.MEMORY_ENABLED = False
    runs_off = _run_condition("off", with_memory=False, batches=batches)
    runs_on = _run_condition("on", with_memory=True, batches=batches)

    runs = {**runs_off, **runs_on}

    print("\n[eval] cluster quality (memory-independent) ...")
    cluster = {b: cluster_quality(b) for b in batches}
    golden, is_proxy = ensure_golden(50)
    subset_acc = subset_label_accuracy(golden, batches=batches)
    if is_proxy:
        print("[eval] WARNING: golden_labels.json was a PROXY. "
              "Hand-label it for a credible number.")

    conds: list[ConditionResult] = []
    for cond in ("off", "on"):
        tnc, d1 = theme_name_consistency(runs, cond, batches=batches)
        ta, d2 = trend_accuracy(runs, cond)
        rr, d3 = repeat_recommendation_rate(runs, cond, batches=batches)
        pa, d4 = preference_adherence(runs, cond, batches=batches)
        conds.append(ConditionResult(
            condition=cond,
            theme_name_consistency=tnc,
            trend_accuracy=ta,
            repeat_recommendation_rate=rr,
            preference_adherence=pa,
            details={"theme_names": d1, "trends": d2,
                     "repeat_recs": d3, "preferences": d4},
        ))
    off, on = conds[0], conds[1]

    metrics = {
        "cluster_quality": cluster,
        "subset_label_accuracy": subset_acc,
        "subset_is_proxy": is_proxy,
        "conditions": {c.condition: asdict(c) for c in conds},
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))

    avg_purity = round(sum(c["purity"] for c in cluster.values()) / 3, 3)
    avg_ari = round(sum(c["ari"] for c in cluster.values()) / 3, 3)

    def fmt(x): return f"{x:.3f}"
    rows = [
        ("Cluster purity", fmt(avg_purity), fmt(avg_purity), "same",
         "— memory-independent"),
        ("Adjusted Rand Index", fmt(avg_ari), fmt(avg_ari), "same",
         "— memory-independent"),
        ("Subset label accuracy (n=50)"
         + (" *proxy" if is_proxy else ""),
         fmt(subset_acc), fmt(subset_acc), "same",
         "— memory-independent"),
        ("Theme-name consistency",
         fmt(off.theme_name_consistency), fmt(on.theme_name_consistency),
         f"{on.theme_name_consistency - off.theme_name_consistency:+.3f}",
         _winner(off.theme_name_consistency, on.theme_name_consistency)),
        ("Trend accuracy",
         fmt(off.trend_accuracy), fmt(on.trend_accuracy),
         f"{on.trend_accuracy - off.trend_accuracy:+.3f}",
         _winner(off.trend_accuracy, on.trend_accuracy)),
        ("Repeat-rec rate (lower=better)",
         fmt(off.repeat_recommendation_rate),
         fmt(on.repeat_recommendation_rate),
         f"{on.repeat_recommendation_rate - off.repeat_recommendation_rate:+.3f}",
         _winner(off.repeat_recommendation_rate,
                 on.repeat_recommendation_rate, lower_is_better=True)),
        ("Preference adherence",
         fmt(off.preference_adherence), fmt(on.preference_adherence),
         f"{on.preference_adherence - off.preference_adherence:+.3f}",
         _winner(off.preference_adherence, on.preference_adherence)),
    ]
    wins = sum(1 for r in rows if r[4] == "ON")
    losses = sum(1 for r in rows if r[4] == "OFF")

    md = [
        "# MemoLens evaluation",
        "",
        f"Reproducible via `python -m eval.eval`. "
        f"Memory ON wins on **{wins}** metric(s), loses on **{losses}**.",
        "",
        "| Metric | Memory OFF | Memory ON | Δ | Winner |",
        "|---|---|---|---|---|",
    ] + [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
    if is_proxy:
        md.append("")
        md.append("\\* Subset label accuracy uses ground-truth labels as a "
                  "proxy because `eval/golden_labels.json` was not hand-"
                  "labeled. Replace with real labels for a credible number.")
    (OUT / "metrics.md").write_text("\n".join(md))

    ui = {
        "comparison": [
            {"metric": "Theme-name consistency",
             "memory_off": off.theme_name_consistency,
             "memory_on": on.theme_name_consistency},
            {"metric": "Trend accuracy",
             "memory_off": off.trend_accuracy,
             "memory_on": on.trend_accuracy},
            {"metric": "Preference adherence",
             "memory_off": off.preference_adherence,
             "memory_on": on.preference_adherence},
            {"metric": "1 − Repeat-rec rate",
             "memory_off": round(1 - off.repeat_recommendation_rate, 3),
             "memory_on": round(1 - on.repeat_recommendation_rate, 3)},
        ],
        "cluster_quality": [
            {"batch": b, "purity": cluster[b]["purity"],
             "ari": cluster[b]["ari"]} for b in sorted(cluster)
        ],
        "subset_label_accuracy": subset_acc,
        "subset_is_proxy": is_proxy,
        "wins": wins, "losses": losses,
    }
    (OUT / "ui.json").write_text(json.dumps(ui, indent=2))

    print()
    print("\n".join(md))
    print(f"\n[eval] wrote:")
    for f in ("metrics.json", "metrics.md", "ui.json"):
        print(f"  eval/results/{f}")

    memory.close_client()


if __name__ == "__main__":
    main()
