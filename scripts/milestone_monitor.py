import json
import os
import sys
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from milestone_image import generate as generate_image, format_amount

BASE_URL = "https://www.propr.xyz"
STATE_FILE = Path(__file__).parent.parent / "state" / "milestones.json"
TWITTER_BASE = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"

REVENUE_MILESTONES = [
    200_000, 300_000, 400_000, 500_000, 750_000,
    1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_000_000,
    4_000_000, 5_000_000, 7_500_000, 10_000_000,
]
TRADER_MILESTONES = [
    5_000, 10_000, 15_000, 20_000, 25_000, 30_000,
    40_000, 50_000, 75_000, 100_000,
]
CAPITAL_MILESTONES = [
    500_000, 1_000_000, 1_500_000, 2_000_000, 2_500_000,
    3_000_000, 5_000_000, 10_000_000,
]


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
        return {"revenue": [], "traders": [], "capital": []}
    return json.loads(STATE_FILE.read_text())


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


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


def format_tweet(milestone_type, value):
    amount = format_amount(value, milestone_type)
    if milestone_type == "revenue":
        return f"Crypto Prop Firm on HyperLiquid $HYPE has surpassed {amount} in Total Cumulative Revenue @ProprXYZ"
    elif milestone_type == "traders":
        return f"Crypto Prop Firm on HyperLiquid $HYPE has surpassed {amount} Total Traders @ProprXYZ"
    elif milestone_type == "capital":
        return f"Crypto Prop Firm on HyperLiquid $HYPE has surpassed {amount} in Active Funded Capital @ProprXYZ"


def check_milestones(session):
    revenue_data = fetch("/api/propr/v1/stats/revenue/history?days=1")
    trader_data  = fetch("/api/propr/v1/stats/traders/history?days=1")
    capital_data = fetch("/api/propr/v1/stats/bbook/capital/history?days=2")

    current_revenue = revenue_data["totalRevenue"]
    current_traders = trader_data["totalTraders"]
    current_capital = capital_data["currentCapital"]

    print(f"Revenue: ${current_revenue:,.2f} | Traders: {current_traders:,} | Capital: ${current_capital:,.2f}")

    state = load_state()
    posted = False

    checks = [
        ("revenue", current_revenue, REVENUE_MILESTONES),
        ("traders", current_traders, TRADER_MILESTONES),
        ("capital", current_capital, CAPITAL_MILESTONES),
    ]

    # Collect all new milestones across all categories
    new_milestones = []
    for milestone_type, current_value, milestones in checks:
        hit = state.get(milestone_type, [])
        for m in milestones:
            if current_value >= m and m not in hit:
                new_milestones.append((milestone_type, m))

    if not new_milestones:
        print("No new milestones")
        return

    if len(new_milestones) > 1:
        remaining = [f"{t}:{m}" for t, m in new_milestones[1:]]
        print(f"Multiple milestones hit — posting first, deferring: {remaining}")

    milestone_type, m = new_milestones[0]
    tweet = format_tweet(milestone_type, m)
    image_path = generate_image(milestone_type, m)
    post_tweet(session, tweet, image_path)
    print(f"Posted: {tweet}")

    state[milestone_type] = state.get(milestone_type, []) + [m]
    save_state(state)


def main():
    session = get_session()
    check_milestones(session)


if __name__ == "__main__":
    main()
