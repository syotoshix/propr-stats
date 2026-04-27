import os
import sys
import requests
import tweepy
from pathlib import Path

BASE_URL = "https://www.propr.xyz"
STATE_FILE = Path(__file__).parent.parent / "state" / "last_payout_id.txt"


def fetch_payouts():
    resp = requests.get(f"{BASE_URL}/api/transparency/payouts", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_twitter_client():
    return tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


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


def main():
    data = fetch_payouts()
    recent = data["recent"]
    stats = data["stats"]

    if not recent:
        print("No payouts found")
        return

    # First run — save current state without tweeting to avoid a flood
    if not STATE_FILE.exists() or STATE_FILE.read_text().strip() == "":
        STATE_FILE.write_text(recent[0]["id"])
        print(f"First run — saved initial state: {recent[0]['id']}")
        return

    last_id = STATE_FILE.read_text().strip()

    # Collect payouts newer than the last known one (recent is newest-first)
    new_payouts = []
    for payout in recent:
        if payout["id"] == last_id:
            break
        new_payouts.append(payout)

    if not new_payouts:
        print("No new payouts")
        return

    client = get_twitter_client()

    # Tweet oldest-first so the timeline reads chronologically
    for payout in reversed(new_payouts):
        tweet = format_payout_tweet(payout, stats)
        print(f"Posting payout tweet:\n{tweet}\n")
        client.create_tweet(text=tweet)
        print(f"Posted: {payout['id']} — ${payout['amount']}")

    STATE_FILE.write_text(recent[0]["id"])
    print(f"State updated to: {recent[0]['id']}")


if __name__ == "__main__":
    main()
