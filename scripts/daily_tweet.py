import os
import sys
import requests
import tweepy
from datetime import datetime, timedelta, timezone

BASE_URL = "https://www.propr.xyz"


def get_yesterday():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


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


def find_day(history, date):
    return next((d for d in history if d["date"] == date), None)


def main():
    yesterday = get_yesterday()

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

    lines = [f"Daily @ProprXYZ trader stats - {date_str}", ""]

    if total_purchases > 0:
        lines.append(f"🛒 {total_purchases} challenges purchased")

    lines.append(f"👥 +{new_traders} new traders | {total_traders:,} total")

    if profit > 0:
        lines.append(f"📈 ${profit:,.0f} in trader profits today")

    if passes > 0:
        lines.append(f"✅ {passes} traders passed their challenge")

    lines += ["", f"Get funded 👉 app.propr.xyz/r/75agXwd6"]

    tweet = "\n".join(lines)
    print(f"Posting tweet:\n{tweet}\n")

    client = get_twitter_client()
    client.create_tweet(text=tweet)
    print(f"Daily tweet posted for {yesterday}")


if __name__ == "__main__":
    main()
