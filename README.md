# MemoLens

A feedback synthesizer that gets measurably better at its job the longer
you use it. Raw app reviews in, a prioritized "what to build next" brief
out — and unlike other synthesis tools, MemoLens remembers what it
recommended last time, what the PM rejected, what shipped, and how this
particular PM likes to be briefed.

Built for the Hindsight hackathon. Memory is 25% of the judging, so it
isn't a bolt-on — it's the load-bearing wall.

---

## Problem

Product managers drown in feedback. Existing tools cluster reviews, name
themes, and emit a brief. Every session. From scratch. They have amnesia:

- They re-invent theme names every run, so trends are invisible.
- They re-recommend rejected ideas, because the rejection was never stored.
- They re-recommend shipped features, because "shipped" isn't data they hold.
- They ignore the PM's format preferences, because those live in a Slack DM.

MemoLens fixes all four by retaining everything that matters into a
Hindsight bank and recalling it before it writes a single word of the
brief.

---

## Architecture
Raw reviews -> Clean -> Embed (MiniLM) -> Cluster (KMeans) -> Label (Groq 20B)
|
+-----------------------------------------+
| v
| Score (freq · sentiment · trend)
| |
RECALL hooks ----------> v
past theme names | Brief (Groq 120B -> 20B fallback)
prior frequencies | |
shipped + rejected | v

PM preferences | Prioritized brief
| |
v v
Hindsight Cloud <---- RETAIN (analysis + names + stats)
bank: taskflow-pm <-- RETAIN (product context)
<-- RETAIN (PM decision)
<-> REFLECT (learned profile)

text

The only module that touches Hindsight is `backend/memory.py`. A single
env flag (`MEMORY_ENABLED`) flips the entire pipeline between cold and warm
without touching any other file. That's what makes the before/after honest.

---

## Memory design

One bank per product workspace (`HINDSIGHT_BANK_ID=taskflow-pm`). Three
memory categories, distinguished by tags and metadata.

| # | Category | Tag | Retained when | Recalled before |
|---|---|---|---|---|
| A | Analysis | `analysis`, `batch:N` | after every pipeline run | (1) theme labeling, (2) trend scoring |
| B | Product context | `product_context`, `shipped`/`roadmap`/... | PM tells the agent a fact | brief generation |
| C | PM decision | `pm_decision`, `accepted`/`rejected`/`edited` | PM reacts to a recommendation | brief generation |

**Four read hooks, all before the LLM sees anything:**

1. Before labeling — `recall_past_theme_names()` so "sync bugs" stays
   "sync bugs" across batches instead of becoming "cross-device sync
   issues" and breaking the trend chart.
2. Before scoring — `get_prior_frequencies()` reads structured frequency
   metadata and computes trend numerically. Up if the theme grew >15%,
   down if it shrank >15%, stable otherwise. No LLM guessing.
3. Before the brief — `recall_context_for_brief()` pulls three things in
   separate queries (so the UI can label them): shipped features, rejected
   recommendations, and PM format/tone preferences. The brief generator
   is instructed not to re-recommend shipped features and not to
   re-surface rejected ideas without noting the rejection.
4. On demand — `reflect_profile()` synthesizes "what I've learned about
   this PM and product". Not a list of memories — a paragraph.

**Every read is logged** to `data/memory_log.jsonl` with query, results,
latency, and purpose. The UI's memory panel renders this live. If you
can't see the recall, it didn't happen.

### Two gotchas we engineered around

1. Hindsight extracts, it doesn't store. Retaining a JSON blob of themes
   returns prose facts on recall. So we retain theme names a second time
   as a prose sentence + `names_csv` metadata, and read the metadata back.
   This is why `retain_analysis()` writes three memories, not one.
2. Hindsight's sync client breaks in FastAPI threadpools. Its
   `asyncio.timeout` requires a running Task. `memory.py` owns a dedicated
   worker thread with its own event loop; all calls hop onto it via
   `run_coroutine_threadsafe` and use the client's async methods.

---

## Setup

Requires Python 3.11+ and Node 18+. Tested on WSL2 Ubuntu 24.04.
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
$EDITOR .env # fill in HINDSIGHT_API_KEY and GROQ_API_KEY
python backend/verify_env.py

text

`verify_env.py` proves Python, both API keys, Groq (both models), and
MiniLM embeddings all work before we run any real pipeline.

### Env vars

| Var | Required | Default | Purpose |
|---|---|---|---|
| `HINDSIGHT_API_KEY` | yes | — | Cloud key, `hsk_…` |
| `HINDSIGHT_BASE_URL` | yes | `https://api.hindsight.vectorize.io` | Cloud endpoint |
| `HINDSIGHT_BANK_ID` | no | `taskflow-pm` | One bank per workspace |
| `GROQ_API_KEY` | yes | — | Groq free tier |
| `GROQ_MODEL_REASON` | no | `openai/gpt-oss-120b` | Brief generation |
| `GROQ_MODEL_FAST` | no | `openai/gpt-oss-20b` | Labeling + classification |
| `MEMORY_ENABLED` | no | `true` | Global kill-switch |
| `ALLOW_RESET` | no | `false` | Set `true` to enable `/reset` |
| `VITE_API_URL` | no | `http://localhost:8000` | Frontend -> backend |

Every LLM call is cached on disk keyed by input hash. Re-running an
analysis is free after the first pass. On the Groq free tier, this is the
single most important engineering decision.

### Run the demo
make run-backend # Terminal 1
make frontend-dev # Terminal 2
make seed-data # Terminal 3, once

text

Open http://localhost:5173 and click the "Run 3-session demo" button.

---

## Evaluation

`make eval` runs the full pipeline twice — once with `MEMORY_ENABLED=false`
and once with `MEMORY_ENABLED=true` — across all three batches, then
computes seven metrics.

Cluster quality metrics are memory-independent by construction. The
clustering step runs identically in both conditions; memory only affects
labeling, scoring, and the brief.

### Last recorded run

| Metric | Memory OFF | Memory ON | Delta | Winner |
|---|---|---|---|---|
| Cluster purity | 0.854 | 0.854 | same | — memory-independent |
| Adjusted Rand Index | 0.615 | 0.615 | same | — memory-independent |
| Subset label accuracy (n=50) proxy | 0.880 | 0.880 | same | — memory-independent |
| Theme-name consistency | 0.486 | 0.750 | +0.264 | ON |
| Trend accuracy | 0.200 | 1.000 | +0.800 | ON |
| Repeat-rec rate (lower=better) | 0.325 | 0.000 | -0.325 | ON |
| Preference adherence | 0.167 | 1.000 | +0.833 | ON |

**Memory ON wins 4, ties 0, loses 0.**

### What the numbers actually mean

- Trend accuracy 1.000 vs 0.200 — memory ON detects all five planted arcs
  (sync grows, startup fades, calendar appears). Memory OFF cannot detect
  trends because it has no history.
- Repeat-rec rate 0.000 vs 0.325 — memory OFF re-suggests rejected or
  already-shipped ideas roughly 1 in 3 recommendations. Memory ON never does.
- Preference adherence 1.000 vs 0.167 — memory ON follows all three stated
  PM preferences on every batch tested.
- Theme-name consistency 0.750 vs 0.486 — moderate win.

### Reproducing
make eval # full run, ~10 min on free tier
make eval-quick # batches 1+2 only, ~4 min

text

---

## Demo script

See DEMO.md. ~2.5 minutes, five beats.

---

## Limitations

Read this before you judge.

- Clustering/scoring is deliberately simple — KMeans with a hand-picked k,
  and a linear score formula. The novelty is memory, not the clustering.
- `gpt-oss` models on Groq occasionally return empty content in JSON mode.
  `llm.py` falls back to plain-text extraction when that happens, and
  `pipeline.py` falls back to a deterministic keyword name if both LLM
  paths fail.
- The 50-review "hand-labeled" subset is a proxy. Replace
  `eval/golden_labels.json` with real hand labels to make the metric real.
- Trend accuracy is a rigged-looking metric by design. Memory OFF cannot
  detect trends because it has no history. The comparison is correct, but
  be ready to explain why any non-trivial trend metric requires memory.
- The compare view diffs recommendations by title string. Two
  recommendations with different wording but the same underlying theme
  register as "newly surfaced" / "suppressed".
- Free tier is real. The 120B model hits a 200k-tokens/day cap. The disk
  cache makes reruns free, and brief generation falls back to 20B with a
  warning field.
- No auth on the API. It's a hackathon demo. Don't expose it.

---

## What we're proud of

- Memory is central and visible, not bolted on.
- The before/after comparison is honest. The pipeline is identical; only
  `MEMORY_ENABLED` differs.
- Engineering around free-tier limits is a feature: disk cache, exponential
  backoff, model routing, and deterministic fallbacks that never leave the
  user with an empty brief.
- Measured improvement, not vibes. Four memory-specific metrics, all
  numeric, all reproducible.

---

## License

MIT.
