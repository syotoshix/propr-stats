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


def base_slug(slug):
    return slug[:-2] if slug.endswith(("-s", "-t")) else slug


def display_name(challenge):
    slug = challenge["slug"]
    if slug.endswith("-s"):
        return f"{challenge['name']} 1-Step"
    elif slug.endswith("-t"):
        return f"{challenge['name']} 2-Step"
    return challenge["name"]


def pass_rate_line(name, slug, pass_rates):
    base = base_slug(slug)
    stats = pass_rates.get(base)
    if not stats:
        return None
    attempts = stats["attempts"]
    passed = stats["passed"]
    trader_str = "1 trader has passed" if passed == 1 else f"{passed} traders have passed"
    if base == "free-trial":
        return f"In total {attempts:,} attempted the {name} ➡️ {trader_str}"
    return f"In total {attempts:,} bought the {name} Challenge ➡️ {trader_str}"


def compact_stat_line(base, pass_rates):
    stats = pass_rates.get(base)
    if not stats:
        return None
    return f"{stats['attempts']:,} attempted ➡️ {stats['passed']:,} traders passed"


def fmt_funded(amount):
    if amount >= 1000 and amount % 1000 == 0:
        return f"${amount // 1000}K"
    return f"${amount:,}"


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
        f"${total_paid:,.2f} paid to {total_count} funded traders so far!\n\nStay liquid 💧 $PROPR",
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

    gold_ids = {k for k, v in challenges.items() if v["slug"].startswith("gold-")}
    gold_passes = [e for e in new_passes if e["challengeId"] in gold_ids]
    other_passes = [e for e in new_passes if e["challengeId"] not in gold_ids]

    pass_rates = fetch_pass_rates()
    tweets_posted = 0

    ACTIVITY_STATE_FILE.write_text(events[0]["attemptId"])

    if gold_passes:
        tweet, image_name = format_pass_tweet(gold_passes, challenges, pass_rates)
        print(f"Posting Gold pass tweet:\n{tweet}\n")
        post_tweet(session, tweet, image_name)
        print(f"Posted Gold pass tweet for {len(gold_passes)} event(s)")
        tweets_posted += 1

    if other_passes:
        if tweets_posted > 0:
            print("Waiting 60s before non-Gold pass tweet...")
            time.sleep(60)
        tweet, image_name = format_pass_tweet(other_passes, challenges, pass_rates)
        print(f"Posting pass tweet:\n{tweet}\n")
        post_tweet(session, tweet, image_name)
        print(f"Posted pass tweet for {len(other_passes)} event(s)")


def format_pass_tweet(new_passes, challenges, pass_rates):
    from collections import defaultdict
    from datetime import datetime, timezone
    occurred_at = datetime.fromisoformat(new_passes[0]["occurredAt"].replace("Z", "+00:00")).astimezone(timezone.utc)
    timestamp = f"⏱️ {occurred_at.strftime('%b %-d, %H:%M UTC')}"
    count = len(new_passes)

    # Group events by base slug (silver, gold, free-trial, etc.)
    base_groups = defaultdict(list)
    unknown_count = 0
    for event in new_passes:
        ch = challenges.get(event["challengeId"])
        if ch:
            base_groups[base_slug(ch["slug"])].append(event)
        else:
            unknown_count += 1

    unique_bases = list(base_groups.keys())

    # Single pass
    if count == 1 and not unknown_count:
        event = new_passes[0]
        challenge = challenges.get(event["challengeId"])
        if challenge and challenge["fundedBalance"] is not None:
            dname = display_name(challenge)
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            price_str = f"${price}" if price else "free"
            stat = pass_rate_line(challenge["name"], challenge["slug"], pass_rates)
            lines = [
                f"✅ A trader just passed the @ProprXYZ {dname} Challenge!",
                timestamp,
                "",
                f"{price_str} challenge 👉 ${funded:,} funded account",
            ]
            if stat:
                lines += ["", stat]
            lines += ["", "Stay liquid 💧 $PROPR"]
            return "\n".join(lines), base_slug(challenge["slug"])
        elif challenge and challenge["fundedBalance"] is None:
            stat = pass_rate_line(challenge["name"], challenge["slug"], pass_rates)
            lines = [f"✅ A trader just passed the @ProprXYZ {challenge['name']}!", timestamp, "", "Time to get funded!"]
            if stat:
                lines += ["", stat]
            lines += ["", "Stay liquid 💧 $PROPR"]
            return "\n".join(lines), "free-trial"
        else:
            return f"✅ A trader just passed their @ProprXYZ challenge!\n{timestamp}\n\nStay liquid 💧 $PROPR", "mixed"

    # All events are same base challenge (e.g., all Silver — mix of 1-step and 2-step is fine)
    if len(unique_bases) == 1 and not unknown_count:
        b = unique_bases[0]
        events_in_group = base_groups[b]
        variant_counts = Counter(e["challengeId"] for e in events_in_group)
        unique_variants = list(variant_counts.keys())
        base_challenge_name = challenges[unique_variants[0]]["name"]

        # All same variant
        if len(unique_variants) == 1:
            challenge = challenges[unique_variants[0]]
            dname = display_name(challenge)
            funded = challenge["fundedBalance"]
            price = challenge["price"]
            cstat = compact_stat_line(b, pass_rates)
            if funded is not None:
                price_str = f"${price}" if price else "free"
                lines = [
                    f"✅ {count} traders recently passed their @ProprXYZ {dname} Challenge",
                    "",
                    f"{price_str} challenge 👉 {fmt_funded(funded)} funded — each",
                ]
                if cstat:
                    lines.append(cstat)
                lines += ["", "Stay liquid 💧 $PROPR"]
                return "\n".join(lines), b
            else:
                lines = [f"✅ {count} traders recently passed their @ProprXYZ {dname}", ""]
                if cstat:
                    lines.append(cstat)
                lines += ["", "Stay liquid 💧 $PROPR"]
                return "\n".join(lines), "free-trial"

        # Mixed variants of same base (e.g., 1x Silver 1-Step + 1x Silver 2-Step)
        sorted_variants = sorted(unique_variants, key=lambda cid: challenges[cid].get("price") or 0, reverse=True)
        lines = [f"✅ {count} traders recently passed their @ProprXYZ {base_challenge_name} Challenge", ""]
        for cid in sorted_variants:
            n = variant_counts[cid]
            ch = challenges[cid]
            dname = display_name(ch)
            funded = ch["fundedBalance"]
            price = ch["price"]
            if funded is not None:
                price_str = f"${price}" if price else "free"
                lines.append(f"{n}x {dname}, {price_str} challenge 👉 {fmt_funded(funded)} funded")
            else:
                lines.append(f"{n}x {dname}")
        cstat = compact_stat_line(b, pass_rates)
        if cstat:
            lines.append(cstat)
        lines += ["", "Stay liquid 💧 $PROPR"]
        return "\n".join(lines), b

    # Multiple different base challenges (mixed tweet)
    lines = [f"✅ {count} traders recently passed their @ProprXYZ challenge", ""]

    sorted_bases = sorted(
        base_groups.items(),
        key=lambda x: max((challenges.get(e["challengeId"], {}).get("fundedBalance") or -1) for e in x[1]),
        reverse=True,
    )

    for b, events_in_group in sorted_bases:
        variant_counts = Counter(e["challengeId"] for e in events_in_group)
        sorted_variants = sorted(variant_counts.keys(), key=lambda cid: challenges.get(cid, {}).get("price") or 0, reverse=True)

        for cid in sorted_variants:
            n = variant_counts[cid]
            ch = challenges[cid]
            dname = display_name(ch)
            funded = ch["fundedBalance"]
            price = ch["price"]
            if funded is not None:
                price_str = f"${price}" if price else "free"
                lines.append(f"{n}x {dname}, {price_str} challenge 👉 {fmt_funded(funded)} funded")
            else:
                lines.append(f"{n}x {dname}")

        cstat = compact_stat_line(b, pass_rates)
        if cstat:
            lines.append(cstat)
        lines.append("")

    if unknown_count:
        lines.append(f"{unknown_count}x Unknown Challenge")
        lines.append("")

    lines.append("Stay liquid 💧 $PROPR")
    return "\n".join(lines), "mixed"


def main():
    challenges = load_challenges()
    session = get_session()
    check_payouts(session)
    time.sleep(30)
    check_passes(session, challenges)


if __name__ == "__main__":
    main()
