"""Preflight: prove every external dependency is reachable."""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()
RESULTS = []


def check(name):
    def deco(fn):
        t0 = time.time()
        try:
            detail = fn()
            RESULTS.append((True, name, detail, time.time() - t0))
        except Exception as e:
            RESULTS.append((False, name, f"{type(e).__name__}: {e}",
                            time.time() - t0))
        return fn
    return deco


@check("python >= 3.11")
def _py():
    assert sys.version_info >= (3, 11), sys.version.split()[0]
    return sys.version.split()[0]


@check("env vars present")
def _env():
    need = ["HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL", "GROQ_API_KEY"]
    missing = [k for k in need
               if not os.getenv(k) or os.getenv(k, "").endswith("replace_me")]
    if missing:
        raise RuntimeError(f"missing/placeholder: {missing}")
    return {k: f"{os.environ[k][:6]}…({len(os.environ[k])}ch)" for k in need}


@check("hindsight-client import")
def _hs():
    import hindsight_client as hc
    return f"v{getattr(hc, '__version__', '?')}, class=Hindsight"


@check("hindsight client constructs")
def _hs_ctor():
    from hindsight_client import Hindsight
    c = Hindsight(
        base_url=os.environ["HINDSIGHT_BASE_URL"],
        api_key=os.environ["HINDSIGHT_API_KEY"],
    )
    return type(c).__name__


def _probe_groq(model_env: str, default_model: str) -> str:
    """Ping a Groq model with JSON mode; fall back to plain text if strict
    JSON is rejected. Returns a short proof string."""
    from groq import Groq, BadRequestError
    c = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = os.getenv(model_env, default_model)
    messages = [
        {"role": "system",
         "content": 'You output strict JSON only. No prose, no markdown. '
                    'Always reply with exactly {"ok": true}'},
        {"role": "user", "content": "Ping. Reply with JSON."},
    ]
    try:
        r = c.chat.completions.create(
            model=model, messages=messages,
            response_format={"type": "json_object"},
            max_tokens=100, temperature=0,
        )
        return r.choices[0].message.content.strip()[:80]
    except BadRequestError:
        # strict JSON mode rejected — retry without response_format
        r = c.chat.completions.create(
            model=model, messages=messages,
            max_tokens=100, temperature=0,
        )
        txt = r.choices[0].message.content.strip()[:80]
        return f"(no-json-mode) {txt}"


@check("groq fast model responds")
def _groq():
    return _probe_groq("GROQ_MODEL_FAST", "openai/gpt-oss-20b")


@check("groq reason model responds")
def _groq_big():
    return _probe_groq("GROQ_MODEL_REASON", "openai/gpt-oss-120b")


@check("sentence-transformers (MiniLM)")
def _st():
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("all-MiniLM-L6-v2")
    v = m.encode(["dark mode please"])
    return f"dim={v.shape[1]}"


@check("sklearn")
def _sk():
    import sklearn
    return sklearn.__version__


print("\n" + "=" * 64)
print("  MemoLens — environment preflight")
print("=" * 64)
for ok, name, detail, dt in RESULTS:
    mark = "PASS" if ok else "FAIL"
    print(f"  {mark}  {name:<34} {dt:6.2f}s  {detail}")
print("=" * 64)
failed = [r for r in RESULTS if not r[0]]
print(f"  {len(RESULTS) - len(failed)}/{len(RESULTS)} passed\n")
if failed:
    print("  Failing checks:")
    for _, name, detail, _ in failed:
        print(f"    - {name}: {detail}")
sys.exit(1 if failed else 0)
