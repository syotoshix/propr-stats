import argparse
import json
import os
import sys
import requests
from pathlib import Path
from requests_oauthlib import OAuth1Session

sys.path.insert(0, str(Path(__file__).parent))
from payout_image import generate as generate_payout_image

BASE_URL = "https://www.propr.xyz"
TX_HASHES_FILE = Path(__file__).parent.parent / "state" / "tweeted_tx_hashes.txt"
PAYOUT_USERS_FILE = Path(__file__).parent.parent / "state" / "payout_users.txt"
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


def load_tweeted_hashes():
    if not TX_HASHES_FILE.exists():
        return set()
    return set(line.strip() for line in TX_HASHES_FILE.read_text().splitlines() if line.strip())


def save_tweeted_hashes(hashes):
    TX_HASHES_FILE.write_text("\n".join(sorted(hashes)))


def normalize_payout(p):
    return {
        "id": p["payoutId"],
        "amount": float(p["userAmount"]),
        "paid_at": p["processedAt"],
        "tx_hash": p["txHash"],
    }


def save_payout_users(payouts_raw):
    existing_payout_ids = set()
    lines = []
    if PAYOUT_USERS_FILE.exists():
        for line in PAYOUT_USERS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(line)
                existing_payout_ids.add(line.split("\t")[0])

    for p in payouts_raw:
        payout_id = p.get("payoutId", "")
        if payout_id in existing_payout_ids:
            continue
        user_id = p.get("userId", "")
        profile = (p.get("user") or {}).get("profile") or {}
        credential = p.get("credential") or {}
        name = profile.get("name", "")
        username = profile.get("username", "")
        wallet = credential.get("address", "")
        amount = p.get("userAmount", "")
        lines.append(f"{payout_id}\t{user_id}\t{name}\t{username}\t{wallet}\t${amount}")
        existing_payout_ids.add(payout_id)

    PAYOUT_USERS_FILE.write_text("\n".join(lines), encoding="utf-8")


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


def format_payout_tweet(payouts, stats, small_payouts=None):
    from datetime import datetime, timezone
    total_paid = stats["totalPaid"]
    total_count = stats["totalCount"]

    if len(payouts) == 1:
        payout = payouts[0]
        paid_at = datetime.fromisoformat(payout["paid_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
        date_str = f"{paid_at.strftime('%b')} {paid_at.day}, {paid_at.strftime('%H:%M UTC')}"
        lines = [
            f"💸 @ProprXYZ just paid out ${float(payout['amount']):,.2f} USDC to a funded trader",
            "",
            f"⏱️ {date_str}",
            "",
            f"Tx: https://etherscan.io/tx/{payout['tx_hash']}",
        ]
    else:
        total_amount = sum(float(p["amount"]) for p in payouts)
        lines = [
            f"💸 @ProprXYZ just paid out to {len(payouts)} funded traders",
            "",
        ]
        for p in payouts:
            p_dt = datetime.fromisoformat(p["paid_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            p_date = f"{p_dt.strftime('%b')} {p_dt.day}, {p_dt.strftime('%H:%M UTC')}"
            lines.append(f"🔵 ${float(p['amount']):,.2f} USDC - ⏱️ {p_date}")
            lines.append(f"Tx: https://etherscan.io/tx/{p['tx_hash']}")
            lines.append("")
        lines.append(f"Total: ${total_amount:,.2f} USDC 💰")

    if small_payouts:
        small_total = sum(float(p["amount"]) for p in small_payouts)
        n = len(small_payouts)
        lines += [
            "",
            f"{n} smaller payout{'s' if n > 1 else ''} detected (< $100) total ${small_total:,.2f} USDC",
        ]

    lines += [
        "",
        f"${total_paid:,.2f} paid to {total_count} funded traders so far! 💰",
        "",
        "Stay liquid 💧 $PROPR",
    ]

    return "\n".join(lines)


def _do_post(session, qualifying, all_payouts, stats, small_payouts=None):
    tweet = format_payout_tweet(qualifying, stats, small_payouts)
    try:
        image_path = generate_payout_image(qualifying, all_payouts)
    except Exception as e:
        print(f"Image generation failed ({e}), using fallback")
        image_path = str(IMAGES_DIR / "payout.png")
    print(f"Posting payout tweet:\n{tweet}\n")
    post_tweet(session, tweet, image_path)


def combined_stats(new_processed):
    old_data = fetch("/api/transparency/payouts")
    old_payouts = old_data["recent"]
    seen = {p["tx_hash"]: float(p["amount"]) for p in old_payouts}
    for p in new_processed:
        seen[p["txHash"]] = float(p["userAmount"])
    return {"totalPaid": sum(seen.values()), "totalCount": len(seen)}


def check_payouts(session):
    raw = fetch("/api/transparency/api-payouts")
    processed = [p for p in raw if p["status"] == "processed" and p.get("txHash")]

    if not processed:
        print("No processed payouts found")
        return

    all_normalized = [normalize_payout(p) for p in processed]
    stats = combined_stats(processed)

    tweeted_hashes = load_tweeted_hashes()
    new_raw = [p for p in processed if p["txHash"] not in tweeted_hashes]

    if not new_raw:
        print("No new payouts")
        return

    save_payout_users(new_raw)

    qualifying = [normalize_payout(p) for p in new_raw if float(p["userAmount"]) >= 100]
    small = [normalize_payout(p) for p in new_raw if float(p["userAmount"]) < 100]

    # Save hashes for all new payouts (including sub-$100) to avoid re-checking
    new_hashes = tweeted_hashes | {p["txHash"] for p in new_raw}
    save_tweeted_hashes(new_hashes)

    if not qualifying:
        print(f"No qualifying payouts to tweet ({len(small)} below $100 skipped)")
        return

    _do_post(session, qualifying, all_normalized, stats, small_payouts=small if small else None)
    print(f"Posted payout tweet for {len(qualifying)} payout(s), mentioned {len(small)} smaller ones")


def manual_payouts_cmd(session, payouts_json):
    payouts = json.loads(payouts_json)
    for p in payouts:
        p["amount"] = float(p["amount"])

    raw = fetch("/api/transparency/api-payouts")
    processed = [p for p in raw if p["status"] == "processed" and p.get("txHash")]
    all_api_normalized = [normalize_payout(p) for p in processed]

    base_stats = combined_stats(processed)
    manual_hashes = {p["tx_hash"] for p in payouts if p.get("tx_hash")}
    extra = [p for p in payouts if p.get("tx_hash") not in {p2["txHash"] for p2 in processed}]
    stats = {
        "totalPaid": base_stats["totalPaid"] + sum(p["amount"] for p in extra),
        "totalCount": base_stats["totalCount"] + len(extra),
    }

    tweeted_hashes = load_tweeted_hashes()
    qualifying = [
        p for p in payouts
        if p["amount"] >= 100 and p.get("tx_hash") not in tweeted_hashes
    ]
    skipped = len(payouts) - len(qualifying)
    if skipped:
        print(f"Skipping {skipped} payout(s) (below $100 or already tweeted)")
    if not qualifying:
        print("No qualifying payouts (all below $100 or already tweeted)")
        return

    all_payouts = all_api_normalized + payouts

    _do_post(session, qualifying, all_payouts, stats)

    new_hashes = tweeted_hashes | {p["tx_hash"] for p in payouts if p.get("tx_hash")}
    save_tweeted_hashes(new_hashes)
    print(f"Posted manual tweet for {len(qualifying)} payout(s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", help="JSON array of payouts to post manually")
    args = parser.parse_args()

    session = get_session()
    if args.manual:
        manual_payouts_cmd(session, args.manual)
    else:
        check_payouts(session)


if __name__ == "__main__":
    main()