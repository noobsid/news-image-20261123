#!/usr/bin/env python3
"""Monday 23 November 2026 - the whole world's news on one broadsheet.

A single cream page in the house style of this series: a giant serif
masthead, a strip of the day's key numbers, a region tally, thirteen
painted story panels (three of them heroes), twenty-four one-line
briefs and a DATE CHECK box that owns up to the borderline datings.

Every scene is painted from scratch with PIL on a stage three times
its printed size and then shrunk with a Lanczos filter, so gradients,
shaded masonry, smoke and glow stay smooth. A seeded random source
per panel makes the finished entry.png byte-identical on every run.
This script is a build tool only; the entry program (main.py) ships
the finished entry.png untouched.
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

SIDE = 1024                     # the page is square
MARGIN = 36                     # cream edge around the page
BODY_W = SIDE - 2 * MARGIN      # printable width
ZOOM = 3                        # scene supersampling factor
SEED = 20261123

PAPER = (247, 242, 225)
PAPER_DK = (238, 230, 204)
INK = (24, 21, 18)
FADED = (99, 92, 77)
RED = (173, 31, 45)
BLUE = (31, 77, 139)
TEAL = (14, 113, 109)
GOLD = (173, 119, 21)
GREEN = (49, 109, 57)
PURPLE = (99, 65, 139)
WHITE = (255, 255, 255)
LITWIN = (255, 209, 124)

REGION_COLOUR = {
    "EUROPE": RED, "ASIA": GOLD, "AMERICAS": BLUE,
    "MIDDLE EAST": TEAL, "AFRICA": GREEN, "OCEANIA": PURPLE,
}

FONTS = "/usr/share/fonts/truetype/liberation/"
F_SERIF = FONTS + "LiberationSerif-Bold.ttf"
F_SERIF_IT = FONTS + "LiberationSerif-BoldItalic.ttf"
F_SANS = FONTS + "LiberationSans-Regular.ttf"
F_SANS_B = FONTS + "LiberationSans-Bold.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(d, text, fnt, width):
    """Break text into lines that fit `width`, newspaper style."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def one_line(d, text, fnt, width):
    """Fit text on a single line, ellipsising from the end if needed."""
    if d.textlength(text, font=fnt) <= width:
        return text
    while text and d.textlength(text + "…", font=fnt) > width:
        text = text.rsplit(" ", 1)[0] if " " in text else text[:-1]
    return text + "…"


def para(d, text, x, y, width, fnt, fill, leading, max_lines):
    """Draw a wrapped paragraph; return the y below its last line."""
    for line in wrap(d, text, fnt, width)[:max_lines]:
        d.text((x, y), line, font=fnt, fill=fill)
        y += leading
    return y


# ------------------------------------------------------------ colour work
def blend(a, b, t):
    """Interpolate between two RGB tuples."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def shade(col, f):
    """Multiply a colour's brightness by f."""
    return tuple(max(0, min(255, int(round(c * f)))) for c in col)


def quad(p0, p1, p2, n=24):
    """Points along a quadratic Bezier curve."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return pts


# -------------------------------------------------------------- the stage
class Panel:
    """A story scene painted at ZOOM times its printed size.

    Opaque painting lands on the base image; smoke, glow and haze are
    kept on a transparent overlay composited at the end, so soft
    effects never muddy the line work underneath.
    """

    def __init__(self, w, h, rng):
        self.w, self.h, self.rng = w, h, rng
        self.base = Image.new("RGB", (w * ZOOM, h * ZOOM), WHITE)
        self.d = ImageDraw.Draw(self.base)
        self.haze = Image.new("RGBA", (w * ZOOM, h * ZOOM), (0, 0, 0, 0))
        self.hd = ImageDraw.Draw(self.haze)

    def _b(self, box):
        return [v * ZOOM for v in box]

    def _p(self, pts):
        return [(x * ZOOM, y * ZOOM) for x, y in pts]

    def rect(self, box, fill=None, outline=None, width=1):
        self.d.rectangle(self._b(box), fill=fill, outline=outline,
                         width=max(1, int(width * ZOOM)))

    def poly(self, pts, fill, outline=None):
        self.d.polygon(self._p(pts), fill=fill, outline=outline)

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._b(box), fill=fill, outline=outline,
                       width=max(1, int(width * ZOOM)))

    def disc(self, cx, cy, r, fill):
        self.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line(self._p(pts), fill=fill,
                    width=max(1, int(width * ZOOM)), joint="curve")

    def arc(self, box, a0, a1, fill, width=1):
        self.d.arc(self._b(box), a0, a1, fill=fill,
                   width=max(1, int(width * ZOOM)))

    def text(self, xy, s, fnt, fill, anchor=None):
        self.d.text((xy[0] * ZOOM, xy[1] * ZOOM), s, font=fnt, fill=fill,
                    anchor=anchor)

    def h_disc(self, cx, cy, r, rgba):
        self.hd.ellipse(self._b([cx - r, cy - r, cx + r, cy + r]), fill=rgba)

    def h_poly(self, pts, rgba):
        self.hd.polygon(self._p(pts), fill=rgba)

    def h_line(self, pts, rgba, width=1):
        self.hd.line(self._p(pts), fill=rgba,
                     width=max(1, int(width * ZOOM)), joint="curve")

    def vgrad(self, top, bottom, y0=0.0, y1=1.0):
        """Vertical gradient between two heights (fractions of height)."""
        a, b = int(self.h * ZOOM * y0), int(self.h * ZOOM * y1)
        for i in range(a, b):
            t = (i - a) / max(1, b - a - 1)
            self.d.line([0, i, self.w * ZOOM, i], fill=blend(top, bottom, t))

    def glow(self, cx, cy, r, col, alpha):
        """A soft halo built from nested translucent discs."""
        for i in range(7, 0, -1):
            rr = r * i / 7
            a = int(alpha * (1 - i / 8) ** 1.5) + 4
            self.h_disc(cx, cy, rr, col + (a,))

    def plume(self, cx, cy, n, drift, climb, col, alpha, r0=3.0):
        """Smoke: a chain of growing puffs leaning with the wind."""
        x, y, r = cx, cy, r0
        for _ in range(n):
            self.h_disc(x, y, r, col + (alpha,))
            x += self.rng.uniform(-drift, drift) + drift * 0.6
            y -= climb
            r += r0 * 0.5

    def cloudbank(self, cx, cy, w, col, alpha):
        """A lumpy cloud from overlapping discs over a flat base."""
        for dx, rr in ((-0.31, 0.30), (-0.11, 0.44), (0.13, 0.39),
                       (0.33, 0.27)):
            self.h_disc(cx + dx * w, cy, rr * w * 0.36, col + (alpha,))
        self.hd.ellipse(self._b([cx - 0.43 * w, cy - 4, cx + 0.45 * w,
                                 cy + 5]), fill=col + (alpha,))

    def window_grid(self, x, y, w, h, cols, rows, lit_ratio, dark):
        """Windows on a facade; a seeded share of them glow warm."""
        cw, ch = w / cols, h / rows
        for i in range(cols):
            for j in range(rows):
                wx = x + i * cw + cw * 0.25
                wy = y + j * ch + ch * 0.27
                col = LITWIN if self.rng.random() < lit_ratio else dark
                self.rect([wx, wy, wx + cw * 0.5, wy + ch * 0.46], fill=col)

    def tower_block(self, x, y, w, h, body, lit_ratio=0.42):
        """An apartment tower: parapet, shaded east face, lit windows."""
        self.rect([x, y, x + w, y + h], fill=body)
        self.rect([x + w * 0.74, y, x + w, y + h], fill=shade(body, 0.76))
        self.rect([x, y, x + w, y + 2.4], fill=shade(body, 1.2))
        cols = max(2, int(w / 8.5))
        rows = max(2, int(h / 9.5))
        self.window_grid(x + 2, y + 4.5, w - 4, h - 6.5, cols, rows,
                         lit_ratio, shade(body, 0.52))

    def glints(self, y0, y1, n, col, alpha):
        """Short bright dashes scattered over water."""
        for _ in range(n):
            x = self.rng.uniform(2, self.w - 8)
            y = self.rng.uniform(y0, y1)
            ln = self.rng.uniform(2.5, 6.5)
            self.h_line([(x, y), (x + ln, y)], col + (alpha,), width=0.8)

    def finish(self):
        out = self.base.convert("RGBA")
        out.alpha_composite(self.haze)
        return out.convert("RGB").resize((self.w, self.h), Image.LANCZOS)


# ------------------------------------------------------------ hero scenes
def art_chip(w, h, ink, rng):
    """Santa Clara at dawn: the Nvidia fab behind a giant glowing AI
    chip on a test bench, its circuit traces running out to a green
    share-price line that climbs off the top of the frame."""
    s = Panel(w, h, rng)
    s.vgrad((18, 26, 54), (86, 84, 110), 0.0, 0.66)
    s.vgrad((40, 40, 50), (24, 24, 32), 0.66, 1.0)
    s.glow(w * 0.86, h * 0.14, 12, (255, 214, 140), 80)
    s.disc(w * 0.86, h * 0.14, 5.0, (255, 220, 150))       # low sun
    # the fab: two long cleanroom sheds with clerestory glass
    for fx, fw, fh, tone_ in ((0.02, 0.30, 0.40, (70, 76, 96)),
                              (0.66, 0.32, 0.46, (62, 68, 90))):
        s.rect([w * fx, h * (0.66 - fh), w * (fx + fw), h * 0.66], fill=tone_)
        s.rect([w * fx, h * (0.66 - fh), w * (fx + fw), h * (0.66 - fh) + 3],
               fill=shade(tone_, 1.25))
        s.window_grid(w * fx + 3, h * (0.66 - fh) + 6, w * fw - 6,
                      h * fh - 12, 5, 3, 0.55, shade(tone_, 0.5))
        s.rect([w * fx + w * fw * 0.4, h * (0.66 - fh) - 5,
                w * fx + w * fw * 0.6, h * (0.66 - fh)], fill=shade(tone_, 1.1))
    # cooling towers with a breath of steam
    for tx in (w * 0.40, w * 0.475):
        s.poly([(tx - 7, h * 0.66), (tx - 4.5, h * 0.40), (tx + 4.5, h * 0.40),
                (tx + 7, h * 0.66)], fill=(88, 92, 106))
        s.ellipse([tx - 4.5, h * 0.385, tx + 4.5, h * 0.415],
                  fill=(120, 124, 138))
        s.plume(tx, h * 0.36, 4, 2.0, 3.6, (210, 212, 220), 60, r0=2.4)
    # the chip itself, centre stage on its bench
    cx, cy, cs = w * 0.50, h * 0.70, h * 0.34
    s.rect([w * 0.16, h * 0.90, w * 0.84, h * 0.90 + 3], fill=(16, 16, 22))
    for i in range(9):                                    # pins, both sides
        px = cx - cs / 2 + 6 + i * (cs - 12) / 8
        s.rect([px - 1.6, cy - cs / 2 - 5, px + 1.6, cy - cs / 2], fill=(196, 198, 204))
        s.rect([px - 1.6, cy + cs / 2, px + 1.6, cy + cs / 2 + 5], fill=(196, 198, 204))
        py = cy - cs / 2 + 6 + i * (cs - 12) / 8
        s.rect([cx - cs / 2 - 5, py - 1.6, cx - cs / 2, py + 1.6], fill=(196, 198, 204))
        s.rect([cx + cs / 2, py - 1.6, cx + cs / 2 + 5, py + 1.6], fill=(196, 198, 204))
    s.glow(cx, cy, cs * 0.85, (118, 200, 90), 120)
    s.rect([cx - cs / 2, cy - cs / 2, cx + cs / 2, cy + cs / 2],
           fill=(30, 44, 30), outline=(150, 220, 120), width=1.6)
    s.rect([cx - cs * 0.30, cy - cs * 0.30, cx + cs * 0.30, cy + cs * 0.30],
           fill=(46, 66, 44), outline=(170, 235, 140), width=1.2)
    for k in range(5):                                    # die traces
        off = -cs * 0.22 + k * cs * 0.11
        s.line([(cx + off, cy - cs * 0.30), (cx + off, cy + cs * 0.30)],
               fill=(120, 190, 100), width=0.8)
    s.text((cx, cy), "AI", font(F_SANS_B, int(13 * ZOOM)), (214, 246, 190),
           anchor="mm")
    # circuit traces running off the bench to the chart line
    for sx, sy in ((cx - cs / 2 - 5, cy + 6), (cx + cs / 2 + 5, cy - 8)):
        s.line([(sx, sy), (sx + (14 if sx > cx else -14), sy + 8)],
               fill=(130, 200, 110), width=1.0)
        s.disc(sx + (14 if sx > cx else -14), sy + 8, 1.6, (170, 235, 140))
    # the share line: flat, a dip on the resignation, then the leap
    pts = [(w * 0.04, h * 0.60), (w * 0.20, h * 0.585), (w * 0.30, h * 0.66),
           (w * 0.38, h * 0.63), (w * 0.55, h * 0.44), (w * 0.72, h * 0.30),
           (w * 0.90, h * 0.10), (w * 0.975, h * 0.045)]
    for i in range(len(pts) - 1):
        s.h_line([pts[i], pts[i + 1]], (120, 235, 130, 210), width=2.2)
    for px, py in pts[3:]:
        s.disc(px, py, 1.7, (190, 255, 180))
    ax, ay = pts[-1]
    s.poly([(ax - 1, ay + 6), (ax + 6, ay - 2), (ax - 3, ay - 3)],
           fill=(150, 245, 150))
    s.text((w * 0.05, h * 0.06), "+33%", font(F_SERIF, int(14 * ZOOM)),
           (170, 245, 160))
    return s.finish()


def art_corvette(w, h, ink, rng):
    """Benghazi harbour at dusk: the corvette Merkury riding at anchor
    under the cranes, seven naval drones converging on it in a fan,
    and the first explosion blooming orange at its stern."""
    s = Panel(w, h, rng)
    s.vgrad((58, 44, 84), (232, 122, 74), 0.0, 0.55)
    s.glow(w * 0.16, h * 0.46, 15, (255, 186, 104), 120)
    s.disc(w * 0.16, h * 0.46, 5.8, (255, 202, 118))
    # Benghazi skyline: minaret, blocks and two harbour cranes
    for bx, bw, bh, tone_ in ((0.0, 0.10, 0.20, (74, 58, 76)),
                              (0.60, 0.12, 0.24, (70, 54, 72)),
                              (0.86, 0.14, 0.19, (76, 60, 78))):
        s.rect([w * bx, h * (0.55 - bh), w * (bx + bw), h * 0.55], fill=tone_)
        s.window_grid(w * bx + 2, h * (0.55 - bh) + 3, w * bw - 4,
                      h * bh - 6, 3, 3, 0.4, shade(tone_, 0.55))
    mx = w * 0.545                                        # minaret
    s.rect([mx - 2.2, h * 0.24, mx + 2.2, h * 0.55], fill=(66, 52, 70))
    s.poly([(mx - 3.4, h * 0.245), (mx + 3.4, h * 0.245), (mx, h * 0.17)],
           fill=(52, 42, 58))
    for gx in (w * 0.24, w * 0.76):                       # gantry cranes
        s.line([(gx, h * 0.55), (gx, h * 0.13)], fill=(38, 34, 44), width=2.2)
        s.line([(gx, h * 0.13), (gx + w * 0.13, h * 0.13)], fill=(38, 34, 44),
               width=1.8)
        s.line([(gx, h * 0.20), (gx + w * 0.115, h * 0.135)], fill=(38, 34, 44),
               width=0.9)
        s.line([(gx + w * 0.10, h * 0.13), (gx + w * 0.10, h * 0.24)],
               fill=(38, 34, 44), width=0.9)
        s.rect([gx + w * 0.10 - 3, h * 0.24, gx + w * 0.10 + 3, h * 0.285],
               fill=(48, 44, 54))
    s.rect([0, h * 0.55, w, h * 0.585], fill=(44, 38, 46))   # quay
    s.vgrad((36, 62, 84), (14, 30, 48), 0.585, 1.0)      # harbour water
    s.glints(h * 0.62, h * 0.96, 26, (255, 178, 110), 110)
    # the corvette, long and grey, riding centre-frame
    hx, hy = w * 0.52, h * 0.635
    s.poly([(hx - w * 0.30, hy), (hx + w * 0.235, hy), (hx + w * 0.315, hy + 5),
            (hx + w * 0.27, hy + 10.5), (hx - w * 0.235, hy + 10.5),
            (hx - w * 0.295, hy + 4)], fill=(96, 102, 112))
    s.rect([hx - w * 0.30, hy - 3.2, hx + w * 0.235, hy], fill=(150, 52, 48))
    s.rect([hx - w * 0.10, hy - 13, hx + w * 0.10, hy - 3.2], fill=(110, 116, 126))
    s.rect([hx + w * 0.005, hy - 21, hx + w * 0.055, hy - 13], fill=(104, 110, 120))
    s.line([(hx + w * 0.03, hy - 21), (hx + w * 0.03, hy - 27)],
           fill=(60, 62, 70), width=1.2)
    s.disc(hx + w * 0.03, hy - 27.5, 1.3, (255, 84, 70))
    s.rect([hx - w * 0.235, hy - 9.5, hx - w * 0.175, hy - 3.2],
           fill=(118, 124, 134))                          # gun turret
    s.line([(hx - w * 0.235, hy - 8), (hx - w * 0.285, hy - 9.5)],
           fill=(70, 74, 82), width=1.6)
    s.window_grid(hx - w * 0.085, hy - 11.5, w * 0.16, 6, 6, 1, 0.7,
                  (70, 76, 88))
    # explosion at the stern and its smoke
    s.glow(hx - w * 0.27, hy - 2, 15, (255, 146, 58), 175)
    s.disc(hx - w * 0.27, hy - 2, 4.6, (255, 196, 96))
    s.plume(hx - w * 0.26, hy - 8, 6, 3.0, 4.6, (40, 36, 40), 130, r0=3.4)
    s.plume(hx - w * 0.05, hy - 16, 4, 2.4, 3.8, (90, 86, 92), 85, r0=2.4)
    # seven naval drones fanning in, wakes behind every one
    drones = [(0.06, 0.86), (0.16, 0.78), (0.13, 0.94), (0.30, 0.845),
              (0.72, 0.83), (0.85, 0.90), (0.90, 0.76)]
    for i, (fx, fy) in enumerate(drones):
        dx, dy = w * fx, h * fy
        flip = 1 if dx < hx else -1
        s.h_line([(dx - flip * 13, dy + 3.4), (dx - flip * 3, dy + 2.2)],
                 (220, 230, 238, 130), width=1.1)
        s.h_line([(dx - flip * 11, dy + 5.2), (dx - flip * 2, dy + 4.2)],
                 (220, 230, 238, 90), width=0.9)
        s.poly([(dx - 8, dy), (dx + 7, dy), (dx + 10.5, dy + 2.6),
                (dx + 5, dy + 4.6), (dx - 5.5, dy + 4.6)], fill=(26, 30, 38))
        s.rect([dx - 2.5, dy - 2.8, dx + 2.5, dy], fill=(38, 44, 54))
        s.disc(dx + flip * 6.5, dy + 1.2, 1.1, (255, 92, 72))
    return s.finish()


def art_hormuz(w, h, ink, rng):
    """The Strait of Hormuz from above the shipping lane: headlands
    pinching the water on both sides, three tankers in line, a grey
    warship watching them, and mines bobbing in the foreground."""
    s = Panel(w, h, rng)
    s.vgrad((70, 52, 88), (226, 128, 78), 0.0, 0.42)
    s.glow(w * 0.5, h * 0.36, 16, (255, 190, 110), 110)
    s.disc(w * 0.5, h * 0.36, 6.2, (255, 206, 124))
    # the two headlands, Oman left and Iran right, hazy with heat
    s.poly([(0, h * 0.30), (w * 0.30, h * 0.40), (w * 0.335, h * 0.55),
            (0, h * 0.58)], fill=(112, 84, 74))
    s.poly([(0, h * 0.30), (w * 0.30, h * 0.40), (w * 0.26, h * 0.44),
            (0, h * 0.40)], fill=(134, 102, 88))
    s.poly([(w, h * 0.27), (w * 0.70, h * 0.385), (w * 0.665, h * 0.55),
            (w, h * 0.60)], fill=(104, 78, 70))
    s.poly([(w, h * 0.27), (w * 0.70, h * 0.385), (w * 0.74, h * 0.425),
            (w, h * 0.38)], fill=(126, 96, 84))
    s.vgrad((28, 70, 92), (10, 34, 52), 0.42, 1.0)        # the strait
    s.glints(h * 0.50, h * 0.97, 30, (255, 186, 116), 105)
    # the blockade line, dashed red across the lane
    for i in range(9):
        x0 = w * (0.36 + i * 0.032)
        s.h_line([(x0, h * 0.565), (x0 + w * 0.018, h * 0.565)],
                 (255, 84, 70, 170), width=1.6)
    # three tankers in line astern, decks rust-red
    for tx, ty, sc in ((w * 0.40, h * 0.655, 0.82), (w * 0.545, h * 0.735, 1.0),
                       (w * 0.70, h * 0.845, 1.2)):
        s.poly([(tx - 30 * sc, ty), (tx + 30 * sc, ty), (tx + 23 * sc, ty + 7 * sc),
                (tx - 23 * sc, ty + 7 * sc)], fill=(26, 30, 38))
        s.rect([tx - 30 * sc, ty - 3.4 * sc, tx + 30 * sc, ty], fill=(164, 56, 48))
        s.rect([tx - 27 * sc, ty - 5.6 * sc, tx + 16 * sc, ty - 3.4 * sc],
               fill=(120, 44, 40))
        s.rect([tx + 19 * sc, ty - 10.5 * sc, tx + 28 * sc, ty - 3.4 * sc],
               fill=(198, 196, 200))
        s.window_grid(tx + 20.5 * sc, ty - 9.5 * sc, 6 * sc, 5 * sc, 2, 2,
                      0.8, (120, 118, 124))
        s.line([(tx - 24 * sc, ty - 5.6 * sc), (tx - 24 * sc, ty - 9 * sc)],
               fill=(52, 54, 60), width=0.9)
    # the watching warship, a grey silhouette on the right shoulder
    wx, wy = w * 0.865, h * 0.60
    s.poly([(wx - 26, wy), (wx + 20, wy), (wx + 26, wy + 3.6), (wx + 21, wy + 7.6),
            (wx - 20, wy + 7.6), (wx - 25, wy + 3)], fill=(52, 58, 68))
    s.rect([wx - 8, wy - 8.6, wx + 8, wy], fill=(60, 66, 78))
    s.rect([wx - 1.5, wy - 14.5, wx + 3.5, wy - 8.6], fill=(56, 62, 74))
    s.line([(wx + 1, wy - 14.5), (wx + 1, wy - 18.5)], fill=(40, 44, 54),
           width=1.0)
    s.disc(wx + 1, wy - 19, 1.1, (255, 96, 80))
    # mines in the foreground water, spiked and half-awash
    for mx, my, mr in ((w * 0.13, h * 0.86, 6.5), (w * 0.30, h * 0.945, 8.0),
                       (w * 0.90, h * 0.955, 7.2)):
        for a in range(8):
            ang = a * math.pi / 4 + 0.4
            s.line([(mx, my), (mx + math.cos(ang) * mr * 1.45,
                               my + math.sin(ang) * mr * 1.45)],
                   fill=(18, 20, 26), width=1.5)
        s.disc(mx, my, mr, (24, 27, 34))
        s.disc(mx - mr * 0.3, my - mr * 0.3, mr * 0.34, (70, 78, 92))
        s.arc([mx - mr * 1.7, my + mr * 0.5, mx + mr * 1.7, my + mr * 1.6],
              15, 165, fill=(190, 205, 215), width=0.9)
    return s.finish()


# ----------------------------------------------------------- panel scenes
def art_dymer(w, h, ink, rng):
    """Dymer at first light after the strike: a holed apartment block
    behind a rescue cordon, a crane lifting a slab, an ambulance and
    a line of rescuers passing rubble hand to hand."""
    s = Panel(w, h, rng)
    s.vgrad((52, 58, 78), (168, 138, 116), 0.0, 0.62)
    s.vgrad((88, 78, 72), (56, 50, 48), 0.62, 1.0)
    s.glow(w * 0.08, h * 0.55, 13, (255, 196, 120), 90)
    # the block: five storeys, a black bite taken out of the middle
    bx, bw = w * 0.30, w * 0.42
    s.rect([bx, h * 0.10, bx + bw, h * 0.64], fill=(104, 98, 102))
    s.rect([bx + bw * 0.76, h * 0.10, bx + bw, h * 0.64], fill=(86, 80, 86))
    s.rect([bx, h * 0.10, bx + bw, h * 0.135], fill=(128, 122, 124))
    s.window_grid(bx + 3, h * 0.16, bw - 6, h * 0.44, 6, 5, 0.30, (62, 58, 64))
    hx0, hy0 = bx + bw * 0.36, h * 0.20                    # the hole
    s.poly([(hx0, hy0), (hx0 + bw * 0.30, hy0 + 4), (hx0 + bw * 0.26, hy0 + h * 0.26),
            (hx0 + bw * 0.08, hy0 + h * 0.31), (hx0 - bw * 0.03, hy0 + h * 0.12)],
           fill=(22, 20, 24))
    for i in range(4):                                    # exposed floor edges
        fy = hy0 + 5 + i * h * 0.07
        s.line([(hx0 + 2, fy), (hx0 + bw * 0.27, fy + 2)], fill=(150, 142, 138),
               width=1.1)
    s.plume(hx0 + bw * 0.14, hy0 + 2, 5, 2.4, 4.0, (140, 132, 128), 95, r0=2.8)
    for i in range(10):                                   # rubble fan
        rx = rng.uniform(bx + bw * 0.2, bx + bw * 0.95)
        ry = rng.uniform(h * 0.60, h * 0.655)
        s.poly([(rx, ry), (rx + rng.uniform(3, 7), ry - rng.uniform(1, 3)),
                (rx + rng.uniform(6, 10), ry)], fill=(110, 102, 100))
    # a neighbour block, untouched, on the left
    s.tower_block(w * 0.03, h * 0.22, w * 0.17, h * 0.42, (88, 86, 98), 0.5)
    # crane on the right, a slab swinging from its jib
    cx = w * 0.885
    s.line([(cx, h * 0.64), (cx, h * 0.06)], fill=(196, 130, 40), width=2.4)
    s.line([(cx, h * 0.06), (w * 0.60, h * 0.06)], fill=(196, 130, 40), width=2.0)
    s.line([(cx, h * 0.16), (w * 0.615, h * 0.065)], fill=(150, 100, 34), width=0.9)
    s.line([(w * 0.665, h * 0.06), (w * 0.665, h * 0.20)], fill=(60, 56, 52),
           width=1.0)
    s.rect([w * 0.635, h * 0.20, w * 0.695, h * 0.245], fill=(120, 114, 110))
    s.rect([cx - 8, h * 0.60, cx + 8, h * 0.64], fill=(170, 110, 36))
    # ambulance, front-left, doors open, light bar flashing
    ax, ay = w * 0.155, h * 0.815
    s.rect([ax - 26, ay - 11, ax + 26, ay + 2], fill=(238, 236, 230))
    s.rect([ax - 26, ay - 5.5, ax + 26, ay - 2.5], fill=(206, 52, 48))
    s.rect([ax + 14, ay - 16, ax + 26, ay - 11], fill=(226, 224, 218))
    s.rect([ax + 16.5, ay - 15, ax + 22.5, ay - 11.8], fill=(150, 190, 210))
    s.rect([ax - 25, ay - 10, ax - 17, ay - 3], fill=(206, 52, 48))
    s.rect([ax - 23.4, ay - 8.6, ax - 18.6, ay - 4.4], fill=(250, 248, 244))
    s.glow(ax - 4, ay - 13.5, 6, (255, 90, 70), 130)
    s.rect([ax - 9, ay - 14.6, ax + 1, ay - 12.4], fill=(226, 60, 50))
    for wx in (-17, 17):
        s.disc(ax + wx, ay + 3.6, 3.4, (20, 20, 24))
        s.disc(ax + wx, ay + 3.6, 1.5, (150, 150, 148))
    # the human chain: rescuers passing rubble to the right
    for i, rx in enumerate((0.44, 0.52, 0.60, 0.68, 0.76)):
        px = w * rx
        s.disc(px, h * 0.755, 3.0, (24, 22, 22))
        s.poly([(px - 5, h * 0.90), (px - 3.4, h * 0.795), (px + 3.4, h * 0.795),
                (px + 5, h * 0.90)], fill=(216, 110, 34))
        s.arc([px - 3.2, h * 0.715, px + 3.2, h * 0.79], 180, 360,
              fill=(246, 200, 70), width=1.6)
        if i < 4:
            s.line([(px + 3.4, h * 0.815), (px + w * 0.055, h * 0.80)],
                   fill=(24, 22, 22), width=1.6)
    # cordon tape across the front
    for i in range(6):
        x0 = w * (0.03 + i * 0.16)
        col = (226, 60, 50) if i % 2 == 0 else (240, 238, 230)
        s.poly([(x0, h * 0.955), (x0 + w * 0.08, h * 0.945),
                (x0 + w * 0.08, h * 0.965), (x0, h * 0.975)], fill=col)
    return s.finish()


def art_cop31b(w, h, ink, rng):
    """Antalya, the morning after: the summit hall empty, a torn
    'COP31' banner over the stage globe, rows of abandoned chairs
    and one delegate asleep at the long table."""
    s = Panel(w, h, rng)
    s.vgrad((44, 48, 62), (96, 88, 84), 0.0, 0.58)
    s.vgrad((86, 70, 56), (54, 42, 36), 0.58, 1.0)
    # stage screen with the globe, dimmed
    s.rect([w * 0.24, h * 0.06, w * 0.76, h * 0.44], fill=(46, 68, 90),
           outline=(170, 160, 140), width=1.4)
    gx, gy, gr = w * 0.50, h * 0.25, h * 0.155
    s.disc(gx, gy, gr, (92, 140, 178))
    s.disc(gx - gr * 0.36, gy - gr * 0.26, gr * 0.30, (84, 138, 102))
    s.disc(gx + gr * 0.34, gy + gr * 0.24, gr * 0.34, (88, 142, 106))
    s.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], outline=(190, 205, 215),
              width=1.0)
    s.line([(gx - gr * 0.5, gy - gr * 0.6), (gx - gr * 0.1, gy),
            (gx + gr * 0.2, gy + gr * 0.62)], fill=(16, 20, 28), width=1.6)
    # the banner, torn in the middle and sagging
    s.poly([(w * 0.10, h * 0.475), (w * 0.485, h * 0.475), (w * 0.47, h * 0.545),
            (w * 0.10, h * 0.53)], fill=(16, 96, 92))
    s.poly([(w * 0.515, h * 0.475), (w * 0.90, h * 0.475), (w * 0.90, h * 0.53),
            (w * 0.53, h * 0.545)], fill=(16, 96, 92))
    s.text((w * 0.295, h * 0.503), "COP", font(F_SANS_B, int(10 * ZOOM)),
           (238, 240, 230), anchor="mm")
    s.text((w * 0.705, h * 0.503), "31", font(F_SANS_B, int(10 * ZOOM)),
           (238, 240, 230), anchor="mm")
    s.line([(w * 0.485, h * 0.475), (w * 0.50, h * 0.56)], fill=(10, 60, 58),
           width=1.2)
    # the long table, nameplates and water glasses left behind
    ty = h * 0.66
    s.poly([(w * 0.08, ty + 8), (w * 0.17, ty), (w * 0.83, ty),
            (w * 0.92, ty + 8), (w * 0.92, h * 0.90), (w * 0.08, h * 0.90)],
           fill=(104, 74, 50))
    s.poly([(w * 0.17, ty), (w * 0.83, ty), (w * 0.92, ty + 8),
            (w * 0.08, ty + 8)], fill=(140, 102, 68))
    for i in range(8):
        px = w * (0.20 + i * 0.078)
        s.poly([(px, ty + 2.5), (px + 11, ty + 2.5), (px + 11, ty + 7.5),
                (px, ty + 7.5)], fill=(238, 232, 216))
        s.rect([px + 13.5, ty + 1.5, px + 16, ty + 6.5], fill=(170, 205, 220))
    # one delegate asleep, head on the table, at the far end
    dx = w * 0.845
    s.disc(dx, ty - 2.5, 3.6, (216, 178, 150))
    s.poly([(dx - 8, ty + 6), (dx - 5, ty - 1), (dx + 6, ty - 0.5),
            (dx + 9, ty + 6)], fill=(40, 44, 60))
    s.text((dx + 7, ty - 12), "z z", font(F_SANS_B, int(6.5 * ZOOM)),
           (210, 205, 195))
    # rows of empty chairs in the foreground gloom
    for row, (cy, sc) in enumerate(((0.925, 1.0), (0.985, 1.25))):
        for i in range(7):
            cx = w * (0.09 + i * 0.135)
            s.rect([cx - 8 * sc, h * cy - 9 * sc, cx + 8 * sc, h * cy],
                   fill=(36, 34, 42))
            s.rect([cx - 6 * sc, h * cy - 12.5 * sc, cx + 6 * sc,
                    h * cy - 9 * sc], fill=(48, 45, 56))
    # fallen draft pages on the floor
    for i in range(5):
        px, py = rng.uniform(w * 0.15, w * 0.8), rng.uniform(h * 0.90, h * 0.96)
        s.h_poly([(px, py), (px + 9, py + 1.6), (px + 8, py + 5.6),
                  (px - 1, py + 4)], (240, 236, 224, 150))
    return s.finish()


def art_capitol(w, h, ink, rng):
    """Washington in celebration blue: the Capitol dome over a
    semicircular seat-chart that fills, dot by dot, with the new
    Democratic majority — 258 of them."""
    s = Panel(w, h, rng)
    s.vgrad((52, 84, 140), (168, 188, 214), 0.0, 0.62)
    s.cloudbank(w * 0.14, h * 0.10, 40, (255, 255, 255), 110)
    s.cloudbank(w * 0.86, h * 0.16, 46, (255, 255, 255), 95)
    s.vgrad((120, 116, 108), (88, 84, 80), 0.62, 1.0)
    # the Capitol: dome, drum and wings
    cx = w * 0.30
    s.rect([cx - w * 0.20, h * 0.44, cx + w * 0.20, h * 0.62], fill=(228, 224, 214))
    s.window_grid(cx - w * 0.19, h * 0.47, w * 0.38, h * 0.12, 10, 2, 0.15,
                  (168, 164, 154))
    s.rect([cx - w * 0.065, h * 0.335, cx + w * 0.065, h * 0.44],
           fill=(236, 232, 224))
    s.poly([(cx - w * 0.075, h * 0.335), (cx + w * 0.075, h * 0.335),
            (cx + w * 0.045, h * 0.235), (cx - w * 0.045, h * 0.235)],
           fill=(240, 237, 229))
    s.ellipse([cx - w * 0.048, h * 0.185, cx + w * 0.048, h * 0.265],
              fill=(244, 241, 234))
    s.rect([cx - 1.6, h * 0.10, cx + 1.6, h * 0.20], fill=(240, 237, 229))
    s.disc(cx, h * 0.095, 2.2, (200, 198, 190))
    for i in range(5):                                    # front columns
        px = cx - w * 0.05 + i * w * 0.025
        s.rect([px - 1.8, h * 0.345, px + 1.8, h * 0.44], fill=(214, 210, 200))
    s.rect([cx - w * 0.23, h * 0.62, cx + w * 0.23, h * 0.645],
           fill=(206, 202, 192))                          # steps
    # flags and a crowd on the plaza
    for fx in (w * 0.055, w * 0.545):
        s.line([(fx, h * 0.60), (fx, h * 0.40)], fill=(70, 68, 66), width=1.1)
        s.poly([(fx, h * 0.40), (fx + 12, h * 0.415), (fx + 12, h * 0.455),
                (fx, h * 0.445)], fill=(52, 96, 180))
    for i in range(14):
        px = rng.uniform(w * 0.04, w * 0.56)
        s.disc(px, h * 0.715, 2.2, (30, 30, 38))
        s.poly([(px - 3.6, h * 0.79), (px - 2.4, h * 0.745), (px + 2.4, h * 0.745),
                (px + 3.6, h * 0.79)], fill=(30, 30, 38))
    # the seat chart, right: concentric arcs of dots, blue to 258
    gx, gy = w * 0.80, h * 0.60
    dots = []
    for ring in range(6):
        r = 12 + ring * 6.4
        n = 9 + ring * 5
        for i in range(n):
            ang = math.pi * (0.06 + 0.88 * i / max(1, n - 1))
            dots.append((gx - math.cos(ang) * r * 1.35,
                         gy - math.sin(ang) * r * 0.78))
    dots.sort(key=lambda p: p[0])                 # blue fills from the left
    n_blue = int(round(len(dots) * 258 / 435))
    for i, (px, py) in enumerate(dots):
        s.disc(px, py, 1.55, (52, 96, 190) if i < n_blue else (196, 84, 74))
    s.text((gx, gy + 4), "258", font(F_SERIF, int(13 * ZOOM)), (36, 40, 52),
           anchor="mm")
    s.text((gx, h * 0.86), "HOUSE SEATS", font(F_SANS_B, int(6.8 * ZOOM)),
           (52, 56, 66), anchor="mm")
    return s.finish()


def art_berlin(w, h, ink, rng):
    """Berlin by night: the Brandenburg Gate lit gold, a NATO-blue
    shield hung over the Pariser Platz, and high above it a satellite
    with a red eye crossing a field of stars."""
    s = Panel(w, h, rng)
    s.vgrad((10, 14, 32), (40, 46, 70), 0.0, 0.70)
    for _ in range(34):
        s.disc(rng.uniform(2, w - 2), rng.uniform(1, h * 0.42),
               rng.uniform(0.3, 0.7), (212, 218, 234))
    s.vgrad((52, 50, 54), (30, 30, 36), 0.70, 1.0)
    # the satellite, top-right, solar wings spread, red eye lit
    sx, sy = w * 0.76, h * 0.15
    s.ellipse([w * 0.30, h * 0.005, w * 1.02, h * 0.30], outline=(110, 126, 160),
              width=0.9)
    s.rect([sx - 5, sy - 3.6, sx + 5, sy + 3.6], fill=(206, 204, 210))
    s.rect([sx - 5, sy - 3.6, sx - 1.5, sy + 3.6], fill=(160, 158, 166))
    for px, sgn in ((sx - 16.5, -1), (sx + 16.5, 1)):
        s.rect([px - 9, sy - 5, px + 9, sy + 5], fill=(44, 74, 150))
        s.line([(px - 9, sy), (px + 9, sy)], fill=(110, 150, 210), width=0.8)
        s.line([(px, sy - 5), (px, sy + 5)], fill=(110, 150, 210), width=0.8)
        s.line([(sx + sgn * 5, sy), (px - sgn * 9, sy)], fill=(190, 188, 194),
               width=1.1)
    s.disc(sx + 1.5, sy + 5.6, 1.8, (240, 70, 60))
    s.glow(sx + 1.5, sy + 5.6, 5.5, (255, 80, 60), 130)
    s.text((w * 0.755, h * 0.315), "PLANNED NUCLEAR SATELLITE?",
           font(F_SANS_B, int(6.2 * ZOOM)), (240, 120, 105), anchor="mm")
    # the Gate: entablature, six columns, the Quadriga on top
    gx, gw = w * 0.16, w * 0.46
    gy = h * 0.70
    s.rect([gx, h * 0.335, gx + gw, h * 0.375], fill=(196, 164, 110))
    s.rect([gx, h * 0.375, gx + gw, h * 0.40], fill=(178, 146, 96))
    for i in range(6):
        px = gx + 5 + i * (gw - 10) / 5
        s.rect([px - 3.4, h * 0.40, px + 3.4, gy], fill=(204, 172, 118))
        s.rect([px - 3.4, h * 0.40, px - 0.8, gy], fill=(222, 190, 136))
    s.rect([gx - 3, gy, gx + gw + 3, gy + 3.4], fill=(168, 138, 90))
    qx = gx + gw / 2                                    # Quadriga silhouette
    s.line([(qx - 11, h * 0.335), (qx + 11, h * 0.335)], fill=(30, 30, 30),
           width=1.6)
    for hx_ in (-8, -2.7, 2.7, 8):
        s.poly([(qx + hx_ - 1.8, h * 0.335), (qx + hx_ - 0.8, h * 0.295),
                (qx + hx_ + 1.8, h * 0.30), (qx + hx_ + 1.6, h * 0.335)],
               fill=(24, 24, 26))
        s.disc(qx + hx_ + 1.8, h * 0.29, 1.5, (24, 24, 26))
    s.disc(qx, h * 0.265, 2.4, (24, 24, 26))
    s.line([(qx, h * 0.275), (qx, h * 0.335)], fill=(24, 24, 26), width=1.6)
    s.glow(gx + gw / 2, h * 0.52, 26, (255, 190, 100), 55)
    # the shield, hung at the right with the compass star
    hx, hy, hr = w * 0.845, h * 0.60, h * 0.185
    s.poly([(hx - hr * 0.8, hy - hr), (hx + hr * 0.8, hy - hr),
            (hx + hr * 0.8, hy + hr * 0.25), (hx, hy + hr),
            (hx - hr * 0.8, hy + hr * 0.25)], fill=(24, 62, 118),
           outline=(220, 226, 236))
    for a in (0, 90, 180, 270):
        ang = math.radians(a)
        s.line([(hx, hy - hr * 0.1), (hx + math.cos(ang) * hr * 0.52,
                                      hy - hr * 0.1 + math.sin(ang) * hr * 0.52)],
               fill=(226, 232, 242), width=1.7)
    s.disc(hx, hy - hr * 0.1, 2.2, (226, 232, 242))
    s.text((hx, hy + hr + 7), "SPACE DEFENCE", font(F_SANS_B, int(6.4 * ZOOM)),
           (200, 208, 224), anchor="mm")
    # two searchlight beams sweeping the sky
    for fx, tx in ((w * 0.06, w * 0.34), (w * 0.60, w * 0.30)):
        s.h_poly([(fx, h * 0.70), (tx, h * 0.03), (tx + 12, h * 0.03)],
                 (255, 240, 200, 36))
    return s.finish()


def art_candy(w, h, ink, rng):
    """Banten at night: the candy factory alight along its roof, pink
    signage dark, a ladder platform working from the right and the
    night shift watching from behind a fence of striped poles."""
    s = Panel(w, h, rng)
    s.vgrad((20, 22, 42), (76, 56, 62), 0.0, 0.68)
    s.vgrad((48, 42, 42), (30, 28, 30), 0.68, 1.0)
    # the long factory shed, left two-thirds
    bx, bw = w * 0.03, w * 0.60
    s.rect([bx, h * 0.30, bx + bw, h * 0.70], fill=(100, 94, 104))
    s.rect([bx, h * 0.30, bx + bw, h * 0.335], fill=(122, 116, 126))
    s.poly([(bx - 3, h * 0.30), (bx + bw + 3, h * 0.30), (bx + bw - 4, h * 0.255),
            (bx + 4, h * 0.255)], fill=(70, 66, 76))
    s.window_grid(bx + 4, h * 0.37, bw - 8, h * 0.28, 8, 3, 0.28, (58, 55, 64))
    # the candy sign, its pink gone dark except one letter
    s.rect([bx + bw * 0.10, h * 0.175, bx + bw * 0.62, h * 0.245],
           fill=(52, 44, 52))
    s.text((bx + bw * 0.36, h * 0.21), "PERMEN", font(F_SANS_B, int(8.5 * ZOOM)),
           (120, 84, 100), anchor="mm")
    s.text((bx + bw * 0.155, h * 0.21), "P", font(F_SANS_B, int(8.5 * ZOOM)),
           (255, 130, 170), anchor="mm")
    s.glow(bx + bw * 0.155, h * 0.21, 6, (255, 110, 160), 80)
    # fire along the roofline and out of the skylights
    s.glow(bx + bw * 0.55, h * 0.225, 20, (255, 140, 60), 150)
    for fx, fh in ((0.38, 11), (0.52, 16), (0.66, 12), (0.80, 8), (0.92, 6)):
        cx = bx + bw * fx
        s.poly([(cx - 4, h * 0.258), (cx, h * 0.258 - fh), (cx + 4, h * 0.258)],
               fill=(246, 128, 44))
        s.poly([(cx - 2, h * 0.258), (cx, h * 0.258 - fh * 0.58),
                (cx + 2, h * 0.258)], fill=(255, 208, 100))
    s.plume(bx + bw * 0.58, h * 0.20, 8, 3.2, 5.0, (28, 26, 30), 135, r0=3.8)
    s.plume(bx + bw * 0.34, h * 0.23, 5, 2.4, 4.0, (56, 50, 52), 105, r0=2.6)
    # water tower behind, untouched
    wx = w * 0.70
    s.ellipse([wx - 10, h * 0.13, wx + 10, h * 0.20], fill=(84, 88, 98))
    s.rect([wx - 10, h * 0.165, wx + 10, h * 0.225], fill=(74, 78, 88))
    for lx in (wx - 7, wx + 7):
        s.line([(lx, h * 0.225), (lx, h * 0.70)], fill=(60, 62, 70), width=1.4)
    # ladder platform from the right, jet arcing onto the roof
    tx, ty = w * 0.865, h * 0.83
    s.rect([tx - 17, ty - 7, tx + 17, ty + 1], fill=(192, 46, 42))
    s.rect([tx + 6, ty - 12, tx + 17, ty - 7], fill=(174, 42, 40))
    s.rect([tx + 8.5, ty - 11.2, tx + 13.5, ty - 8], fill=(170, 205, 220))
    for wx_ in (-11, 11):
        s.disc(tx + wx_, ty + 2.4, 3.2, (20, 20, 24))
    s.line([(tx - 4, ty - 7), (bx + bw * 0.86, h * 0.30)], fill=(214, 212, 208),
           width=1.6)
    jet = quad((bx + bw * 0.865, h * 0.315), (bx + bw * 0.72, h * 0.13),
               (bx + bw * 0.60, h * 0.265))
    for i in range(len(jet) - 1):
        a = 160 - i * 4
        s.h_line([jet[i], jet[i + 1]], (196, 224, 244, max(45, a)), width=2.0)
    # the night shift behind the striped fence, hard hats on
    for i, px in enumerate((0.10, 0.20, 0.31, 0.43, 0.55)):
        x = w * px
        s.disc(x, h * 0.845, 2.9, (18, 17, 20))
        s.poly([(x - 5, h * 0.955), (x - 3.4, h * 0.88), (x + 3.4, h * 0.88),
                (x + 5, h * 0.955)], fill=(18, 17, 20))
        s.arc([x - 3.2, h * 0.805, x + 3.2, h * 0.875], 180, 360,
              fill=(240, 190, 60), width=1.6)
    for i in range(7):
        x0 = w * (0.04 + i * 0.135)
        col = (226, 60, 50) if i % 2 == 0 else (240, 238, 230)
        s.rect([x0, h * 0.925, x0 + 3, h * 0.995], fill=col)
    s.line([(w * 0.03, h * 0.925), (w * 0.97, h * 0.925)], fill=(200, 196, 188),
           width=1.0)
    return s.finish()


def art_sinaloa(w, h, ink, rng):
    """Sinaloa, late afternoon: a walled ranch at the end of a dirt
    track, federal vehicles drawn up in an arc before the gate, a
    helicopter holding overhead and dust hanging in the light."""
    s = Panel(w, h, rng)
    s.vgrad((66, 58, 92), (228, 146, 90), 0.0, 0.60)
    s.glow(w * 0.14, h * 0.50, 16, (255, 190, 110), 110)
    s.disc(w * 0.14, h * 0.50, 6.4, (255, 204, 128))
    for gx, gh, col in ((0.30, 0.30, (96, 76, 94)), (0.62, 0.22, (106, 86, 100)),
                        (0.90, 0.34, (88, 70, 88))):      # sierra backdrop
        s.poly([(w * gx - 36, h * 0.60), (w * gx, h * (0.60 - gh)),
                (w * gx + 40, h * 0.60)], fill=col)
    s.vgrad((150, 114, 76), (106, 80, 54), 0.60, 1.0)     # desert floor
    for i in range(22):                                   # scrub and stones
        x, y = rng.uniform(0, w), rng.uniform(h * 0.63, h * 0.97)
        s.line([(x, y), (x + rng.uniform(2, 4.5), y - 1)], fill=(90, 68, 44),
               width=0.7)
    # the ranch: long wall, gate, tiled house and a water tank
    rx, ry = w * 0.565, h * 0.475
    s.rect([rx - 34, ry + 6, rx + 40, ry + 15], fill=(206, 188, 160))
    s.rect([rx - 34, ry + 6, rx + 40, ry + 8.6], fill=(188, 168, 140))
    s.rect([rx - 4, ry + 6, rx + 8, ry + 15], fill=(96, 66, 46))   # the gate
    s.rect([rx + 12, ry - 6, rx + 36, ry + 6], fill=(220, 204, 180))
    s.poly([(rx + 9, ry - 6), (rx + 24, ry - 12.5), (rx + 39, ry - 6)],
           fill=(172, 86, 58))
    s.rect([rx + 20, ry - 1, rx + 25, ry + 6], fill=(90, 62, 44))
    s.rect([rx + 14.5, ry - 3.5, rx + 18, ry - 0.5], fill=LITWIN)
    s.rect([rx - 30, ry - 8, rx - 22, ry + 6], fill=(150, 148, 150))
    s.ellipse([rx - 30, ry - 10.5, rx - 22, ry - 5.5], fill=(168, 166, 168))
    # the arc of federal vehicles facing the gate, dust behind them
    for vx, vy, sc, ang in ((w * 0.10, h * 0.80, 1.15, 0), (w * 0.27, h * 0.715, 0.95, 0),
                            (w * 0.42, h * 0.665, 0.78, 0), (w * 0.80, h * 0.70, 0.9, 0),
                            (w * 0.93, h * 0.79, 1.1, 0)):
        flip = 1 if vx < rx else -1
        s.plume(vx - flip * 13 * sc, vy + 3 * sc, 3, 2.0, 1.4,
                (208, 182, 144), 80, r0=2.3 * sc)
        s.rect([vx - 13 * sc, vy - 6 * sc, vx + 13 * sc, vy + 3 * sc],
               fill=(50, 54, 50))
        cab0 = vx + (3 * sc if flip > 0 else -13 * sc)
        cab1 = vx + (13 * sc if flip > 0 else -3 * sc)
        s.rect([cab0, vy - 10 * sc, cab1, vy - 6 * sc], fill=(60, 64, 60))
        win0 = vx + (5.5 * sc if flip > 0 else -10 * sc)
        win1 = vx + (10 * sc if flip > 0 else -5.5 * sc)
        s.rect([win0, vy - 9.4 * sc, win1, vy - 6.8 * sc],
               fill=(168, 200, 214))
        s.rect([vx - 13 * sc, vy - 6 * sc, vx + 13 * sc, vy - 4.2 * sc],
               fill=(240, 238, 232))                     # federal stripe
        for wx in (-8, 7):
            s.disc(vx + wx * sc, vy + 4.2 * sc, 2.6 * sc, (22, 22, 24))
            s.disc(vx + wx * sc, vy + 4.2 * sc, 1.1 * sc, (120, 120, 118))
    # officers as small dark figures between vehicles and gate
    for px in (0.33, 0.475, 0.60):
        x = w * px
        s.disc(x, h * 0.795, 2.4, (22, 22, 24))
        s.poly([(x - 3.8, h * 0.875), (x - 2.6, h * 0.83), (x + 2.6, h * 0.83),
                (x + 3.8, h * 0.875)], fill=(22, 22, 24))
    # helicopter holding top-centre, searchlight raking the yard
    hx, hy = w * 0.42, h * 0.155
    s.ellipse([hx - 13, hy - 4.6, hx + 10, hy + 4.6], fill=(26, 27, 32))
    s.poly([(hx + 9, hy - 1.5), (hx + 24, hy - 3.6), (hx + 24, hy - 0.6),
            (hx + 9, hy + 1)], fill=(26, 27, 32))
    s.line([(hx - 15, hy - 6.6), (hx + 15, hy - 6.6)], fill=(20, 20, 24),
           width=1.7)
    s.disc(hx - 2, hy - 0.5, 2.9, (150, 190, 214))
    s.disc(hx + 12, hy + 5.5, 1.2, (255, 80, 60))
    s.h_poly([(hx, hy + 4), (rx - 16, ry + 14), (rx + 6, ry + 14)],
             (255, 242, 196, 44))
    return s.finish()


def art_cyber(w, h, ink, rng):
    """Austin after dark: two glass towers face each other across
    the river, streams of data pouring from both into one bright
    merged core — a $44 billion handshake drawn in light."""
    s = Panel(w, h, rng)
    s.vgrad((16, 24, 48), (60, 62, 92), 0.0, 0.70)
    for _ in range(20):
        s.disc(rng.uniform(2, w - 2), rng.uniform(1, h * 0.30),
               rng.uniform(0.3, 0.65), (208, 216, 232))
    s.vgrad((18, 40, 54), (10, 24, 36), 0.70, 1.0)        # the river
    s.glints(h * 0.74, h * 0.96, 22, (140, 200, 230), 100)
    # the two towers
    for tx, tw, th, tone_, lit in ((0.06, 0.20, 0.52, (52, 66, 96), 0.5),
                                   (0.74, 0.20, 0.58, (58, 62, 100), 0.45)):
        s.rect([w * tx, h * (0.70 - th), w * (tx + tw), h * 0.70], fill=tone_)
        s.rect([w * tx, h * (0.70 - th), w * (tx + tw), h * (0.70 - th) + 3],
               fill=shade(tone_, 1.3))
        s.rect([w * (tx + tw * 0.78), h * (0.70 - th), w * (tx + tw), h * 0.70],
               fill=shade(tone_, 0.74))
        s.window_grid(w * tx + 2.5, h * (0.70 - th) + 5, w * tw - 5,
                      h * th - 10, 4, 8, lit, shade(tone_, 0.5))
    s.text((w * 0.16, h * 0.085), "CROWDSTRIKE", font(F_SANS_B, int(6.0 * ZOOM)),
           (190, 214, 240), anchor="mm")
    s.text((w * 0.84, h * 0.055), "ZSCALER", font(F_SANS_B, int(6.0 * ZOOM)),
           (190, 214, 240), anchor="mm")
    # lower skyline shoulders and the bridge between them
    for bx, bw, bh in ((0.28, 0.09, 0.24), (0.63, 0.09, 0.20), (0.40, 0.06, 0.15)):
        s.rect([w * bx, h * (0.70 - bh), w * (bx + bw), h * 0.70],
               fill=(40, 50, 76))
        s.window_grid(w * bx + 1.5, h * (0.70 - bh) + 3, w * bw - 3,
                      h * bh - 6, 2, 4, 0.4, (28, 36, 54))
    s.rect([w * 0.10, h * 0.685, w * 0.90, h * 0.70], fill=(30, 36, 52))
    for i in range(6):
        px = w * (0.16 + i * 0.135)
        s.disc(px, h * 0.692, 1.3, (255, 210, 130))
    # data streams pouring into the merged core
    core = (w * 0.50, h * 0.40)
    for k in range(5):
        y0 = h * (0.24 + k * 0.075)
        pts = quad((w * 0.265, y0), (w * 0.38, y0 + h * 0.05), core, n=16)
        for i in range(len(pts) - 1):
            s.h_line([pts[i], pts[i + 1]], (110, 200, 250, 150), width=1.3)
        pts = quad((w * 0.735, y0), (w * 0.62, y0 + h * 0.05), core, n=16)
        for i in range(len(pts) - 1):
            s.h_line([pts[i], pts[i + 1]], (150, 160, 250, 150), width=1.3)
    s.glow(core[0], core[1], 17, (140, 210, 255), 150)
    s.disc(core[0], core[1], 8.5, (216, 238, 255))
    s.disc(core[0], core[1], 5.2, (120, 180, 240))
    # a shield outline round the core, drawn in light
    s.arc([core[0] - 13, core[1] - 14, core[0] + 13, core[1] + 12], 200, 340,
          fill=(210, 236, 255), width=1.4)
    s.line([(core[0] - 12.2, core[1] + 4), (core[0] - 8, core[1] + 13),
            (core[0], core[1] + 16.5)], fill=(210, 236, 255), width=1.4)
    s.line([(core[0] + 12.2, core[1] + 4), (core[0] + 8, core[1] + 13),
            (core[0], core[1] + 16.5)], fill=(210, 236, 255), width=1.4)
    # the price tag on a board over the river
    s.rect([w * 0.385, h * 0.745, w * 0.615, h * 0.745 + 13], fill=(14, 20, 32),
           outline=(190, 205, 225), width=1.2)
    s.text((w * 0.50, h * 0.745 + 6.5), "$44 BILLION", font(F_SANS_B,
           int(8.5 * ZOOM)), (170, 230, 190), anchor="mm")
    return s.finish()


def art_arena(w, h, ink, rng):
    """Manchester at night: the Co-op Live arena glowing across the
    canal, a greenish haze at one vomitory door, crowds streaming
    out along the towpath and ambulances waiting with lights on."""
    s = Panel(w, h, rng)
    s.vgrad((18, 22, 44), (66, 64, 88), 0.0, 0.64)
    s.vgrad((26, 44, 54), (14, 28, 36), 0.64, 1.0)        # canal
    s.glints(h * 0.68, h * 0.96, 20, (200, 190, 220), 90)
    # the arena: a great drum with a glowing band and roof ribs
    ax, aw = w * 0.16, w * 0.68
    s.rect([ax, h * 0.26, ax + aw, h * 0.64], fill=(58, 58, 74))
    s.ellipse([ax - 4, h * 0.175, ax + aw + 4, h * 0.30], fill=(76, 76, 94))
    s.ellipse([ax - 4, h * 0.175, ax + aw + 4, h * 0.235], fill=(96, 96, 116))
    for i in range(7):
        px = ax + 8 + i * (aw - 16) / 6
        s.line([(px, h * 0.235), (px, h * 0.26)], fill=(52, 52, 66), width=1.2)
    s.rect([ax, h * 0.315, ax + aw, h * 0.375], fill=(120, 90, 170))
    s.glow(ax + aw / 2, h * 0.345, 22, (160, 120, 230), 70)
    s.text((ax + aw / 2, h * 0.345), "CO-OP LIVE", font(F_SANS_B,
           int(9.5 * ZOOM)), (240, 236, 250), anchor="mm")
    s.window_grid(ax + 5, h * 0.40, aw - 10, h * 0.10, 12, 2, 0.75, (40, 40, 54))
    # doors spilling light — and at the middle door, the haze
    for i, dx in enumerate((0.14, 0.38, 0.62, 0.86)):
        px = ax + aw * dx
        s.rect([px - 6, h * 0.525, px + 6, h * 0.64], fill=(250, 214, 140))
        s.h_poly([(px - 6, h * 0.64), (px + 6, h * 0.64), (px + 11, h * 0.72),
                  (px - 11, h * 0.72)], (255, 224, 160, 52))
        if i == 1:
            s.plume(px + 3, h * 0.52, 5, 2.0, 2.6, (150, 200, 140), 48, r0=2.0)
            s.glow(px, h * 0.55, 6, (160, 220, 140), 40)
    # the crowd streaming away along both towpaths
    for i in range(26):
        side = rng.random()
        px = rng.uniform(w * 0.03, w * 0.30) if side < 0.5 else \
            rng.uniform(w * 0.70, w * 0.97)
        py = rng.uniform(h * 0.68, h * 0.86)
        sc = 0.8 + (py - h * 0.68) / h
        s.disc(px, py, 1.9 * sc, (16, 15, 20))
        s.poly([(px - 3.2 * sc, py + 6.5 * sc), (px - 2.1 * sc, py + 2.4 * sc),
                (px + 2.1 * sc, py + 2.4 * sc), (px + 3.2 * sc, py + 6.5 * sc)],
               fill=(16, 15, 20))
    # two ambulances at the right, light bars strobing
    for bx, by, sc in ((w * 0.845, h * 0.885, 1.0), (w * 0.66, h * 0.935, 0.8)):
        s.rect([bx - 19 * sc, by - 8 * sc, bx + 19 * sc, by + 1.5 * sc],
               fill=(238, 236, 230))
        s.rect([bx - 19 * sc, by - 4 * sc, bx + 19 * sc, by - 1.6 * sc],
               fill=(240, 190, 50))
        s.rect([bx + 10 * sc, by - 12 * sc, bx + 19 * sc, by - 8 * sc],
               fill=(226, 224, 218))
        s.rect([bx + 12 * sc, by - 11.4 * sc, bx + 16.5 * sc, by - 8.6 * sc],
               fill=(150, 190, 210))
        s.glow(bx - 3 * sc, by - 9.8 * sc, 5 * sc, (255, 90, 70), 130)
        s.rect([bx - 6.5 * sc, by - 10.6 * sc, bx + 0.5 * sc, by - 9 * sc],
               fill=(226, 60, 50))
        for wx in (-12, 12):
            s.disc(bx + wx * sc, by + 2.8 * sc, 2.6 * sc, (20, 20, 24))
    return s.finish()


def art_khartoum(w, h, ink, rng):
    """Khartoum where the Niles meet: a white UN block flying its
    blue flag on the near bank, drones crossing a smoke-stained sky,
    and fires burning across the river in the old city."""
    s = Panel(w, h, rng)
    s.vgrad((96, 74, 84), (226, 156, 102), 0.0, 0.50)
    s.glow(w * 0.82, h * 0.42, 14, (255, 192, 112), 110)
    s.disc(w * 0.82, h * 0.42, 5.4, (255, 208, 124))
    # far bank skyline, low and dusty, with two fire glows
    for bx, bw, bh, tone_ in ((0.52, 0.10, 0.16, (120, 94, 84)),
                              (0.64, 0.08, 0.22, (112, 88, 80)),
                              (0.74, 0.12, 0.14, (122, 96, 86)),
                              (0.88, 0.11, 0.19, (114, 90, 82))):
        s.rect([w * bx, h * (0.52 - bh), w * (bx + bw), h * 0.52], fill=tone_)
        s.window_grid(w * bx + 1.5, h * (0.52 - bh) + 3, w * bw - 3,
                      h * bh - 6, 3, 3, 0.3, shade(tone_, 0.55))
    for fx in (w * 0.68, w * 0.92):
        s.glow(fx, h * 0.47, 8, (255, 140, 60), 150)
        s.plume(fx, h * 0.45, 6, 2.8, 4.4, (52, 46, 46), 125, r0=3.0)
    s.rect([0, h * 0.52, w, h * 0.555], fill=(128, 104, 84))   # far bank
    s.vgrad((40, 84, 92), (18, 48, 58), 0.555, 1.0)       # the Nile
    s.glints(h * 0.60, h * 0.95, 24, (255, 190, 120), 100)
    # a bridge stitching the banks, centre-right
    s.line([(w * 0.44, h * 0.545), (w * 0.99, h * 0.545)], fill=(60, 58, 56),
           width=2.0)
    for i in range(5):
        px = w * (0.50 + i * 0.11)
        s.line([(px, h * 0.545), (px, h * 0.60)], fill=(60, 58, 56), width=1.2)
        s.arc([px - w * 0.05, h * 0.545, px + w * 0.05, h * 0.625], 0, 180,
              fill=(70, 68, 66), width=1.1)
    # the UN block on the near bank, white and flagged
    ux, uw = w * 0.05, w * 0.30
    s.rect([ux, h * 0.60, ux + uw, h * 0.86], fill=(238, 236, 230))
    s.rect([ux, h * 0.60, ux + uw, h * 0.635], fill=(214, 212, 204))
    s.rect([ux + uw * 0.72, h * 0.60, ux + uw, h * 0.86], fill=(218, 216, 206))
    s.window_grid(ux + 3, h * 0.65, uw - 6, h * 0.17, 6, 3, 0.35, (150, 148, 140))
    s.rect([ux + uw * 0.36, h * 0.775, ux + uw * 0.64, h * 0.86],
           fill=(104, 96, 88))
    fx = ux + uw / 2
    s.line([(fx, h * 0.60), (fx, h * 0.475)], fill=(90, 88, 84), width=1.3)
    wave = rng.uniform(-1.0, 1.0)
    s.poly([(fx, h * 0.475), (fx + 17, h * 0.485 + wave), (fx + 17, h * 0.525 + wave),
            (fx, h * 0.515)], fill=(90, 160, 215))
    s.text((fx + 8.5, h * 0.495 + wave / 2), "UN", font(F_SANS_B,
           int(6.2 * ZOOM)), (250, 250, 250), anchor="mm")
    s.rect([0, h * 0.86, w * 0.42, h * 0.885], fill=(140, 116, 90))
    # three drones crossing high, tracer dotted paths behind them
    for dx, dy, flip in ((w * 0.30, h * 0.13, 1), (w * 0.52, h * 0.075, 1),
                         (w * 0.70, h * 0.17, -1)):
        s.poly([(dx - 10, dy - 2.4), (dx + 7, dy + 0.8), (dx + 10, dy + 3.8),
                (dx - 5, dy + 3)], fill=(18, 17, 20))
        s.line([(dx - 9, dy - 4.6), (dx - 2, dy - 0.8)], fill=(18, 17, 20),
               width=1.3)
        s.line([(dx + 6, dy - 4), (dx + 9, dy + 0.6)], fill=(18, 17, 20),
               width=1.3)
        s.disc(dx + 4.5, dy + 1.6, 1.4, (255, 74, 60))
        s.glow(dx + 4.5, dy + 1.6, 4.4, (255, 80, 60), 120)
        for t in (0.3, 0.55, 0.8):
            s.h_disc(dx - flip * t * 34, dy + t * 7, 0.95, (255, 130, 105, 130))
    # one explosion blooming over the far bank, right
    s.glow(w * 0.80, h * 0.40, 11, (255, 150, 62), 165)
    s.disc(w * 0.80, h * 0.40, 3.8, (255, 200, 100))
    return s.finish()


def art_tennis(w, h, ink, rng):
    """Turin, championship point: the hard court under arena lights,
    Alcaraz sliding into a forehand on the near side, Zverev waiting
    at the far baseline, and the trophy gleaming courtside."""
    s = Panel(w, h, rng)
    s.vgrad((24, 28, 48), (52, 56, 82), 0.0, 0.34)
    for i in range(5):                                    # light rigs
        lx = w * (0.10 + i * 0.20)
        s.glow(lx, h * 0.075, 8, (255, 244, 200), 130)
        s.disc(lx, h * 0.075, 2.4, (255, 248, 214))
        s.h_poly([(lx - 3, h * 0.09), (lx + 3, h * 0.09), (lx + 13, h * 0.36),
                  (lx - 13, h * 0.36)], (255, 244, 200, 26))
    # crowd banks in the gloom
    for row in range(3):
        for i in range(30):
            px = rng.uniform(4, w - 4)
            py = h * (0.155 + row * 0.055) + rng.uniform(-1.5, 1.5)
            s.disc(px, py, 1.35, blend((30, 32, 46), (120, 110, 130),
                                       rng.random() * 0.5))
    # the court in perspective: blue inside, green runback
    s.poly([(w * 0.02, h * 0.98), (w * 0.20, h * 0.36), (w * 0.80, h * 0.36),
            (w * 0.98, h * 0.98)], fill=(44, 116, 74))
    s.poly([(w * 0.155, h * 0.98), (w * 0.295, h * 0.40), (w * 0.705, h * 0.40),
            (w * 0.845, h * 0.98)], fill=(52, 96, 168))
    s.line([(w * 0.295, h * 0.40), (w * 0.155, h * 0.98)], fill=(238, 240, 244),
           width=1.2)
    s.line([(w * 0.705, h * 0.40), (w * 0.845, h * 0.98)], fill=(238, 240, 244),
           width=1.2)
    s.line([(w * 0.36, h * 0.565), (w * 0.64, h * 0.565)], fill=(238, 240, 244),
           width=1.0)
    s.line([(w * 0.50, h * 0.565), (w * 0.50, h * 0.98)], fill=(238, 240, 244),
           width=1.0)
    # the net
    s.line([(w * 0.235, h * 0.665), (w * 0.765, h * 0.665)], fill=(240, 240, 244),
           width=1.8)
    for i in range(13):
        px = w * (0.245 + i * 0.0425)
        s.line([(px, h * 0.665), (px, h * 0.715)], fill=(30, 30, 40), width=0.8)
    s.line([(w * 0.235, h * 0.715), (w * 0.765, h * 0.715)], fill=(30, 30, 40),
           width=1.0)
    # Zverev at the far baseline, tall, racket up
    zx, zy = w * 0.60, h * 0.415
    s.disc(zx, zy - 9, 2.6, (232, 196, 164))
    s.line([(zx, zy - 6), (zx, zy + 5)], fill=(240, 240, 244), width=2.2)
    s.line([(zx, zy + 5), (zx - 3.4, zy + 13)], fill=(30, 30, 38), width=1.7)
    s.line([(zx, zy + 5), (zx + 3.8, zy + 13)], fill=(30, 30, 38), width=1.7)
    s.line([(zx, zy - 4), (zx + 6.5, zy - 9)], fill=(232, 196, 164), width=1.7)
    s.ellipse([zx + 5.5, zy - 14.5, zx + 10.5, zy - 7.5], outline=(200, 200, 205),
              width=1.1)
    # Alcaraz sliding in near-side, forehand wound up, ball streaking
    ax, ay = w * 0.335, h * 0.845
    s.poly([(ax - 15, ay + 12.5), (ax + 17, ay + 12.5), (ax + 10, ay + 15.5),
            (ax - 9, ay + 15.5)], fill=(30, 30, 40))       # his shadow skid
    s.disc(ax, ay - 12, 3.4, (196, 138, 100))
    s.poly([(ax - 3.4, ay - 9), (ax + 3.4, ay - 9), (ax + 2.6, ay + 2),
            (ax - 2.6, ay + 2)], fill=(214, 52, 52))
    s.line([(ax - 2, ay + 2), (ax - 8.5, ay + 12)], fill=(40, 40, 48), width=2.2)
    s.line([(ax + 2, ay + 2), (ax + 10.5, ay + 11)], fill=(40, 40, 48), width=2.2)
    s.line([(ax + 3, ay - 7), (ax + 11, ay - 2)], fill=(196, 138, 100), width=2.0)
    s.ellipse([ax + 9.5, ay - 9.5, ax + 16.5, ay + 0.5], outline=(220, 220, 226),
              width=1.3)
    s.line([(ax + 11, ay - 2), (ax + 12.5, ay - 4.5)], fill=(120, 120, 126),
           width=1.0)
    bx_, by_ = ax + 21, ay - 6
    s.h_line([(ax + 17, ay - 5), (bx_ - 3, by_)], (220, 240, 120, 170), width=1.6)
    s.disc(bx_, by_, 2.3, (214, 232, 84))
    s.glow(bx_, by_, 5.5, (220, 240, 120), 100)
    # scoreboard and trophy, courtside right
    s.rect([w * 0.845, h * 0.42, w * 0.975, h * 0.42 + 17], fill=(14, 16, 26),
           outline=(190, 200, 214), width=1.1)
    s.text((w * 0.91, h * 0.42 + 8.5), "6-2  7-6", font(F_SANS_B,
           int(7.6 * ZOOM)), (255, 224, 140), anchor="mm")
    tx, ty = w * 0.925, h * 0.80
    s.glow(tx, ty - 6, 10, (255, 214, 110), 120)
    s.poly([(tx - 5.5, ty - 13), (tx + 5.5, ty - 13), (tx + 3.6, ty - 5),
            (tx - 3.6, ty - 5)], fill=(240, 198, 92))
    s.arc([tx - 9.5, ty - 13.5, tx - 3, ty - 6], 90, 300, fill=(240, 198, 92),
          width=1.3)
    s.arc([tx + 3, ty - 13.5, tx + 9.5, ty - 6], 240, 90, fill=(240, 198, 92),
          width=1.3)
    s.rect([tx - 1.3, ty - 5, tx + 1.3, ty - 1.5], fill=(226, 182, 80))
    s.rect([tx - 4.4, ty - 1.5, tx + 4.4, ty + 0.8], fill=(214, 170, 72))
    return s.finish()


SCENES = {
    "chip": art_chip, "corvette": art_corvette, "hormuz": art_hormuz,
    "dymer": art_dymer, "cop31b": art_cop31b, "capitol": art_capitol,
    "berlin": art_berlin, "candy": art_candy, "sinaloa": art_sinaloa,
    "cyber": art_cyber, "arena": art_arena, "khartoum": art_khartoum,
    "tennis": art_tennis,
}


# ------------------------------------------------------------------ ledger
FIGURES = [  # Monday in six numbers
    ("33%", "Nvidia shares leap after Huang returns"),
    ("7", "naval drones sink Russian corvette at Benghazi"),
    ("+4.82%", "S&P 500 rebound after AI sell-off (Nikkei -5%)"),
    ("258", "House seats — Democrats' largest majority since 1992"),
    ("24", "dead in Banten candy-factory fire, dozens missing"),
    ("$44bn", "CrowdStrike deal to buy Zscaler"),
]
TALLY = [("EUROPE", 11), ("AMERICAS", 10), ("ASIA", 7),
         ("MIDDLE EAST", 4), ("AFRICA", 4), ("OCEANIA", 1)]
HEROES = [
    {"region": "AMERICAS", "art": "chip", "src": "Reuters",
     "headline": "Nvidia brings back Jensen Huang; shares leap 33%",
     "body": "Santa Clara's board reinstates its co-founder as CEO, 11 days "
             "after he resigned; the Nasdaq jumps 6.5%."},
    {"region": "EUROPE", "art": "corvette", "src": "Reuters",
     "headline": "Ukraine sinks Russian corvette in Libyan port",
     "body": "Seven naval drones sink the Merkury at Benghazi — Kyiv's "
             "first admitted strike in the Mediterranean."},
    {"region": "MIDDLE EAST", "art": "hormuz", "src": "Reuters",
     "headline": "Iran vows 'all means' against US blockade",
     "body": "Tehran vows to counter the US naval blockade of the Strait "
             "of Hormuz; three tankers are reported hit by mines."},
]
FEATURES = [
    {"region": "EUROPE", "art": "dymer", "src": "AP",
     "headline": "Strike on Dymer flats kills at least 11",
     "body": "Rescuers free a boy, 7, and woman, 79, alive after 22 hours "
             "in rubble."},
    {"region": "EUROPE", "art": "cop31b", "src": "OneTurn",
     "headline": "COP31 ends with no deal in Antalya",
     "body": "First failed climate summit in 17 years; the draft omitted "
             "fossil fuels."},
    {"region": "AMERICAS", "art": "capitol", "src": "Reuters",
     "headline": "Democrats take 258 House seats",
     "body": "The largest House majority since 1992, with 56 Senate "
             "seats too."},
    {"region": "EUROPE", "art": "berlin", "src": "Reuters",
     "headline": "NATO warns Russia, pledges space defence",
     "body": "Berlin meeting amid reports of a planned nuclear-armed "
             "satellite."},
    {"region": "ASIA", "art": "candy", "src": "BBC",
     "headline": "Banten candy-factory fire toll hits 24",
     "body": "About 34 are still missing; DNA tests are needed to name "
             "the dead."},
    {"region": "AMERICAS", "art": "sinaloa", "src": "Reuters",
     "headline": "Mexico captures 'El Chapo Isidro'",
     "body": "FBI most-wanted boss seized in Sinaloa with US intelligence "
             "help."},
    {"region": "AMERICAS", "art": "cyber", "src": "Reuters",
     "headline": "CrowdStrike to buy Zscaler for $44bn",
     "body": "Austin deal struck as AI fuels a new wave of cyberattacks."},
    {"region": "EUROPE", "art": "arena", "src": "BBC",
     "headline": "12,000 flee Manchester concert",
     "body": "An irritant released at Co-op Live; more than 80 treated."},
    {"region": "AFRICA", "art": "khartoum", "src": "AP",
     "headline": "Drones hit Khartoum and UN building",
     "body": "Sudan's army blames the RSF for the attacks on the capital."},
    {"region": "EUROPE", "art": "tennis", "src": "AP",
     "headline": "Alcaraz wins first ATP Finals title",
     "body": "He beats Zverev 6-2, 7-6 in Turin to close the season on top."},
]
BRIEFS = [
    (14, "EU proposes 22nd sanctions package on Russia"),
    (15, "US sanctions Iran 'shadow banking' networks"),
    (16, "Houthis claim Saudi refinery attack; 17 die in Yemen strikes"),
    (17, "Trump calls Putin 'my friend' after Shenzhen summit"),
    (18, "Belgian airports shut in anti-austerity strike"),
    (19, "India pledges $1.6bn as Nepal PM visits Delhi"),
    (20, "Spain's top court grants Puigdemont amnesty"),
    (21, "Iran flogs singer Parastoo Ahmadi, 74 lashes"),
    (22, "Tajikistan begins leaving the ICC, fourth country to quit"),
    (23, "450 German schools get bomb threats; Denmark too"),
    (24, "South Korea's education minister quits over exam cheating"),
    (25, "Tata Steel buys $1.67bn stake in APL Apollo"),
    (26, "ConocoPhillips exits Norway in $4.4bn Ekofisk deal"),
    (27, "European gas jumps 8.6% on cold; oil slides 4%, Brent $86.72"),
    (28, "Capita shares plunge 70% as boss quits over pensions"),
    (29, "Australia warns jobless rate will pass 5%"),
    (30, "Brazil storm kills five, displaces thousands"),
    (31, "Nigeria mourners' boat capsizes, 24 dead"),
    (32, "Paramilitary attack kills 24 in South Sudan"),
    (33, "Kenya and DR Congo restore diplomatic ties"),
    (34, "Zambia opposition leader charged with treason"),
    (35, "US seeks $1bn crypto stolen in Binance hack"),
    (36, "Anthropic mathematician claims Riemann proof"),
    (37, "Márquez wins eighth MotoGP title, equals Agostini"),
]
DATE_CHECK = ("Checked before printing: the Dymer strike hit on the night "
              "of 22 Nov — its toll and the two rescues were confirmed on "
              "Monday 23 Nov. COP31's collapse was confirmed in Monday's "
              "editions after the summit broke up overnight. BepiColombo "
              "is left out as Sunday background. All other stories are "
              "dated Monday 23 November 2026.")
DECK = ("Huang returns and Nvidia leaps, a corvette sinks at Benghazi, "
        "Iran defies the Hormuz blockade: one Monday.")


# -------------------------------------------------------------------- page
def badge(d, x, y, n, size=22):
    d.ellipse([x, y, x + size, y + size], fill=RED)
    d.text((x + size / 2, y + size / 2), str(n), font=font(F_SANS_B, 12),
           fill=WHITE, anchor="mm")


def paint(page, st, x, y, w, h, seed):
    scene = SCENES[st["art"]](int(round(w)), int(round(h)),
                              REGION_COLOUR[st["region"]],
                              random.Random(seed))
    page.paste(scene, (int(round(x)), int(round(y))))


def hero_card(page, d, st, x, y, w, h, n):
    d.rectangle([x, y, x + w, y + h], fill=WHITE, outline=INK, width=2)
    ink = REGION_COLOUR[st["region"]]
    d.rectangle([x, y, x + w, y + 5], fill=ink)
    paint(page, st, x + 7, y + 10, w - 14, 64, SEED + n)
    ty = y + 80
    badge(d, x + 8, ty, n, 22)
    d.text((x + 37, ty + 4), st["region"], font=font(F_SANS_B, 11), fill=ink)
    d.text((x + w - 8, ty + 5), st.get("src", ""), font=font(F_SANS, 9),
           fill=FADED, anchor="ra")
    hy = para(d, st["headline"], x + 9, ty + 27, w - 18, font(F_SERIF, 18),
              INK, 19, 3)
    para(d, st["body"], x + 9, hy + 2, w - 18, font(F_SANS, 10.5), FADED,
         13, 3)


def feature_card(page, d, st, x, y, w, h, n):
    d.rectangle([x, y, x + w, y + h], fill=WHITE, outline=INK, width=2)
    ink = REGION_COLOUR[st["region"]]
    d.rectangle([x, y, x + w, y + 4], fill=ink)
    paint(page, st, x + 6, y + 8, w - 12, 54, SEED + n)
    ty = y + 66
    badge(d, x + 7, ty, n, 18)
    d.text((x + 30, ty + 3), st["region"], font=font(F_SANS_B, 9.5), fill=ink)
    d.text((x + w - 7, ty + 4), st.get("src", ""), font=font(F_SANS, 8),
           fill=FADED, anchor="ra")
    hy = para(d, st["headline"], x + 8, ty + 20, w - 16, font(F_SERIF, 12.5),
              INK, 13.5, 2)
    para(d, st["body"], x + 8, hy + 1, w - 16, font(F_SANS, 8.8), FADED,
         10.5, 2)


def masthead(d):
    d.text((MARGIN, 20), "THE DAILY WORLD · THE WORLD IN ONE DAY",
           font=font(F_SANS_B, 13), fill=RED)
    right = "37 STORIES · 6 REGIONS · EVERY ONE DATED MONDAY 23 NOVEMBER 2026"
    d.text((SIDE - MARGIN, 20), right, font=font(F_SANS_B, 13), fill=INK,
           anchor="ra")
    d.line([MARGIN, 40, SIDE - MARGIN, 40], fill=INK, width=3)
    d.text((SIDE / 2, 47), "Monday 23 November 2026", font=font(F_SERIF, 54),
           fill=INK, anchor="ma")
    d.line([MARGIN, 110, SIDE - MARGIN, 110], fill=INK, width=1)
    d.text((SIDE / 2, 116), DECK, font=font(F_SERIF_IT, 17.5), fill=FADED,
           anchor="ma")


def figures_band(d, top):
    cell = BODY_W / 6
    d.rectangle([MARGIN, top, SIDE - MARGIN, top + 56], fill=PAPER_DK,
                outline=INK, width=2)
    for i, (val, cap) in enumerate(FIGURES):
        cx = MARGIN + i * cell
        if i:
            d.line([cx, top, cx, top + 56], fill=INK, width=1)
        d.text((cx + cell / 2, top + 5), val, font=font(F_SERIF, 24),
               fill=RED, anchor="ma")
        for j, line in enumerate(wrap(d, cap, font(F_SANS, 9.5),
                                      cell - 12)[:2]):
            d.text((cx + cell / 2, top + 34 + j * 11), line,
                   font=font(F_SANS, 9.5), fill=FADED, anchor="ma")


def tally_band(d, top):
    d.rectangle([MARGIN, top, SIDE - MARGIN, top + 26], fill=INK)
    label = "   ·   ".join(f"{name} {n}" for name, n in TALLY)
    d.text((SIDE / 2, top + 5), label, font=font(F_SANS_B, 13.5), fill=WHITE,
           anchor="ma")


def briefs_section(d, top, gap):
    d.text((MARGIN, top), "ALSO ON MONDAY 23 NOVEMBER — THE REST OF THE DAY",
           font=font(F_SANS_B, 13), fill=INK)
    d.line([MARGIN, top + 19, SIDE - MARGIN, top + 19], fill=INK, width=1)
    col_w = (BODY_W - 2 * gap) / 3
    bf = font(F_SANS, 9.2)
    per_col = (len(BRIEFS) + 2) // 3
    for i, (n, text) in enumerate(BRIEFS):
        col, row = divmod(i, per_col)
        bx = MARGIN + col * (col_w + gap)
        by = top + 26 + row * 14.5
        d.text((bx, by), f"{n}.", font=font(F_SANS_B, 9.2), fill=RED)
        d.text((bx + 20, by), one_line(d, text, bf, col_w - 22), font=bf,
               fill=INK)


def date_check(d):
    top = 916
    d.rectangle([MARGIN, top, SIDE - MARGIN, top + 54], outline=RED, width=2)
    d.text((MARGIN + 10, top + 7), "DATE CHECK", font=font(F_SANS_B, 12),
           fill=RED)
    for j, line in enumerate(wrap(d, DATE_CHECK, font(F_SANS, 10),
                                  BODY_W - 24)[:2]):
        d.text((MARGIN + 12, top + 25 + j * 13), line, font=font(F_SANS, 10),
               fill=INK)
    d.text((SIDE - MARGIN, top + 62),
           "Sources credited per panel · Original artwork",
           font=font(F_SANS, 9.5), fill=FADED, anchor="ra")
    d.text((MARGIN, top + 62), "THE DAILY WORLD — Monday 23 November 2026",
           font=font(F_SANS, 9.5), fill=FADED)


def store(img, path):
    """Save the page; quantise without dithering only if detail overflows
    the one-megabyte budget."""
    img.save(path, optimize=True)
    if os.path.getsize(path) > 1_000_000:
        img.quantize(colors=256, method=Image.MEDIANCUT,
                     dither=Image.NONE).save(path, optimize=True)
    return os.path.getsize(path)


def build():
    img = Image.new("RGB", (SIDE, SIDE), PAPER)
    d = ImageDraw.Draw(img)
    masthead(d)
    figures_band(d, 146)
    tally_band(d, 210)
    gap = 10
    hero_w = (BODY_W - 2 * gap) / 3
    for i, st in enumerate(HEROES):
        hero_card(img, d, st, MARGIN + i * (hero_w + gap), 246, hero_w, 190,
                  i + 1)
    mid_w = (BODY_W - 4 * gap) / 5
    for r in range(2):
        for i, st in enumerate(FEATURES[r * 5:(r + 1) * 5]):
            feature_card(img, d, st, MARGIN + i * (mid_w + gap),
                         444 + r * 158, mid_w, 150, r * 5 + i + 4)
    briefs_section(d, 764, gap)
    date_check(d)
    size = store(img, os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "entry.png"))
    print(f"wrote entry.png ({size} bytes)")


if __name__ == "__main__":
    build()
