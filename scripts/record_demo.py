"""Record docs/demo.gif from the real running app (python server.py must be up).

Draws a robot stroke by stroke with the mouse, waits for the live preview, presses
Make 3D, then turns the viewer through one full turn. The 3D wait is shortened in the
GIF; everything else plays at roughly real speed.

    pip install playwright && python -m playwright install chromium
    python scripts/record_demo.py [--url http://127.0.0.1:7861] [--out docs/demo.gif]
"""

import argparse
import io
import math
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORT = {"width": 1400, "height": 640}
GIF_WIDTH = 960
PROMPT = "a cute toy robot"
SEED = 1056993011

# Polylines in canvas pixels (the canvas is 1024x1024).
def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def circle(cx, cy, r, n=16):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


STROKES = [
    rect(392, 180, 240, 190),                  # head
    [(512, 180), (512, 124)], circle(512, 110, 14),  # antenna
    circle(462, 260, 26), circle(562, 260, 26),  # eyes
    [(462, 320), (562, 320)],                  # mouth
    rect(352, 390, 320, 300),                  # body
    rect(452, 450, 120, 90),                   # chest panel
    [(352, 420), (262, 560)], [(672, 420), (762, 560)],  # arms
    rect(392, 690, 80, 150), rect(552, 690, 80, 150),    # legs
]


class Recorder:
    def __init__(self, page, clip):
        self.page, self.clip, self.frames = page, clip, []

    def snap(self, ms):
        png = self.page.screenshot(clip=self.clip)
        self.frames.append((Image.open(io.BytesIO(png)).convert("RGB"), ms))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7861")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo.gif"))
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page.goto(args.url)
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_function("document.getElementById('status').textContent === 'ready' || document.getElementById('output').src")
        page.fill("#prompt", PROMPT)
        page.fill("#seed", str(SEED))
        page.dispatch_event("#seed", "change")
        page.fill("#size", "10")

        main_box = page.locator("main").bounding_box()
        clip = {"x": 0, "y": 0, "width": VIEWPORT["width"], "height": main_box["y"] + main_box["height"]}
        rec = Recorder(page, clip)
        stage = page.locator("#sketch-stage").bounding_box()
        to_page = lambda x, y: (stage["x"] + x * stage["width"] / 1024, stage["y"] + y * stage["height"] / 1024)

        rec.snap(800)
        for stroke in STROKES:
            page.mouse.move(*to_page(*stroke[0]))
            page.mouse.down()
            for (x0, y0), (x1, y1) in zip(stroke, stroke[1:]):
                steps = max(2, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 40))
                page.mouse.move(*to_page(x1, y1), steps=steps)
            page.mouse.up()
            time.sleep(0.15)  # let the live preview catch up so each frame shows it
            rec.snap(180)
        time.sleep(1.0)
        rec.snap(1500)

        page.click("#make3d")
        started = time.perf_counter()
        while page.is_disabled("#make3d"):
            time.sleep(1.5)
            rec.snap(220)  # sped up: ~1.5s of real waiting per 0.22s of GIF
        print(f"3D took {time.perf_counter() - started:.1f}s")
        page.mouse.move(-10, -10)  # park the cursor off the viewer
        time.sleep(0.6)
        rec.snap(900)

        # One exact turn. (A simulated mouse drag overshoots: OrbitControls damping runs per rendered
        # frame, and frames are slow in a software-GL headless browser.)
        turn_frames = 48
        for i in range(1, turn_frames + 1):
            page.evaluate(f"viewer.orbitTo({2 * math.pi * i / turn_frames})")
            time.sleep(0.05)  # let the render loop draw the new view
            rec.snap(70)
        rec.frames[-1] = (rec.frames[-1][0], 2000)
        browser.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rec.frames[-1][0].save(out.with_name("screenshot.png"))
    scale = GIF_WIDTH / rec.frames[0][0].width
    size = (GIF_WIDTH, round(rec.frames[0][0].height * scale))
    # One shared palette keeps the UI chrome from flickering between frames.
    imgs = [f.resize(size, Image.LANCZOS) for f, _ in rec.frames]
    palette = imgs[-1].quantize(colors=255, method=Image.MEDIANCUT)
    imgs = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in imgs]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=[ms for _, ms in rec.frames],
                 loop=0, optimize=True, disposal=1)
    print(f"{out}: {len(imgs)} frames, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
