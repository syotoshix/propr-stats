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
