import json
import os
import time
import requests
import tweepy
from pathlib import Path

BASE_URL = "https://www.propr.xyz"
PAYOUT_STATE_FILE = Path(__file__).parent.parent / "state" / "last_payout_id.txt"
ACTIVITY_STATE_FILE = Path(__file__).parent.parent / "state" / "last_activity_id.txt"
CHALLENGES_FILE = Path(__file__).parent.parent / "data" / "challenges.json"


def fetch(path):
    resp = requests.get(f"{BASE_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_twitter_client():
    return tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def load_challenges():
    with open(CHALLENGES_FILE) as f:
        return json.load(f)


def read_state(path):
    if not path.exists():
        return None
    content = path.read_text().strip()
    return content if content else None


def check_payouts(client):
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
            client.create_tweet(text=tweet)
            print(f"Posted: {payout['id']} — ${payout['amount']}")
        PAYOUT_STATE_FILE.write_text(recent[0]["id"])


def format_payout_tweet(payout, stats):
    amount = payout["amount"]
    trader = payout["anon_user"]
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]
    chain_id = payout["chain_id"]
    tx_hash = payout["tx_hash"]
    badge = payout.get("badge", "")

    lines = [f"💸 @ProprXYZ just paid out ${amount:,.2f} to a funded trader", ""]

    if badge:
        lines.append(f"{trader} — {badge.lower()} ✅")
    else:
        lines.append(trader)

    lines += ["", f"${total_paid:,.2f} paid to {total_count} funded traders so far"]

    if chain_id == 1:
        lines.append(f"https://etherscan.io/tx/{tx_hash}")
    else:
        lines.append(f"Tx: {tx_hash}")

    return "\n".join(lines)


def check_passes(client, challenges):
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

    tweet = format_pass_tweet(new_passes, challenges)
    print(f"Posting pass tweet:\n{tweet}\n")
    client.create_tweet(text=tweet)
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
            split = challenge["profitSplit"]
            price_str = f"${price}" if price else "free"
            return (
                f"✅ A trader just passed the @ProprXYZ {name} Challenge!\n\n"
                f"{price_str} challenge → ${funded:,} funded account | {split}% split\n\n"
                f"Get funded 👉 app.propr.xyz/r/75agXwd6"
            )
        elif challenge and challenge["fundedBalance"] is None:
            name = challenge["name"]
            return (
                f"✅ A trader just passed the @ProprXYZ {name}!\n\n"
                f"Ready to go funded? 👉 app.propr.xyz/r/75agXwd6"
            )
        else:
            return (
                f"✅ A trader just passed their @ProprXYZ challenge!\n\n"
                f"Get funded 👉 app.propr.xyz/r/75agXwd6"
            )

    # Multiple passes — group by challenge
    from collections import Counter
    challenge_counts = Counter(event["challengeId"] for event in new_passes)
    unique_challenges = list(challenge_counts.keys())

    if len(unique_challenges) == 1:
        challenge_id = unique_challenges[0]
        challenge = challenges.get(challenge_id)

        if challenge and challenge["fundedBalance"] is not None:
            name = challenge["name"]
            funded = challenge["fundedBalance"]
            split = challenge["profitSplit"]
            return (
                f"✅ {count} traders just passed their @ProprXYZ {name} Challenge\n\n"
                f"${funded:,} funded account | {split}% split — each\n\n"
                f"Get funded 👉 app.propr.xyz/r/75agXwd6"
            )
        else:
            name = challenge["name"] if challenge else "challenge"
            return (
                f"✅ {count} traders just passed their @ProprXYZ {name}\n\n"
                f"Get funded 👉 app.propr.xyz/r/75agXwd6"
            )

    # Mixed challenges — show breakdown sorted by funded balance descending
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
            split = challenge["profitSplit"]
            if funded is not None:
                lines.append(f"{n}x {name} → ${funded:,} funded | {split}% split")
            else:
                lines.append(f"{n}x {name}")
        else:
            lines.append(f"{n}x Unknown Challenge")

    lines += ["", "Get funded 👉 app.propr.xyz/r/75agXwd6"]
    return "\n".join(lines)


def main():
    challenges = load_challenges()
    client = get_twitter_client()
    check_payouts(client)
    time.sleep(30)
    check_passes(client, challenges)


if __name__ == "__main__":
    main()
