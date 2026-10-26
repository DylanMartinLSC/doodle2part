"""Draw a rough, slightly wobbly test sketch: a mounting plate with dimension labels."""

import random
import sys

from PIL import Image, ImageDraw, ImageFont

random.seed(7)


def wobbly_line(draw, a, b, width=4):
    # Split the segment and jitter the midpoints so it looks hand-drawn.
    pts = [a]
    for i in range(1, 8):
        t = i / 8
        pts.append((a[0] + (b[0] - a[0]) * t + random.uniform(-2, 2), a[1] + (b[1] - a[1]) * t + random.uniform(-2, 2)))
    pts.append(b)
    draw.line(pts, fill="black", width=width, joint="curve")


def wobbly_circle(draw, c, r):
    draw.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline="black", width=4)


img = Image.new("RGB", (768, 768), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("arial.ttf", 30)
except OSError:
    font = ImageFont.load_default()

# Plate outline (top view), 120 x 80 mm drawn at 4 px/mm.
x0, y0, x1, y1 = 144, 224, 624, 544
for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
    wobbly_line(d, a, b)
# Four corner holes and a big center hole.
for cx, cy in [(x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x0 + 40, y1 - 40), (x1 - 40, y1 - 40)]:
    wobbly_circle(d, (cx, cy), 14)
wobbly_circle(d, ((x0 + x1) // 2, (y0 + y1) // 2), 60)

# Dimension lines and labels.
wobbly_line(d, (x0, y0 - 40), (x1, y0 - 40), 2)
d.text(((x0 + x1) // 2 - 40, y0 - 85), "120 mm", fill="black", font=font)
wobbly_line(d, (x1 + 40, y0), (x1 + 40, y1), 2)
d.text((x1 + 50, (y0 + y1) // 2 - 15), "80", fill="black", font=font)
d.text((x0, y1 + 30), "plate, 6 mm thick", fill="black", font=font)
d.text((x0, y1 + 70), "4x M6 holes, 30 mm center hole", fill="black", font=font)

img.save(sys.argv[1] if len(sys.argv) > 1 else "sketch_plate.png")
