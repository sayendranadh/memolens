"""
backend/run.py — CLI

    python -m backend.run --batch 1 --memory off
    python -m backend.run --batch 3 --memory on
    python -m backend.run --batch 1 --memory off --json
"""
from __future__ import annotations

import argparse
import json

from .pipeline import run_pipeline


def _print_brief(result) -> None:
    bar = "=" * 72
    print(f"\n{bar}")
    print(f"  Batch {result.batch}  ·  {result.date}  ·  "
          f"memory={'ON' if result.memory_enabled else 'OFF'}")
    print(bar)
    if result.warning:
        print(f"  ! {result.warning}")

    print("\n  THEMES (ranked by score)")
    print("  " + "-" * 68)
    for t in result.themes:
        bd = ", ".join(f"{k}={v:.2f}" for k, v in t.score_breakdown.items())
        print(f"  {t.score:.2f}  {t.name}")
        print(f"        {t.summary}")
        print(f"        freq={t.frequency}  sentiment={t.sentiment_score:.2f}"
              f"  trend={t.trend}")
        print(f"        breakdown: {bd}")
        if t.evidence:
            print(f"        evidence: {t.evidence[0][:80]!r}")

    print("\n  BRIEF — what to build next")
    print("  " + "-" * 68)
    print(f"  {result.brief.summary}\n")
    for i, r in enumerate(result.brief.recommendations, 1):
        print(f"  {i}. {r.title}  [score {r.score:.2f}]")
        print(f"     Action: {r.action}")
        print(f"     Why:    {r.rationale}")
        if r.memory_citations:
            print(f"     Memory: {len(r.memory_citations)} citation(s)")
            for c in r.memory_citations[:2]:
                print(f"       · {c[:110]}")
        print()

    if result.memory_enabled and result.recalled_memories:
        by_purpose: dict[str, int] = {}
        for m in result.recalled_memories:
            by_purpose[m.purpose] = by_purpose.get(m.purpose, 0) + 1
        print(f"  RECALLED MEMORIES ({len(result.recalled_memories)} total)")
        print("  " + "-" * 68)
        for purpose, n in by_purpose.items():
            print(f"    {purpose:<34} {n} hits")
    print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, choices=[1, 2, 3], required=True)
    p.add_argument("--memory", choices=["on", "off"], default="off")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = run_pipeline(batch=args.batch, memory_enabled=(args.memory == "on"))

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, default=str))
    else:
        _print_brief(result)


if __name__ == "__main__":
    main()
