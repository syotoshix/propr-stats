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


def fetch_pass_rates():
    data = fetch("/api/propr/v1/stats/challenges/pass-rates")
    totals = {}
    for ch in data:
        slug = ch["slug"]
        base = slug[:-2] if slug.endswith(("-s", "-t")) else slug
        if base not in totals:
            totals[base] = {"attempts": 0, "passed": 0}
        totals[base]["attempts"] += ch["totalAttempts"]
        totals[base]["passed"] += ch["passedAttempts"]
    return totals


def pass_rate_line(name, slug, pass_rates):
    base = slug[:-2] if slug.endswith(("-s", "-t")) else slug
    stats = pass_rates.get(base)
    if not stats:
        return None
    attempts = stats["attempts"]
    passed = stats["passed"]
    trader_str = "1 trader has passed" if passed == 1 else f"{passed} traders have passed"
    if base == "free-trial":
        return f"In total {attempts:,} attempted the {name} ➡️ {trader_str}"
    return f"In total {attempts:,} bought the {name} Challenge ➡️ {trader_str}"


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
    from datetime import datetime, timezone
    amount = payout["amount"]
    trader = payout["anon_user"]
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]
    tx_hash = payout["tx_hash"]
    badge = payout.get("badge", "")

    paid_at = datetime.fromisoformat(payout["paid_at"]).astimezone(timezone.utc)
    date_str = paid_at.strftime("%b %-d, %H:%M UTC")

    lines = [f"💸 @ProprXYZ just paid out ${amount:,.2f} USDC to a funded trader", ""]

    if badge:
        lines.append(f"{trader} — {badge.lower()} ✅")
    else:
        lines.append(trader)

    lines += [
        "",
        f"{date_str} · Tx: https://etherscan.io/tx/{tx_hash}",
        "",
        f"${total_paid:,.2f} paid to {total_count} funded traders so far!\n\nStay liquid $PROPR",
    ]

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

    pass_rates = fetch_pass_rates()
    tweet, image_name = format_pass_tweet(new_passes, challenges, pass_rates)
    print(f"Posting pass tweet:\n{tweet}\n")
    post_tweet(session, tweet, image_name)
    print(f"Posted pass tweet for {len(new_passes)} event(s)")

    ACTIVITY_STATE_FILE.write_text(events[0]["attemptId"])


def format_pass_tweet(new_passes, challenges, pass_rates):
    count = len(new_passes)

    if count == 1:
        event = new_passes[0]
        challenge = challenges.get(event["challengeId"])

        if challenge and challenge["fundedBalance"] is not None:
            name = challenge["name"]
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            price_str = f"${price}" if price else "free"
            stat = pass_rate_line(name, challenge["slug"], pass_rates)
            lines = [
                f"✅ A trader just passed the @ProprXYZ {name} Challenge!",
                "",
                f"{price_str} challenge 👉 ${funded:,} funded account",
            ]
            if stat:
                lines.append(stat)
            lines += ["", "Stay liquid $PROPR"]
            return "\n".join(lines), challenge["slug"].split("-")[0]
        elif challenge and challenge["fundedBalance"] is None:
            name = challenge["name"]
            stat = pass_rate_line(name, challenge["slug"], pass_rates)
            lines = [f"✅ A trader just passed the @ProprXYZ {name}!", "", "Time to get funded!"]
            if stat:
                lines.append(stat)
            lines += ["", "Stay liquid $PROPR"]
            return "\n".join(lines), "free-trial"
        else:
            return f"✅ A trader just passed their @ProprXYZ challenge!\n\nStay liquid $PROPR", "mixed"

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
            stat = pass_rate_line(name, challenge["slug"], pass_rates)
            lines = [
                f"✅ {count} traders just passed their @ProprXYZ {name} Challenge",
                "",
                f"{price_str} challenge 👉 ${funded:,} funded account — each",
            ]
            if stat:
                lines.append(stat)
            lines += ["", "Stay liquid $PROPR"]
            return "\n".join(lines), challenge["slug"].split("-")[0]
        else:
            name = challenge["name"] if challenge else "challenge"
            stat = pass_rate_line(name, challenge["slug"], pass_rates) if challenge else None
            lines = [f"✅ {count} traders just passed their @ProprXYZ {name}"]
            if stat:
                lines += ["", stat]
            lines += ["", "Stay liquid $PROPR"]
            return "\n".join(lines), "free-trial"

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
            stat = pass_rate_line(name, challenge["slug"], pass_rates)
            if funded is not None:
                price_str = f"${price}" if price else "free"
                lines.append(f"{n}x {name}, {price_str} challenge 👉 ${funded:,} funded")
            else:
                lines.append(f"{n}x {name}")
            if stat:
                lines.append(stat)
            lines.append("")
        else:
            lines.append(f"{n}x Unknown Challenge")
            lines.append("")

    lines.append("Stay liquid $PROPR")
    return "\n".join(lines), "mixed"


def main():
    challenges = load_challenges()
    session = get_session()
    check_payouts(session)
    time.sleep(30)
    check_passes(session, challenges)


if __name__ == "__main__":
    main()
