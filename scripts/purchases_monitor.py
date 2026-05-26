import json
import os
import sys
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from purchases_image import generate as generate_image

BASE_URL       = "https://www.propr.xyz"
STATE_FILE     = Path(__file__).parent.parent / "state" / "purchases.json"
TWITTER_BASE   = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"

PRODUCT_TO_NAME = {
    "urn:prp-product:c8G6xJFioauB": "Starter",   # starter-t
    "urn:prp-product:VHri3yE798BT": "Starter",    # starter-s
    "urn:prp-product:iPfhDbCzox6V": "Explorer",   # explorer-t
    "urn:prp-product:mE1sSAJUHVCS": "Explorer",   # explorer-s
    "urn:prp-product:UBpMkZ49RwkQ": "Bronze",     # bronze-t
    "urn:prp-product:VhgJq9jWaCdw": "Bronze",     # bronze-s
    "urn:prp-product:TFeMnT5pSAUi": "Silver",     # silver-s
    "urn:prp-product:CN8PbKNJAgEn": "Gold",       # gold-s
    "urn:prp-product:7aoFGBNm3PQw": "Gold",       # gold-t
}


def get_session():
    return OAuth1Session(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def fetch_events_since(since: datetime):
    resp = requests.get(
        f"{BASE_URL}/api/propr/v1/stats/activity",
        params={"limit": 500, "types": "purchase"},
        timeout=10,
    )
    resp.raise_for_status()
    events = resp.json()["events"]
    return [
        e for e in events
        if datetime.fromisoformat(e["occurredAt"].replace("Z", "+00:00")) > since
    ]


def group_events(events):
    grouped = {}
    for e in events:
        name = PRODUCT_TO_NAME.get(e["productId"])
        if not name:
            print(f"Unknown productId: {e['productId']} (total={e['total']})")
            continue
        if name not in grouped:
            grouped[name] = {"count": 0, "revenue": 0.0}
        grouped[name]["count"]   += 1
        grouped[name]["revenue"] += float(e["total"])
    return grouped


def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


def save_state(run_time: datetime):
    STATE_FILE.write_text(json.dumps({"last_run": run_time.isoformat()}, indent=2))


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
    now   = datetime.now(timezone.utc)
    state = load_state()

    if state is None:
        since = now - timedelta(hours=12)
        print("First run — looking back 12h")
    else:
        since = datetime.fromisoformat(state["last_run"])

    hours_since = (now - since).total_seconds() / 3600
    events  = fetch_events_since(since)
    grouped = group_events(events)

    total_usdc  = sum(d["revenue"] for d in grouped.values())
    total_count = sum(d["count"]   for d in grouped.values())

    print(f"Since {since.isoformat()} ({hours_since:.1f}h): ${total_usdc:,.2f} USDC across {total_count} purchases")
    for name, d in grouped.items():
        print(f"  {name}: {d['count']}x ${d['revenue']:,.2f}")

    if total_usdc <= 0:
        print("No new purchases — skipping tweet")
        save_state(now)
        return

    hours_display = round(hours_since)
    tweet = (
        f"${total_usdc:,.0f} in @ProprXYZ Challenge purchases in the last {hours_display}h! 💸\n\n"
        f"Earn airdrop points through purchases, trading activity & more! \n\n"
        f"Estimate your $PROPR allocation 👇\n"
        f"http://liquidtradershub.com/propr-airdrop"
    )

    image_path = generate_image(grouped, total_usdc)
    post_tweet(session, tweet, image_path)
    print(f"Posted: {tweet}")

    save_state(now)


def main():
    session = get_session()
    check_purchases(session)


if __name__ == "__main__":
    main()
