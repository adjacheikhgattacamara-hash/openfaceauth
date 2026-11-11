"""Boîte à outils de dessin de l'interface FaceAuth (Pillow uniquement).

Tout l'écran est dessiné avec Pillow puis affiché par tkinter : le rendu est donc
identique sur tous les Linux et peut être testé sans écran. Les coordonnées sont
en « unités de conception » (fenêtre de W × H) ; `scale` les adapte à l'écran.
"""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = ASSETS / "fonts"

W, H = 1200, 660  # taille de conception de la fenêtre

# Palette
BG_TOP, BG_BOTTOM = "#030a18", "#07142b"
BLUE, BLUE_LIGHT, BLUE_DARK = "#1e90ff", "#43a8ff", "#0b5fd1"
CYAN = "#37d6ff"
TEXT, MUTED, DIM = "#eaf2ff", "#9db3d8", "#5f7599"
GREEN, GREEN_DARK = "#25e07c", "#0d8a4a"
RED, RED_DARK = "#ff3d3d", "#b81818"
AMBER = "#ffb020"
PANEL_A, PANEL_B = (12, 28, 60, 232), (6, 15, 34, 238)
BORDER = (30, 120, 235, 190)


def col(c, alpha=None):
    """Couleur « #rrggbb » ou tuple → tuple RGBA."""
    if isinstance(c, str):
        r, g, b = ImageColor.getrgb(c)[:3]
        return (r, g, b, 255 if alpha is None else alpha)
    c = tuple(c)
    if len(c) == 3:
        return c + (255 if alpha is None else alpha,)
    return c[:3] + ((c[3] if alpha is None else alpha),)


_FONT_FILES = {
    ("regular", False): "Poppins-Regular.ttf", ("medium", False): "Poppins-Medium.ttf",
    ("bold", False): "Poppins-Bold.ttf", ("regular", True): "Poppins-Italic.ttf",
    ("medium", True): "Poppins-Italic.ttf", ("bold", True): "Poppins-BoldItalic.ttf",
}
_font_cache = {}


def get_font(px, weight="regular", italic=False):
    key = (max(6, int(round(px))), weight, italic)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(str(FONTS / _FONT_FILES[(weight, italic)]), key[0])
        except OSError:
            try:
                _font_cache[key] = ImageFont.load_default(size=key[0])
            except TypeError:  # très vieux Pillow
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _rot(points, deg, cx=0.0, cy=0.0):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in points]


def soft_blur(img, radius):
    """Flou gaussien rapide : on floute une version réduite puis on la ré-agrandit.
    Pour un grand rayon le résultat est lisse et la différence est invisible, mais
    c'est 5 à 15 fois plus rapide (le flou dominait le temps de redessin)."""
    f = int(min(4, radius // 3))
    if f < 2:
        return img.filter(ImageFilter.GaussianBlur(radius))
    w, h = img.size
    small = img.resize((max(1, w // f), max(1, h // f)), Image.BOX)
    small = small.filter(ImageFilter.GaussianBlur(radius / f))
    return small.resize((w, h), Image.BILINEAR)


class Cv:
    """Toile de dessin suréchantillonnée (anti-crénelage) en unités de conception."""

    def __init__(self, w, h, scale=1.0, ss=2, bg=None):
        self.w, self.h, self.s, self.ss = w, h, scale, ss
        self.m = scale * ss
        size = (max(1, round(w * self.m)), max(1, round(h * self.m)))
        self.img = Image.new("RGBA", size, col(bg) if bg else (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    # -- utilitaires -------------------------------------------------------
    def finish(self):
        size = (max(1, round(self.w * self.s)), max(1, round(self.h * self.s)))
        return self.img.resize(size, Image.LANCZOS)

    def _put(self, layer, x, y):
        bw, bh = self.img.size
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + layer.width, bw), min(y + layer.height, bh)
        if x1 <= x0 or y1 <= y0:
            return
        self.img.alpha_composite(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))

    def paste(self, image, x, y, w=None, h=None):
        """Colle une image RGBA (logo...) redimensionnée en unités de conception."""
        w = w or image.width
        h = h or round(w * image.height / image.width)
        im = image.convert("RGBA").resize((max(1, round(w * self.m)), max(1, round(h * self.m))), Image.LANCZOS)
        self._put(im, round(x * self.m), round(y * self.m))

    # -- formes ---------------------------------------------------------------
    def _shape(self, x, y, w, h, maskfn, fill=None, outline=None, ow=1, glow=None):
        """glow = (couleur, rayon, alpha) : halo flou autour de la forme."""
        m = self.m
        pad = (int(glow[1] * m * 2.4) if glow else 0) + 3
        pw, ph = max(1, round(w * m)), max(1, round(h * m))
        lw, lh = pw + 2 * pad, ph + 2 * pad
        bb = (pad, pad, pad + pw - 1, pad + ph - 1)
        layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        if glow:
            g = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
            gcol = col(glow[0], glow[2])
            maskfn(ImageDraw.Draw(g), bb, gcol, gcol, max(1, round(ow * m * 1.6)))
            layer.alpha_composite(soft_blur(g, glow[1] * m))
        if fill is not None:
            if isinstance(fill, tuple) and fill and fill[0] == "grad":
                _, c1, c2, direction = (fill + ("v",))[:4]
                mask = Image.new("L", (lw, lh), 0)
                maskfn(ImageDraw.Draw(mask), bb, 255, None, 0)
                ramp = Image.linear_gradient("L").resize((lw, lh))
                if direction == "h":
                    ramp = ramp.rotate(90, expand=True).resize((lw, lh))
                gimg = Image.composite(Image.new("RGBA", (lw, lh), col(c2)),
                                       Image.new("RGBA", (lw, lh), col(c1)), ramp)
                gimg.putalpha(ImageChops.multiply(gimg.getchannel("A"), mask))
                layer.alpha_composite(gimg)
            else:
                maskfn(ImageDraw.Draw(layer), bb, col(fill), None, 0)
        if outline is not None:
            maskfn(ImageDraw.Draw(layer), bb, None, col(outline), max(1, round(ow * m)))
        self._put(layer, round(x * m) - pad, round(y * m) - pad)

    def rrect(self, x, y, w, h, r=12, fill=None, outline=None, ow=1, glow=None):
        rad = r * self.m
        self._shape(x, y, w, h, lambda d, bb, f, o, wd: d.rounded_rectangle(
            bb, radius=rad, fill=f, outline=o, width=wd), fill, outline, ow, glow)

    def ellipse(self, cx, cy, rx, ry=None, fill=None, outline=None, ow=1, glow=None):
        ry = rx if ry is None else ry
        self._shape(cx - rx, cy - ry, 2 * rx, 2 * ry, lambda d, bb, f, o, wd: d.ellipse(
            bb, fill=f, outline=o, width=wd), fill, outline, ow, glow)

    def line(self, pts, color, width=2, round_caps=True):
        m = self.m
        p = [(x * m, y * m) for x, y in pts]
        wd = max(1, round(width * m))
        self.d.line(p, fill=col(color), width=wd, joint="curve")
        if round_caps and wd > 3:
            r = wd / 2
            for x, y in (p[0], p[-1]):
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=col(color))

    def poly(self, pts, fill=None, outline=None, width=1):
        m = self.m
        p = [(x * m, y * m) for x, y in pts]
        if fill is not None:
            self.d.polygon(p, fill=col(fill))
        if outline is not None:
            self.line(pts + [pts[0]], outline, width)

    def arc(self, cx, cy, r, a0, a1, color, width=2):
        m = self.m
        self.d.arc((round((cx - r) * m), round((cy - r) * m), round((cx + r) * m), round((cy + r) * m)),
                   a0, a1, fill=col(color), width=max(1, round(width * m)))

    def glow_blob(self, cx, cy, rx, ry, color, alpha=60, blur=60):
        m = self.m
        pad = int(blur * m * 2)
        w, h = round(2 * rx * m) + 2 * pad, round(2 * ry * m) + 2 * pad
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse((pad, pad, w - pad, h - pad), fill=col(color, alpha))
        layer = soft_blur(layer, blur * m)
        self._put(layer, round((cx - rx) * m) - pad, round((cy - ry) * m) - pad)

    # -- texte ----------------------------------------------------------------
    def text(self, x, y, s, size, weight="regular", fill=TEXT, anchor="la", italic=False):
        f = get_font(size * self.m, weight, italic)
        self.d.text((x * self.m, y * self.m), s, font=f, fill=col(fill), anchor=anchor)
        return f.getlength(s) / self.m

    def measure(self, s, size, weight="regular", italic=False):
        return get_font(size * self.m, weight, italic).getlength(s) / self.m

    def wrap(self, s, size, max_w, weight="regular"):
        lines, cur = [], ""
        for word in s.split():
            test = (cur + " " + word).strip()
            if self.measure(test, size, weight) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines


# ---------------------------------------------------------------------------
# Fond et panneaux
# ---------------------------------------------------------------------------
def draw_background(cv):
    cv.rrect(0, 0, cv.w, cv.h, 0, fill=("grad", BG_TOP, BG_BOTTOM, "v"))
    cv.glow_blob(cv.w * 0.78, 40, 380, 120, BLUE, 34, 70)
    cv.glow_blob(120, cv.h - 20, 220, 140, BLUE_DARK, 40, 70)


def panel(cv, x, y, w, h, r=16, glow=True):
    cv.rrect(x, y, w, h, r, fill=("grad", PANEL_A, PANEL_B, "v"), outline=BORDER, ow=1.2,
             glow=((BLUE, 7, 70) if glow else None))


# ---------------------------------------------------------------------------
# Icônes (dessinées au trait, centrées sur cx, cy ; s = taille)
# ---------------------------------------------------------------------------
def _head_shoulders(cv, cx, cy, s, c, k=1.0):
    cv.ellipse(cx, cy - .17 * s * k, .15 * s * k, fill=c)
    m = cv.m
    cv.d.pieslice((round((cx - .27 * s * k) * m), round((cy + .02 * s * k) * m),
                   round((cx + .27 * s * k) * m), round((cy + .56 * s * k) * m)), 180, 360, fill=col(c))


def icon_home(cv, cx, cy, s, c):
    g = .08 * s
    q = .34 * s
    for dx in (-1, 1):
        for dy in (-1, 1):
            cv.rrect(cx + (dx * (g / 2 + q / 2)) - q / 2, cy + (dy * (g / 2 + q / 2)) - q / 2, q, q, .07 * s, fill=c)


def icon_users(cv, cx, cy, s, c):
    _head_shoulders(cv, cx - .13 * s, cy, s * .9, c)
    _head_shoulders(cv, cx + .2 * s, cy + .03 * s, s * .7, c)


def icon_gear(cv, cx, cy, s, c):
    for k in range(8):
        a = k * 45
        tooth = _rot([(-.07 * s, -.42 * s), (.07 * s, -.42 * s), (.07 * s, -.24 * s), (-.07 * s, -.24 * s)], a)
        cv.poly([(cx + x, cy + y) for x, y in tooth], fill=c)
    cv.ellipse(cx, cy, .3 * s, fill=None, outline=c, ow=.17 * s)


def icon_info(cv, cx, cy, s, c):
    cv.ellipse(cx, cy, .44 * s, outline=c, ow=.09 * s)
    cv.ellipse(cx, cy - .17 * s, .05 * s, fill=c)
    cv.line([(cx, cy - .04 * s), (cx, cy + .22 * s)], c, .09 * s)


def icon_user_plus(cv, cx, cy, s, c):
    _head_shoulders(cv, cx - .1 * s, cy, s * .85, c)
    cv.line([(cx + .22 * s, cy - .02 * s), (cx + .46 * s, cy - .02 * s)], c, .08 * s)
    cv.line([(cx + .34 * s, cy - .14 * s), (cx + .34 * s, cy + .1 * s)], c, .08 * s)


def icon_check(cv, cx, cy, s, c, w=None):
    cv.line([(cx - .3 * s, cy + .02 * s), (cx - .08 * s, cy + .24 * s), (cx + .32 * s, cy - .22 * s)],
            c, w or .13 * s)


def icon_shield(cv, cx, cy, s, c):
    pts = [(cx, cy - .46 * s), (cx + .38 * s, cy - .3 * s), (cx + .38 * s, cy + .05 * s),
           (cx + .2 * s, cy + .32 * s), (cx, cy + .46 * s), (cx - .2 * s, cy + .32 * s),
           (cx - .38 * s, cy + .05 * s), (cx - .38 * s, cy - .3 * s)]
    cv.poly(pts, outline=c, width=.08 * s)
    icon_check(cv, cx, cy, s * .6, c, .08 * s)


def icon_rocket(cv, cx, cy, s, c):
    body = [(0, -.5), (.15, -.25), (.15, .18), (-.15, .18), (-.15, -.25)]
    fins = [[(.15, .0), (.32, .22), (.15, .22)], [(-.15, .0), (-.32, .22), (-.15, .22)]]
    tail = [(-.09, .22), (.09, .22), (0, .46)]
    for part in [body] + fins + [tail]:
        pts = _rot([(cx + x * s, cy + y * s) for x, y in part], 45, cx, cy)
        cv.poly(pts, fill=c)
    cv.ellipse(cx + .0 * s + .0, cy - .17 * s, .06 * s, fill=BG_BOTTOM)


def icon_camera(cv, cx, cy, s, c):
    cv.rrect(cx - .42 * s, cy - .22 * s, .84 * s, .56 * s, .1 * s, outline=c, ow=.08 * s)
    cv.poly([(cx - .14 * s, cy - .22 * s), (cx - .08 * s, cy - .34 * s), (cx + .08 * s, cy - .34 * s),
             (cx + .14 * s, cy - .22 * s)], fill=c)
    cv.ellipse(cx, cy + .06 * s, .15 * s, outline=c, ow=.08 * s)


def icon_play(cv, cx, cy, s, c):
    cv.poly([(cx - .22 * s, cy - .34 * s), (cx + .38 * s, cy), (cx - .22 * s, cy + .34 * s)], fill=c)


def icon_bolt(cv, cx, cy, s, c):
    cv.poly([(cx + .08 * s, cy - .46 * s), (cx - .3 * s, cy + .06 * s), (cx - .02 * s, cy + .06 * s),
             (cx - .1 * s, cy + .46 * s), (cx + .3 * s, cy - .1 * s), (cx + .02 * s, cy - .1 * s)], fill=c)


def icon_plus(cv, cx, cy, s, c):
    cv.line([(cx - .34 * s, cy), (cx + .34 * s, cy)], c, .09 * s)
    cv.line([(cx, cy - .34 * s), (cx, cy + .34 * s)], c, .09 * s)


def icon_keyboard(cv, cx, cy, s, c):
    cv.rrect(cx - .46 * s, cy - .28 * s, .92 * s, .56 * s, .08 * s, outline=c, ow=.07 * s)
    for row, n in enumerate((5, 5)):
        for k in range(n):
            cv.rrect(cx - .34 * s + k * .15 * s, cy - .17 * s + row * .15 * s, .09 * s, .08 * s, .02 * s, fill=c)
    cv.rrect(cx - .24 * s, cy + .12 * s, .48 * s, .07 * s, .02 * s, fill=c)


def icon_power(cv, cx, cy, s, c):
    cv.arc(cx, cy + .02 * s, .3 * s, 125, 415, c, .1 * s)
    cv.line([(cx, cy - .4 * s), (cx, cy - .04 * s)], c, .1 * s)


def icon_warning(cv, cx, cy, s, c):
    cv.poly([(cx, cy - .44 * s), (cx + .46 * s, cy + .36 * s), (cx - .46 * s, cy + .36 * s)], fill=c)
    cv.line([(cx, cy - .14 * s), (cx, cy + .1 * s)], "#ffffff", .09 * s)
    cv.ellipse(cx, cy + .24 * s, .05 * s, fill="#ffffff")


def icon_pulse(cv, cx, cy, s, c):
    cv.line([(cx - .5 * s, cy), (cx - .24 * s, cy), (cx - .12 * s, cy - .32 * s), (cx + .08 * s, cy + .34 * s),
             (cx + .2 * s, cy), (cx + .5 * s, cy)], c, .08 * s)


def icon_face_scan(cv, cx, cy, s, c):
    a, L = .46 * s, .2 * s
    for sx in (-1, 1):
        for sy in (-1, 1):
            cv.line([(cx + sx * a, cy + sy * (a - L)), (cx + sx * a, cy + sy * a), (cx + sx * (a - L), cy + sy * a)],
                    c, .075 * s)
    cv.ellipse(cx, cy - .02 * s, .24 * s, .29 * s, outline=c, ow=.06 * s)
    cv.ellipse(cx - .09 * s, cy - .06 * s, .03 * s, fill=c)
    cv.ellipse(cx + .09 * s, cy - .06 * s, .03 * s, fill=c)
    cv.arc(cx, cy + .06 * s, .1 * s, 20, 160, c, .05 * s)


def icon_terminal(cv, cx, cy, s, c):
    cv.rrect(cx - .44 * s, cy - .34 * s, .88 * s, .68 * s, .1 * s, outline=c, ow=.07 * s)
    cv.line([(cx - .26 * s, cy - .12 * s), (cx - .1 * s, cy + .02 * s), (cx - .26 * s, cy + .16 * s)], c, .07 * s)
    cv.line([(cx + .02 * s, cy + .18 * s), (cx + .24 * s, cy + .18 * s)], c, .07 * s)


def icon_calendar(cv, cx, cy, s, c):
    cv.rrect(cx - .4 * s, cy - .32 * s, .8 * s, .72 * s, .09 * s, outline=c, ow=.07 * s)
    cv.line([(cx - .4 * s, cy - .1 * s), (cx + .4 * s, cy - .1 * s)], c, .07 * s)
    cv.line([(cx - .18 * s, cy - .44 * s), (cx - .18 * s, cy - .22 * s)], c, .07 * s)
    cv.line([(cx + .18 * s, cy - .44 * s), (cx + .18 * s, cy - .22 * s)], c, .07 * s)


def icon_arrow(cv, cx, cy, s, c):
    cv.line([(cx - .34 * s, cy), (cx + .34 * s, cy)], c, .09 * s)
    cv.line([(cx + .12 * s, cy - .22 * s), (cx + .34 * s, cy), (cx + .12 * s, cy + .22 * s)], c, .09 * s)


def icon_trash(cv, cx, cy, s, c):
    cv.rrect(cx - .26 * s, cy - .18 * s, .52 * s, .6 * s, .06 * s, outline=c, ow=.07 * s)
    cv.line([(cx - .36 * s, cy - .26 * s), (cx + .36 * s, cy - .26 * s)], c, .08 * s)
    cv.line([(cx - .1 * s, cy - .36 * s), (cx + .1 * s, cy - .36 * s)], c, .07 * s)


def icon_refresh(cv, cx, cy, s, c):
    cv.arc(cx, cy, .3 * s, 40, 330, c, .09 * s)
    cv.poly([(cx + .38 * s, cy - .3 * s), (cx + .38 * s, cy - .02 * s), (cx + .1 * s, cy - .1 * s)], fill=c)


def icon_list(cv, cx, cy, s, c):
    for k in (-1, 0, 1):
        cv.ellipse(cx - .3 * s, cy + k * .25 * s, .04 * s, fill=c)
        cv.line([(cx - .16 * s, cy + k * .25 * s), (cx + .38 * s, cy + k * .25 * s)], c, .07 * s)


ICONS = {
    "home": icon_home, "users": icon_users, "gear": icon_gear, "info": icon_info,
    "user_plus": icon_user_plus, "check": icon_check, "shield": icon_shield, "rocket": icon_rocket,
    "camera": icon_camera, "play": icon_play, "bolt": icon_bolt, "plus": icon_plus,
    "keyboard": icon_keyboard, "power": icon_power, "warning": icon_warning, "pulse": icon_pulse,
    "face_scan": icon_face_scan, "terminal": icon_terminal, "calendar": icon_calendar,
    "arrow": icon_arrow, "trash": icon_trash, "refresh": icon_refresh, "list": icon_list,
}


def icon(cv, name, cx, cy, s, color=TEXT):
    ICONS[name](cv, cx, cy, s, color)


def icon_badge(cv, name, cx, cy, r, color=BLUE_LIGHT):
    """Icône dans un disque lumineux (cartes d'action)."""
    cv.ellipse(cx, cy, r, fill=(8, 28, 64, 255), outline=color, ow=1.6, glow=(BLUE, 6, 110))
    icon(cv, name, cx, cy, r * 1.15, color)


# ---------------------------------------------------------------------------
# Boutons
# ---------------------------------------------------------------------------
BTN_STYLES = {
    "primary": (("grad", "#2aa0ff", "#0b62d8", "v"), "#7cc4ff", "#ffffff"),
    "danger": (("grad", "#ff4a4a", "#b81818", "v"), "#ff8a8a", "#ffffff"),
    "ghost": ((14, 34, 72, 255), "#2f78d6", "#d7e6ff"),
    "success": (("grad", "#2fe58a", "#0d8a4a", "v"), "#8affc0", "#ffffff"),
}


def draw_button(cv, x, y, w, h, label, style="primary", ic=None, arrow=False, state="normal", size=11):
    fill, border, fg = BTN_STYLES[style]
    glow = None
    if state == "disabled":
        fill, border, fg = (24, 36, 60, 255), "#2a3a5a", "#6b7f9f"
    elif state in ("hover", "pressed"):
        glow = ((RED if style == "danger" else BLUE_LIGHT), 7, 150 if state == "hover" else 200)
        if isinstance(fill, tuple) and fill[0] == "grad":
            fill = ("grad",) + tuple(_lighten(c, 22 if state == "hover" else -14) for c in fill[1:3]) + (fill[3],)
        else:
            fill = (24, 56, 112, 255)
    cv.rrect(x, y, w, h, h / 2 if h <= 44 else 14, fill=fill, outline=border, ow=1.2, glow=glow)
    iw = (size * 1.5 + 8) if ic else 0
    aw = (size * 1.3 + 8) if arrow else 0
    tw = cv.measure(label, size, "bold")
    start = x + (w - (iw + tw + aw)) / 2
    cy = y + h / 2
    if ic:
        icon(cv, ic, start + size * .75, cy, size * 1.5, fg)
    cv.text(start + iw, cy, label, size, "bold", fg, "lm")
    if arrow:
        icon(cv, "arrow", start + iw + tw + size * .8 + 6, cy, size * 1.3, fg)


def _lighten(c, amt):
    r, g, b, a = col(c)
    return (max(0, min(255, r + amt)), max(0, min(255, g + amt)), max(0, min(255, b + amt)), a)


def draw_nav_item(cv, x, y, w, h, label, ic, active=False, state="normal"):
    if active:
        cv.rrect(x, y, w, h, 12, fill=("grad", "#2a9bff", "#0e63da", "h"), outline="#7cc4ff", ow=1,
                 glow=(BLUE, 6, 120))
    elif state in ("hover", "pressed"):
        cv.rrect(x, y, w, h, 12, fill=(20, 46, 96, 230), outline="#2a62b8", ow=1)
    fg = "#ffffff" if active else (TEXT if state != "normal" else MUTED)
    icon(cv, ic, x + 28, y + h / 2, 20, fg)
    cv.text(x + 52, y + h / 2, label, 12.5, "medium", fg, "lm")


def draw_link(cv, x, y, w, h, label, state="normal", ic="arrow"):
    c = BLUE_LIGHT if state in ("hover", "pressed") else MUTED
    tw = cv.measure(label, 10, "medium")
    cv.text(x + w - 20 - tw, y + h / 2, label, 10, "medium", c, "lm")
    if ic:
        icon(cv, ic, x + w - 9, y + h / 2, 11, c)


def draw_chip(cv, x, y, w, h, label, selected=False, state="normal"):
    if selected:
        cv.rrect(x, y, w, h, h / 2, fill=("grad", "#2aa0ff", "#0b62d8", "v"), outline="#7cc4ff", glow=(BLUE, 5, 110))
        fg = "#ffffff"
    else:
        hov = state in ("hover", "pressed")
        cv.rrect(x, y, w, h, h / 2, fill=(22, 52, 104, 255) if hov else (14, 34, 72, 255),
                 outline="#3a86e6" if hov else "#27508f")
        fg = TEXT if hov else MUTED
    cv.text(x + w / 2, y + h / 2, label, 10.5, "medium", fg, "mm")


# ---------------------------------------------------------------------------
# Visuel de scan du visage (animé)
# ---------------------------------------------------------------------------
def _mesh_points():
    pts = []
    for iy in range(-5, 7):
        t = iy / 6.0
        half = math.sqrt(max(0.0, 1 - (t * .92) ** 2)) * (1 - .1 * max(0.0, t))
        n = max(2, int(round(half * 7)))
        for ix in range(-n, n + 1):
            pts.append((ix / max(n, 1) * half, t))
    return pts


_MESH = _mesh_points()


_scan_cache = {}


def _scan_static(cv, w, h, mode):
    """Couches qui ne bougent pas (visage filaire, coins) : calculées une fois."""
    key = (w, h, mode, cv.s, cv.ss)
    if key in _scan_cache:
        return _scan_cache[key]
    tone = {"idle": CYAN, "busy": CYAN, "ok": GREEN, "fail": RED}[mode]
    cx, cy = w / 2, h / 2 - 4
    ring_r = min(w, h) * .43
    face = Cv(w, h, cv.s, cv.ss)
    fw, fh = ring_r * .62, ring_r * .86
    face.ellipse(cx, cy, fw, fh, fill=(8, 34, 74, 255), outline=tone, ow=1.4)
    pts = [(cx + px * fw * .94, cy + py * fh * .94) for px, py in _MESH]
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:i + 5]:
            if (x1 - x2) ** 2 + (y1 - y2) ** 2 < (fw * .36) ** 2:
                face.line([(x1, y1), (x2, y2)], (45, 130, 220, 255), .6, round_caps=False)
    for x1, y1 in pts:
        face.ellipse(x1, y1, 1.5, fill=tone)
    for sx in (-1, 1):
        face.ellipse(cx + sx * fw * .38, cy - fh * .16, fw * .15, fw * .08, outline="#bfe9ff", ow=1.2)
    face.line([(cx, cy - fh * .1), (cx - fw * .06, cy + fh * .16), (cx + fw * .08, cy + fh * .17)], "#8fd2ff", 1.2)
    face.arc(cx, cy + fh * .3, fw * .26, 20, 160, "#bfe9ff", 1.4)
    a, L = min(w, h) * .47, 34
    for sx in (-1, 1):
        for sy_ in (-1, 1):
            face.line([(cx + sx * a, cy + sy_ * (a - L)), (cx + sx * a, cy + sy_ * a),
                       (cx + sx * (a - L), cy + sy_ * a)], tone, 4)
    disc = Cv(w, h, cv.s, cv.ss)
    disc.ellipse(cx, cy, ring_r + 6, fill=(5, 22, 52, 255), glow=(tone, 14, 70 if mode != "idle" else 45))
    _scan_cache[key] = (disc.img, face.img)
    return _scan_cache[key]


def draw_scan_visual(cv, w, h, phase=0.0, mode="idle"):
    """Anneaux tournants + visage filaire. mode : idle | busy | ok | fail."""
    cx, cy = w / 2, h / 2 - 4
    tone = {"idle": CYAN, "busy": CYAN, "ok": GREEN, "fail": RED}[mode]
    ring_r = min(w, h) * .43
    disc, face = _scan_static(cv, w, h, mode)
    cv._put(disc, 0, 0)
    spin = phase * 360
    for r, wd, start, span, sp in [(ring_r, 3.2, 20, 110, 1), (ring_r, 3.2, 200, 110, 1),
                                   (ring_r - 16, 2.2, 70, 80, -1.4), (ring_r - 16, 2.2, 250, 80, -1.4),
                                   (ring_r - 30, 1.6, 0, 40, 2), (ring_r - 30, 1.6, 180, 40, 2)]:
        a0 = start + spin * sp
        cv.arc(cx, cy, r, a0, a0 + span, tone, wd)
    cv.ellipse(cx, cy, ring_r - 38, outline=(40, 120, 220, 255), ow=1)
    cv._put(face, 0, 0)
    if mode == "busy":
        fh = ring_r * .86
        fw = ring_r * .62
        sy = cy - fh + (phase * 2 % 1) * 2 * fh
        for k in range(6):
            cv.line([(cx - fw * 1.1, sy - k * 2), (cx + fw * 1.1, sy - k * 2)],
                    tone if k == 0 else (30, 110, 190, 255), 1)


# ---------------------------------------------------------------------------
# Décors de la barre latérale et logo Linux
# ---------------------------------------------------------------------------
_BUILDINGS = [(0, 17, 38), (19, 12, 64), (33, 19, 50), (54, 11, 86), (67, 21, 56), (90, 15, 98),
              (107, 19, 62), (128, 12, 74), (142, 21, 44), (165, 11, 60)]


def draw_skyline(cv, x, y, w, base):
    """Ville lumineuse (bâtiments, fenêtres, circuits) posée sur la ligne `base`."""
    cv.glow_blob(x + w / 2, base - 20, w * .55, 46, BLUE, 110, 34)
    for i, (dx, bw, bh) in enumerate(_BUILDINGS):
        bx = x + 2 + dx
        cv.rrect(bx, base - bh, bw, bh, 1.5, fill=("grad", (16, 58, 138, 255), (5, 18, 46, 255), "v"),
                 outline=(60, 160, 255, 255), ow=.9, glow=(CYAN, 3, 50))
        for wy in range(int(base - bh + 6), int(base - 5), 8):
            for wx in range(int(bx + 3), int(bx + bw - 3), 6):
                if (wx * 7 + wy * 13 + i) % 5 != 0:
                    cv.rrect(wx, wy, 2.4, 3.2, .5, fill="#8fdcff" if (wx + wy) % 3 else "#ffffff")
    cv.line([(x, base + 1), (x + w, base + 1)], (70, 170, 255, 255), 1.4)
    # circuits au pied des bâtiments
    for k, (cx0, ln) in enumerate(((x + 8, 34), (x + 84, 26), (x + 122, 30))):
        cy = base + 7 + (k % 2) * 4
        cv.line([(cx0, cy), (cx0 + ln, cy)], (40, 140, 255, 255), 1)
        cv.ellipse(cx0 + ln, cy, 2, fill=CYAN)


def draw_light_streak(cv, x0, y0, x1, y1, bend=-16):
    """Trait de lumière courbe (blanc au centre, bleu aux extrémités)."""
    n = 48
    pts = []
    for i in range(n + 1):
        t = i / n
        px = x0 + (x1 - x0) * t
        py = y0 + (y1 - y0) * t + bend * 4 * t * (1 - t)
        pts.append((px, py))
    cv.glow_blob((x0 + x1) / 2, (y0 + y1) / 2 + bend / 2, (x1 - x0) / 2, 5, BLUE_LIGHT, 120, 7)
    for i in range(n):
        t = (i + .5) / n
        k = 1 - abs(2 * t - 1)
        c = (int(60 + 195 * k), int(150 + 105 * k), 255, 255)
        cv.line([pts[i], pts[i + 1]], c, .6 + 2.4 * k, round_caps=False)


def icon_tux(cv, cx, cy, s):
    """Pingouin Linux (dessin original simplifié)."""
    edge = "#d6e2f5"
    cv.ellipse(cx, cy + .06 * s, .3 * s, .4 * s, fill=(18, 22, 34, 255), outline=edge, ow=.04 * s)      # corps
    cv.ellipse(cx, cy - .3 * s, .19 * s, .2 * s, fill=(18, 22, 34, 255), outline=edge, ow=.04 * s)      # tête
    cv.ellipse(cx, cy + .12 * s, .19 * s, .3 * s, fill="#f4f7fb")                                         # ventre
    for sx in (-1, 1):
        cv.ellipse(cx + sx * .07 * s, cy - .33 * s, .055 * s, .07 * s, fill="#ffffff")
        cv.ellipse(cx + sx * .07 * s, cy - .32 * s, .025 * s, fill="#101420")
        cv.ellipse(cx + sx * .21 * s, cy + .46 * s, .12 * s, .06 * s, fill="#ffb11a")                    # pieds
        cv.poly([(cx + sx * .27 * s, cy - .02 * s), (cx + sx * .46 * s, cy + .22 * s), (cx + sx * .3 * s, cy + .28 * s)],
                fill=(18, 22, 34, 255), outline=edge, width=.03 * s)                                      # ailes
    cv.poly([(cx - .09 * s, cy - .23 * s), (cx + .09 * s, cy - .23 * s), (cx, cy - .15 * s)], fill="#ffb11a")  # bec


def draw_scan_overlay(cv, w, h, phase=0.0, mode="idle"):
    """Effets animés posés sur l'illustration du visage : balayage et teinte d'état."""
    tone = {"idle": CYAN, "busy": CYAN, "ok": GREEN, "fail": RED}[mode]
    if mode in ("ok", "fail"):
        cv.rrect(0, 0, w, h, 14, fill=col(tone, 34))
    strength = {"idle": 55, "busy": 170, "ok": 0, "fail": 0}[mode]
    if strength:
        y = (phase * (2 if mode == "busy" else 1) % 1) * (h - 30)
        cv.rrect(10, y, w - 20, 26, 6, fill=("grad", col(tone, 0), col(tone, strength // 2), "v"))
        cv.line([(14, y + 26), (w - 14, y + 26)], col(tone, strength + 40), 1.6, False)
