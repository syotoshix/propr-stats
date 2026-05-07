from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGES_DIR = Path(__file__).parent.parent / "images"
FONTS_DIR = Path(__file__).parent.parent / "fonts"
ICONS_DIR = IMAGES_DIR / "challenge_icons"

TEMPLATES = {
    1: "single-challenge.png",
    2: "double-challenge.png",
    3: "triple-challenge.png",
}
OUTPUTS = {
    1: "single-challenge-generated.png",
    2: "double-challenge-generated.png",
    3: "triple-challenge-generated.png",
}

ICON_MAP = {
    "free-trial": "trial_icon",
    "explorer": "explorer_icon",
    "starter": "starter_icon",
    "bronze": "bronze_icon",
    "silver": "silver_icon",
    "gold": "gold_icon",
}

WHITE = (255, 255, 255)
GRAY = (160, 160, 160)
GREEN = (16, 185, 129)

# Card bounding boxes as fractions of image dimensions
# Derived from scanning card border pixel positions in the actual 3200x1800 templates
CARD_X = (0.08, 0.91)
DIVIDER_FRAC = 0.47  # divider as fraction of card width from left

CARD_Y = {
    1: [(0.380, 0.622)],
    2: [(0.232, 0.478), (0.521, 0.770)],
    3: [(0.228, 0.427), (0.452, 0.650), (0.675, 0.873)],
}


def _font(size, bold=False):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), max(8, size))


def _fit_font(draw, text, max_width, start_size, bold=False):
    size = start_size
    while size > 8:
        f = _font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=f)
        if (bbox[2] - bbox[0]) <= max_width:
            return f
        size = int(size * 0.88)
    return _font(8, bold=bold)


def _load_icon(base_slug, size):
    name = ICON_MAP.get(base_slug, "trial_icon")
    path = ICONS_DIR / f"{name}.webp"
    if not path.exists():
        return None
    icon = Image.open(path).convert("RGBA")
    return icon.resize((size, size), Image.LANCZOS)


def _funded_k(amount):
    return f"${amount // 1000}K"


def _draw_card(draw, img, card, box):
    x1, y1, x2, y2 = box
    card_w = x2 - x1
    card_h = y2 - y1

    divider_x = x1 + int(card_w * DIVIDER_FRAC)

    small_size = max(12, int(card_h * 0.14))
    small_f = _font(small_size)
    funded_size = max(16, int(card_h * 0.18))
    funded_f = _font(funded_size, bold=True)
    stat_size = max(20, int(card_h * 0.28))
    stat_f = _font(stat_size, bold=True)
    label_size = max(10, int(card_h * 0.11))
    label_f = _font(label_size)
    arrow_f = _font(max(14, int(card_h * 0.13)))

    # --- Left section: icon + text ---
    icon_size = max(24, int(card_h * 0.62))
    left_margin = int(card_w * 0.08)   # push content away from card left edge
    gap = int(card_w * 0.022)          # gap between icon and text

    icon_x = x1 + left_margin
    icon_y = y1 + (card_h - icon_size) // 2

    icon = _load_icon(card["base_slug"], icon_size)
    if icon:
        img.paste(icon, (icon_x, icon_y), icon)

    text_x = icon_x + icon_size + gap
    name_max_w = divider_x - text_x - gap
    name_f = _fit_font(draw, card["name"], name_max_w, max(16, int(card_h * 0.20)), bold=True)
    name_size_actual = name_f.size

    # Stack name / price / funded with tight spacing; vertically center the block
    v_gap = max(6, int(card_h * 0.04))
    has_funded = card.get("funded") is not None
    block_h = name_size_actual + v_gap + small_size + (v_gap + funded_size if has_funded else 0)
    text_y = y1 + (card_h - block_h) // 2

    draw.text((text_x, text_y), card["name"], font=name_f, fill=WHITE)

    price_y = text_y + name_size_actual + v_gap
    price = card.get("price")
    price_str = f"${price:,} challenge" if price else "Free challenge"
    draw.text((text_x, price_y), price_str, font=small_f, fill=GRAY)

    if has_funded:
        draw.text((text_x, price_y + small_size + v_gap), f"→ {_funded_k(card['funded'])} funded", font=funded_f, fill=GREEN)

    # --- Right section: 3 stat blocks, vertically centered ---
    # Small gap from divider so stats sit slightly left of center-right
    right_x = divider_x + int(card_w * 0.01)
    right_w = x2 - right_x - int(card_w * 0.02)  # leave small right margin

    attempts = card.get("attempts", 0)
    passed = card.get("passed", 0)
    pct = int(passed / attempts * 100) if attempts > 0 else 0

    stats = [
        (f"{attempts:,}", "attempted", WHITE),
        (f"{passed:,}", "passed", GREEN),
        (f"{pct}%", "pass rate", GREEN),
    ]

    block_w = right_w // 3
    max_num_w = int(block_w * 0.80)  # numbers must fit within 80% of their column

    # Auto-fit stat font so the widest number stays within its column
    fitted_stat_size = stat_size
    while fitted_stat_size > 12:
        f_test = _font(fitted_stat_size, bold=True)
        widest = max(draw.textbbox((0, 0), s[0], font=f_test)[2] for s in stats)
        if widest <= max_num_w:
            break
        fitted_stat_size = int(fitted_stat_size * 0.90)
    stat_f = _font(fitted_stat_size, bold=True)
    stat_size = fitted_stat_size

    # Center the number+label block vertically in the card
    v_gap_stat = max(4, int(card_h * 0.03))
    stat_block_h = stat_size + v_gap_stat + label_size
    num_y = y1 + (card_h - stat_block_h) // 2
    label_y = num_y + stat_size + v_gap_stat

    # Arrow vertically centered with numbers
    arrow_size = max(14, int(card_h * 0.11))
    arrow_y = num_y + (stat_size - arrow_size) // 2

    centers = [right_x + block_w // 2, right_x + block_w + block_w // 2, right_x + 2 * block_w + block_w // 2]

    for i, (cx, (num, lbl, color)) in enumerate(zip(centers, stats)):
        bbox = draw.textbbox((0, 0), num, font=stat_f)
        draw.text((cx - (bbox[2] - bbox[0]) // 2, num_y), num, font=stat_f, fill=color)

        bbox = draw.textbbox((0, 0), lbl, font=label_f)
        draw.text((cx - (bbox[2] - bbox[0]) // 2, label_y), lbl, font=label_f, fill=GRAY)

        if i < 2:
            arr_cx = (centers[i] + centers[i + 1]) // 2
            bbox = draw.textbbox((0, 0), "→", font=arrow_f)
            draw.text((arr_cx - (bbox[2] - bbox[0]) // 2, arrow_y), "→", font=arrow_f, fill=GRAY)


def generate(challenge_cards, out_name=None):
    """
    challenge_cards: list of dicts with keys: base_slug, name, price, funded, attempts, passed
    Returns path to generated image, or None if no cards.
    """
    n = min(len(challenge_cards), 3)
    if n == 0:
        return None

    template_path = IMAGES_DIR / TEMPLATES[n]
    out_path = IMAGES_DIR / (out_name or OUTPUTS[n])

    img = Image.open(template_path).convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    for i, card in enumerate(challenge_cards[:n]):
        y_lo, y_hi = CARD_Y[n][i]
        box = (int(W * CARD_X[0]), int(H * y_lo), int(W * CARD_X[1]), int(H * y_hi))
        _draw_card(draw, img, card, box)

    bg = Image.new("RGB", img.size, (0, 0, 0))
    bg.paste(img, mask=img.split()[3])
    bg.save(str(out_path))
    return str(out_path)
