import argparse
import json
import os
import sys
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from leaderboard_image import generate

API_BASE = "https://api.propr.xyz"
STATE_DIR = Path(__file__).parent.parent / "state"
WEEKLY_STATE_FILE = STATE_DIR / "leaderboard_weekly.json"
ALLTIME_STATE_FILE = STATE_DIR / "leaderboard_alltime.json"
TWITTER_BASE = "https://api.x.com/2"
TWITTER_UPLOAD = "https://api.x.com/2/media/upload"

MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}
PERIOD_LABEL = {"weekly": "Weekly", "all_time": "All-Time"}
PERIOD_TEMPLATE = {
    "weekly": "weekly_leaderboard_template.png",
    "all_time": "alltime_leaderboard_template.png",
}
PERIOD_OUT = {
    "weekly": "weekly_leaderboard_generated.png",
    "all_time": "alltime_leaderboard_generated.png",
}


def get_session():
    return OAuth1Session(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def fetch_leaderboard(period, limit=10):
    resp = requests.get(
        f"{API_BASE}/v1/leaderboard",
        params={"period": period, "challengeType": "evaluation", "limit": limit, "offset": 0},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"]


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


def read_state(path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_state(path, data):
    path.write_text(json.dumps([
        {"rank": e["rank"], "username": e["trader"]["username"]}
        for e in data[:3]
    ]))


def top1_changed(old_state, new_data):
    old_top1 = next((e["username"] for e in old_state if e["rank"] == 1), None)
    new_top1 = new_data[0]["trader"]["username"] if new_data else None
    return old_top1 != new_top1


def format_entry_line(entry):
    medal = MEDAL[entry["rank"]]
    sign = "+" if entry["pnl"] >= 0 else ""
    return f"{medal} {entry['username']} — {sign}${entry['pnl']:,.0f} ({sign}{entry['pct']:.2f}%)"


def format_change_tweet(top3, period):
    label = PERIOD_LABEL[period]
    name = top3[0]["username"]
    headline = f"🔥 {name} just took the number #1 spot on the @ProprXYZ {label} Leaderboard!"
    lines = [headline, ""] + [format_entry_line(e) for e in top3] + ["", "Stay liquid 💧 $PROPR"]
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


def check_period(session, period, state_file):
    raw_data = fetch_leaderboard(period, limit=10)
    entries = [to_entry(item) for item in raw_data]
    top3 = entries[:3]

    old_state = read_state(state_file)

    if old_state is None:
        save_state(state_file, raw_data)
        print(f"First run ({period}) — saved initial state")
        return

    changed = top1_changed(old_state, raw_data)
    save_state(state_file, raw_data)

    if not changed:
        print(f"No #1 change ({period})")
        return

    image_path = generate(entries, template_name=PERIOD_TEMPLATE[period], out_name=PERIOD_OUT[period])
    media_id = upload_media(session, image_path)

    tweet = format_change_tweet(top3, period)
    print(f"Posting {period} leaderboard change tweet:\n{tweet}\n")
    post_tweet(session, tweet, media_id=media_id)
    print(f"Posted {period} leaderboard change tweet (new #1: {top3[0]['username']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=["weekly", "all_time"], required=True)
    args = parser.parse_args()

    state_file = WEEKLY_STATE_FILE if args.period == "weekly" else ALLTIME_STATE_FILE
    session = get_session()
    check_period(session, args.period, state_file)


if __name__ == "__main__":
    main()
