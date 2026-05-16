import json
import os
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

from leaderboard_image import generate

API_BASE = "https://api.propr.xyz"
TWITTER_BASE = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"

MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def get_session():
    return OAuth1Session(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def fetch_leaderboard(limit=10):
    resp = requests.get(
        f"{API_BASE}/v1/leaderboard",
        params={"period": "daily", "challengeType": "evaluation", "limit": limit, "offset": 0},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def parse_challenge_name(raw):
    try:
        return json.loads(raw).get("en", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw


def to_entry(item):
    pnl = float(item["pnl"])
    pct = pnl / float(item["initialBalance"]) * 100
    return {
        "rank": item["rank"],
        "username": item["trader"]["username"],
        "pnl": pnl,
        "pct": pct,
        "challenge": parse_challenge_name(item["challengeName"]),
    }


def format_tweet_line(entry):
    medal = MEDAL[entry["rank"]]
    sign = "+" if entry["pnl"] >= 0 else ""
    return f"{medal} {entry['username']} {sign}${entry['pnl']:,.0f} ({sign}{entry['pct']:.2f}%) | {entry['challenge']}"


def format_tweet(top3):
    lines = (
        ["🏆 @ProprXYZ Daily Leaderboard", ""]
        + [format_tweet_line(e) for e in top3]
        + ["", "Stay liquid 💧 $PROPR"]
    )
    return "\n".join(lines)


def upload_media(session, image_path):
    with open(image_path, "rb") as f:
        resp = session.post(
            TWITTER_UPLOAD,
            files={"media": f},
            data={"media_category": "tweet_image"},
        )
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def post_tweet(session, text, media_id=None):
    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    resp = session.post(f"{TWITTER_BASE}/tweets", json=body)
    if not resp.ok:
        print(f"Tweet POST failed {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def main():
    session = get_session()
    result = fetch_leaderboard(limit=10)

    entries = [to_entry(item) for item in result["data"]]
    top3 = entries[:3]
    total = result["total"]

    image_path = generate(entries)
    media_id = upload_media(session, image_path)

    tweet = format_tweet(top3)
    print(f"Posting daily leaderboard tweet:\n{tweet}\n")
    post_tweet(session, tweet, media_id=media_id)
    print("Posted daily leaderboard tweet")


if __name__ == "__main__":
    main()
