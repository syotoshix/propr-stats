import json
import os
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from purchases_image import generate as generate_image

BASE_URL       = "https://www.propr.xyz"
STATE_FILE     = Path(__file__).parent.parent / "state" / "purchases.json"
TWITTER_BASE   = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"

SLUG_TO_NAME = {
    "starter-s": "Starter",  "starter-t": "Starter",
    "explorer-s": "Explorer", "explorer-t": "Explorer",
    "bronze-s": "Bronze",     "bronze-t": "Bronze",
    "silver-s": "Silver",     "silver-t": "Silver",
    "gold-s": "Gold",         "gold-t": "Gold",
}


def get_session():
    return OAuth1Session(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def fetch(path):
    resp = requests.get(f"{BASE_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


def save_state(totals):
    STATE_FILE.write_text(json.dumps({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
    }, indent=2))


def get_current_totals():
    data = fetch("/api/propr/v1/stats/challenges/purchases/history?days=7")
    totals = {}
    for ch in data["byChallenge"]:
        slug = ch["slug"]
        totals[slug] = {
            "count":   sum(d["purchases"] for d in ch["history"]),
            "revenue": sum(d["revenue"]   for d in ch["history"]),
        }
    return totals


def compute_delta(current, previous):
    delta = {}
    for slug, cur in current.items():
        prev = previous.get(slug, {"count": 0, "revenue": 0.0})
        dc = cur["count"]   - prev["count"]
        dr = cur["revenue"] - prev["revenue"]
        if dc > 0 or dr > 0:
            delta[slug] = {"count": max(0, dc), "revenue": max(0.0, dr)}
    return delta


def group_by_name(delta):
    grouped = {}
    for slug, data in delta.items():
        name = SLUG_TO_NAME.get(slug)
        if not name:
            continue
        if name not in grouped:
            grouped[name] = {"count": 0, "revenue": 0.0}
        grouped[name]["count"]   += data["count"]
        grouped[name]["revenue"] += data["revenue"]
    return grouped


def upload_media(session, image_path):
    with open(image_path, "rb") as f:
        resp = session.post(TWITTER_UPLOAD, files={"media": f}, data={"media_category": "tweet_image"})
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def post_tweet(session, text, image_path):
    media_id = upload_media(session, image_path)
    body = {"text": text, "media": {"media_ids": [media_id]}}
    resp = session.post(f"{TWITTER_BASE}/tweets", json=body)
    if not resp.ok:
        print(f"Tweet POST failed {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def check_purchases(session):
    current = get_current_totals()
    state   = load_state()

    if state is None:
        print("First run — saving initial state, no tweet")
        save_state(current)
        return

    last_run    = datetime.fromisoformat(state["last_run"])
    hours_since = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600

    delta   = compute_delta(current, state["totals"])
    grouped = group_by_name(delta)

    total_usdc  = sum(d["revenue"] for d in grouped.values())
    total_count = sum(d["count"]   for d in grouped.values())

    print(f"Delta since last run ({hours_since:.1f}h): ${total_usdc:,.2f} USDC across {total_count} purchases")
    for name, d in grouped.items():
        print(f"  {name}: {d['count']}x ${d['revenue']:,.2f}")

    if total_usdc <= 0:
        print("No new purchases — skipping tweet")
        save_state(current)
        return

    hours_display = round(hours_since)
    total_pts = int(total_usdc * 10)
    tweet = (
        f"${total_usdc:,.0f} in @ProprXYZ Challenge purchases in the last {hours_display}h! 💸\n\n"
        f"💰 ~+{total_pts:,} $PROPR airdrop points earned \n\n"
        f"Earn airdrop points through purchases, trading activity & more! Estimate your airdrop allocation below 👇\n"
        f"liquidtradershub.com/propr-airdrop"
    )

    image_path = generate_image(grouped, total_usdc)
    post_tweet(session, tweet, image_path)
    print(f"Posted: {tweet}")

    save_state(current)


def main():
    session = get_session()
    check_purchases(session)


if __name__ == "__main__":
    main()
