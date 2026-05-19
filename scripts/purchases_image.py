from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import sys

sys.path.insert(0, str(Path(__file__).parent))
from milestone_image import _make_gradient, _draw_gradient_text

IMAGES_DIR = Path(__file__).parent.parent / "images"
FONTS_DIR   = Path(__file__).parent.parent / "fonts"

TEMPLATE = "purchases/challenge-purchases-template.png"
OUTPUT   = "purchases/challenge-purchases-generated.png"

# 3200x1800 layout
CARD_CXS        = [447, 1023, 1600, 2151, 2751]
CHALLENGE_ORDER = ["Starter", "Explorer", "Bronze", "Silver", "Gold"]

TOTAL_CY  = 480   # gradient total header
COUNT_CY  = 1186  # between card name (bottom ~1104) and divider (1268)
DOLLAR_CY = 1420  # below divider
POINTS_CY = 1565  # near card bottom

WHITE = (255, 255, 255)
GREEN_PILL = (34, 197, 94, 255)


def _font(size, bold=True):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), size)


def _center_text(draw, text, font, cx, cy, fill):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2), text, font=font, fill=fill)


def _draw_pill(img, text, cx, cy, font):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb  = tmp.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = 30, 15

    rx0, ry0 = cx - tw // 2 - pad_x, cy - th // 2 - pad_y
    rx1, ry1 = cx + tw // 2 + pad_x, cy + th // 2 + pad_y

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle([rx0, ry0, rx1, ry1], radius=22, fill=GREEN_PILL)
    img.alpha_composite(overlay)

    ImageDraw.Draw(img).text(
        (cx - tw // 2 - bb[0], cy - th // 2 - bb[1]),
        text, font=font, fill=WHITE,
    )


def generate(challenge_data, total_usdc, out_path=None):
    """
    challenge_data: {"Starter": {"count": 3, "revenue": 180.0}, ...}
    Returns output file path.
    """
    img  = Image.open(IMAGES_DIR / TEMPLATE).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Gradient total header
    total_font = _font(200)
    total_text = f"${total_usdc:,.2f} USDC"
    _draw_gradient_text(img, total_text, total_font, 1600, TOTAL_CY)
    draw = ImageDraw.Draw(img)

    count_font  = _font(130)
    dollar_font = _font(100)
    pts_font    = _font(68)

    for cx, name in zip(CARD_CXS, CHALLENGE_ORDER):
        data    = challenge_data.get(name, {"count": 0, "revenue": 0.0})
        count   = data["count"]
        revenue = data["revenue"]

        _center_text(draw, f"{count}x", count_font, cx, COUNT_CY, WHITE)

        if count > 0:
            # Dollar amount (show cents only if non-integer)
            if revenue == int(revenue):
                dollar_text = f"${int(revenue):,}"
            else:
                dollar_text = f"${revenue:,.2f}"
            _center_text(draw, dollar_text, dollar_font, cx, DOLLAR_CY, WHITE)

            # Points pill
            pts = int(revenue * 10)
            _draw_pill(img, f"+{pts:,} PTS", cx, POINTS_CY, pts_font)
            draw = ImageDraw.Draw(img)

    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(img, mask=img.split()[3])
    if out_path is None:
        out_path = IMAGES_DIR / OUTPUT
    out.save(str(out_path))
    return str(out_path)
