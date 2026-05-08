import math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont
from datetime import datetime, timezone

IMAGES_DIR = Path(__file__).parent.parent / "images"
FONTS_DIR = Path(__file__).parent.parent / "fonts"

TEMPLATE = "payout-template.png"
OUTPUT = "payout-generated.png"

WHITE = (255, 255, 255, 255)
GRAY = (160, 160, 160, 255)
GREEN = (16, 185, 129, 255)
GREEN_TOP = (143, 218, 88)
GREEN_BOTTOM = (47, 176, 144)


def _font(size, bold=False):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), max(8, size))


def _fit_font(draw, text, max_width, start_size, bold=False):
    size = start_size
    while size > 8:
        f = _font(size, bold=bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
        size = int(size * 0.88)
    return _font(8, bold=bold)


def _nice_step(max_val, n_steps=4):
    if max_val <= 0:
        return 100
    raw = max_val / n_steps
    mag = 10 ** math.floor(math.log10(raw))
    for mult in [1, 2, 2.5, 5, 10]:
        if mult * mag >= raw:
            return mult * mag
    return mag * 10


def _format_y(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1000:
        k = val / 1000
        return f"${int(k)}K" if k == int(k) else f"${k:.1f}K"
    return f"${int(val)}"


def _pick_label_indices(n, target=5):
    if n <= target:
        return list(range(n))
    result = {0, n - 1}
    step = (n - 1) / (target - 1)
    for i in range(1, target - 1):
        result.add(round(i * step))
    return sorted(result)


def _dashed_hline(draw, x1, x2, y, color, dash=6, gap=4):
    x = x1
    while x < x2:
        draw.line([(x, y), (min(x + dash, x2), y)], fill=color, width=1)
        x += dash + gap


def _parse_dt(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _make_gradient(w, h, color_top, color_bottom):
    grad = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(grad)
    for row in range(h):
        t = row / max(h - 1, 1)
        r = int(color_top[0] * (1 - t) + color_bottom[0] * t)
        g = int(color_top[1] * (1 - t) + color_bottom[1] * t)
        b = int(color_top[2] * (1 - t) + color_bottom[2] * t)
        d.line([(0, row), (w - 1, row)], fill=(r, g, b, 255))
    return grad


def _draw_gradient_text(img, text, font, x, y, color_top, color_bottom):
    bx0, by0, bx1, by1 = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    tw, th = bx1 - bx0, by1 - by0
    if tw <= 0 or th <= 0:
        return
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).text((-bx0, -by0), text, font=font, fill=255)
    grad = _make_gradient(tw, th, color_top, color_bottom)
    grad.putalpha(mask)
    img.alpha_composite(grad, (x + bx0, y + by0))


def generate(new_payouts, all_payouts):
    """
    new_payouts: list of new payout dicts, oldest-first (1 or more)
    all_payouts: list of all payouts (any order), each with amount and paid_at
    Returns path to generated image.
    """
    payout = new_payouts[-1]  # most recent, used for tooltip timestamp
    is_multi = len(new_payouts) > 1

    img = Image.open(IMAGES_DIR / TEMPLATE).convert("RGBA")
    W, H = img.size

    sorted_payouts = sorted(all_payouts, key=lambda p: p["paid_at"])
    cum_data = []
    running = 0.0
    for p in sorted_payouts:
        running += float(p["amount"])
        cum_data.append((p["paid_at"], running))

    draw = ImageDraw.Draw(img, "RGBA")

    # Title — Inter Regular, gradient
    nl_f = _font(max(16, int(H * 0.065)))
    nl_text = "New Payouts" if is_multi else "New Payout"
    nlb = draw.textbbox((0, 0), nl_text, font=nl_f)
    nl_y = int(H * 0.200)
    _draw_gradient_text(img, nl_text, nl_f, W // 2 - (nlb[2] - nlb[0]) // 2, nl_y, GREEN_TOP, GREEN_BOTTOM)

    # Amount: total for multi, single amount otherwise
    display_amount = sum(float(p["amount"]) for p in new_payouts) if is_multi else float(payout["amount"])
    main_str = f"${display_amount:,.2f}"
    usdc_str = " USDC"
    am_size = max(24, int(H * 0.115))
    am_f = _fit_font(draw, main_str, int(W * 0.60), am_size, bold=True)
    usdc_f = _font(max(14, int(H * 0.060)), bold=True)

    main_b = draw.textbbox((0, 0), main_str, font=am_f)
    usdc_b = draw.textbbox((0, 0), usdc_str, font=usdc_f)
    main_w = main_b[2] - main_b[0]
    usdc_w = usdc_b[2] - usdc_b[0]

    am_y = nl_y + (nlb[3] - nlb[1]) + int(H * 0.012)
    am_x = W // 2 - (main_w + usdc_w) // 2

    _draw_gradient_text(img, main_str, am_f, am_x, am_y, GREEN_TOP, GREEN_BOTTOM)

    # Align USDC baseline to bottom of main amount
    main_h = main_b[3] - main_b[1]
    usdc_h = usdc_b[3] - usdc_b[1]
    usdc_y = am_y + main_h - usdc_h
    _draw_gradient_text(img, usdc_str, usdc_f, am_x + main_w, usdc_y, GREEN_TOP, GREEN_BOTTOM)

    # Recreate draw after alpha_composite operations
    draw = ImageDraw.Draw(img, "RGBA")

    if len(cum_data) >= 2:
        # Chart bounds — 65% width, centered
        cx1, cx2 = int(W * 0.175), int(W * 0.825)
        cy1, cy2 = int(H * 0.43), int(H * 0.93)

        # Transparent background — no dark overlay drawn

        # "CUMULATIVE PAID OUT" label
        cl_f = _font(max(8, int(H * 0.022)))
        draw.text(
            (cx1 + int(W * 0.012), cy1 + int(H * 0.012)),
            "CUMULATIVE PAID OUT",
            font=cl_f,
            fill=(110, 110, 110, 255),
        )

        y_f = _font(max(8, int(H * 0.026)))
        x_f = _font(max(8, int(H * 0.026)))

        # Plot bounds with label margins
        px1 = cx1 + int(W * 0.055)
        px2 = cx2 - int(W * 0.012)
        py1 = cy1 + int(H * 0.075)
        py2 = cy2 - int(H * 0.095)

        # Y range
        max_cum = cum_data[-1][1]
        step = _nice_step(max_cum, 4)
        n_steps = math.ceil(max_cum / step)
        y_max = step * n_steps

        for i in range(n_steps + 1):
            val = step * i
            y_px = py2 - int((val / y_max) * (py2 - py1))
            _dashed_hline(draw, px1, px2, y_px, (45, 75, 55, 200))
            lbl = _format_y(val)
            lb = draw.textbbox((0, 0), lbl, font=y_f)
            draw.text(
                (px1 - (lb[2] - lb[0]) - int(W * 0.006), y_px - (lb[3] - lb[1]) // 2),
                lbl, font=y_f, fill=GRAY,
            )

        dates = [_parse_dt(d) for d, _ in cum_data]
        t0, t1 = dates[0].timestamp(), dates[-1].timestamp()
        t_span = max(t1 - t0, 1)

        def to_px(ts, val):
            x = px1 + int((ts - t0) / t_span * (px2 - px1))
            y = py2 - int((val / y_max) * (py2 - py1))
            return x, y

        points = [to_px(d.timestamp(), v) for d, (_, v) in zip(dates, cum_data)]

        # Fading green fill below the line
        fill_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fill_draw = ImageDraw.Draw(fill_layer)
        poly_pts = list(points) + [(points[-1][0], py2), (points[0][0], py2)]
        fill_draw.polygon(poly_pts, fill=(16, 185, 129, 255))
        grad_mask = Image.new("L", (W, H), 0)
        grad_draw = ImageDraw.Draw(grad_mask)
        for row in range(py1, py2 + 1):
            t = (row - py1) / max(py2 - py1, 1)
            grad_draw.line([(0, row), (W - 1, row)], fill=int(150 * (1 - t)))
        _, _, _, fill_a = fill_layer.split()
        fill_layer.putalpha(ImageChops.multiply(fill_a, grad_mask))
        img.alpha_composite(fill_layer)
        draw = ImageDraw.Draw(img, "RGBA")

        # Line
        lw = max(2, int(H * 0.005))
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=GREEN, width=lw)

        # Dots: spaced out to avoid clutter, always show last
        dot_r = max(4, int(H * 0.013))
        last_dot_x = -9999
        for i, (x, y) in enumerate(points):
            is_last = (i == len(points) - 1)
            if is_last or x - last_dot_x >= int(W * 0.04):
                draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=GREEN)
                last_dot_x = x

        # X-axis labels: evenly spread, skip overlapping ones, always show last
        last_lx = -9999
        for i, (x, _) in enumerate(points):
            lbl = f"{dates[i].strftime('%b')} {dates[i].day}"
            lb = draw.textbbox((0, 0), lbl, font=x_f)
            lw2 = lb[2] - lb[0]
            is_last = (i == len(points) - 1)
            if is_last or x - last_lx >= lw2 + int(W * 0.025):
                draw.text((x - lw2 // 2, py2 + int(H * 0.012)), lbl, font=x_f, fill=GRAY)
                last_lx = x

        # Tooltip at last point
        paid_dt = _parse_dt(payout["paid_at"])
        tip_date = f"{paid_dt.strftime('%b')} {paid_dt.day}, {paid_dt.strftime('%H:%M UTC')}"
        tip_val = f"${display_amount:,.2f}"

        tip_df = _font(max(8, int(H * 0.024)))
        tip_vf = _font(max(10, int(H * 0.032)), bold=True)

        pad = int(W * 0.012)
        tdb = draw.textbbox((0, 0), tip_date, font=tip_df)
        tvb = draw.textbbox((0, 0), tip_val, font=tip_vf)
        tip_w = max(tdb[2] - tdb[0], tvb[2] - tvb[0]) + 2 * pad
        tip_h = (tdb[3] - tdb[1]) + (tvb[3] - tvb[1]) + int(H * 0.035) + 2 * pad

        last_x, last_y = points[-1]
        tip_x = last_x - tip_w - int(W * 0.012)
        tip_x = max(cx1 + 2, min(tip_x, cx2 - tip_w - 2))
        tip_y = last_y - tip_h + int(H * 0.02)
        tip_y = max(cy1 + 2, min(tip_y, cy2 - tip_h - 2))

        try:
            draw.rounded_rectangle(
                [tip_x, tip_y, tip_x + tip_w, tip_y + tip_h],
                radius=max(4, int(H * 0.015)),
                fill=(8, 28, 18, 230),
            )
        except AttributeError:
            draw.rectangle([tip_x, tip_y, tip_x + tip_w, tip_y + tip_h], fill=(8, 28, 18, 230))

        draw.text((tip_x + pad, tip_y + pad), tip_date, font=tip_df, fill=GRAY)
        draw.text(
            (tip_x + pad, tip_y + pad + (tdb[3] - tdb[1]) + int(H * 0.018)),
            tip_val, font=tip_vf, fill=GREEN,
        )

        draw.line([(last_x, tip_y + tip_h), (last_x, last_y - dot_r)], fill=(70, 120, 90, 200), width=1)

    bg = Image.new("RGB", img.size, (0, 0, 0))
    bg.paste(img, mask=img.split()[3])
    out_path = IMAGES_DIR / OUTPUT
    bg.save(str(out_path))
    return str(out_path)
