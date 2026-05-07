import os
import time
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

BASE_URL = "https://www.propr.xyz"
PAYOUT_STATE_FILE = Path(__file__).parent.parent / "state" / "last_payout_id.txt"
IMAGES_DIR = Path(__file__).parent.parent / "images"
TWITTER_BASE = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"


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


def read_state(path):
    if not path.exists():
        return None
    content = path.read_text().strip()
    return content if content else None


def upload_media(session, image_name):
    path = IMAGES_DIR / f"{image_name}.png"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        resp = session.post(TWITTER_UPLOAD, files={"media": f}, data={"media_category": "tweet_image"})
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def post_tweet(session, text, image_name=None):
    body = {"text": text}
    if image_name:
        media_id = upload_media(session, image_name)
        if media_id:
            body["media"] = {"media_ids": [media_id]}
    resp = session.post(f"{TWITTER_BASE}/tweets", json=body)
    if not resp.ok:
        print(f"Tweet POST failed {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def format_payout_tweet(payout, stats):
    from datetime import datetime, timezone
    amount = payout["amount"]
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]
    tx_hash = payout["tx_hash"]

    paid_at = datetime.fromisoformat(payout["paid_at"]).astimezone(timezone.utc)
    date_str = f"{paid_at.strftime('%b')} {paid_at.day}, {paid_at.strftime('%H:%M UTC')}"

    lines = [
        f"💸 @ProprXYZ just paid out ${amount:,.2f} USDC to a funded trader",
        "",
        f"⏱️ {date_str}",
        "",
        f"Tx: https://etherscan.io/tx/{tx_hash}",
        "",
        f"${total_paid:,.2f} paid to {total_count} funded traders so far! 💰",
        "",
        "Stay liquid 💧 $PROPR",
    ]

    return "\n".join(lines)


def check_payouts(session):
    data = fetch("/api/transparency/payouts")
    recent = data["recent"]
    stats = data["stats"]

    if not recent:
        print("No payouts found")
        return

    last_id = read_state(PAYOUT_STATE_FILE)

    if last_id is None:
        PAYOUT_STATE_FILE.write_text(recent[0]["id"])
        print(f"First run (payouts) — saved initial state: {recent[0]['id']}")
        return

    new_payouts = []
    for payout in recent:
        if payout["id"] == last_id:
            break
        new_payouts.append(payout)

    if not new_payouts:
        print("No new payouts")
    else:
        PAYOUT_STATE_FILE.write_text(recent[0]["id"])
        tweets_posted = 0
        for payout in reversed(new_payouts):
            if payout["amount"] < 100:
                print(f"Skipping payout tweet (${payout['amount']} below $100 minimum): {payout['id']}")
                continue
            if tweets_posted > 0:
                print("Waiting 60s before next payout tweet...")
                time.sleep(60)
            tweet = format_payout_tweet(payout, stats)
            print(f"Posting payout tweet:\n{tweet}\n")
            post_tweet(session, tweet, "payout")
            print(f"Posted: {payout['id']} — ${payout['amount']}")
            tweets_posted += 1


def main():
    session = get_session()
    check_payouts(session)


if __name__ == "__main__":
    main()
