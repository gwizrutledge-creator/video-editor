"""Draw the episode title card: python3 scripts/make_card.py <out.png> <W> <H> <line1> <line2>.

Black background, line 1 in brand gold with wide tracking, a thin gold rule, line 2 in white.
"""
import sys

from PIL import Image, ImageDraw, ImageFont

GOLD, WHITE, BG = (242, 177, 60), (255, 255, 255), (8, 8, 8)
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-{}.otf"


def tracked(draw, y, text, font, fill, W, track):
    widths = [draw.textlength(c, font=font) for c in text]
    total = sum(widths) + track * (len(text) - 1)
    x = (W - total) / 2
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += w + track


def main() -> None:
    out, W, H, l1, l2 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
    s = W / 1920
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FONT.format("Black"), round(84 * s))
    f2 = ImageFont.truetype(FONT.format("SemiBold"), round(40 * s))
    tracked(d, H / 2 - 110 * s, l1, f1, GOLD, W, round(10 * s))
    d.rectangle([W / 2 - 60 * s, H / 2 + 8 * s, W / 2 + 60 * s, H / 2 + 11 * s], fill=GOLD)
    tracked(d, H / 2 + 42 * s, l2, f2, WHITE, W, round(6 * s))
    img.save(out)


if __name__ == "__main__":
    main()
