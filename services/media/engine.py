"""Template-driven video renderer.

Evolved from the 神机妙述 demo renderer. Input: validated Storyboard +
per-scene TTS results. Output: muxed MP4 + QC report.

PIL note: ImageDraw's "RGBA" blend mode only applies to RGB base images; on
RGBA frames fills REPLACE pixels. All translucent drawing therefore goes
through small scratch layers + alpha_composite.
"""
import math
import os
import subprocess
import time
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FPS = 30
XF = 0.4
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}

FONT_CN = os.environ.get("MIAOSHU_FONT_CN", "/System/Library/Fonts/Hiragino Sans GB.ttc")
FONT_CN_BOLD_INDEX = int(os.environ.get("MIAOSHU_FONT_CN_BOLD_INDEX", "2"))
FONT_EN = os.environ.get("MIAOSHU_FONT_EN", "/System/Library/Fonts/HelveticaNeue.ttc")

_fonts = {}
def F(kind, size):
    key = (kind, size)
    if key not in _fonts:
        if kind == "cn":     _fonts[key] = ImageFont.truetype(FONT_CN, size, index=0)
        elif kind == "cnb":  _fonts[key] = ImageFont.truetype(FONT_CN, size, index=FONT_CN_BOLD_INDEX)
        elif kind == "en":   _fonts[key] = ImageFont.truetype(FONT_EN, size, index=10)
        elif kind == "enb":  _fonts[key] = ImageFont.truetype(FONT_EN, size, index=1)
    return _fonts[key]

WHITE  = (244, 247, 255)
MUTED  = (142, 160, 191)
CYAN   = (34, 211, 238)
VIOLET = (139, 92, 246)
GREEN  = (52, 211, 153)
WARM_A = (245, 158, 11)
WARM_B = (244, 63, 94)
CARD_FILL = (255, 255, 255, 14)
CARD_LINE = (255, 255, 255, 38)
ACCENTS = [CYAN, VIOLET, WARM_A, GREEN]

def ease_out(t):  return 1 - (1 - t) ** 3
def ease_io(t):   return t * t * (3 - 2 * t)
def clamp01(t):   return max(0.0, min(1.0, t))
def anim(t, start, dur=0.5):
    return ease_out(clamp01((t - start) / dur))

def tsize(font, text):
    b = font.getbbox(text)
    return b[2] - b[0], b[3] - b[1], b[1]

def A(color, alpha):
    return color[:3] + (int((color[3] if len(color) > 3 else 255) * alpha),)

# ---------- composited drawing primitives ----------
def rrect(frame, box, radius, fill=None, outline=None, width=1):
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 <= x0 or y1 <= y0:
        return
    sc = Image.new("RGBA", (x1 - x0 + 4, y1 - y0 + 4), (0, 0, 0, 0))
    ImageDraw.Draw(sc).rounded_rectangle(
        [2, 2, x1 - x0 + 1, y1 - y0 + 1], radius=radius,
        fill=fill, outline=outline, width=width)
    frame.alpha_composite(sc, (x0 - 2, y0 - 2))

def ellipse(frame, box, fill):
    x0, y0, x1, y1 = [int(v) for v in box]
    sc = Image.new("RGBA", (x1 - x0 + 4, y1 - y0 + 4), (0, 0, 0, 0))
    ImageDraw.Draw(sc).ellipse([2, 2, x1 - x0 + 1, y1 - y0 + 1], fill=fill)
    frame.alpha_composite(sc, (x0 - 2, y0 - 2))

def poly(frame, pts, fill):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2
    sc = Image.new("RGBA", (int(max(xs)) - x0 + 4, int(max(ys)) - y0 + 4), (0, 0, 0, 0))
    ImageDraw.Draw(sc).polygon([(p[0] - x0, p[1] - y0) for p in pts], fill=fill)
    frame.alpha_composite(sc, (x0, y0))

def lines(frame, pts, fill, width):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)) - width - 2, int(min(ys)) - width - 2
    sc = Image.new("RGBA", (int(max(xs)) - x0 + width + 4,
                            int(max(ys)) - y0 + width + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(sc)
    shifted = [(p[0] - x0, p[1] - y0) for p in pts]
    d.line(shifted, fill=fill, width=width, joint="curve")
    r = width / 2 - 0.5
    for p in (shifted[0], shifted[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)
    frame.alpha_composite(sc, (x0, y0))

def txt(frame, xy, text, font, fill, alpha=1.0, dy=0, anchor=None):
    if alpha <= 0.004 or not text:
        return 0
    b = font.getbbox(text)
    w, h = b[2] - b[0], b[3] - b[1]
    if w <= 0 or h <= 0:
        return 0
    sc = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    ImageDraw.Draw(sc).text((4 - b[0], 4 - b[1]), text, font=font,
                            fill=fill[:3] + (int(255 * alpha),))
    x, y = xy[0], xy[1] + dy
    if anchor == "mm":
        frame.alpha_composite(sc, (int(x - w / 2 - 4), int(y - h / 2 - 4)))
    else:
        frame.alpha_composite(sc, (int(x + b[0] - 4), int(y + b[1] - 4)))
    return w

def grad_tile(w, h, c1, c2, horizontal=True):
    w, h = max(1, int(w)), max(1, int(h))
    ax = np.linspace(0, 1, w)[None, :] if horizontal else np.linspace(0, 1, h)[:, None]
    arr = np.zeros((h, w, 3))
    for i in range(3):
        arr[..., i] = c1[i] * (1 - ax) + c2[i] * ax
    return Image.fromarray(arr.astype(np.uint8), "RGB")

def grad_text(frame, xy, text, font, c1, c2, alpha=1.0, dy=0, anchor=None):
    if alpha <= 0.004:
        return 0
    b = font.getbbox(text)
    w, h = b[2] - b[0], b[3] - b[1]
    mask = Image.new("L", (w + 8, h + 8), 0)
    ImageDraw.Draw(mask).text((4 - b[0], 4 - b[1]), text, font=font, fill=255)
    g = grad_tile(w + 8, h + 8, c1, c2).convert("RGBA")
    g.putalpha(mask.point(lambda v: int(v * alpha)))
    x, y = xy[0], xy[1] + dy
    if anchor == "mm":
        frame.alpha_composite(g, (int(x - w / 2 - 4), int(y - h / 2 - 4)))
    else:
        frame.alpha_composite(g, (int(x + b[0] - 4), int(y + b[1] - 4)))
    return w

def grad_rrect(frame, box, radius, c1, c2, alpha=1.0):
    x0, y0, x1, y1 = [int(v) for v in box]
    g = grad_tile(x1 - x0, y1 - y0, c1, c2).convert("RGBA")
    m = Image.new("L", g.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, x1 - x0 - 1, y1 - y0 - 1],
                                        radius=radius, fill=int(255 * alpha))
    g.putalpha(m)
    frame.alpha_composite(g, (x0, y0))

def card(frame, box, radius=20, fill=CARD_FILL, line=CARD_LINE, alpha=1.0, width=2):
    rrect(frame, box, radius, fill=A(fill, alpha), outline=A(line, alpha), width=width)

def draw_icon(frame, kind, cx, cy, s, color, alpha=1.0):
    c = A(color, alpha)
    wd = max(3, int(s * 0.18))
    if kind == "x":
        lines(frame, [(cx - s / 2, cy - s / 2), (cx + s / 2, cy + s / 2)], c, wd)
        lines(frame, [(cx + s / 2, cy - s / 2), (cx - s / 2, cy + s / 2)], c, wd)
    elif kind == "check":
        lines(frame, [(cx - s * 0.52, cy + s * 0.02), (cx - s * 0.12, cy + s * 0.40),
                      (cx + s * 0.55, cy - s * 0.38)], c, wd)
    elif kind == "image":
        rrect(frame, [cx - s * 0.6, cy - s * 0.48, cx + s * 0.6, cy + s * 0.48],
              int(s * 0.16), outline=c, width=max(3, int(s * 0.09)))
        ellipse(frame, [cx - s * 0.32, cy - s * 0.28, cx - s * 0.08, cy - s * 0.04], c)
        poly(frame, [(cx - s * 0.42, cy + s * 0.30), (cx - s * 0.02, cy - s * 0.10),
                     (cx + s * 0.22, cy + s * 0.14), (cx + s * 0.38, cy - s * 0.02),
                     (cx + s * 0.44, cy + s * 0.30)], c)
    elif kind == "video":
        rrect(frame, [cx - s * 0.6, cy - s * 0.48, cx + s * 0.6, cy + s * 0.48],
              int(s * 0.16), outline=c, width=max(3, int(s * 0.09)))
        poly(frame, [(cx - s * 0.14, cy - s * 0.22), (cx - s * 0.14, cy + s * 0.22),
                     (cx + s * 0.26, cy)], c)
    elif kind == "doc":
        rrect(frame, [cx - s * 0.42, cy - s * 0.5, cx + s * 0.42, cy + s * 0.5],
              int(s * 0.12), outline=c, width=max(3, int(s * 0.09)))
        for i in (-1, 0, 1):
            lines(frame, [(cx - s * 0.22, cy + i * s * 0.22),
                          (cx + s * 0.22, cy + i * s * 0.22)], c, max(2, int(s * 0.07)))
    elif kind == "bank":
        poly(frame, [(cx - s * 0.55, cy - s * 0.12), (cx, cy - s * 0.5),
                     (cx + s * 0.55, cy - s * 0.12)], c)
        for dx in (-0.36, 0, 0.36):
            lines(frame, [(cx + dx * s, cy - s * 0.02), (cx + dx * s, cy + s * 0.34)],
                  c, max(3, int(s * 0.1)))
        lines(frame, [(cx - s * 0.5, cy + s * 0.48), (cx + s * 0.5, cy + s * 0.48)],
              c, max(3, int(s * 0.1)))

def chip(frame, xy, text, font, alpha=1.0, accent=None, pad=(26, 13),
         icon=None, icon_color=None):
    w, h, ot = tsize(font, text)
    isz = int((h + ot) * 0.62)
    iw = (isz + 18) if icon else 0
    box = [xy[0], xy[1], xy[0] + w + iw + pad[0] * 2, xy[1] + h + ot + pad[1] * 2]
    fill = (accent + (30,)) if accent else CARD_FILL
    line = (accent + (110,)) if accent else CARD_LINE
    card(frame, box, radius=(box[3] - box[1]) // 2, fill=fill, line=line, alpha=alpha)
    tx = xy[0] + pad[0]
    if icon:
        draw_icon(frame, icon, tx + isz / 2, (box[1] + box[3]) / 2, isz,
                  icon_color or accent or MUTED, alpha)
        tx += iw
    txt(frame, (tx, xy[1] + pad[1] - ot), text, font,
        accent if accent else WHITE, alpha)
    return box[2] - box[0], box[3] - box[1]

def chip_width(text, font, icon=False, pad=26):
    w, h, ot = tsize(font, text)
    isz = int((h + ot) * 0.62)
    return w + ((isz + 18) if icon else 0) + pad * 2

def progress(frame, box, frac, alpha=1.0):
    x0, y0, x1, y1 = [int(v) for v in box]
    rrect(frame, box, (y1 - y0) // 2, fill=A((255, 255, 255, 20), alpha))
    if frac > 0.01:
        wpx = max(int((x1 - x0) * clamp01(frac)), y1 - y0)
        grad_rrect(frame, [x0, y0, x0 + wpx, y1], (y1 - y0) // 2, CYAN, VIOLET, alpha)

def logo_mark(frame, xy, size, alpha=1.0):
    grad_rrect(frame, [xy[0], xy[1], xy[0] + size, xy[1] + size],
               int(size * 0.28), CYAN, VIOLET, alpha)
    s = size
    poly(frame, [(xy[0] + s * 0.40, xy[1] + s * 0.30), (xy[0] + s * 0.40, xy[1] + s * 0.74),
                 (xy[0] + s * 0.78, xy[1] + s * 0.52)], A((255, 255, 255, 240), alpha))
    ellipse(frame, [xy[0] + s * 0.22, xy[1] + s * 0.24, xy[0] + s * 0.32, xy[1] + s * 0.34],
            A((255, 255, 255, 210), alpha))

def mini_lines(frame, x, y, widths, gap=26, h=14, alpha=1.0, color=(255, 255, 255, 46)):
    for i, w_ in enumerate(widths):
        rrect(frame, [x, y + i * gap, x + w_, y + i * gap + h], h // 2,
              fill=A(color, alpha))

def browser(frame, box, alpha=1.0, url=""):
    x0, y0, x1, y1 = box
    card(frame, box, radius=22, fill=(16, 22, 40, 235), line=CARD_LINE, alpha=alpha)
    for i, c in enumerate([(255, 96, 92), (255, 189, 68), (0, 202, 78)]):
        ellipse(frame, [x0 + 26 + i * 30, y0 + 22, x0 + 42 + i * 30, y0 + 38],
                A(c + (200,), alpha))
    card(frame, [x0 + 130, y0 + 16, x1 - 26, y0 + 44], radius=14,
         fill=(255, 255, 255, 12), line=(255, 255, 255, 0), alpha=alpha)
    txt(frame, (x0 + 148, y0 + 19), url, F("en", 19), MUTED, alpha)
    rrect(frame, [x0 + 2, y0 + 57, x1 - 2, y0 + 59], 1,
          fill=A((255, 255, 255, 30), alpha))

# ---------- background (cached per size) ----------
_bg_cache = {}
def get_bg(W, H):
    if (W, H) in _bg_cache:
        return _bg_cache[(W, H)]
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    r = 10 + 8 * y + 4 * x
    g = 15 + 10 * y + 3 * x
    b = 28 + 16 * y + 6 * x
    cx, cy = 0.5, 0.42
    if W > H:
        d = np.sqrt((x - cx) ** 2 * 1.4 + (y - cy) ** 2)
    else:
        d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2 * 1.2)
    v = 1 - 0.35 * np.clip(d / 0.75, 0, 1) ** 2
    arr = np.stack([r * v, g * v, b * v], -1)
    arr += np.random.normal(0, 1.1, arr.shape)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for gx in range(0, W + 1, 96):
        gd.line([(gx, 0), (gx, H)], fill=(160, 190, 255, 7), width=1)
    for gy in range(0, H + 1, 96):
        gd.line([(0, gy), (W, gy)], fill=(160, 190, 255, 7), width=1)
    base.alpha_composite(grid)
    glow_c = _make_glow(CYAN, 420 if W > H else 380)
    glow_v = _make_glow(VIOLET, 460 if W > H else 420)
    _bg_cache[(W, H)] = (base, glow_c, glow_v)
    return _bg_cache[(W, H)]

def _make_glow(color, radius):
    im = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([radius * 0.45, radius * 0.45,
                                radius * 1.55, radius * 1.55], fill=color + (90,))
    return im.filter(ImageFilter.GaussianBlur(radius * 0.35))

def new_frame(W, H, T):
    base, gc, gv = get_bg(W, H)
    f = base.copy()
    f.alpha_composite(gc, (int(-280 + 110 * math.sin(T * 0.21)),
                           int(-280 + 80 * math.cos(T * 0.17))))
    f.alpha_composite(gv, (int(W - 520 + 120 * math.sin(T * 0.16 + 2)),
                           int(H - 630 + 90 * math.cos(T * 0.19 + 1))))
    return f

# ---------- chrome ----------
def brand_bar(frame, C, alpha=1.0):
    x = 70 if C["W"] > C["H"] else 56
    logo_mark(frame, (x, 52), 40, alpha)
    w = txt(frame, (x + 58, 56), C["brand"]["name"], F("cnb", 30), WHITE, alpha)
    if C["brand"].get("byline"):
        txt(frame, (x + 58 + w + 22, 64), C["brand"]["byline"], F("cn", 21), MUTED, alpha)

def step_dots(frame, C, idx, alpha=1.0):
    n = C["nscenes"]
    m = 70 if C["W"] > C["H"] else 56
    x0 = C["W"] - m - n * 26
    for i in range(n):
        cx = x0 + i * 26
        if i == idx:
            rrect(frame, [cx - 4, 62, cx + 16, 74], 6, fill=A(CYAN + (230,), alpha))
        else:
            ellipse(frame, [cx, 62, cx + 12, 74], A((255, 255, 255, 56), alpha))

def _wrap(text, font, maxw):
    w, _, _ = tsize(font, text)
    if w <= maxw:
        return [text]
    seps = [i for i, c in enumerate(text) if c in "，、？。！ "]
    if not seps:
        return [text]
    mid = min(seps, key=lambda i: abs(i - len(text) // 2))
    return [text[:mid + 1].strip(), text[mid + 1:].strip()]

def subtitle(frame, C, text, alpha):
    if alpha <= 0.01 or not text:
        return
    W, H = C["W"], C["H"]
    font = F("cn", 37 if W > H else 33)
    linestxt = _wrap(text, font, W - 200)
    ws = [tsize(font, l)[0] for l in linestxt]
    _, h, ot = tsize(font, linestxt[0])
    lh = h + ot + 16
    pw = max(ws) + 84
    ph = lh * len(linestxt) + 36
    x0, y0 = (W - pw) // 2, H - (74 if W > H else 96) - ph
    card(frame, [x0, y0, x0 + pw, y0 + ph], radius=min(ph // 2, 44),
         fill=(8, 12, 24, 178), line=(255, 255, 255, 30), alpha=alpha)
    for i, l in enumerate(linestxt):
        txt(frame, ((W - ws[i]) // 2, y0 + 22 - ot + i * lh), l, font, WHITE,
            alpha, dy=8)

# =============================================================
# TEMPLATES — each draws (frame, t, P, C); C = {W, H, brand, nscenes}
# =============================================================

def t_hook(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    fsz = 92 if horiz else 80
    y1, y2 = (330, 402) if horiz else (560, 660)
    f = F("cnb", fsz)
    a1 = anim(t, 0.15, 0.55)
    txt(frame, (W // 2, y1), P.get("line1", ""), f, WHITE, a1,
        dy=int(36 * (1 - a1)), anchor="mm")
    a2 = anim(t, 0.55, 0.55)
    if a2 > 0:
        segs = [(P.get("line2_pre", ""), None), (P.get("line2_hi", ""), (WARM_A, WARM_B)),
                (P.get("line2_post", ""), None)]
        total = sum(tsize(f, s)[0] for s, _ in segs if s)
        x = (W - total) // 2
        dy = int(36 * (1 - a2))
        for s, grad in segs:
            if not s:
                continue
            if grad:
                x += grad_text(frame, (x, y2), s, f, grad[0], grad[1], a2, dy=dy)
            else:
                x += txt(frame, (x, y2), s, f, WHITE, a2, dy=dy)
    chips = P.get("chips", [])
    font = F("cn", 30)
    if horiz:
        rows = [chips]
        ybase = 640
    else:
        rows = [chips[:3], chips[3:]] if len(chips) > 3 else [chips]
        ybase = 920
    for r, row in enumerate(rows):
        if not row:
            continue
        ws = [chip_width(s, font, icon=True) for s in row]
        x = (W - sum(ws) - 24 * (len(row) - 1)) // 2
        for i, s in enumerate(row):
            k = (r * len(rows[0]) + i) if len(rows) > 1 else i
            a = anim(t, 1.7 + k * 0.16, 0.4)
            if a > 0:
                chip(frame, (x, int(ybase + r * 92 + 22 * (1 - a))), s, font, a,
                     icon="x", icon_color=WARM_B)
            x += ws[i] + 24

def t_options(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    headline = P.get("headline", "")
    if horiz:
        a1 = anim(t, 0.1, 0.5)
        txt(frame, (W // 2, 265), headline, F("cnb", 72), WHITE, a1,
            dy=int(30 * (1 - a1)), anchor="mm")
    else:
        parts = _wrap(headline, F("cnb", 66), W - 120)
        for i, p in enumerate(parts):
            a1 = anim(t, 0.1 + i * 0.15, 0.5)
            txt(frame, (W // 2, 480 + i * 105), p, F("cnb", 66), WHITE, a1,
                dy=int(30 * (1 - a1)), anchor="mm")
    url = P.get("input_url")
    y_after = 0
    if url:
        a2 = anim(t, 0.45, 0.5)
        if a2 > 0:
            bw, bh = (1080, 118) if horiz else (960, 110)
            x0 = (W - bw) // 2
            y0 = 400 if horiz else 720
            card(frame, [x0, y0, x0 + bw, y0 + bh], radius=26,
                 fill=(16, 22, 40, 235), line=(255, 255, 255, 60), alpha=a2)
            n = int(clamp01((t - 0.9) / 1.2) * len(url))
            fe = F("en", 40 if horiz else 38)
            wt = txt(frame, (x0 + 42, y0 + 34), url[:n], fe, WHITE, a2)
            if t < 2.4 and int(t * 2.5) % 2 == 0:
                rrect(frame, [x0 + 48 + wt, y0 + 28, x0 + 51 + wt, y0 + bh - 28], 1,
                      fill=A(CYAN + (220,), a2))
            ab = anim(t, 2.4, 0.4)
            if ab > 0:
                blabel = P.get("button", "生成视频 →")
                grad_rrect(frame, [x0 + bw - 262, y0 + 22, x0 + bw - 22, y0 + bh - 22],
                           (bh - 44) // 2 + 4, CYAN, VIOLET, ab)
                txt(frame, (x0 + bw - 232, y0 + 40), blabel, F("cnb", 29), (10, 14, 26), ab)
        y_after = (586 if horiz else 900)
        opt_start = 3.0
    else:
        y_after = (470 if horiz else 780)
        opt_start = 0.9
    opts = P.get("options", [])[:3]
    if not opts:
        return
    ch = 128
    if horiz:
        n = len(opts)
        cw = min(480, (W - 200 - 40 * (n - 1)) // max(n, 1))
        x = (W - cw * n - 40 * (n - 1)) // 2
        for i, o in enumerate(opts):
            a = anim(t, opt_start + i * 0.3, 0.45)
            if a > 0:
                y0 = int(y_after + 24 * (1 - a))
                card(frame, [x, y0, x + cw, y0 + ch], radius=20, alpha=a)
                draw_icon(frame, o.get("icon", "image"), x + 62, y0 + ch / 2, 52,
                          ACCENTS[i % 4], a)
                txt(frame, (x + 118, y0 + 26), o.get("title", ""), F("cnb", 29), WHITE, a)
                txt(frame, (x + 118, y0 + 76), o.get("sub", ""), F("cn", 23), MUTED, a * 0.9)
            x += cw + 40
    else:
        cw = 960
        x = (W - cw) // 2
        for i, o in enumerate(opts):
            a = anim(t, opt_start + i * 0.3, 0.45)
            if a > 0:
                y0 = int(y_after + i * 156 + 24 * (1 - a))
                card(frame, [x, y0, x + cw, y0 + ch], radius=20, alpha=a)
                draw_icon(frame, o.get("icon", "image"), x + 66, y0 + ch / 2, 52,
                          ACCENTS[i % 4], a)
                txt(frame, (x + 126, y0 + 26), o.get("title", ""), F("cnb", 29), WHITE, a)
                txt(frame, (x + 126, y0 + 76), o.get("sub", ""), F("cn", 23), MUTED, a * 0.9)

def t_features(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    hx = 110 if horiz else 70
    a1 = anim(t, 0.1, 0.5)
    txt(frame, (hx, 130 if horiz else 230), P.get("headline", ""),
        F("cnb", 66 if horiz else 58), WHITE, a1, dy=int(24 * (1 - a1)))
    txt(frame, (hx + 4, 245 if horiz else 330), P.get("subhead", ""),
        F("cn", 31 if horiz else 28), MUTED, anim(t, 0.35, 0.5))
    ab = anim(t, 0.5, 0.6)
    bx = [110, 360, 890, 900] if horiz else [70, 420, 1010, 940]
    if ab > 0:
        browser(frame, bx, ab, url=P.get("browser_url", ""))
        ix = bx[0] + 40
        mini_lines(frame, ix, bx[1] + 90, [420, 300], gap=40, h=22, alpha=ab,
                   color=(255, 255, 255, 70))
        rrect(frame, [ix, bx[1] + 200, ix + 410, bx[1] + 340], 14,
              fill=A((120, 150, 255, 26), ab))
        poly(frame, [(ix + 180, bx[1] + 245), (ix + 180, bx[1] + 295),
                     (ix + 226, bx[1] + 270)], A((255, 255, 255, 90), ab))
        mini_lines(frame, ix + 450, bx[1] + 215, [220, 250, 190], gap=42, h=16, alpha=ab)
        cw3 = (bx[2] - bx[0] - 80 - 32) // 3
        for i in range(3):
            cx0 = ix + i * (cw3 + 26)
            card(frame, [cx0, bx[1] + 370, cx0 + cw3, bx[1] + 470], radius=14,
                 fill=(255, 255, 255, 10), line=(255, 255, 255, 30), alpha=ab)
            mini_lines(frame, cx0 + 24, bx[1] + 396, [min(140, cw3 - 60), min(100, cw3 - 90)],
                       gap=30, h=13, alpha=ab)
        if 0.8 < t < 4.0:
            prog = (t - 0.8) / 3.2
            by = bx[1] + 10 + prog * (bx[3] - bx[1] - 40)
            bw_ = bx[2] - bx[0] - 10
            beam = grad_tile(bw_, 4, CYAN, VIOLET).convert("RGBA")
            beam.putalpha(160)
            frame.alpha_composite(beam, (bx[0] + 5, int(by)))
            gl = Image.new("RGBA", (bw_, 60), (0, 0, 0, 0))
            ImageDraw.Draw(gl).rectangle([0, 0, bw_, 60], fill=CYAN + (28,))
            gl = gl.filter(ImageFilter.GaussianBlur(12))
            frame.alpha_composite(gl, (bx[0] + 5, int(by) - 56))
    cards = P.get("cards", [])[:3]
    for i, c in enumerate(cards):
        st = 1.4 + i * 0.8
        a = anim(t, st, 0.5)
        if a <= 0:
            continue
        ac = ACCENTS[i % 4]
        if horiz:
            x0, y0, cw_ = 960 + int(60 * (1 - a)), 360 + i * 152, 850
            tagf, mainf, evf = F("cn", 21), F("cnb", 30), F("cn", 23)
            toff = 150
        else:
            x0, y0, cw_ = 70 + int(60 * (1 - a)), 990 + i * 150, 940
            tagf, mainf, evf = F("cn", 20), F("cnb", 27), F("cn", 22)
            toff = 138
        card(frame, [x0, y0, x0 + cw_, y0 + 126], radius=18, alpha=a)
        chip(frame, (x0 + 26, y0 + 23), c.get("tag", f"卖点 {i+1}"), tagf, a,
             accent=ac, pad=(15, 8))
        txt(frame, (x0 + toff, y0 + 28), c.get("text", ""), mainf, WHITE, a)
        txt(frame, (x0 + toff + 2, y0 + 82), c.get("evidence", ""), evf, MUTED, a * 0.9)
    done = P.get("done_chip")
    if done:
        af = anim(t, 1.4 + len(cards) * 0.8 + 0.8, 0.5)
        if af > 0:
            dx0 = 960 if horiz else 70
            dy0 = 360 + len(cards) * 152 - 10 if horiz else 990 + len(cards) * 150 - 12
            chip(frame, (dx0, int(dy0 + 18 * (1 - af))), done, F("cnb", 27), af,
                 accent=GREEN, icon="check")

def t_editor(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    a1 = anim(t, 0.1, 0.5)
    txt(frame, (W // 2, 165 if horiz else 235), P.get("headline", ""),
        F("cnb", 66 if horiz else 58), WHITE, a1, dy=int(24 * (1 - a1)), anchor="mm")
    a2 = anim(t, 0.4, 0.5)
    if a2 <= 0:
        return
    edit_at = 1.5
    lines_ = P.get("lines", [])[:4]
    ei = P.get("edit_index", 1) % max(len(lines_), 1)
    enew = P.get("edit_new", "")
    if horiz:
        ex, ey, ew, eh = 150, 270, 760, 620
        px, py, pw_, ph_ = 990, 270, 780, 620
    else:
        ex, ey, ew, eh = 70, 330, 940, 600
        px, py, pw_, ph_ = 70, 980, 940, 560
    card(frame, [ex, ey, ex + ew, ey + eh], radius=22, fill=(16, 22, 40, 235), alpha=a2)
    txt(frame, (ex + 36, ey + 28), P.get("panel_title", "脚本编辑器"),
        F("cnb", 27), MUTED, a2)
    font = F("cn", 31 if horiz else 30)
    gap = 120 if horiz else 112
    for i, line in enumerate(lines_):
        ly = ey + 118 + i * gap
        sel = i == ei
        ea = anim(t, edit_at, 0.35) if sel else 0
        if sel and ea > 0:
            rrect(frame, [ex + 24, ly - 20, ex + ew - 24, ly + 58], 12,
                  fill=A(CYAN + (30,), ea), outline=A(CYAN + (140,), ea), width=2)
        shown, color, fnt = line, WHITE, font
        if sel and t > edit_at + 0.4 and enew:
            n = int(clamp01((t - edit_at - 0.4) / 1.1) * len(enew))
            shown, color, fnt = enew[:n], CYAN, F("cnb", 31 if horiz else 30)
        txt(frame, (ex + 46, ly), f"{i + 1:02d}", F("en", 24), MUTED, a2 * 0.8, dy=6)
        txt(frame, (ex + 108, ly), shown, fnt, color, a2)
    chip(frame, (ex + 36, ey + eh - 92), P.get("sync_chip", "改动实时同步到镜头"),
         F("cn", 22), anim(t, edit_at + 1.0, 0.5), accent=CYAN, pad=(15, 8))
    card(frame, [px, py, px + pw_, py + ph_], radius=22, alpha=a2)
    txt(frame, (px + 36, py + 28), P.get("preview_title", "镜头预览"),
        F("cnb", 27), MUTED, a2)
    vx, vy = px + 36, py + 88
    vw, vh = pw_ - 72, ph_ - 220
    rrect(frame, [vx, vy, vx + vw, vy + vh], 16, fill=A((9, 13, 26, 255), a2))
    upd = anim(t, edit_at + 1.5, 0.4)
    g = grad_tile(vw - 120, 56, CYAN, VIOLET).convert("RGBA")
    g.putalpha(int(70 * a2))
    frame.alpha_composite(g, (vx + 60, vy + 56))
    before = P.get("preview_before", ["", ""])
    after = P.get("preview_after", ["", ""])
    big = after if upd > 0.5 else before
    bf = F("cnb", 50)
    txt(frame, (vx + vw // 2, vy + vh // 2 - 40), big[0], bf, WHITE, a2, anchor="mm")
    txt(frame, (vx + vw // 2, vy + vh // 2 + 40), big[1] if len(big) > 1 else "", bf,
        CYAN if upd > 0.5 else WHITE, a2, anchor="mm")
    if upd > 0:
        flash = upd * (1 - anim(t, edit_at + 2.4, 0.6))
        rrect(frame, [vx, vy, vx + vw, vy + vh], 16,
              outline=A(CYAN + (200,), flash), width=3)
        chip(frame, (vx + vw - 205, vy + vh - 64), "已更新", F("cn", 21),
             upd, accent=GREEN, icon="check", pad=(13, 7))
    progress(frame, (vx, vy + vh + 38, vx + vw, vy + vh + 50),
             0.32 if upd < 0.5 else 0.32 + 0.3 * anim(t, edit_at + 1.6, 1.2), a2)

def t_formats(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    a1 = anim(t, 0.1, 0.5)
    txt(frame, (W // 2, 165 if horiz else 235), P.get("headline", ""),
        F("cnb", 66 if horiz else 58), WHITE, a1, dy=int(24 * (1 - a1)), anchor="mm")
    labels = [i.get("label", "") for i in P.get("items", [])][:3]
    while len(labels) < 3:
        labels.append("")
    if horiz:
        specs = [(labels[0], 300, 330, 640, 360, 0.4),
                 (labels[1], 1030, 300, 236, 420, 0.65),
                 (labels[2], 1360, 340, 340, 340, 0.9)]
    else:
        specs = [(labels[0], 230, 340, 620, 349, 0.4),
                 (labels[1], 200, 790, 236, 420, 0.65),
                 (labels[2], 530, 830, 340, 340, 0.9)]
    name = C["brand"]["name"]
    for i, (label, x0, y0, w_, h_, st) in enumerate(specs):
        a = anim(t, st, 0.5)
        if a <= 0:
            continue
        y0 += int(30 * (1 - a))
        card(frame, [x0, y0, x0 + w_, y0 + h_], radius=20,
             fill=(16, 22, 40, 235), alpha=a)
        g = grad_tile(w_ - 48, 42, CYAN, VIOLET).convert("RGBA")
        g.putalpha(int(60 * a))
        frame.alpha_composite(g, (x0 + 24, y0 + 27))
        txt(frame, (x0 + w_ // 2, y0 + h_ // 2 - 22), name,
            F("cnb", 38 if w_ > 300 else 29), WHITE, a, anchor="mm")
        mini_lines(frame, x0 + 50, y0 + h_ // 2 + 30, [w_ - 100], h=10, alpha=a * 0.6)
        pst = 1.3 + i * 0.55
        frac = clamp01((t - pst) / 1.6)
        progress(frame, (x0 + 24, y0 + h_ - 45, x0 + w_ - 24, y0 + h_ - 33), frac, a)
        if frac >= 1:
            ok = anim(t, pst + 1.6, 0.3)
            chip(frame, (x0 + w_ - 156, y0 + 17), "已生成", F("cn", 20), ok,
                 accent=GREEN, icon="check", pad=(12, 6))
        txt(frame, (x0 + 4, y0 + h_ + 20), label, F("cn", 25 if horiz else 24),
            MUTED, a * 0.95)

def t_cta(frame, t, P, C):
    W, H = C["W"], C["H"]
    horiz = W > H
    ly = 290 if horiz else 620
    a1 = anim(t, 0.15, 0.7)
    size = int((120 if horiz else 130) * (0.94 + 0.06 * a1))
    logo_mark(frame, ((W - size) // 2, ly - size // 2), size, a1)
    grad_text(frame, (W // 2, (475 if horiz else 830)), P.get("title", C["brand"]["name"]),
              F("cnb", 108 if horiz else 100), (120, 220, 255), (190, 150, 255),
              a1, dy=int(20 * (1 - a1)), anchor="mm")
    a2 = anim(t, 0.7, 0.6)
    txt(frame, (W // 2, 618 if horiz else 975), P.get("slogan", ""),
        F("cn", 46 if horiz else 42), WHITE, a2, anchor="mm")
    a3 = anim(t, 1.2, 0.6)
    txt(frame, (W // 2, 700 if horiz else 1055), P.get("byline", ""),
        F("cn", 28 if horiz else 27), MUTED, a3, anchor="mm")
    a4 = anim(t, 1.7, 0.6)
    url = P.get("url", "")
    if a4 > 0 and url:
        font = F("en", 30 if horiz else 29)
        wt, _, _ = tsize(font, url)
        pw = wt + 96
        x0 = (W - pw) // 2
        y0 = 780 if horiz else 1140
        card(frame, [x0, y0, x0 + pw, y0 + 68], radius=34,
             fill=(255, 255, 255, 16), line=(255, 255, 255, 60), alpha=a4)
        txt(frame, (W // 2, y0 + 34), url, font, WHITE, a4, anchor="mm")

TEMPLATES = {
    "hook":     {"fn": t_hook,     "lead": 0.5, "tail": 0.6, "min": 4.5},
    "options":  {"fn": t_options,  "lead": 0.4, "tail": 0.9, "min": 5.5},
    "features": {"fn": t_features, "lead": 0.4, "tail": 0.7, "min": 6.5},
    "editor":   {"fn": t_editor,   "lead": 0.4, "tail": 0.9, "min": 5.0},
    "formats":  {"fn": t_formats,  "lead": 0.4, "tail": 0.9, "min": 5.6},
    "cta":      {"fn": t_cta,      "lead": 0.4, "tail": 1.3, "min": 4.5},
}

# ---------- timeline ----------
def compute_timeline(scenes, vo_durs):
    """Scene length = max(template minimum, requested minimum, lead+vo+tail)."""
    durs, vo_at, starts = [], [], []
    acc = 0.0
    for sc, vd in zip(scenes, vo_durs):
        cfg = TEMPLATES[sc.visual.template]
        want = (sc.duration_ms or 0) / 1000.0
        d = max(cfg["min"], want, cfg["lead"] + vd + cfg["tail"])
        d = round(d * FPS) / FPS
        starts.append(acc)
        vo_at.append(acc + cfg["lead"])
        durs.append(d)
        acc += d
    return starts, durs, vo_at, acc

# ---------- music (procedural ambient bed) ----------
def make_music(duration, path):
    SR = 44100
    BPM = 90.0
    BEAT = 60.0 / BPM
    BAR = BEAT * 4
    A2, C3, E3, A3 = 110.0, 130.81, 164.81, 220.0
    F2, C4, F3 = 87.31, 261.63, 174.61
    G2, B3, D3, G3 = 98.0, 246.94, 146.83, 196.0
    CHORDS = [[A2, C3, E3, A3], [F2, F3, A3, C4],
              [C3, E3, G3, C4], [G2, D3, G3, B3]]
    nbars = int(duration / BAR) + 2
    chords = (CHORDS * (nbars // 4 + 1))[:nbars]
    n_all = int(SR * duration)
    mix = np.zeros(n_all)

    def env_ad(n, attack, release):
        e = np.ones(n)
        na, nr = int(attack * SR), int(release * SR)
        if na > 0:
            e[:na] = np.linspace(0, 1, na)
        if nr > 0:
            e[-nr:] *= np.linspace(1, 0, nr)
        return e

    rng = np.random.default_rng(7)
    for bi, chord in enumerate(chords):
        i0 = int(bi * BAR * SR)
        if i0 >= n_all:
            break
        n = min(int(BAR * SR * 1.06), n_all - i0)
        t = np.arange(n) / SR
        seg = np.zeros(n)
        for f in chord:
            for det in (0.9985, 1.0, 1.0018):
                seg += np.sin(2 * np.pi * f * det * t + rng.random() * 6.28) / (f / 110.0)
        mix[i0:i0 + n] += seg * env_ad(n, 0.5, 0.9) * 0.045
        if bi > 0:
            tones = [chord[1] * 2, chord[2] * 2, chord[3] * 2, chord[2] * 2,
                     chord[1] * 2, chord[3] * 2, chord[2] * 2, chord[3] * 4]
            for k in range(8):
                j0 = int((bi * BAR + k * BEAT / 2) * SR)
                m = int(0.45 * SR)
                if j0 + m > n_all:
                    continue
                tt = np.arange(m) / SR
                s = (np.sin(2 * np.pi * tones[k] * tt)
                     + 0.35 * np.sin(4 * np.pi * tones[k] * tt)) \
                    * np.exp(-tt * 9.0) * 0.055
                mix[j0:j0 + m] += s * (0.6 if k % 2 else 1.0)
        for k in (0, 2):
            j0 = int((bi * BAR + k * BEAT) * SR)
            m = int(0.5 * SR)
            if j0 + m > n_all:
                continue
            tt = np.arange(m) / SR
            mix[j0:j0 + m] += np.sin(2 * np.pi * (chord[0] / 2) * tt) \
                * np.exp(-tt * 6.0) * 0.05
    fi, fo = int(0.8 * SR), int(2.2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    mix = np.tanh(mix * 2.2)
    mix = mix / max(1e-9, np.abs(mix).max()) * 0.55
    stereo = np.stack([mix, np.roll(mix, 220)], -1)
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

# ---------- audio mix ----------
def _load_wav(path):
    with wave.open(path) as w:
        assert w.getframerate() == 44100 and w.getnchannels() == 2, path
        d = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    return d.reshape(-1, 2).astype(np.float64) / 32768.0

def mix_audio(vo_paths, vo_at, total, out_path, music_path=None):
    from scipy.ndimage import gaussian_filter1d, maximum_filter1d
    SR = 44100
    n_all = int(total * SR)
    mix = np.zeros((n_all, 2))
    env = np.zeros(n_all)
    for path, at in zip(vo_paths, vo_at):
        v = _load_wav(path) * 0.95
        i0 = int(at * SR)
        n = min(len(v), n_all - i0)
        mix[i0:i0 + n] += v[:n]
        env[i0:i0 + n] = np.maximum(env[i0:i0 + n], np.abs(v[:n]).max(1))
    if music_path:
        music = _load_wav(music_path)
        m = np.zeros((n_all, 2))
        n = min(len(music), n_all)
        m[:n] = music[:n]
        e = maximum_filter1d(env, int(0.15 * SR))
        e = gaussian_filter1d(e, int(0.08 * SR))
        e = np.clip(e / max(e.max(), 1e-9), 0, 1)
        mix += m * (0.34 * (1.0 - 0.62 * e))[:, None]
    mix = np.tanh(mix * 1.15)
    mix = mix / max(np.abs(mix).max(), 1e-9) * 0.89
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

# ---------- render ----------
def render_video(storyboard, aspect, vo_results, out_path, workdir,
                 progress_cb=None):
    """Render one aspect. vo_results: list of TTSResult aligned with scenes."""
    t0 = time.time()
    W, H = ASPECTS[aspect]
    scenes = storyboard.scenes
    vo_durs = [r.duration for r in vo_results]
    starts, durs, vo_at, total = compute_timeline(scenes, vo_durs)

    C = {"W": W, "H": H, "nscenes": len(scenes),
         "brand": {"name": storyboard.brand.name, "byline": storyboard.brand.byline}}

    def render_scene(i, tl, T):
        frame = new_frame(W, H, T)
        TEMPLATES[scenes[i].visual.template]["fn"](
            frame, min(max(tl, 0.0), durs[i]), scenes[i].visual.params, C)
        is_last = i == len(scenes) - 1
        brand_alpha = anim(T, 0.2, 0.6) if i == 0 else 1.0
        if not is_last:
            brand_bar(frame, C, brand_alpha)
            step_dots(frame, C, i, brand_alpha)
        sa = anim(T, vo_at[i] - 0.15, 0.35)
        end = min(vo_at[i] + vo_durs[i] + 1.2, starts[i] + durs[i] - 0.1)
        if T > end:
            sa *= clamp01(1 - (T - end) / 0.3)
        subtitle(frame, C, scenes[i].subtitle or scenes[i].voiceover, sa)
        return frame

    noaudio = os.path.join(workdir, f"noaudio-{aspect.replace(':', 'x')}.mp4")
    nframes = int(round(total * FPS))
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "pipe:0",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", noaudio],
        stdin=subprocess.PIPE)
    for n in range(nframes):
        T = n / FPS
        i = len([s for s in starts if s <= T]) - 1
        frame = render_scene(i, T - starts[i], T)
        if i + 1 < len(scenes):
            b = starts[i + 1]
            if T > b - XF:
                k = ease_io((T - (b - XF)) / XF)
                frame = Image.blend(frame, render_scene(i + 1, T - b, T), k)
        fade = min(1.0, T / 0.5, max(0.0, (total - T) / 0.7))
        if fade < 1.0:
            frame = Image.blend(Image.new("RGBA", (W, H), (5, 8, 16, 255)), frame, fade)
        ff.stdin.write(frame.convert("RGB").tobytes())
        if progress_cb and n % 90 == 0:
            progress_cb(n / nframes)
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg video encode failed")

    music_path = None
    if storyboard.music:
        music_path = os.path.join(workdir, "music.wav")
        if not os.path.exists(music_path):
            make_music(total, music_path)
    mix_path = os.path.join(workdir, f"mix-{aspect.replace(':', 'x')}.wav")
    mix_audio([r.audio_path for r in vo_results], vo_at, total, mix_path, music_path)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", noaudio, "-i", mix_path,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", out_path], check=True)
    os.remove(noaudio)

    scene_report = [
        {"id": sc.id, "template": sc.visual.template,
         "start_ms": int(st * 1000), "duration_ms": int(d * 1000),
         "vo_duration_ms": int(vd * 1000)}
        for sc, st, d, vd in zip(scenes, starts, durs, vo_durs)]
    return {"aspect": aspect, "path": out_path, "total_s": round(total, 3),
            "frames": nframes, "render_wall_s": round(time.time() - t0, 1),
            "scenes": scene_report}

# ---------- QC ----------
def qc_check(path, expect_total, aspect):
    W, H = ASPECTS[aspect]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate",
         "-of", "json", path], capture_output=True, text=True, check=True)
    import json
    info = json.loads(out.stdout)
    vstreams = [s for s in info["streams"] if s.get("codec_type") == "video"]
    astreams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    dur = float(info["format"]["duration"])
    checks = {
        "video_stream": bool(vstreams),
        "audio_stream": bool(astreams),
        "resolution": bool(vstreams) and vstreams[0]["width"] == W
                      and vstreams[0]["height"] == H,
        "fps": bool(vstreams) and vstreams[0]["r_frame_rate"] == f"{FPS}/1",
        "duration": abs(dur - expect_total) < 0.35,
    }
    # sample 3 frames, reject black/frozen output
    lumas = []
    for frac in (0.2, 0.5, 0.8):
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(dur * frac), "-i", path,
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray",
             "-s", "64x36", "pipe:1"], capture_output=True, check=True)
        lumas.append(float(np.frombuffer(p.stdout, np.uint8).mean()))
    checks["not_black"] = all(l > 6 for l in lumas)
    checks["frames_vary"] = (max(lumas) - min(lumas)) > 1e-6 or len(set(lumas)) > 1
    return {"pass": all(checks.values()), "checks": checks,
            "duration": dur, "sampled_luma": [round(l, 1) for l in lumas]}
