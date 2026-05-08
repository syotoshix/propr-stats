import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from datetime import datetime

IMAGES_DIR = Path(__file__).parent.parent / "images"
FONTS_DIR = Path(__file__).parent.parent / "fonts"

TEMPLATE = "daily-stats-template.png"
OUTPUT = "daily-stats-generated.png"

WHITE = (255, 255, 255, 255)
GRAY = (160, 160, 160, 255)
TRADER_LINE_LEFT = (34, 197, 94)
TRADER_LINE_RIGHT = (6, 182, 212)
TRADER_LINE_MID = (20, 190, 153)

TIER_ORDER = ["free-trial", "starter", "explorer", "bronze", "silver", "gold"]
CHART_TIERS = ["starter", "explorer", "bronze", "silver", "gold"]
TIER_LABELS = {
    "free-trial": "Free Trial",
    "starter": "Starter",
    "explorer": "Explorer",
    "bronze": "Bronze",
    "silver": "Silver",
    "gold": "Gold",
}
TIER_COLORS = {
    "free-trial": (244, 114, 182, 255),
    "starter": (77, 208, 142, 255),
    "explorer": (75, 222, 245, 255),
    "bronze": (227, 173, 51, 255),
    "silver": (199, 199, 204, 255),
    "gold": (251, 221, 63, 255),
}


def _font(size, bold=False):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), max(8, size))


def _nice_step(max_val, n_steps=4):
    if max_val <= 0:
        return 1
    raw = max_val / n_steps
    mag = 10 ** math.floor(math.log10(max(raw, 1)))
    for mult in [1, 2, 2.5, 5, 10]:
        if mult * mag >= raw:
            return mult * mag
    return mag * 10


def base_slug(slug):
    return slug[:-2] if slug.endswith(("-s", "-t")) else slug


def build_daily_data(purchases_data, days=7):
    """Transform API purchases response into {date: {tier: count}} for last N days."""
    daily = {}
    for ch in purchases_data["byChallenge"]:
        tier = base_slug(ch["slug"])
        if tier not in TIER_ORDER:
            continue
        for entry in ch["history"]:
            date = entry["date"]
            if date not in daily:
                daily[date] = {t: 0 for t in TIER_ORDER}
            daily[date][tier] += entry["purchases"]
    sorted_dates = sorted(daily)[-days:]
    return {d: daily[d] for d in sorted_dates}


def generate(daily_by_tier, highlight_date=None, traders_by_date=None, new_traders_by_date=None, passes_count=None, pnl_day=None, cum_payouts=None):
    """
    daily_by_tier: {date_str: {tier: count}} ordered chronologically
    highlight_date: date to show tooltip on (defaults to most recent)
    traders_by_date: {date_str: total_traders} for right-axis line chart
    new_traders_by_date: {date_str: new_traders} shown in tooltip
    passes_count: number of challenge passes for the highlight date
    pnl_day: dict with profit/loss/net keys for the highlight date
    Returns path to generated image.
    """
    img = Image.open(IMAGES_DIR / TEMPLATE).convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    dates = sorted(daily_by_tier.keys())
    tip_date = highlight_date or (dates[-1] if dates else None)

    # Plot area
    px1 = int(W * 0.07)
    px2 = int(W * 0.95)
    py1 = int(H * 0.21)
    py2 = int(H * 0.74)

    # Y-axis range (chart tiers only, free-trial excluded from bars)
    max_total = max((sum(daily_by_tier[d].get(t, 0) for t in CHART_TIERS) for d in dates), default=1)
    step = _nice_step(max_total, 4)
    n_steps = math.ceil(max_total / step)
    y_max = step * n_steps

    # Gridlines and Y labels
    y_f = _font(max(8, int(H * 0.028)))
    for i in range(n_steps + 1):
        val = step * i
        y_px = py2 - int((val / y_max) * (py2 - py1))
        draw.line([(px1, y_px), (px2, y_px)], fill=(55, 65, 60, 160), width=2)
        lbl = str(int(val))
        lb = draw.textbbox((0, 0), lbl, font=y_f)
        draw.text(
            (px1 - (lb[2] - lb[0]) - int(W * 0.008), y_px - (lb[3] - lb[1]) // 2),
            lbl, font=y_f, fill=GRAY,
        )

    # Bars
    n = len(dates)
    if n == 0:
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        out_path = IMAGES_DIR / OUTPUT
        bg.save(str(out_path))
        return str(out_path)

    slot_w = (px2 - px1) / n
    bar_w = max(4, int(slot_w * 0.60))
    bar_tops = {}

    # Neon glow — two-pass blurred bars composited before the sharp bars
    def _draw_glow_bars(alpha):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i, date in enumerate(dates):
            bar_cx = int(px1 + (i + 0.5) * slot_w)
            bar_x1 = bar_cx - bar_w // 2
            bar_y = py2
            for tier in CHART_TIERS:
                count = daily_by_tier[date].get(tier, 0)
                if count <= 0:
                    continue
                seg_h = max(2, int((count / y_max) * (py2 - py1)))
                r, g, b, _ = TIER_COLORS[tier]
                d.rectangle([bar_x1, bar_y - seg_h, bar_x1 + bar_w - 1, bar_y - 1], fill=(r, g, b, alpha))
                bar_y -= seg_h
        return layer

    wide  = _draw_glow_bars(180).filter(ImageFilter.GaussianBlur(radius=max(45, int(H * 0.055))))
    img.alpha_composite(wide)
    mid   = _draw_glow_bars(230).filter(ImageFilter.GaussianBlur(radius=max(22, int(H * 0.032))))
    img.alpha_composite(mid)
    inner = _draw_glow_bars(255).filter(ImageFilter.GaussianBlur(radius=max(10, int(H * 0.014))))
    img.alpha_composite(inner)
    draw = ImageDraw.Draw(img, "RGBA")

    for i, date in enumerate(dates):
        bar_cx = int(px1 + (i + 0.5) * slot_w)
        bar_x1 = bar_cx - bar_w // 2
        bar_y = py2
        for tier in CHART_TIERS:
            count = daily_by_tier[date].get(tier, 0)
            if count <= 0:
                continue
            seg_h = max(2, int((count / y_max) * (py2 - py1)))
            draw.rectangle(
                [bar_x1, bar_y - seg_h, bar_x1 + bar_w - 1, bar_y - 1],
                fill=TIER_COLORS[tier],
            )
            bar_y -= seg_h
        bar_tops[date] = bar_y

    # Trader count line (right Y-axis)
    trader_points = []
    if traders_by_date:
        trader_vals = [(d, traders_by_date[d]) for d in dates if d in traders_by_date]
        if len(trader_vals) >= 2:
            t_min = min(v for _, v in trader_vals)
            t_max = max(v for _, v in trader_vals)
            t_range = max(t_max - t_min, 1)
            t_min_plot = max(0, t_min - t_range * 0.15)
            t_max_plot = t_max + t_range * 0.15

            def t_to_y(val):
                return py2 - int((val - t_min_plot) / (t_max_plot - t_min_plot) * (py2 - py1))

            # Right Y-axis labels
            r_step = _nice_step(t_max_plot - t_min_plot, 4)
            r_f = _font(max(8, int(H * 0.024)))
            r_val = math.ceil(t_min_plot / r_step) * r_step
            while r_val <= t_max_plot:
                y_px = t_to_y(r_val)
                if py1 <= y_px <= py2:
                    lbl = f"{int(r_val):,}"
                    lb = draw.textbbox((0, 0), lbl, font=r_f)
                    draw.text(
                        (px2 + int(W * 0.008), y_px - (lb[3] - lb[1]) // 2),
                        lbl, font=r_f, fill=TRADER_LINE_MID + (255,),
                    )
                r_val += r_step

            x_min = int(px1 + 0.5 * slot_w)
            x_max = int(px1 + (len(dates) - 0.5) * slot_w)
            x_span = max(x_max - x_min, 1)

            def _line_color(x):
                t = (x - x_min) / x_span
                r = int(TRADER_LINE_LEFT[0] * (1 - t) + TRADER_LINE_RIGHT[0] * t)
                g = int(TRADER_LINE_LEFT[1] * (1 - t) + TRADER_LINE_RIGHT[1] * t)
                b = int(TRADER_LINE_LEFT[2] * (1 - t) + TRADER_LINE_RIGHT[2] * t)
                return (r, g, b, 255)

            for d, val in trader_vals:
                i = dates.index(d)
                x = int(px1 + (i + 0.5) * slot_w)
                trader_points.append((x, t_to_y(val)))

            lw_t = max(5, int(H * 0.010))
            for i in range(len(trader_points) - 1):
                mx = (trader_points[i][0] + trader_points[i + 1][0]) // 2
                draw.line([trader_points[i], trader_points[i + 1]], fill=_line_color(mx), width=lw_t)

            dot_r_t = max(4, int(H * 0.012))
            for x, y in trader_points:
                draw.ellipse([x - dot_r_t, y - dot_r_t, x + dot_r_t, y + dot_r_t], fill=_line_color(x))

    # X-axis labels
    x_f = _font(max(8, int(H * 0.028)))
    for i, date in enumerate(dates):
        bar_cx = int(px1 + (i + 0.5) * slot_w)
        dt = datetime.strptime(date, "%Y-%m-%d")
        lbl = f"{dt.strftime('%b')} {dt.day}"
        lb = draw.textbbox((0, 0), lbl, font=x_f)
        draw.text((bar_cx - (lb[2] - lb[0]) // 2, py2 + int(H * 0.018)), lbl, font=x_f, fill=GRAY)

    # Legend centered at bottom
    TIER_ICON_FILES = {
        "free-trial": "trial_icon.webp",
        "starter": "starter_icon.webp",
        "explorer": "explorer_icon.webp",
        "bronze": "bronze_icon.webp",
        "silver": "silver_icon.webp",
        "gold": "gold_icon.webp",
    }
    icon_size = max(8, int(H * 0.038))

    active_tiers = [t for t in CHART_TIERS if any(daily_by_tier[d].get(t, 0) > 0 for d in dates)]
    leg_f = _font(max(8, int(H * 0.030)))
    dot_r = max(4, int(H * 0.013))
    leg_gap = int(W * 0.030)
    leg_y = int(H * 0.860)

    leg_parts = []
    for tier in active_tiers:
        lb = draw.textbbox((0, 0), TIER_LABELS[tier], font=leg_f)
        item_w = icon_size + int(W * 0.010) + (lb[2] - lb[0])
        leg_parts.append(("tier", tier, TIER_LABELS[tier], TIER_COLORS[tier], item_w, lb))
    if trader_points:
        lb = draw.textbbox((0, 0), "Traders", font=leg_f)
        item_w = dot_r * 2 + int(W * 0.010) + (lb[2] - lb[0])
        leg_parts.append(("line", None, "Traders", TRADER_LINE_MID + (255,), item_w, lb))

    total_leg_w = sum(p[4] for p in leg_parts) + leg_gap * (len(leg_parts) - 1)
    leg_x = W // 2 - total_leg_w // 2

    for kind, tier, label, color, item_w, lb in leg_parts:
        text_y = leg_y - (lb[1] + lb[3]) // 2
        if kind == "line":
            mid_y = leg_y
            draw.line([(leg_x, mid_y), (leg_x + dot_r * 2, mid_y)], fill=color, width=max(2, int(H * 0.004)))
            cx = leg_x + dot_r
            draw.ellipse([cx - dot_r // 2, mid_y - dot_r // 2, cx + dot_r // 2, mid_y + dot_r // 2], fill=color)
            draw.text((leg_x + dot_r * 2 + int(W * 0.010), text_y), label, font=leg_f, fill=WHITE)
            leg_x += item_w + leg_gap
        else:
            icon_file = TIER_ICON_FILES.get(tier)
            if icon_file:
                icon = Image.open(IMAGES_DIR / "challenge_icons" / icon_file).convert("RGBA")
                icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
                icon_y = leg_y - icon_size // 2
                img.paste(icon, (leg_x, icon_y), icon)
                draw = ImageDraw.Draw(img, "RGBA")
            else:
                draw.ellipse([leg_x, leg_y - dot_r, leg_x + dot_r * 2, leg_y + dot_r], fill=color)
            draw.text((leg_x + icon_size + int(W * 0.010), text_y), label, font=leg_f, fill=WHITE)
            leg_x += item_w + leg_gap

    # Tooltip — two-column, centered on image, semi-transparent
    if tip_date and tip_date in bar_tops:
        tier_data = daily_by_tier[tip_date]
        total = sum(tier_data.get(t, 0) for t in TIER_ORDER)

        tip_lbl_f = _font(max(8, int(H * 0.033)))
        tip_val_f = _font(max(8, int(H * 0.033)), bold=True)
        tip_date_f = _font(max(8, int(H * 0.037)), bold=True)
        pad = int(W * 0.024)
        col_gap = int(W * 0.042)
        row_h = int(H * 0.047)

        dt = datetime.strptime(tip_date, "%Y-%m-%d")
        date_display = f"{dt.strftime('%b')} {dt.day}, {dt.year}"

        trader_total = traders_by_date.get(tip_date) if traders_by_date else None
        trader_new = new_traders_by_date.get(tip_date) if new_traders_by_date else None

        # Left column: all tiers + Total
        left_col = [
            (f"{TIER_LABELS[t]}: ", str(tier_data.get(t, 0)), TIER_COLORS[t] if tier_data.get(t, 0) > 0 else GRAY)
            for t in TIER_ORDER
        ]
        left_col.append(("Total: ", str(total), WHITE))

        # Right column: Traders, New, Passed, PnL
        right_col = []
        if trader_total is not None:
            right_col.append(("Traders: ", f"{trader_total:,}", TRADER_LINE_MID + (255,)))
        if trader_new is not None:
            right_col.append(("New: ", f"+{trader_new:,}", TRADER_LINE_MID + (255,)))
        if passes_count is not None:
            right_col.append(("Passed: ", str(passes_count), (52, 211, 153, 255)))
        if pnl_day:
            profit = pnl_day.get("profit", 0)
            loss = pnl_day.get("loss", 0)
            net = pnl_day.get("net", 0)
            right_col.append(("Profit: ", f"${profit:,.0f}", (52, 211, 153, 255)))
            right_col.append(("Loss: ", f"${loss:,.0f}", (239, 68, 68, 255)))
            net_color = (52, 211, 153, 255) if net >= 0 else (239, 68, 68, 255)
            net_str = f"+${net:,.0f}" if net >= 0 else f"-${abs(net):,.0f}"
            right_col.append(("Net: ", net_str, net_color))
        if cum_payouts is not None and cum_payouts > 0:
            right_col.append(("Payouts: ", f"${cum_payouts:,.2f}", (251, 191, 36, 255)))

        def _item_w(lbl, val):
            return draw.textbbox((0, 0), lbl, font=tip_lbl_f)[2] + draw.textbbox((0, 0), val, font=tip_val_f)[2]

        col1_w = max((_item_w(lbl, val) for lbl, val, _ in left_col), default=0)
        col2_w = max((_item_w(lbl, val) for lbl, val, _ in right_col), default=0)
        date_w = draw.textbbox((0, 0), date_display, font=tip_date_f)[2]
        content_w = max(col1_w + (col_gap + col2_w if right_col else 0), date_w)

        n_rows = max(len(left_col), len(right_col))
        tip_w = content_w + 2 * pad
        tip_h = row_h + row_h * n_rows + 2 * pad  # date row + data rows

        # Center horizontally, place in upper chart area
        tip_x = W // 2 - tip_w // 2
        tip_y = py1 + int(H * 0.02)

        # Draw background on separate layer so alpha composites over chart content
        tip_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tip_bg_draw = ImageDraw.Draw(tip_bg)
        try:
            tip_bg_draw.rounded_rectangle(
                [tip_x, tip_y, tip_x + tip_w, tip_y + tip_h],
                radius=max(4, int(H * 0.014)),
                fill=(15, 22, 18, 192),
            )
        except AttributeError:
            tip_bg_draw.rectangle([tip_x, tip_y, tip_x + tip_w, tip_y + tip_h], fill=(15, 22, 18, 192))
        img.alpha_composite(tip_bg)
        draw = ImageDraw.Draw(img, "RGBA")

        # Date header — bold white, centered
        db = draw.textbbox((0, 0), date_display, font=tip_date_f)
        cy = tip_y + pad
        draw.text((tip_x + tip_w // 2 - (db[2] - db[0]) // 2, cy), date_display, font=tip_date_f, fill=WHITE)
        cy += row_h

        # Data rows
        x2 = tip_x + pad + col1_w + col_gap
        for i in range(n_rows):
            if i < len(left_col):
                lbl, val, color = left_col[i]
                lw = draw.textbbox((0, 0), lbl, font=tip_lbl_f)[2]
                draw.text((tip_x + pad, cy), lbl, font=tip_lbl_f, fill=GRAY)
                draw.text((tip_x + pad + lw, cy), val, font=tip_val_f, fill=color)
            if right_col and i < len(right_col):
                lbl, val, color = right_col[i]
                lw = draw.textbbox((0, 0), lbl, font=tip_lbl_f)[2]
                draw.text((x2, cy), lbl, font=tip_lbl_f, fill=GRAY)
                draw.text((x2 + lw, cy), val, font=tip_val_f, fill=color)
            cy += row_h

    bg = Image.new("RGB", img.size, (0, 0, 0))
    bg.paste(img, mask=img.split()[3])
    out_path = IMAGES_DIR / OUTPUT
    bg.save(str(out_path))
    return str(out_path)
