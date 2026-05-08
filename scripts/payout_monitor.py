import os
import sys
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from payout_image import generate as generate_payout_image

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


def upload_media(session, image_path):
    path = Path(image_path)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        resp = session.post(TWITTER_UPLOAD, files={"media": f}, data={"media_category": "tweet_image"})
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def post_tweet(session, text, image_path=None):
    body = {"text": text}
    if image_path:
        media_id = upload_media(session, image_path)
        if media_id:
            body["media"] = {"media_ids": [media_id]}
    resp = session.post(f"{TWITTER_BASE}/tweets", json=body)
    if not resp.ok:
        print(f"Tweet POST failed {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def format_payout_tweet(payouts, stats):
    from datetime import datetime, timezone
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]

    if len(payouts) == 1:
        payout = payouts[0]
        paid_at = datetime.fromisoformat(payout["paid_at"]).astimezone(timezone.utc)
        date_str = f"{paid_at.strftime('%b')} {paid_at.day}, {paid_at.strftime('%H:%M UTC')}"
        lines = [
            f"💸 @ProprXYZ just paid out ${payout['amount']:,.2f} USDC to a funded trader",
            "",
            f"⏱️ {date_str}",
            "",
            f"Tx: https://etherscan.io/tx/{payout['tx_hash']}",
            "",
            f"${total_paid:,.2f} paid to {total_count} funded traders so far! 💰",
            "",
            "Stay liquid 💧 $PROPR",
        ]
    else:
        total_amount = sum(p["amount"] for p in payouts)
        lines = [
            f"💸 @ProprXYZ just paid out to {len(payouts)} funded traders",
            "",
        ]
        for p in payouts:
            p_dt = datetime.fromisoformat(p["paid_at"]).astimezone(timezone.utc)
            p_date = f"{p_dt.strftime('%b')} {p_dt.day}, {p_dt.strftime('%H:%M UTC')}"
            lines.append(f"🔵 ${p['amount']:,.2f} USDC - ⏱️ {p_date}")
            lines.append(f"Tx: https://etherscan.io/tx/{p['tx_hash']}")
            lines.append("")
        lines += [
            f"Total: ${total_amount:,.2f} USDC 💰",
            "",
            f"${total_paid:,.2f} paid to {total_count} funded traders so far!",
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
        qualifying = [p for p in reversed(new_payouts) if p["amount"] >= 100]
        skipped = len(new_payouts) - len(qualifying)
        if skipped:
            print(f"Skipping {skipped} payout(s) below $100 minimum")
        if not qualifying:
            print("No qualifying payouts to tweet")
            return
        tweet = format_payout_tweet(qualifying, stats)
        try:
            image_path = generate_payout_image(qualifying, recent)
        except Exception as e:
            print(f"Image generation failed ({e}), using fallback")
            image_path = str(IMAGES_DIR / "payout.png")
        print(f"Posting payout tweet:\n{tweet}\n")
        post_tweet(session, tweet, image_path)
        print(f"Posted payout tweet for {len(qualifying)} payout(s)")


def main():
    session = get_session()
    check_payouts(session)


if __name__ == "__main__":
    main()
