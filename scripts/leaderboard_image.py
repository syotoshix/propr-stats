from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

FONTS_DIR = Path(__file__).parent.parent / "fonts"
IMAGES_DIR = Path(__file__).parent.parent / "images"

# 3200x1800 layout
IMG_W, IMG_H = 3200, 1800
CONTENT_Y_START = 450
CONTENT_Y_END = 1645
ROWS = 5
ROW_H = (CONTENT_Y_END - CONTENT_Y_START) // ROWS  # 275px per row

COL_X = [400, 2000]   # left and right column x start
RANK_NUM_W = 155       # space reserved for rank number glyph

RANK_FONT_SIZE = 95
NAME_FONT_SIZE = 62
PNL_FONT_SIZE = 54

# Rank number colours
RANK_COLORS = {
    1: (255, 196, 0),    # gold
    2: (192, 192, 192),  # silver
    3: (255, 120, 0),    # bronze/orange
}
DEFAULT_RANK_COLOR = (140, 140, 140)

WHITE = (255, 255, 255)
PNL_POSITIVE = (16, 185, 129)   # emerald green
PNL_NEGATIVE = (239, 68, 68)    # red


def _font(size, bold=False):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), size)


def _draw_entry(draw, entry, col_x, row_y, fonts):
    rank_font, name_font_bold, name_font_reg, pnl_font_bold, pnl_font_reg = fonts
    rank = entry["rank"]

    # --- rank number ---
    rank_color = RANK_COLORS.get(rank, DEFAULT_RANK_COLOR)
    draw.text((col_x, row_y + 30), str(rank), font=rank_font, fill=rank_color)

    text_x = col_x + RANK_NUM_W

    # --- username (bold for top 3) ---
    nf = name_font_bold if rank <= 3 else name_font_reg
    draw.text((text_x, row_y + 38), entry["username"], font=nf, fill=WHITE)

    # --- pnl line (bold for top 3) ---
    pnl = entry["pnl"]
    pct = entry["pct"]
    sign = "+" if pnl >= 0 else ""
    pnl_text = f"{sign}${pnl:,.2f}  ({sign}{pct:.2f}%)"
    pnl_color = PNL_POSITIVE if pnl >= 0 else PNL_NEGATIVE
    pf = pnl_font_bold if rank <= 3 else pnl_font_reg
    draw.text((text_x, row_y + 118), pnl_text, font=pf, fill=pnl_color)


# All-Time Leaderboard template layout (1080x1200)
_AT_CONTENT_X0 = 215
_AT_CONTENT_X1 = 1070
_AT_CONTENT_CX = (_AT_CONTENT_X0 + _AT_CONTENT_X1) // 2
_AT_ROWS = [{"rank": 1, "cy": 601}, {"rank": 2, "cy": 803}, {"rank": 3, "cy": 1005}]
_AT_LINE_GAP = 10
_AT_PNL_COLOR = (74, 222, 128)    # bright green
_AT_BG_COLOR  = (0, 0, 0, 160)   # semi-transparent black pill behind pnl


def generate_alltime(entries, out_name="alltime_leaderboard_generated.png"):
    """Render top-3 onto All_Time_Leaderboard.png template."""
    img = Image.open(IMAGES_DIR / "All_Time_Leaderboard.png").convert("RGBA")
    draw = ImageDraw.Draw(img)

    name_font = _font(54, bold=True)
    pnl_font  = _font(38, bold=True)

    entry_map = {e["rank"]: e for e in entries}

    # First pass: collect layout so we can composite the bg overlay before drawing text
    layouts = []
    for row in _AT_ROWS:
        entry = entry_map.get(row["rank"])
        if entry is None:
            continue

        pnl = entry["pnl"]
        pct = entry["pct"]
        sign = "+" if pnl >= 0 else "-"
        username = entry["username"]
        pnl_text = f"{sign}${abs(pnl):,.0f}  ({sign}{abs(pct):.2f}%)"

        nb = draw.textbbox((0, 0), username, font=name_font)
        pb = draw.textbbox((0, 0), pnl_text, font=pnl_font)
        nh = nb[3] - nb[1]
        total_h = nh + _AT_LINE_GAP + (pb[3] - pb[1])
        block_top = row["cy"] - total_h // 2

        name_draw = (_AT_CONTENT_CX - (nb[2] - nb[0]) // 2 - nb[0], block_top - nb[1])
        pnl_draw  = (_AT_CONTENT_CX - (pb[2] - pb[0]) // 2 - pb[0], block_top + nh + _AT_LINE_GAP - pb[1])
        layouts.append((username, pnl_text, name_draw, pnl_draw, nb, pb))

    # Draw semi-transparent black pills behind pnl text only
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ovl_draw = ImageDraw.Draw(overlay)
    pad_x, pad_y = 24, 8
    for _, _, _, (px, py), nb, pb in layouts:
        rx0, ry0 = px + pb[0] - pad_x, py + pb[1] - pad_y
        rx1, ry1 = px + pb[2] + pad_x, py + pb[3] + pad_y
        ovl_draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=10, fill=_AT_BG_COLOR)
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw text on top
    for username, pnl_text, name_draw, pnl_draw, _, __ in layouts:
        draw.text(name_draw, username, font=name_font, fill=WHITE)
        draw.text(pnl_draw,  pnl_text, font=pnl_font,  fill=_AT_PNL_COLOR)

    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(img, mask=img.split()[3])
    out_path = IMAGES_DIR / out_name
    out.save(out_path, "PNG")
    return out_path


def generate(entries, template_name="daily_leaderboard_template.png", out_name="daily_leaderboard_generated.png"):
    """
    entries: list of dicts — rank, username, pnl (float), pct (float)
    Returns the output file path.
    """
    template_path = IMAGES_DIR / template_name
    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    fonts = (
        _font(RANK_FONT_SIZE, bold=True),
        _font(NAME_FONT_SIZE, bold=True),
        _font(NAME_FONT_SIZE, bold=False),
        _font(PNL_FONT_SIZE, bold=True),
        _font(PNL_FONT_SIZE, bold=False),
    )

    for entry in entries:
        rank = entry["rank"]
        col = 0 if rank <= 5 else 1
        row = (rank - 1) % 5
        col_x = COL_X[col]
        row_y = CONTENT_Y_START + row * ROW_H
        _draw_entry(draw, entry, col_x, row_y, fonts)

    # Flatten RGBA onto black background
    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(img, mask=img.split()[3])

    out_path = IMAGES_DIR / out_name
    out.save(out_path, "PNG")
    return out_path
