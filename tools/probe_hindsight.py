"""Introspect the REAL Hindsight client API. We do not guess."""
import inspect
from dotenv import load_dotenv

load_dotenv()


def show(obj, name: str) -> None:
    print(f"\n=== {name} ===")
    for a in sorted(dir(obj)):
        if a.startswith("_"):
            continue
        try:
            m = getattr(obj, a)
        except Exception as e:
            print(f"  {a} <getattr err {type(e).__name__}: {e}>")
            continue
        if callable(m):
            try:
                print(f"  {a}{inspect.signature(m)}")
            except (ValueError, TypeError):
                print(f"  {a}(<no signature>)")


import hindsight_client as hc

print(f"package version: {getattr(hc, '__version__', 'unknown')}")

Hindsight = hc.Hindsight
show(Hindsight, "class Hindsight")
print("\n__init__ signature:")
print("  ", inspect.signature(Hindsight.__init__))

print("\n=== live construction ===")
try:
    client = Hindsight()
    print("  constructed OK ->", type(client))
    show(client, "client instance")
except Exception as e:
    print(f"  construction failed: {type(e).__name__}: {e}")
    print("  -> try Hindsight(base_url=..., api_key=...) explicitly")
