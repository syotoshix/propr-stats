import os
import sys
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from requests_oauthlib import OAuth1Session

BASE_URL = "https://www.propr.xyz"
IMAGES_DIR = Path(__file__).parent.parent / "images"
DAILY_STATE_FILE = Path(__file__).parent.parent / "state" / "last_daily_date.txt"
TWITTER_BASE = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"


def get_session():
    return OAuth1Session(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def upload_media(session, image_name):
    path = IMAGES_DIR / f"{image_name}.png"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        resp = session.post(TWITTER_UPLOAD, files={"media": f}, data={"media_category": "tweet_image"})
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def post_tweet(session, text, media_id=None):
    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    resp = session.post(f"{TWITTER_BASE}/tweets", json=body)
    resp.raise_for_status()
    return resp.json()["data"]["id"]



def get_yesterday():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def fetch(path):
    resp = requests.get(f"{BASE_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def find_day(history, date):
    return next((d for d in history if d["date"] == date), None)


def main():
    yesterday = get_yesterday()

    if DAILY_STATE_FILE.exists() and DAILY_STATE_FILE.read_text().strip() == yesterday:
        print(f"Daily tweet already posted for {yesterday}, skipping")
        sys.exit(0)

    traders_data = fetch("/api/propr/v1/stats/traders/history?days=2")
    trader_day = find_day(traders_data["history"], yesterday)
    if not trader_day:
        print(f"No trader data for {yesterday}, skipping")
        sys.exit(0)

    purchases_data = fetch("/api/propr/v1/stats/challenges/purchases/history?days=2")
    total_purchases = sum(
        next((d["purchases"] for d in ch["history"] if d["date"] == yesterday), 0)
        for ch in purchases_data["byChallenge"]
    )

    pnl_data = fetch("/api/propr/v1/stats/pnl/aggregated?days=2")
    pnl_day = find_day(pnl_data["overall"], yesterday)

    pass_data = fetch("/api/propr/v1/stats/challenges/pass-rate/history?days=3")
    pass_yesterday = find_day(pass_data["overall"], yesterday)
    day_before = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    pass_day_before = find_day(pass_data["overall"], day_before)

    new_traders = trader_day["newTraders"]
    total_traders = trader_day["totalTraders"]
    profit = pnl_day["profit"] if pnl_day else 0
    passes = (
        (pass_yesterday["passed"] - pass_day_before["passed"])
        if pass_yesterday and pass_day_before
        else (pass_yesterday["passed"] if pass_yesterday else 0)
    )

    date_str = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%b %-d")

    lines = [f"Daily @ProprXYZ trader stats - $PROPR {date_str}", ""]

    if total_purchases > 0:
        lines.append(f"🛒 {total_purchases} challenges purchased")

    lines.append(f"👥 +{new_traders} new traders | {total_traders:,} total")

    if profit > 0:
        lines.append(f"📈 +${profit:,.0f} in trader profits")

    if passes > 0:
        lines.append(f"✅ {passes} traders passed their challenge")

    lines += ["", "Get funded 👉 app.propr.xyz/r/75agXwd6", "", "Stay liquid $PROPR 💧"]

    tweet = "\n".join(lines)
    print(f"Posting tweet:\n{tweet}\n")

    session = get_session()
    media_id = upload_media(session, "daily")
    tweet_id = post_tweet(session, tweet, media_id)
    DAILY_STATE_FILE.write_text(yesterday)
    print(f"Daily tweet posted for {yesterday}: {tweet_id}")


if __name__ == "__main__":
    main()
