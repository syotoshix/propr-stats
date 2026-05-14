from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGES_DIR = Path(__file__).parent.parent / "images"
FONTS_DIR  = Path(__file__).parent.parent / "fonts"

TEMPLATES = {
    "revenue": "milestones/revenue_milestone_template.png",
    "traders": "milestones/traders_milestone_template.png",
    "capital": "milestones/funded_milestone_template.png",
}

OUTPUTS = {
    "revenue": "milestones/revenue_milestone_generated.png",
    "traders": "milestones/traders_milestone_generated.png",
    "capital": "milestones/funded_milestone_generated.png",
}

GRAD_TOP    = (6, 182, 212)   # cyan
GRAD_BOTTOM = (34, 197, 94)   # green


def _font(size, bold=True):
    name = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), max(8, size))


def _fit_font(draw, text, max_width, start_size):
    size = start_size
    while size > 12:
        f = _font(size)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
        size = int(size * 0.9)
    return _font(12)


def _detect_text_top(img, search_from=0.4):
    """Find the topmost row with significant bright pixels in the center band."""
    gray = img.convert("L")
    W, H = gray.size
    cx1, cx2 = int(W * 0.3), int(W * 0.7)
    for y in range(int(H * search_from), H):
        row = [gray.getpixel((x, y)) for x in range(cx1, cx2)]
        if max(row) > 200 and sum(1 for p in row if p > 200) > 10:
            return y
    return int(H * 0.55)


def _make_gradient(w, h):
    grad = Image.new("RGBA", (w, h))
    pixels = grad.load()
    for y in range(h):
        for x in range(w):
            t = (x / max(w - 1, 1) + y / max(h - 1, 1)) / 2
            r = int(GRAD_TOP[0] * (1 - t) + GRAD_BOTTOM[0] * t)
            g = int(GRAD_TOP[1] * (1 - t) + GRAD_BOTTOM[1] * t)
            b = int(GRAD_TOP[2] * (1 - t) + GRAD_BOTTOM[2] * t)
            pixels[x, y] = (r, g, b, 255)
    return grad


def _draw_gradient_text(img, text, font, cx, cy):
    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bx0, by0, bx1, by1 = tmp_draw.textbbox((0, 0), text, font=font)
    tw, th = bx1 - bx0, by1 - by0
    if tw <= 0 or th <= 0:
        return
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).text((-bx0, -by0), text, font=font, fill=255)
    grad = _make_gradient(tw, th)
    grad.putalpha(mask)
    img.alpha_composite(grad, (cx - tw // 2 + bx0, cy - th // 2 + by0))


def format_amount(value, milestone_type):
    if milestone_type == "traders":
        return f"{value:,}+"
    if value >= 1_000_000:
        m = value / 1_000_000
        s = f"${m:.1f}M" if m != int(m) else f"${int(m)}M"
    else:
        s = f"${value // 1_000}K"
    return s + ("+" if milestone_type == "capital" else "")


def generate(milestone_type, value):
    template_path = IMAGES_DIR / TEMPLATES[milestone_type]
    output_path   = IMAGES_DIR / OUTPUTS[milestone_type]

    img = Image.open(template_path).convert("RGBA")
    W, H = img.size

    text_top = _detect_text_top(img)
    padding  = int(H * 0.07)

    text   = format_amount(value, milestone_type)
    max_w  = int(W * 0.70)
    draw   = ImageDraw.Draw(img)
    font   = _fit_font(draw, text, max_w, int(H * 0.18))

    bx0, by0, bx1, by1 = draw.textbbox((0, 0), text, font=font)
    th = by1 - by0
    cy = text_top - padding - th // 2

    _draw_gradient_text(img, text, font, W // 2, cy)

    bg = Image.new("RGB", img.size, (0, 0, 0))
    bg.paste(img, mask=img.split()[3])
    bg.save(str(output_path))
    return str(output_path)
