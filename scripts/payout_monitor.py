import json
import os
import time
import requests
from collections import Counter
from pathlib import Path
from requests_oauthlib import OAuth1Session

BASE_URL = "https://www.propr.xyz"
PAYOUT_STATE_FILE = Path(__file__).parent.parent / "state" / "last_payout_id.txt"
ACTIVITY_STATE_FILE = Path(__file__).parent.parent / "state" / "last_activity_id.txt"
CHALLENGES_FILE = Path(__file__).parent.parent / "data" / "challenges.json"
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


def load_challenges():
    with open(CHALLENGES_FILE) as f:
        return json.load(f)


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
    resp.raise_for_status()
    return resp.json()["data"]["id"]


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
        for i, payout in enumerate(reversed(new_payouts)):
            if i > 0:
                print("Waiting 60s before next payout tweet...")
                time.sleep(60)
            tweet = format_payout_tweet(payout, stats)
            print(f"Posting payout tweet:\n{tweet}\n")
            post_tweet(session, tweet, "payout")
            print(f"Posted: {payout['id']} — ${payout['amount']}")
        PAYOUT_STATE_FILE.write_text(recent[0]["id"])


def format_payout_tweet(payout, stats):
    amount = payout["amount"]
    trader = payout["anon_user"]
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]
    tx_hash = payout["tx_hash"]
    badge = payout.get("badge", "")

    lines = [f"💸 @ProprXYZ just paid out ${amount:,.2f} USDC to a funded trader", ""]

    if badge:
        lines.append(f"{trader} — {badge.lower()} ✅")
    else:
        lines.append(trader)

    lines += ["", f"${total_paid:,.2f} paid to {total_count} funded traders so far! $PROPR"]
    lines.append(f"Tx: https://etherscan.io/tx/{tx_hash}")

    return "\n".join(lines)


def check_passes(session, challenges):
    data = fetch("/api/propr/v1/stats/activity?limit=20&types=passed")
    events = data["events"]

    if not events:
        print("No activity events found")
        return

    last_id = read_state(ACTIVITY_STATE_FILE)

    if last_id is None:
        ACTIVITY_STATE_FILE.write_text(events[0]["attemptId"])
        print(f"First run (activity) — saved initial state: {events[0]['attemptId']}")
        return

    new_passes = []
    for event in events:
        if event["attemptId"] == last_id:
            break
        new_passes.append(event)

    if not new_passes:
        print("No new pass events")
        return

    tweet, image_name = format_pass_tweet(new_passes, challenges)
    print(f"Posting pass tweet:\n{tweet}\n")
    post_tweet(session, tweet, image_name)
    print(f"Posted pass tweet for {len(new_passes)} event(s)")

    ACTIVITY_STATE_FILE.write_text(events[0]["attemptId"])


def format_pass_tweet(new_passes, challenges):
    count = len(new_passes)

    if count == 1:
        event = new_passes[0]
        challenge = challenges.get(event["challengeId"])

        if challenge and challenge["fundedBalance"] is not None:
            name = challenge["name"]
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            price_str = f"${price}" if price else "free"
            tweet = (
                f"✅ A trader just passed the @ProprXYZ {name} Challenge!\n\n"
                f"{price_str} challenge 👉 ${funded:,} funded account\n\n$PROPR"
            )
            return tweet, challenge["slug"].split("-")[0]
        elif challenge and challenge["fundedBalance"] is None:
            name = challenge["name"]
            return f"✅ A trader just passed the @ProprXYZ {name}!\n\nTime to get funded! $PROPR 💰", "free-trial"
        else:
            return f"✅ A trader just passed their @ProprXYZ challenge!\n\n$PROPR", "mixed"

    challenge_counts = Counter(event["challengeId"] for event in new_passes)
    unique_challenges = list(challenge_counts.keys())

    if len(unique_challenges) == 1:
        challenge_id = unique_challenges[0]
        challenge = challenges.get(challenge_id)

        if challenge and challenge["fundedBalance"] is not None:
            name = challenge["name"]
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            price_str = f"${price}" if price else "free"
            tweet = (
                f"✅ {count} traders just passed their @ProprXYZ {name} Challenge\n\n"
                f"{price_str} challenge 👉 ${funded:,} funded account — each\n\n$PROPR"
            )
            return tweet, challenge["slug"].split("-")[0]
        else:
            name = challenge["name"] if challenge else "challenge"
            return f"✅ {count} traders just passed their @ProprXYZ {name}\n\n$PROPR", "free-trial"

    lines = [f"✅ {count} traders just passed their @ProprXYZ challenge", ""]

    sorted_challenges = sorted(
        challenge_counts.items(),
        key=lambda x: (challenges.get(x[0], {}).get("fundedBalance") or -1),
        reverse=True,
    )

    for challenge_id, n in sorted_challenges:
        challenge = challenges.get(challenge_id)
        if challenge:
            name = challenge["name"]
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            if funded is not None:
                price_str = f"${price}" if price else "free"
                lines.append(f"{n}x {name}, {price_str} challenge 👉 ${funded:,} funded")
            else:
                lines.append(f"{n}x {name}")
        else:
            lines.append(f"{n}x Unknown Challenge")

    lines.append("\n$PROPR")
    return "\n".join(lines), "mixed"


def main():
    challenges = load_challenges()
    session = get_session()
    check_payouts(session)
    time.sleep(30)
    check_passes(session, challenges)


if __name__ == "__main__":
    main()
