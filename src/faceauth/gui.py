"""Fenêtre FaceAuth (tkinter) : affiche l'image dessinée par `app.App` et lui
transmet souris et clavier. Les droits administrateur passent par pkexec."""
import base64
import io
import os
import subprocess
import sys

from . import __version__
from .app import App, classify  # noqa: F401  (classify ré-exporté)
from .commands import FACEAUTH, ROOT, commands, config_command, profile_command  # noqa: F401
from .uikit import ASSETS, H, W

LOGO_PATH = ASSETS / "logo.png"
ICON_PATH = ASSETS / "icon.png"
NOISE = ("QFontDatabase", "Qt no longer ships")


def logo_path():
    """Chemin du logo s'il existe, sinon None (l'interface s'en passe)."""
    return LOGO_PATH if LOGO_PATH.is_file() else None


def main() -> int:
    try:
        import queue
        import threading
        import tkinter as tk
    except ImportError:
        print("Interface graphique indisponible : installe python3-tk (sudo apt install python3-tk).")
        return 1

    root = tk.Tk()
    root.title(f"FaceAuth {__version__}")
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    # Taille de départ : grande sur un écran d'ordinateur, sans dépasser l'écran.
    scale = max(0.6, min(1.5, (sw - 60) * 0.9 / W, (sh - 110) * 0.92 / H))
    wpx, hpx = round(W * scale), round(H * scale)
    root.geometry(f"{wpx}x{hpx}+{max(0, (sw - wpx) // 2)}+{max(0, (sh - hpx) // 3)}")
    root.minsize(round(W * 0.6), round(H * 0.6))
    root.resizable(True, True)
    canvas = tk.Canvas(root, width=wpx, height=hpx, highlightthickness=0, bd=0, bg="#030a18")
    canvas.pack(fill="both", expand=True)
    off = {"x": 0, "y": 0}  # marges quand la fenêtre n'a pas le même rapport que le dessin

    refs = {}

    def to_photo(img):
        try:
            from PIL import ImageTk
            return ImageTk.PhotoImage(img)
        except Exception:  # noqa: BLE001  (Pillow sans ImageTk : PNG encodé)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))

    try:
        refs["icon"] = tk.PhotoImage(file=str(ICON_PATH))
        root.iconphoto(True, refs["icon"])
    except Exception:  # noqa: BLE001  (une icône illisible ne bloque pas l'application)
        pass

    q = queue.Queue()

    def worker(cmd, kind):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True,
                                    env=dict(os.environ, PYTHONUNBUFFERED="1"))
            for line in proc.stdout:
                if not any(n in line for n in NOISE):
                    q.put(("line", line))
            q.put(("done", proc.wait()))
        except FileNotFoundError:
            q.put(("line", "Commande introuvable : FaceAuth est-il bien installé ?\n"))
            q.put(("done", 127))

    def spawn(cmd, kind):
        threading.Thread(target=worker, args=(cmd, kind), daemon=True).start()

    app = App(scale, spawn=spawn)
    frame_item = canvas.create_image(0, 0, anchor="nw")
    anim_item = canvas.create_image(0, 0, anchor="nw")
    state = {"dirty": True, "resize": None, "last": None}

    def apply_resize():
        """Fin du redimensionnement : redessin net à la bonne échelle, centré."""
        state["resize"] = None
        cw, ch = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        app.set_scale(min(cw / W, ch / H))
        off["x"] = max(0, (cw - round(W * app.scale)) // 2)
        off["y"] = max(0, (ch - round(H * app.scale)) // 2)
        canvas.coords(frame_item, off["x"], off["y"])
        redraw()

    def preview():
        """Pendant qu'on tire la fenêtre : on étire aussitôt la dernière image nette
        (quelques millisecondes) au lieu d'attendre le vrai redessin (plus d'une demi-seconde)."""
        from PIL import Image

        img = state.get("last")
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if img is None or cw < 2 or ch < 2:
            return
        sc = min(cw / W, ch / H)
        nw, nh = max(1, round(W * sc)), max(1, round(H * sc))
        refs["frame"] = to_photo(img.resize((nw, nh), Image.BILINEAR))
        canvas.itemconfig(frame_item, image=refs["frame"])
        canvas.coords(frame_item, (cw - nw) // 2, (ch - nh) // 2)
        canvas.itemconfig(anim_item, state="hidden")

    def on_configure(_event):
        preview()
        # Le redessin net n'a lieu qu'une fois la souris relâchée (150 ms sans mouvement).
        if state["resize"] is not None:
            root.after_cancel(state["resize"])
        state["resize"] = root.after(150, apply_resize)

    canvas.bind("<Configure>", on_configure)

    def toggle_fullscreen(_event=None):
        root.attributes("-fullscreen", not root.attributes("-fullscreen"))

    root.bind("<F11>", toggle_fullscreen)
    root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))

    def redraw():
        img = app.frame()
        state["last"] = img
        refs["frame"] = to_photo(img)
        canvas.itemconfig(frame_item, image=refs["frame"])
        state["dirty"] = False

    def update_anim():
        a = app.anim()
        if a is None:
            canvas.itemconfig(anim_item, state="hidden")
            return
        refs["anim"] = to_photo(a[0])
        canvas.itemconfig(anim_item, image=refs["anim"], state="normal")
        canvas.coords(anim_item, a[1] + off["x"], a[2] + off["y"])

    def touch(changed=True):
        if changed:
            state["dirty"] = True
        canvas.config(cursor=app.cursor())

    canvas.bind("<Motion>", lambda e: touch(app.motion(e.x - off["x"], e.y - off["y"])))
    canvas.bind("<Leave>", lambda e: touch(app.leave()))
    canvas.bind("<ButtonPress-1>", lambda e: touch(app.press(e.x - off["x"], e.y - off["y"])))
    canvas.bind("<ButtonRelease-1>", lambda e: touch(app.release(e.x - off["x"], e.y - off["y"])))
    canvas.bind("<MouseWheel>", lambda e: touch(app.wheel(e.delta)))
    canvas.bind("<Button-4>", lambda e: touch(app.wheel(1)))
    canvas.bind("<Button-5>", lambda e: touch(app.wheel(-1)))
    root.bind("<Key>", lambda e: touch(app.key(e.char, e.keysym) or True))

    def tick():
        try:
            while True:
                kind, payload = q.get_nowait()
                (app.on_line if kind == "line" else app.on_done)(payload)
                state["dirty"] = True
        except queue.Empty:
            pass
        if app.tick() or app.busy:
            state["dirty"] = True
        if state["resize"] is None:  # pas de redessin au milieu d'un redimensionnement
            if state["dirty"]:
                redraw()
            update_anim()
        root.after(70, tick)

    root.after(10, tick)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
