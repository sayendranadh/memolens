# MemoLens — 2.5 minute demo

**Setup (before you present):**

Terminal 1:  make run-backend
Terminal 2:  make frontend-dev

Then open http://localhost:5173 and click "Run 3-session demo" once.
Let it finish (~5-8 min). This warms the LLM disk cache so the live
demo runs fast and free.

Reset for the live demo:

    curl -s -X POST localhost:8000/reset -H "X-Confirm-Reset: yes"

---

## Beat 1 — the problem (15s)

> "Every PM tool does the same thing: cluster reviews, name themes, write
> a brief. And they all have amnesia. Every Monday, from scratch."

Point at the Analysis tab, Memory toggle.

> "This is what you get with memory off."

Click Analyze on batch 1, with memory toggled OFF.

> "Plausible. Generic. And next week it will say the exact same thing
> with different names."

## Beat 2 — teach it (20s)

Click "Run 3-session demo" in the header. The banner narrates progress.

> "Now I do what a PM actually does. I reject dark mode — enterprise
> customers only. I accept the sync bug fix. And I tell it we shipped a
> startup speed fix last quarter."

Point at the "Teach the agent" card (bottom left). That's where context
gets retained.

> "Every one of those facts goes into the memory bank."

## Beat 3 — memory makes it better (30s)

Demo finishes. UI is on batch 3.

> "Same product. Six weeks later. Watch what changed."

Point at the memory panel on the right — recall entries are streaming in.

> "Before it wrote a single word of the brief, it recalled my rejection,
> the shipped fix, and the theme names it used last time."

Point at the brief:

- Dark mode is gone — the rejected idea didn't come back.
- Startup speed isn't recommended — it shipped.
- Sync shows up — the trend was computed across three batches.
- Calendar integration is new — it appeared in batch 3.

## Beat 4 — the before/after (30s)

Switch to Before / After tab. Click "Compare 3". Wait ~2 min.

> "Same input. Same LLM. Same clustering. The only difference is memory."

Point at the two columns:

- Memory OFF column with red-tinted cards = recommendations memory suppresses.
- Memory ON column with green-tinted cards = recommendations memory surfaced.
- Bottom summary: N newly surfaced / M suppressed.

> "This is the whole project on one screen. Memory isn't a feature,
> it's the difference between a generic brief and a brief that knows you."

## Beat 5 — the learned profile (25s)

Switch to Learned profile tab.

> "And it can tell me what it's learned about me."

Read the reflect() paragraph aloud. It should mention enterprise focus,
the dark-mode rejection, and the shipped fix.

Point at the timeline below it.

> "Every analysis, every product fact, every PM decision. Timestamped.
> Recallable weeks later. That's Hindsight."

## Closing (10s)

Switch back to Before / After.

> "The brief on the left was written by the same model that wrote the one
> on the right. The difference is what it remembered."

---

## If something breaks on stage

- No recalls in memory panel: bank empty. Run python backend/verify_env.py
  to confirm keys, then re-run the demo button.
- Demo hangs on Groq: rate-limited. Every call is disk-cached; re-running
  the same demo serves from cache. Wait 60s.
- Brief looks identical in ON and OFF: the ON run didn't reach the bank.
  Check data/memory_log.jsonl — if empty, MEMORY_ENABLED was false.
- Full reset: curl -X POST localhost:8000/reset -H "X-Confirm-Reset: yes"
- Reset returns 403: set ALLOW_RESET=true in .env and restart the backend.
