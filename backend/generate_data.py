"""
backend/generate_data.py

Deterministic synthetic data generator for the TaskFlow demo. Template-based,
seeded RNG — `make seed-data` is reproducible and costs no tokens.

Planted arcs across three batches:

    theme                   b1    b2    b3    shape
    sync_bugs               40    70   100    growing (getting worse)
    slow_startup            55    30    15    fading (we shipped a fix)
    dark_mode               30    32    28    steady
    pricing                 45    50    55    steady
    calendar_integration     0     0    60    NEW in batch 3
    (+ 5 background themes, ~10-12 each batch)

Writes data/batch_{1,2,3}.json. Every review carries a ground_truth_theme
label; the pipeline NEVER reads this field — only eval/ does.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"
DATA_DIR.mkdir(exist_ok=True)

SEED = 20260928

# ── template pools ──────────────────────────────────────────────────────
SYNC_BUGS = [
    "Sync keeps losing my edits between my laptop and phone. Lost hours of work.",
    "My notes don't sync between devices. I have to re-enter everything manually.",
    "Getting 'sync failed' errors constantly. Can't rely on this for work.",
    "Data conflict warnings every time I switch devices. Unacceptable.",
    "The mobile and desktop apps are completely out of sync.",
    "Just lost a whole project because sync overwrote my desktop edits.",
    "Sync is broken. Changes on one device don't show up on another.",
    "Why does it take 10+ minutes for changes to sync across devices?",
    "Cross-device sync has been unreliable for weeks now.",
    "Sync delay is killing my workflow. I switch between 3 devices daily.",
    "Sync failed silently and I didn't notice until days later.",
    "Multiple sync conflicts this week. No clean way to resolve them.",
    "Sync doesn't work on Android. Works fine on iOS.",
    "Every time I open on a second device I see the wrong state.",
]
SLOW_STARTUP = [
    "Takes 15 seconds to open. Way too slow.",
    "Startup is painfully slow since the last update.",
    "App takes forever to launch. I've started using alternatives.",
    "Cold start is over 20 seconds on my phone.",
    "Why is startup so slow? A simple app should open instantly.",
    "Loading screen is up for ages every single time.",
    "Slow to launch and slow to load my tasks. Painful.",
    "Would love a faster launch. Currently unusable in a hurry.",
    "The app hangs for 10+ seconds on open since v2.2.",
    "Startup performance has gotten worse, not better.",
    "Takes so long to open I forget what I wanted to add.",
    "Slow launch times make me reach for a notes app instead.",
]
DARK_MODE = [
    "Please add a dark mode. The white background kills my eyes at night.",
    "Why is there still no dark theme in 2026?",
    "Dark mode request — I use this app at night a lot.",
    "Would pay extra for a proper dark mode.",
    "Dark theme would make this nicer for evening use.",
    "Add dark mode please. My only real complaint.",
    "Feature request: dark mode. Everything else is great.",
    "The bright white UI is hard on the eyes. Dark mode would help.",
    "Consider adding a dark theme for night owls.",
    "Can we get a dark mode? Would improve late-night usage.",
    "Dark mode is the one thing missing for me.",
    "Please add a night mode / dark theme option.",
]
PRICING = [
    "Way too expensive for what it does. $15/mo is a lot for a to-do app.",
    "Can't justify the subscription price when free options exist.",
    "Pricing is out of touch. I use 10% of the paid features.",
    "Raised prices again? Time to look at alternatives.",
    "The paid tier feels overpriced for personal use.",
    "Free tier is too limited and paid is too expensive.",
    "Not worth the monthly fee compared to competitors.",
    "Would switch to paid if the price was reasonable.",
    "Cancelled my subscription. Price doesn't match the value.",
    "Team plan pricing is absurd for a small team.",
    "Too expensive. I'd rather pay once than subscribe.",
    "Cost keeps going up with no new features that matter.",
]
CALENDAR = [
    "Please integrate with Google Calendar. I live in my calendar.",
    "Would love two-way calendar sync so tasks show up in my schedule.",
    "Calendar integration is the missing piece for me.",
    "Feature request: pull in Outlook / Google Calendar events.",
    "I want my tasks to appear in my calendar automatically.",
    "Please add calendar integration. I miss deadlines otherwise.",
    "Connect to Apple Calendar and I'd pay in a heartbeat.",
    "Calendar view / integration would make this a daily driver.",
    "Add calendar sync please. Scheduling is half my workflow.",
    "I have to manually copy tasks into my calendar. Please integrate.",
    "Google Calendar integration is top of my wishlist.",
    "Any plans for calendar integration? Would be a game-changer.",
]
NOTIFICATIONS = [
    "Notifications are unreliable. I miss reminders constantly.",
    "Reminders sometimes don't fire at all.",
    "Would love more granular notification controls.",
    "Push notifications arrive late on iOS.",
    "Notifications are too aggressive on shared tasks.",
    "Missing the reminder feature that worked in the old version.",
]
MOBILE_UI = [
    "The mobile UI is cramped on smaller phones.",
    "Bottom nav is awkward on a tablet.",
    "Mobile keyboard covers the input field.",
    "iPhone app feels like an afterthought.",
    "Android version lags behind the web app.",
    "Mobile font size is too small for my eyes.",
]
SEARCH = [
    "Search doesn't find tasks I know exist.",
    "Would love full-text search across notes and tasks.",
    "Search is case-sensitive for some reason.",
    "Search results are outdated by a day or so.",
    "Filtering by tag in search would help a lot.",
    "Search is slow with a large task list.",
]
ONBOARDING = [
    "Onboarding is confusing — I didn't know where to start.",
    "The tutorial is too long and skippable.",
    "Would benefit from a template gallery when signing up.",
    "First-run experience felt empty. No guidance.",
    "Give me sample projects when I sign up.",
    "Onboarding didn't mention the keyboard shortcuts.",
]
SHARING = [
    "Sharing a task with someone outside the team is clunky.",
    "Would like read-only sharing links.",
    "Collaboration features are limited for small teams.",
    "Real-time co-editing is missing.",
    "Sharing permissions are confusing.",
    "Would love guest access without a full account.",
]

TEMPLATES = {
    "sync_bugs": SYNC_BUGS,
    "slow_startup": SLOW_STARTUP,
    "dark_mode": DARK_MODE,
    "pricing": PRICING,
    "calendar_integration": CALENDAR,
    "notifications": NOTIFICATIONS,
    "mobile_ui": MOBILE_UI,
    "search": SEARCH,
    "onboarding": ONBOARDING,
    "sharing": SHARING,
}

RATING_POOLS = {
    "sync_bugs": [1, 1, 1, 2, 2, 2, 3],
    "slow_startup": [1, 2, 2, 3, 3, 4],
    "dark_mode": [3, 3, 4, 4, 4, 5],
    "pricing": [1, 2, 2, 3, 3, 4],
    "calendar_integration": [3, 4, 4, 4, 5],
    "notifications": [2, 2, 3, 3, 4],
    "mobile_ui": [2, 3, 3, 3, 4],
    "search": [2, 3, 3, 4],
    "onboarding": [3, 3, 4, 4],
    "sharing": [3, 3, 4, 4, 5],
}

BATCH_COUNTS = {
    1: {"sync_bugs": 40, "slow_startup": 55, "dark_mode": 30,
        "pricing": 45, "calendar_integration": 0,
        "notifications": 12, "mobile_ui": 10, "search": 10,
        "onboarding": 8, "sharing": 8},
    2: {"sync_bugs": 70, "slow_startup": 30, "dark_mode": 32,
        "pricing": 50, "calendar_integration": 0,
        "notifications": 11, "mobile_ui": 10, "search": 10,
        "onboarding": 8, "sharing": 8},
    3: {"sync_bugs": 100, "slow_startup": 15, "dark_mode": 28,
        "pricing": 55, "calendar_integration": 60,
        "notifications": 12, "mobile_ui": 10, "search": 10,
        "onboarding": 8, "sharing": 8},
}

# Week starting dates — batch 3 is 6 weeks after batch 1.
BATCH_START = {
    1: datetime(2026, 8, 10),
    2: datetime(2026, 8, 31),
    3: datetime(2026, 9, 21),
}
BATCH_DAYS = 7

# Only prefixes that won't stack with base templates that already read
# like a bug report or feature request.
PREFIXES = ["", "", "", "", "", "Honestly, ", "Seriously, ",
            "Please — ", "FYI: "]
SUFFIXES = ["", "", "", "", " Please fix.", " Thanks.",
            " Love the app otherwise.", " Considering switching.",
            " Just a heads up.", " Would appreciate it."]


def _vary(text: str, rng: random.Random) -> str:
    prefix = rng.choice(PREFIXES)
    suffix = rng.choice(SUFFIXES)
    if prefix and text and text[0].isalpha():
        text = text[0].upper() + text[1:]
    return f"{prefix}{text}{suffix}".strip()


def _generate_batch(batch: int, rng: random.Random) -> list[dict]:
    plan = BATCH_COUNTS[batch]
    start = BATCH_START[batch]
    reviews: list[dict] = []
    for theme, count in plan.items():
        if count == 0:
            continue
        templates = TEMPLATES[theme]
        ratings = RATING_POOLS[theme]
        for _ in range(count):
            base = rng.choice(templates)
            text = _vary(base, rng)
            rating = rng.choice(ratings)
            day = rng.randint(0, BATCH_DAYS - 1)
            hour = rng.randint(7, 22)
            minute = rng.randint(0, 59)
            date = start + timedelta(days=day, hours=hour, minutes=minute)
            reviews.append({
                "id": "tmp",
                "text": text,
                "rating": rating,
                "date": date.strftime("%Y-%m-%d"),
                "ground_truth_theme": theme,
            })
    rng.shuffle(reviews)
    for i, r in enumerate(reviews, 1):
        r["id"] = f"b{batch}-r{i:03d}"
    return reviews


def main() -> None:
    rng = random.Random(SEED)
    for batch in (1, 2, 3):
        reviews = _generate_batch(batch, rng)
        path = DATA_DIR / f"batch_{batch}.json"
        path.write_text(json.dumps(reviews, indent=2))
        counts: dict[str, int] = {}
        for r in reviews:
            counts[r["ground_truth_theme"]] = \
                counts.get(r["ground_truth_theme"], 0) + 1
        print(f"wrote {path.relative_to(REPO)} — {len(reviews)} reviews")
        for t, c in sorted(counts.items()):
            print(f"    {t:<24} {c}")


if __name__ == "__main__":
    main()
