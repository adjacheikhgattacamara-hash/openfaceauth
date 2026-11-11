"""Modèle et rendu de l'interface FaceAuth, indépendants de tkinter.

`App` garde l'état (page, profils, test en cours...) et dessine l'écran avec
Pillow ; `gui.py` ne fait que l'afficher et lui transmettre souris / clavier.
Ainsi toute l'interface est testable sans écran.
"""
import datetime
import json
import os
import re
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PIL import Image, ImageDraw

from . import __version__
from . import commands as C
from . import uikit as u
from .config import load_config
from .uikit import ASSETS, BLUE_LIGHT, CYAN, DIM, GREEN, H, MUTED, RED, TEXT, W, Cv

GITHUB = "https://github.com/adjacheikhgattacamara-hash/openfaceauth"
PAD = 14
PROFILE_RE = re.compile(r"^[a-z0-9_-]+$")

NAV = [("home", "Accueil", "home"), ("profiles", "Profils", "users"),
       ("settings", "Paramètres", "gear"), ("about", "À propos", "info")]

CHALLENGE_LABELS = [("none", "Aucun"), ("blink", "Clignement"), ("turn", "Rotation"),
                    ("both", "Les deux"), ("strict", "Strict")]
CHALLENGE_HELP = {
    "none": "Aucun défi : une simple photo peut suffire (déconseillé).",
    "blink": "Il faut cligner des yeux devant la caméra.",
    "turn": "Il faut tourner la tête d'un côté tiré au hasard.",
    "both": "Clignement des yeux + rotation de la tête (recommandé).",
    "strict": "Clignement + rotation à gauche et à droite, dans un ordre aléatoire : le plus sûr, un peu plus long.",
}


@dataclass
class Item:
    """Élément dynamique : dessiné (et mis en cache) selon son état."""
    id: str
    x: float
    y: float
    w: float
    h: float
    draw: Callable
    action: Optional[Callable] = None
    sig: Any = None
    idle_only: bool = False
    pad: int = PAD


def _os_name():
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def compute_status():
    """État affiché dans l'en-tête (rapide, sans droits root)."""
    cfg = load_config()
    services = []
    try:
        from . import pamconf

        for svc, label in (("sudo", "sudo"), ("gdm-password", "écran de connexion")):
            try:
                if pamconf.is_enabled(svc):
                    services.append(label)
            except (OSError, ValueError):
                pass
    except Exception:  # noqa: BLE001
        pass
    if not os.access(C.FACEAUTH, os.X_OK):
        title, sub, tone = "Installation incomplète", "Lance le diagnostic", "warn"
    elif not cfg.enabled:
        title, sub, tone = "FaceAuth désactivé", "Réglage général sur « non »", "warn"
    elif services:
        title, sub, tone = "Système prêt", "Reconnaissance faciale activée", "ok"
    else:
        title, sub, tone = "Système prêt", "Aucun service activé", "ok"
    return {"title": title, "sub": sub, "tone": tone, "os": _os_name(), "cfg": cfg}


def challenge_items(mode):
    return {
        "none": [], "blink": [("blink", "Clignement des yeux")],
        "turn": [("turn", "Rotation de la tête")],
        "both": [("blink", "Clignement des yeux"), ("turn", "Rotation de la tête")],
        "strict": [("blink", "Clignement des yeux"), ("left", "Rotation à gauche"), ("right", "Rotation à droite")],
    }.get(mode, [])


def _fit(cv, s, size, weight, max_w):
    while size > 7 and cv.measure(s, size, weight) > max_w:
        size -= .5
    return size


def _ellipsize(cv, s, size, weight, max_w):
    if cv.measure(s, size, weight) <= max_w:
        return s
    while s and cv.measure(s + "…", size, weight) > max_w:
        s = s[:-1]
    return s + "…"


def _blit(img, sprite, x, y):
    bw, bh = img.size
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + sprite.width, bw), min(y + sprite.height, bh)
    if x1 > x0 and y1 > y0:
        img.alpha_composite(sprite.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


class App:
    def __init__(self, scale=1.0, status_fn=compute_status, spawn=None, open_url=None, today=None):
        self.scale = scale
        self.status_fn = status_fn
        self.spawn = spawn
        self.open_url = open_url or webbrowser.open
        self.today = today or datetime.date.today()
        self.page = "home"
        self.hover = self.pressed = None
        self.phase = 0.0
        self.profiles = None          # None = pas encore chargés (liste réservée à root)
        self.busy = None              # None ou {"kind", "title"}
        self.log = []                 # [(texte, tag)]
        self.log_open = False
        self.log_scroll = 0
        self.status_line = ""
        self.toast = None             # [texte, ton, durée restante]
        self.modal = None
        self.test_state = "idle"      # idle | busy | ok | fail
        self._cur = None
        self._buf = []
        self._base_cache = {}
        self._sprites = {}
        self._items = []
        self._anim_cache = {}
        self._logo = None
        self._art = {}
        self.refresh_status()
        self.reset_live()

    # ------------------------------------------------------------------ état
    def refresh_status(self):
        self.status = self.status_fn()
        cfg = self.status["cfg"]
        self.draft = {"challenge": cfg.challenge, "tolerance": round(cfg.tolerance, 2),
                      "timeout": int(cfg.timeout), "enabled": cfg.enabled}
        self._saved = dict(self.draft)

    def reset_live(self):
        self.live = [{"key": k, "label": lbl, "state": "idle"}
                     for k, lbl in challenge_items(self.status["cfg"].challenge)]

    def go(self, page):
        self.page = page
        self.log_open = False

    def show_toast(self, text, tone="info"):
        self.toast = [text, tone, 45]

    # ------------------------------------------------------------- commandes
    def run(self, cmd, title, kind):
        if self.busy:
            self.show_toast("Une action est déjà en cours.", "warn")
            return False
        if self.spawn is None:
            self.show_toast("Impossible de lancer la commande ici.", "err")
            return False
        self.busy = {"kind": kind, "title": title}
        self._buf = []
        self.log.append((f"▶ {title}", "title"))
        self.status_line = title + "…"
        self.spawn(cmd, kind)
        return True

    def on_line(self, line):
        line = line.rstrip("\n")
        if not line.strip():
            return
        kind = self.busy["kind"] if self.busy else ""
        self._buf.append(line)
        self.log.append((line, classify(line)))
        self.status_line = line
        if kind == "test":
            self._parse_test(line)

    def _parse_test(self, line):
        key = None
        if "Fermez les yeux" in line:
            key = "blink"
        elif "votre gauche" in line:
            key = "left"
        elif "votre droite" in line:
            key = "right"
        if key:
            keys = [i["key"] for i in self.live]
            self._cur = "turn" if (key in ("left", "right") and "turn" in keys) else key
        elif line.strip() == "✓" and self._cur:
            for it in self.live:
                if it["key"] == self._cur:
                    it["state"] = "done"

    def on_done(self, code):
        busy, self.busy = self.busy, None
        kind = busy["kind"] if busy else ""
        tail = [t for t, _ in self.log[-6:]]
        self.log.append((f"[terminé, code {code}]", "ok" if code == 0 else "err"))
        self.status_line = ""
        denied = code in (126, 127)
        if kind == "test":
            ok = code == 0
            self.test_state = "ok" if ok else "fail"
            if ok:
                for it in self.live:
                    it["state"] = "done"
            else:
                for it in self.live:
                    if it["state"] != "done":
                        it["state"] = "fail"
                        break
                reason = next((ln for ln in reversed(self._buf) if ln.startswith("ÉCHEC")), None)
                self.open_modal("Vérification échouée", reason or "Le test a échoué. Voir le journal.",
                                icon="warning", buttons=[("Voir le journal", "ghost", self._open_log),
                                                         ("Fermer", "primary", self.close_modal)])
            return
        if denied and kind not in ("enroll", "profile"):
            self.show_toast("Mot de passe administrateur annulé ou refusé.", "warn")
            return
        if kind in ("enroll", "profile"):
            if code == 0:
                self.profiles = None
                self.show_toast("Visage enregistré. Lance maintenant le test.", "ok")
            else:
                self.show_toast("Enregistrement non terminé : voir le journal.", "err")
                self.log_open = True
        elif kind == "profiles":
            data = next((json.loads(ln) for ln in reversed(self._buf) if ln.startswith("{")), None) \
                if code == 0 else None
            if data is not None:
                self.profiles = list(data.get("profiles", []))
                self.show_toast(f"{len(self.profiles)} profil(s) chargé(s).", "ok")
            else:
                self.show_toast("Impossible de lire les profils.", "err")
        elif kind == "delete":
            if code == 0:
                self.profiles = None
                self.show_toast("Profil supprimé.", "ok")
            else:
                self.show_toast("Suppression impossible : voir le journal.", "err")
        elif kind == "config":
            if code == 0:
                self.refresh_status()
                self.reset_live()
                self.show_toast("Réglages enregistrés.", "ok")
            else:
                self.show_toast("Réglages refusés : voir le journal.", "err")
                self.log_open = True
        elif kind in ("enable_sudo", "enable_login", "disable_all"):
            self.refresh_status()
            self.show_toast(tail[-1] if code == 0 and tail else "Action échouée : voir le journal.",
                            "ok" if code == 0 else "err")
        elif kind in ("doctor", "status"):
            self._open_log()

    # --------------------------------------------------------------- actions
    def _open_log(self):
        self.close_modal()
        self.log_open = True
        self.log_scroll = 0

    def act_enroll(self):
        self.run(C.commands()["enroll"], "Enregistrement du visage", "enroll")

    def act_test(self):
        if self.busy:
            return self.show_toast("Une action est déjà en cours.", "warn")
        self.reset_live()
        self._cur = None
        self.test_state = "busy"
        if not self.run(C.commands()["test"], "Test de reconnaissance", "test"):
            self.test_state = "idle"

    def act_activate(self):
        self.open_modal(
            "Activer l'authentification",
            "Où veux-tu utiliser la reconnaissance faciale ? Ton mot de passe reste toujours disponible.",
            icon="rocket",
            buttons=[("Annuler", "ghost", self.close_modal),
                     ("Écran de connexion", "ghost", self._confirm_login),
                     ("Pour sudo", "primary", self._enable_sudo)])

    def _enable_sudo(self):
        self.close_modal()
        self.run(C.commands()["enable_sudo"], "Activation pour sudo", "enable_sudo")

    def _confirm_login(self):
        self.open_modal(
            "Écran de connexion",
            "Ton mot de passe continue de fonctionner. Le trousseau de clés GNOME ne se déverrouille pas "
            "avec le visage. Teste d'abord avec sudo, et garde un moyen de revenir en arrière "
            "(« Tout désactiver » ou Ctrl+Alt+F3).",
            icon="warning",
            buttons=[("Annuler", "ghost", self.close_modal), ("Activer", "primary", self._enable_login)])

    def _enable_login(self):
        self.close_modal()
        self.run(C.commands()["enable_login"], "Activation à l'écran de connexion", "enable_login")

    def act_disable_all(self):
        self.open_modal("Tout désactiver",
                        "Retirer FaceAuth de sudo et de l'écran de connexion ? Le mot de passe seul sera utilisé.",
                        icon="power",
                        buttons=[("Annuler", "ghost", self.close_modal), ("Tout désactiver", "danger", self._disable_all)])

    def _disable_all(self):
        self.close_modal()
        self.run(C.commands()["disable_all"], "Désactivation", "disable_all")

    def act_add_profile(self):
        self.open_modal("Ajouter un profil",
                        "Donne un nom au profil (ex. lunettes, voile, barbe). Le visage sera capturé de nouveau.",
                        icon="user_plus", input_text="",
                        buttons=[("Annuler", "ghost", self.close_modal), ("Continuer", "primary", self._submit_profile)])

    def _submit_profile(self):
        name = self.modal["input"].strip().lower().replace(" ", "-") if self.modal else ""
        if not PROFILE_RE.match(name):
            self.modal["error"] = "Utilise seulement a-z, 0-9, - et _."
            return
        self.close_modal()
        self.run(C.profile_command(name), f"Enregistrement du profil « {name} »", "profile")

    def act_load_profiles(self):
        self.run(C.commands()["profiles"], "Chargement des profils", "profiles")

    def act_delete_profile(self, name):
        self.open_modal("Supprimer le profil",
                        f"Supprimer le profil « {name} » ? Cette action est définitive.", icon="trash",
                        buttons=[("Annuler", "ghost", self.close_modal),
                                 ("Supprimer", "danger", lambda: self._delete(name))])

    def _delete(self, name):
        self.close_modal()
        self.run(C.remove_profile_command(name), f"Suppression du profil « {name} »", "delete")

    def act_save_settings(self):
        values = {"liveness.challenge": self.draft["challenge"],
                  "recognition.tolerance": f"{self.draft['tolerance']:.2f}",
                  "liveness.timeout": str(self.draft["timeout"]),
                  "general.enabled": "true" if self.draft["enabled"] else "false"}
        self.run(C.config_command(values), "Enregistrement des réglages", "config")

    def act_run(self, kind, title):
        self.run(C.commands()[kind], title, kind)

    def _step(self, key, delta, lo, hi, nd):
        self.draft[key] = round(min(hi, max(lo, self.draft[key] + delta)), nd)

    # ----------------------------------------------------------------- modal
    def open_modal(self, title, text, icon="info", buttons=(), input_text=None):
        self.modal = {"title": title, "text": text, "icon": icon, "buttons": list(buttons),
                      "input": input_text, "error": ""}

    def close_modal(self):
        self.modal = None

    # ------------------------------------------------------------- événements
    def _hit(self, x, y):
        for it in reversed(self._items):
            if self.modal and not it.id.startswith("mb"):
                continue
            if it.action and it.x <= x <= it.x + it.w and it.y <= y <= it.y + it.h:
                return it
        return None

    def _pt(self, px, py):
        return px / self.scale, py / self.scale

    def motion(self, px, py):
        it = self._hit(*self._pt(px, py))
        new = it.id if it else None
        changed = new != self.hover
        self.hover = new
        return changed

    def cursor(self):
        it = next((i for i in self._items if i.id == self.hover), None)
        return "hand2" if it and not (it.idle_only and self.busy) else ""

    def leave(self):
        changed = self.hover is not None or self.pressed is not None
        self.hover = self.pressed = None
        return changed

    def press(self, px, py):
        it = self._hit(*self._pt(px, py))
        self.pressed = it.id if it else None
        return bool(it)

    def release(self, px, py):
        it = self._hit(*self._pt(px, py))
        pressed, self.pressed = self.pressed, None
        if not it or it.id != pressed:
            return True
        if it.idle_only and self.busy:
            self.show_toast("Une action est déjà en cours.", "warn")
        else:
            it.action()
        return True

    def key(self, char, keysym):
        if self.modal:
            m = self.modal
            if keysym == "Escape":
                self.close_modal()
            elif keysym in ("Return", "KP_Enter") and m["buttons"]:
                m["buttons"][-1][2]()
            elif m["input"] is not None:
                if keysym == "BackSpace":
                    m["input"] = m["input"][:-1]
                elif char and char.isprintable() and len(m["input"]) < 24:
                    m["input"] += char
                m["error"] = ""
        elif keysym == "Escape" and self.log_open:
            self.log_open = False

    def wheel(self, delta):
        if self.log_open:
            self.log_scroll = max(0, self.log_scroll + (3 if delta > 0 else -3))
            return True
        return False

    def tick(self):
        """Avance l'animation ; renvoie True si le cadre fixe doit être redessiné."""
        self.phase = (self.phase + 1 / 48) % 1.0
        redraw = False
        if self.toast:
            self.toast[2] -= 1
            if self.toast[2] <= 0:
                self.toast = None
            redraw = True
        if self.modal and self.modal["input"] is not None and int(self.phase * 48) % 12 == 0:
            redraw = True  # curseur clignotant
        return redraw

    # ----------------------------------------------------------------- rendu
    def art(self, name):
        """Image de assets/art/<name>.png (extraite de la maquette), ou None si absente."""
        if name not in self._art:
            f = ASSETS / "art" / f"{name}.png"
            self._art[name] = Image.open(f).convert("RGBA") if f.is_file() else None
        return self._art[name]

    @property
    def logo(self):
        if self._logo is None:
            p = ASSETS / "logo.png"
            self._logo = Image.open(p).convert("RGBA") if p.is_file() else False
        return self._logo or None

    def new_cv(self, w, h, bg=None):
        # Sur-échantillonnage 2× en taille normale ; 1,5× au-delà : la résolution interne
        # reste à peu près constante, donc le redessin ne devient pas plus lent en grand.
        return Cv(w, h, self.scale, ss=2 if self.scale <= 1.1 else 1.5, bg=bg)

    def set_scale(self, scale: float) -> bool:
        """Change l'échelle de dessin (fenêtre redimensionnée). Vide les caches
        dépendants de l'échelle ; retourne True si l'échelle a vraiment changé."""
        scale = max(0.4, min(float(scale), 3.0))
        if abs(scale - self.scale) < 0.005:
            return False
        self.scale = scale
        self._base_cache.clear()
        self._sprites.clear()
        self._anim_cache.clear()
        return True

    def _common_base(self):
        if "common" in self._base_cache:
            return self._base_cache["common"]
        cv = self.new_cv(W, H, bg="#000000")
        u.draw_background(cv)
        # barre latérale
        side = self.art("sidebar_art")
        cv.rrect(12, 12, 172, 636, 18, fill=("grad", (5, 16, 40, 245), (3, 11, 30, 245), "v"),
                 outline=(50, 150, 255, 230), ow=1.6, glow=(u.BLUE, 11, 120))
        if self.logo:
            cv.paste(self.logo, 22, 24, 152)
        if side:
            art = side.crop((0, 0, side.width, int(side.height * .96)))
            cv.paste(art, 11, 452, 176)
        else:
            cv.text(98, 468, "Innover • Protéger • Avancer", 9.5, "regular", TEXT, "mm", italic=True)
            cv.text(98, 487, "ACGC INNOV'BOT", 8.5, "medium", "#cfe4ff", "mm")
            u.draw_light_streak(cv, 30, 524, 172, 510)
            u.draw_skyline(cv, 14, 540, 168, 636)
        # en-tête
        u.panel(cv, 196, 12, 992, 78, 18)
        head = self.art("head_icon")
        if head:
            cv.paste(head, 211, 22, 62)
        else:
            u.icon(cv, "face_scan", 242, 51, 54, BLUE_LIGHT)
        cv.line([(282, 26), (282, 76)], (30, 90, 180, 255), 1.2)
        cv.text(298, 24, "FaceAuth", 31, "bold", "#ffffff", italic=True)
        cv.text(300, 62, "Votre visage, votre accès sécurisé", 11.5, "regular", TEXT, italic=True)
        cv.line([(1040, 28), (1040, 74)], (30, 90, 180, 255), 1.2)
        # pied de page
        u.panel(cv, 196, 604, 992, 44, 14, glow=False)
        u.icon(cv, "info", 222, 626, 18, BLUE_LIGHT)
        self._base_cache["common"] = cv.img.copy(), cv
        return self._base_cache["common"]

    def _base(self, page):
        if page in self._base_cache:
            return self._base_cache[page]
        img, proto = self._common_base()
        cv = self.new_cv(W, H)
        cv.img = img.copy()
        cv.d = ImageDraw.Draw(cv.img)
        getattr(self, f"_base_{page}")(cv)
        out = cv.finish()
        self._base_cache[page] = out
        return out

    def _base_home(self, cv):
        u.panel(cv, 196, 100, 330, 282, 16)
        face = self.art("face_panel")
        if face:
            cv.paste(face, 196, 100, 330, 282)
        for dx in (0, 8):
            cv.poly([(548 + dx, 126), (555 + dx, 108), (560 + dx, 108), (553 + dx, 126)], fill=u.BLUE)
        cv.text(578, 117, "Que souhaitez-vous faire ?", 16, "bold", "#ffffff", "lm", italic=True)
        cards = [("user_plus", "Enregistrer un visage", "Capturez votre visage (pour ajouter un profil)."),
                 ("shield", "Tester la reconnaissance", "Vérifiez votre identité avec les défis anti-fraude."),
                 ("rocket", "Activer l'authentification", "Utilisez FaceAuth pour sudo et l'écran de connexion.")]
        for i, (ic, title, text) in enumerate(cards):
            x = 546 + i * 218
            u.panel(cv, x, 134, 206, 248, 14)
            badge = self.art(f"badge_{ic}")
            if badge:
                cv.paste(badge, x + 63, 146, 80)
            else:
                u.icon_badge(cv, ic, x + 103, 186, 29)
            size = _fit(cv, title, 12, "bold", 186)
            cv.text(x + 103, 244, title, size, "bold", "#ffffff", "mm")
            for j, line in enumerate(cv.wrap(text, 10, 168)):
                cv.text(x + 103, 270 + j * 16, line, 10, "regular", MUTED, "mm")
        # rangée du bas
        u.panel(cv, 196, 394, 380, 196, 14)
        u.icon(cv, "users", 222, 418, 22, BLUE_LIGHT)
        u.panel(cv, 593, 394, 328, 196, 14)
        u.icon(cv, "pulse", 619, 418, 22, BLUE_LIGHT)
        cv.text(640, 418, "Détection du vivant", 12.5, "bold", "#ffffff", "lm")
        u.panel(cv, 938, 394, 250, 196, 14)
        u.icon(cv, "warning", 962, 418, 22, RED)
        cv.text(982, 418, "Mot de passe de secours", 11.5, "bold", "#ffffff", "lm")
        u.icon(cv, "keyboard", 1063, 468, 34, BLUE_LIGHT)
        cv.rrect(952, 492, 222, 50, 10, fill=(6, 18, 40, 255), outline=(30, 70, 140, 255))
        for j, line in enumerate(cv.wrap("Votre mot de passe Linux reste toujours disponible en cas de besoin.", 9.5, 200)):
            cv.text(1063, 505 + j * 15, line, 9.5, "regular", MUTED, "mm")

    def _base_profiles(self, cv):
        u.panel(cv, 196, 100, 992, 490, 16)
        cv.text(226, 118, "Profils enregistrés", 18, "bold", "#ffffff")
        cv.text(226, 148, "Chaque profil est un jeu d'échantillons (lunettes, voile, barbe…). "
                          "Tous sont acceptés à la connexion.", 10.5, "regular", MUTED)

    def _base_settings(self, cv):
        u.panel(cv, 196, 100, 992, 490, 16)
        cv.text(226, 118, "Paramètres", 18, "bold", "#ffffff")
        cv.text(226, 148, "Les réglages sont enregistrés dans /etc/faceauth/faceauth.conf (mot de passe "
                          "administrateur demandé).", 10.5, "regular", MUTED)
        for label, y in (("Défis anti-fraude", 186), ("Tolérance de reconnaissance", 280),
                         ("Délai maximum", 352), ("FaceAuth actif", 424)):
            cv.text(226, y, label, 12.5, "bold", "#ffffff")
        cv.rrect(780, 186, 380, 258, 14, fill=(8, 22, 50, 255), outline=(30, 80, 160, 255))
        cv.text(804, 208, "Maintenance", 12.5, "bold", "#ffffff")
        cv.text(804, 232, "Contrôle l'installation, la caméra et les services activés.", 9.5, "regular", MUTED)

    def _base_about(self, cv):
        u.panel(cv, 196, 100, 992, 490, 16)
        if self.logo:
            cv.paste(self.logo, 232, 150, 230)
        cv.text(500, 140, "FaceAuth", 32, "bold", "#ffffff", italic=True)
        cv.text(500, 186, f"Version {__version__} · par ACGC Innov'Bot · licence MIT", 11, "regular", BLUE_LIGHT)
        desc = ("FaceAuth ajoute la reconnaissance faciale à sudo et à l'écran de connexion de Linux "
                "avec une simple webcam, sans capteur infrarouge. Un défi aléatoire (clignement, rotation de "
                "la tête) bloque les photos, et le mot de passe reste toujours utilisable.")
        for i, line in enumerate(cv.wrap(desc, 11.5, 640)):
            cv.text(500, 222 + i * 22, line, 11.5, "regular", TEXT)
        cv.rrect(500, 350, 640, 96, 12, fill=(40, 28, 6, 255), outline=(150, 100, 20, 255))
        u.icon(cv, "warning", 530, 398, 26, u.AMBER)
        warn = ("Une webcam ordinaire ne voit pas la profondeur : FaceAuth est moins sûr qu'un capteur "
                "infrarouge ou une empreinte. Une vidéo générée en direct ou un masque 3D peut encore le tromper.")
        for i, line in enumerate(cv.wrap(warn, 10.5, 570)):
            cv.text(558, 372 + i * 20, line, 10.5, "regular", "#ffd991")

    # ------------------------------------------------------------- éléments
    def _make_items(self):
        items = []
        add = items.append
        st = self.status

        def button(id_, x, y, w, h, label, style, ic=None, arrow=False, action=None, idle_only=True, size=11):
            add(Item(id_, x, y, w, h,
                     lambda cv, px, py, pw, ph, state, l=label, s=style, i=ic, a=arrow, z=size:
                     u.draw_button(cv, px, py, pw, ph, l, s, i, a, state, z),
                     action, (label, style), idle_only))

        # barre latérale
        for i, (key, label, ic) in enumerate(NAV):
            add(Item(f"nav:{key}", 20, 196 + i * 54, 156, 46,
                     lambda cv, px, py, pw, ph, state, l=label, c=ic, k=key:
                     u.draw_nav_item(cv, px, py, pw, ph, l, c, k == self.page, state),
                     lambda k=key: self.go(k), self.page == key))
        # en-tête : état du système + système d'exploitation
        add(Item("status", 788, 24, 244, 54, self._draw_status, None, (st["title"], st["sub"], st["tone"])))
        add(Item("os", 1050, 24, 130, 54, self._draw_os, None, st["os"]))
        # pied de page
        line = self.status_line if self.busy else ""
        add(Item("footer", 236, 610, 520, 32, self._draw_footer, None, line))
        add(Item("journal", 800, 610, 100, 32,
                 lambda cv, px, py, pw, ph, state: u.draw_button(cv, px, py, pw, ph, "Journal", "ghost", "list",
                                                                 False, state, 10),
                 lambda: setattr(self, "log_open", not self.log_open), len(self.log)))
        add(Item("date", 916, 610, 262, 32, self._draw_date, None, str(self.today)))
        if self.log_open:
            items += self._log_items()
        else:
            getattr(self, f"_items_{self.page}")(items, button)
        if self.toast:
            add(Item("toast", 300, 556, 600, 40, self._draw_toast, None, tuple(self.toast[:2]), pad=20))
        if self.modal:
            items += self._modal_items()
        return items

    # -- éléments communs
    def _draw_status(self, cv, x, y, w, h, state):
        st = self.status
        tone = {"ok": GREEN, "warn": u.AMBER}.get(st["tone"], GREEN)
        cv.rrect(x, y, w, h, h / 2, fill=(6, 30, 26, 255) if st["tone"] == "ok" else (40, 28, 6, 255),
                 outline=tone, ow=1.3, glow=(tone, 6, 70))
        cv.ellipse(x + 30, y + h / 2, 11, fill=tone, glow=(tone, 7, 150))
        cv.text(x + 54, y + 19, st["title"], 13.5, "bold", tone, "lm")
        cv.text(x + 54, y + 38, _ellipsize(cv, st["sub"], 9.5, "regular", w - 70), 9.5, "regular", TEXT, "lm")

    def _draw_os(self, cv, x, y, w, h, state):
        tux = self.art("tux")
        if tux:
            cv.paste(tux, x + 2, y + 3, 34)
        else:
            u.icon_tux(cv, x + 20, y + h / 2, 42)
        cv.text(x + 46, y + 19, "Linux", 13.5, "bold", "#ffffff", "lm")
        cv.text(x + 46, y + 38, _ellipsize(cv, self.status["os"], 9, "regular", w - 48), 9, "regular", MUTED, "lm")

    def _draw_footer(self, cv, x, y, w, h, state):
        if self.busy and self.status_line:
            cv.ellipse(x + 6, y + h / 2, 4, fill=CYAN, glow=(CYAN, 4, 160))
            cv.text(x + 20, y + h / 2, _ellipsize(cv, self.status_line, 10, "regular", w - 24), 10, "regular", TEXT, "lm")
        else:
            wd = cv.text(x, y + h / 2, "FaceAuth - ACGC INNOV'BOT", 10, "medium", TEXT, "lm")
            cv.text(x + wd + 14, y + h / 2, "|", 10, "regular", DIM, "lm")
            cv.text(x + wd + 30, y + h / 2, "Sécurité, Innovation, Excellence", 10, "regular", MUTED, "lm")

    def _draw_date(self, cv, x, y, w, h, state):
        txt = f"v{__version__}  •  {self.today.strftime('%d/%m/%Y')}"
        tw = cv.measure(txt, 10, "medium")
        cv.text(x + w - 6, y + h / 2, txt, 10, "medium", TEXT, "rm")
        u.icon(cv, "calendar", x + w - 6 - tw - 18, y + h / 2, 18, BLUE_LIGHT)

    def _draw_toast(self, cv, x, y, w, h, state):
        text, tone = self.toast[0], self.toast[1]
        c = {"ok": GREEN, "err": RED, "warn": u.AMBER}.get(tone, BLUE_LIGHT)
        tw = min(w, cv.measure(text, 11, "medium") + 56)
        x0 = x + (w - tw) / 2
        cv.rrect(x0, y, tw, h, h / 2, fill=(8, 20, 44, 255), outline=c, ow=1.3, glow=(c, 7, 110))
        cv.ellipse(x0 + 20, y + h / 2, 5, fill=c)
        cv.text(x0 + 34, y + h / 2, _ellipsize(cv, text, 11, "medium", tw - 46), 11, "medium", TEXT, "lm")

    # -- accueil
    def _items_home(self, items, button):
        add = items.append
        add(Item("badge", 222, 346, 278, 34, self._draw_badge, None, self.test_state))
        specs = [("Commencer", "camera", True, self.act_enroll), ("Tester", "play", True, self.act_test),
                 ("Activer", "bolt", True, self.act_activate)]
        for i, (label, ic, arrow, act) in enumerate(specs):
            button(f"card{i}", 546 + i * 218 + 16, 334, 174, 38, label, "primary", ic, arrow, act)
        # profils
        add(Item("manage", 470, 404, 100, 28,
                 lambda cv, px, py, pw, ph, state: u.draw_link(cv, px, py, pw, ph, "Gérer", state),
                 lambda: self.go("profiles")))
        add(Item("ptitle", 244, 404, 220, 28, self._draw_profiles_title, None, self._count()))
        if self.profiles is None:
            add(Item("pmsg", 214, 448, 344, 44, lambda cv, x, y, w, h, s: [
                cv.text(x + w / 2, y + 8, "La liste des profils est protégée.", 10.5, "medium", TEXT, "mm"),
                cv.text(x + w / 2, y + 28, "Le mot de passe administrateur sera demandé.", 9.5, "regular", MUTED, "mm")],
                None, 0))
            button("pload", 270, 506, 232, 36, "Charger les profils", "ghost", "refresh", False, self.act_load_profiles)
        else:
            shown = self.profiles[:3]
            for i, name in enumerate(shown):
                add(Item(f"prof{i}", 214 + i * 90, 446, 82, 132, self._profile_card(name), None, name))
            slot = len(shown)
            add(Item("padd", 214 + slot * 90, 446, 82, 132, self._draw_add_card, self.act_add_profile, 0, True))
        # détection du vivant
        if not self.live:
            add(Item("lnone", 615, 450, 190, 40, lambda cv, x, y, w, h, s: cv.text(
                x, y + 12, "Aucun défi actif (déconseillé)", 10.5, "regular", u.AMBER, "lm"), None, 0))
        for i, it in enumerate(self.live[:3]):
            add(Item(f"live{i}", 615, 446 + i * 34, 200, 28, self._live_row(i), None, (it["state"], it["label"])))
        add(Item("ring", 784, 444, 112, 112, self._draw_ring, None, self.test_state))
        add(Item("pill", 764, 550, 140, 28, self._draw_pill, None, self.test_state))
        button("alloff", 958, 546, 210, 36, "Tout désactiver", "danger", "power", False, self.act_disable_all)

    def _count(self):
        return "?" if self.profiles is None else str(len(self.profiles))

    def _draw_profiles_title(self, cv, x, y, w, h, state):
        cv.text(x, y + h / 2, f"Profils enregistrés ({self._count()})", 12.5, "bold", "#ffffff", "lm")

    def _draw_badge(self, cv, x, y, w, h, state):
        mode = self.test_state
        label, tone = {"idle": ("Prêt pour la reconnaissance", GREEN), "busy": ("Analyse en cours…", CYAN),
                       "ok": ("Visage reconnu", GREEN), "fail": ("Visage non reconnu", RED)}[mode]
        cv.rrect(x, y, w, h, h / 2, fill=(5, 24, 30, 255), outline=tone, ow=1.4, glow=(tone, 6, 100))
        cv.ellipse(x + 24, y + h / 2, 11, fill=tone)
        if mode == "fail":
            cv.line([(x + 20, y + h / 2 - 4), (x + 28, y + h / 2 + 4)], "#ffffff", 2)
            cv.line([(x + 28, y + h / 2 - 4), (x + 20, y + h / 2 + 4)], "#ffffff", 2)
        else:
            u.icon(cv, "check", x + 24, y + h / 2, 16, "#ffffff")
        cv.text(x + 46, y + h / 2, label, 12, "bold", tone, "lm")

    def _profile_card(self, name):
        def draw(cv, x, y, w, h, state):
            cv.rrect(x, y, w, h, 12, fill=(8, 24, 54, 255), outline=(30, 80, 160, 255))
            cx = x + w / 2
            cv.ellipse(cx, y + 38, 29, fill=("grad", "#2a8fff", "#0a3d96", "v"), outline=BLUE_LIGHT, ow=1.4)
            cv.text(cx, y + 38, name[:1].upper(), 24, "bold", "#ffffff", "mm")
            label = name.capitalize()
            cv.text(cx, y + 88, _ellipsize(cv, label, 10, "bold", w - 8), 10, "bold", "#ffffff", "mm")
            cv.ellipse(cx - 20, y + 108, 3.5, fill=GREEN)
            cv.text(cx - 12, y + 108, "Actif", 9, "medium", GREEN, "lm")
        return draw

    def _draw_add_card(self, cv, x, y, w, h, state):
        hov = state in ("hover", "pressed")
        c = (80, 150, 240, 255) if hov else (45, 100, 180, 255)
        if hov:
            cv.rrect(x, y, w, h, 12, fill=(14, 38, 80, 255))
        for x0 in range(int(x) + 8, int(x + w) - 8, 10):
            cv.line([(x0, y), (x0 + 5, y)], c, 1.2, False)
            cv.line([(x0, y + h), (x0 + 5, y + h)], c, 1.2, False)
        for y0 in range(int(y) + 8, int(y + h) - 8, 10):
            cv.line([(x, y0), (x, y0 + 5)], c, 1.2, False)
            cv.line([(x + w, y0), (x + w, y0 + 5)], c, 1.2, False)
        u.icon(cv, "plus", x + w / 2, y + 44, 30, BLUE_LIGHT if hov else TEXT)
        for j, line in enumerate(("Ajouter un", "profil")):
            cv.text(x + w / 2, y + 84 + j * 15, line, 10, "regular", TEXT if hov else MUTED, "mm")

    def _live_row(self, i):
        def draw(cv, x, y, w, h, state):
            it = self.live[i]
            st = it["state"]
            c = {"done": GREEN, "fail": RED}.get(st, BLUE_LIGHT)
            cv.ellipse(x + 11, y + h / 2, 10, fill=c if st in ("done", "fail") else (8, 28, 64, 255),
                       outline=c, ow=1.4)
            if st == "fail":
                cv.line([(x + 7, y + h / 2 - 4), (x + 15, y + h / 2 + 4)], "#ffffff", 2)
                cv.line([(x + 15, y + h / 2 - 4), (x + 7, y + h / 2 + 4)], "#ffffff", 2)
            else:
                u.icon(cv, "check", x + 11, y + h / 2, 13, "#ffffff" if st == "done" else (60, 130, 220, 255))
            cv.text(x + 30, y + h / 2, it["label"], 11, "medium", "#ffffff" if st != "idle" else TEXT, "lm")
        return draw

    def _draw_ring(self, cv, x, y, w, h, state):
        mode = self.test_state
        c = {"ok": GREEN, "fail": RED, "busy": CYAN}.get(mode, (40, 110, 210, 255))
        cx, cy = x + w / 2, y + h / 2
        cv.ellipse(cx, cy, 38, fill=(4, 20, 30, 255) if mode == "ok" else (6, 18, 40, 255), outline=c, ow=3,
                   glow=(c, 8, 90 if mode != "idle" else 40))
        if mode == "fail":
            cv.line([(cx - 14, cy - 14), (cx + 14, cy + 14)], c, 5)
            cv.line([(cx + 14, cy - 14), (cx - 14, cy + 14)], c, 5)
        elif mode == "ok":
            u.icon(cv, "check", cx, cy, 52, c)
        elif mode == "busy":
            cv.arc(cx, cy, 38, self.phase * 720, self.phase * 720 + 90, "#ffffff", 3)
            u.icon(cv, "shield", cx, cy, 40, c)
        else:
            u.icon(cv, "shield", cx, cy, 40, c)

    def _draw_pill(self, cv, x, y, w, h, state):
        label, c = {"idle": ("En attente", DIM), "busy": ("Vérification…", CYAN),
                    "ok": ("Vérification réussie !", GREEN), "fail": ("Vérification échouée", RED)}[self.test_state]
        cv.rrect(x, y, w, h, h / 2, fill=(6, 22, 28, 255) if self.test_state == "ok" else (8, 20, 44, 255),
                 outline=c, ow=1.2, glow=(c, 4, 90) if self.test_state != "idle" else None)
        cv.text(x + w / 2, y + h / 2, label, 10, "bold", c, "mm")

    # -- profils
    def _items_profiles(self, items, button):
        add = items.append
        button("padd2", 846, 116, 176, 38, "Ajouter un profil", "primary", "user_plus", False, self.act_add_profile, size=10.5)
        button("prefresh", 1034, 116, 130, 38, "Actualiser", "ghost", "refresh", False, self.act_load_profiles, size=10.5)
        if self.profiles is None:
            add(Item("pmsg2", 226, 270, 940, 60, lambda cv, x, y, w, h, s: [
                cv.text(x + w / 2, y + 10, "La liste des profils est protégée (réservée à l'administrateur).", 12, "medium", TEXT, "mm"),
                cv.text(x + w / 2, y + 36, "Clique sur « Actualiser » : le mot de passe administrateur sera demandé.", 10.5, "regular", MUTED, "mm")],
                None, 0))
        elif not self.profiles:
            add(Item("pmsg3", 226, 270, 940, 60, lambda cv, x, y, w, h, s: cv.text(
                x + w / 2, y + 20, "Aucun profil enregistré. Commence par enregistrer ton visage.", 12, "medium", TEXT, "mm"), None, 0))
            button("penr", 480, 340, 240, 40, "Enregistrer mon visage", "primary", "camera", False, self.act_enroll)
        for i, name in enumerate((self.profiles or [])[:6]):
            y = 178 + i * 66
            add(Item(f"row{i}", 226, y, 880, 56, self._profile_row(name), None, name))
            add(Item(f"del{i}", 1118, y + 8, 40, 40,
                     lambda cv, px, py, pw, ph, state: u.draw_button(cv, px, py, pw, ph, "", "danger" if state != "normal" else "ghost",
                                                                     "trash", False, state, 12),
                     lambda n=name: self.act_delete_profile(n), "trash", True))

    def _profile_row(self, name):
        def draw(cv, x, y, w, h, state):
            cv.rrect(x, y, w, h, 12, fill=(8, 24, 54, 255), outline=(30, 80, 160, 255))
            cv.ellipse(x + 34, y + h / 2, 19, fill=("grad", "#2a8fff", "#0a3d96", "v"), outline=BLUE_LIGHT, ow=1.2)
            cv.text(x + 34, y + h / 2, name[:1].upper(), 16, "bold", "#ffffff", "mm")
            cv.text(x + 66, y + 19, name.capitalize(), 12.5, "bold", "#ffffff", "lm")
            cv.text(x + 66, y + 38, "Enregistrement principal" if name == "principal" else "Profil supplémentaire",
                    9.5, "regular", MUTED, "lm")
            cv.ellipse(x + w - 62, y + h / 2, 4, fill=GREEN)
            cv.text(x + w - 52, y + h / 2, "Actif", 10, "medium", GREEN, "lm")
        return draw

    # -- paramètres
    def _items_settings(self, items, button):
        add = items.append
        d = self.draft
        for i, (val, label) in enumerate(CHALLENGE_LABELS):
            add(Item(f"ch:{val}", 226 + i * 104, 214, 96, 32,
                     lambda cv, px, py, pw, ph, state, v=val, l=label: u.draw_chip(cv, px, py, pw, ph, l, d["challenge"] == v, state),
                     lambda v=val: d.__setitem__("challenge", v), d["challenge"] == val, True))
        add(Item("chhelp", 226, 254, 520, 20, lambda cv, x, y, w, h, s: cv.text(
            x, y + h / 2, _ellipsize(cv, CHALLENGE_HELP[d["challenge"]], 10, "regular", w), 10, "regular", MUTED, "lm"),
            None, d["challenge"]))
        self._stepper(items, "tol", 308, "tolerance", .05, .30, .60, 2, lambda v: f"{v:.2f}",
                      lambda v: "Très strict" if v <= .35 else "Strict" if v <= .42 else
                      "Équilibré (conseillé)" if v <= .50 else "Permissif")
        self._stepper(items, "to", 380, "timeout", 2, 6, 30, 0, lambda v: f"{int(v)} s",
                      lambda v: "Au-delà, le mot de passe reprend la main.")
        for i, (val, label) in enumerate(((True, "Oui"), (False, "Non"))):
            add(Item(f"en:{val}", 226 + i * 120, 452, 110, 32,
                     lambda cv, px, py, pw, ph, state, v=val, l=label: u.draw_chip(cv, px, py, pw, ph, l, d["enabled"] == v, state),
                     lambda v=val: d.__setitem__("enabled", v), d["enabled"] == val, True))
        changed = d != self._saved
        button("save", 226, 518, 240, 42, "Enregistrer les réglages", "primary" if changed else "ghost", "check",
               False, self.act_save_settings if changed else None, size=11)
        if changed:
            button("cancel", 478, 518, 130, 42, "Annuler", "ghost", None, False,
                   lambda: d.update(self._saved), size=11)
        button("doctor", 804, 262, 332, 40, "Diagnostic", "ghost", "shield", False,
               lambda: self.act_run("doctor", "Diagnostic"), size=10.5)
        button("status", 804, 314, 332, 40, "État de l'installation", "ghost", "info", False,
               lambda: self.act_run("status", "État"), size=10.5)
        button("openlog", 804, 366, 332, 40, "Ouvrir le journal", "ghost", "list", False, self._open_log, False, size=10.5)

    def _stepper(self, items, id_, y, key, step, lo, hi, nd, fmt, desc):
        d = self.draft
        for j, (sym, delta, x) in enumerate((("−", -step, 226), ("+", step, 372))):
            items.append(Item(f"{id_}{'m' if delta < 0 else 'p'}", x, y, 36, 36,
                              lambda cv, px, py, pw, ph, state, s=sym: u.draw_button(cv, px, py, pw, ph, s, "ghost", None, False, state, 15),
                              lambda dl=delta: self._step(key, dl, lo, hi, nd), 0, True))
        items.append(Item(f"{id_}v", 268, y, 100, 36, lambda cv, x, y_, w, h, s: cv.text(
            x + w / 2, y_ + h / 2, fmt(d[key]), 14, "bold", "#ffffff", "mm"), None, d[key]))
        items.append(Item(f"{id_}d", 426, y, 330, 36, lambda cv, x, y_, w, h, s: cv.text(
            x, y_ + h / 2, desc(d[key]), 10.5, "regular", MUTED, "lm"), None, d[key]))

    # -- à propos
    def _items_about(self, items, button):
        button("github", 500, 474, 300, 42, "Voir le projet sur GitHub", "primary", "arrow", False,
               lambda: self.open_url(GITHUB), False, size=11)

    # -- journal
    def _log_items(self):
        items = [Item("logpanel", 196, 100, 992, 490, self._draw_log, None, (len(self.log), self.log_scroll), pad=4)]
        items.append(Item("logclear", 960, 110, 100, 34, lambda cv, px, py, pw, ph, st: u.draw_button(
            cv, px, py, pw, ph, "Effacer", "ghost", "trash", False, st, 10),
            lambda: (self.log.clear(), setattr(self, "log_scroll", 0)), len(self.log)))
        items.append(Item("logclose", 1070, 110, 100, 34, lambda cv, px, py, pw, ph, st: u.draw_button(
            cv, px, py, pw, ph, "Fermer", "primary", None, False, st, 10),
            lambda: setattr(self, "log_open", False), 0))
        return items

    def _draw_log(self, cv, x, y, w, h, state):
        u.panel(cv, x, y, w, h, 16)
        cv.text(x + 30, y + 28, "Journal", 18, "bold", "#ffffff", "lm")
        rows = []
        for text, tag in self.log:
            wrapped = cv.wrap(text, 10, w - 70) or [""]
            rows += [(ln, tag) for ln in wrapped]
        per = 22
        end = len(rows) - self.log_scroll
        shown = rows[max(0, end - per):max(0, end)]
        colors = {"ok": GREEN, "err": RED, "warn": u.AMBER, "title": BLUE_LIGHT, "": TEXT}
        if not rows:
            cv.text(x + 30, y + 80, "Le journal est vide : lance une action pour voir ses messages ici.", 10.5, "regular", MUTED, "lm")
        for i, (ln, tag) in enumerate(shown):
            cv.text(x + 30, y + 76 + i * 18.5, ln, 10, "bold" if tag == "title" else "regular", colors.get(tag, TEXT), "lm")

    # -- fenêtre de dialogue
    def _modal_items(self):
        m = self.modal
        cv = self.new_cv(10, 10)
        lines = cv.wrap(m["text"], 11, 400)
        h = 150 + len(lines) * 18 + (60 if m["input"] is not None else 0)
        w = 460
        x0, y0 = (W - w) / 2, (H - h) / 2
        items = [Item("modal", 0, 0, W, H, self._draw_modal(x0, y0, w, h, lines), None,
                      (id(m), m["input"], m["error"], int(self.phase * 4) if m["input"] is not None else 0), pad=0)]
        bx = x0 + w - 24
        for i, (label, style, action) in reversed(list(enumerate(m["buttons"]))):
            bw = max(110, cv.measure(label, 11, "bold") + 44)
            bx -= bw
            items.append(Item(f"mb{i}", bx, y0 + h - 62, bw, 40,
                              lambda c, px, py, pw, ph, state, l=label, s=style: u.draw_button(c, px, py, pw, ph, l, s, None, False, state, 11),
                              action, (label, style)))
            bx -= 12
        return items

    def _draw_modal(self, x0, y0, w, h, lines):
        m = self.modal

        def draw(cv, x, y, ww, hh, state):
            cv.rrect(0, 0, W, H, 0, fill=(2, 6, 16, 200))
            u.panel(cv, x0, y0, w, h, 18)
            u.icon_badge(cv, m["icon"], x0 + 52, y0 + 56, 24, u.RED if m["icon"] in ("power", "trash") else BLUE_LIGHT)
            cv.text(x0 + 94, y0 + 56, m["title"], 16, "bold", "#ffffff", "lm")
            for i, ln in enumerate(lines):
                cv.text(x0 + 30, y0 + 104 + i * 18, ln, 11, "regular", MUTED, "lm")
            if m["input"] is not None:
                iy = y0 + 104 + len(lines) * 18 + 14
                cv.rrect(x0 + 30, iy, w - 60, 38, 10, fill=(6, 18, 40, 255), outline=BLUE_LIGHT if not m["error"] else RED, ow=1.4)
                cursor = "│" if int(self.phase * 4) % 2 == 0 else " "
                cv.text(x0 + 44, iy + 19, m["input"] + cursor, 12, "medium", "#ffffff", "lm")
                if m["error"]:
                    cv.text(x0 + 30, iy + 54, m["error"], 9.5, "regular", RED, "lm")
        return draw

    # ------------------------------------------------------------- composition
    def _state_of(self, it):
        if it.idle_only and self.busy:
            return "disabled"
        if self.pressed == it.id:
            return "pressed"
        if self.hover == it.id:
            return "hover"
        return "normal"

    def _sprite(self, it):
        state = self._state_of(it) if it.action else "normal"
        key = (it.id, state, it.sig, it.w, it.h)
        sp = self._sprites.get(key)
        if sp is None:
            if len(self._sprites) > 600:
                self._sprites.clear()
            cv = self.new_cv(it.w + 2 * it.pad, it.h + 2 * it.pad)
            it.draw(cv, it.pad, it.pad, it.w, it.h, state)
            sp = self._sprites[key] = cv.finish()
        return sp

    def frame(self):
        """Image complète (sans le visuel animé, géré à part)."""
        img = self._base(self.page).copy()
        self._items = self._make_items()
        s = self.scale
        for it in self._items:
            sp = self._sprite(it)
            _blit(img, sp, round((it.x - it.pad) * s), round((it.y - it.pad) * s))
        return img.convert("RGB")

    def anim_visible(self):
        return self.page == "home" and not self.modal and not self.log_open

    def anim(self):
        """(image, x, y) de l'animation du visage à la phase courante, ou None."""
        if not self.anim_visible():
            return None
        mode = self.test_state
        idx = int(self.phase * 24) % 24
        key = (idx, mode)
        sp = self._anim_cache.get(key)
        has_art = self.art("face_panel") is not None
        if sp is None:
            if has_art:
                cv = self.new_cv(314, 236)
                u.draw_scan_overlay(cv, 314, 236, idx / 24, mode)
            else:
                cv = self.new_cv(314, 226)
                u.draw_scan_visual(cv, 314, 226, idx / 24, mode)
            sp = self._anim_cache[key] = cv.finish()
        return sp, round(204 * self.scale), round(108 * self.scale)

    def image(self):
        """Écran complet, pour les captures et les tests."""
        img = self.frame().convert("RGBA")
        a = self.anim()
        if a:
            _blit(img, a[0], a[1], a[2])
        return img.convert("RGB")


def classify(line: str) -> str:
    """Choisit la couleur d'une ligne de sortie (« ok », « err », « warn » ou « »)."""
    low = line.lower()
    if any(k in low for k in ("erreur", "error", "échec", "echec", "refusé", "introuvable",
                              "non reconnu", "traceback", "[ko]")):
        return "err"
    if any(k in low for k in ("avertissement", "warning", "attention")):
        return "warn"
    if any(k in low for k in ("succès", "reconnu", "activé", "enregistré", "[ok]", "✓")):
        return "ok"
    return ""
