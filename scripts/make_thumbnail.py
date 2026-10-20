"""Compose the YouTube thumbnail (1280x720) from a real frame cutout.

Usage: python3 scripts/make_thumbnail.py <cutout.png> <out.png> "<white line>|<white line>|<gold line>"
The cutout (RGBA, from rembg) is cropped above the StreamYard name bar, scaled up, sharpened
and set on charcoal with a soft warm glow; the text stacks on the left with a drop shadow.
"""
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
GOLD, WHITE, BG = (242, 177, 60), (255, 255, 255), (14, 14, 14)
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
CROP = (100, 20, 620, 440)   # head, hands and shoulders; above the name bar
SCALE, X, Y = 1.75, 470, 0


def main() -> None:
    cut = Image.open(sys.argv[1]).convert("RGBA").crop(CROP)
    cut = cut.resize((round(cut.width * SCALE), round(cut.height * SCALE)), Image.LANCZOS)
    rgb = cut.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    alpha = cut.getchannel("A").filter(ImageFilter.GaussianBlur(1.6))  # soften the matte edge
    cut = Image.merge("RGBA", (*rgb.split(), alpha))

    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([X + 120, Y - 40, X + 860, Y + 700], fill=52)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img.paste(Image.new("RGB", (W, H), GOLD), (0, 0), glow)
    img.paste(cut, (X, Y), cut)

    lines = sys.argv[3].split("|")
    font = ImageFont.truetype(FONT, 132)
    lh = 128
    y0 = (H - lh * len(lines)) // 2 - 10
    shadow = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shadow)
    for i, line in enumerate(lines):
        sd.text((58 + 6, y0 + i * lh + 8), line, font=font, fill=230)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((58, y0 + i * lh), line, font=font, fill=GOLD if i == len(lines) - 1 else WHITE)
    yb = y0 + lh * len(lines) + 18
    d.rectangle([62, yb, 62 + 150, yb + 9], fill=GOLD)
    img.save(sys.argv[2])


if __name__ == "__main__":
    main()
