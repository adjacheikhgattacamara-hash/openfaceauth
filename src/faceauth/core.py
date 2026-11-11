"""Cœur de FaceAuth : caméra, enregistrement du visage, vérification."""
import os
import time

import numpy as np

# Évite les avertissements Qt d'OpenCV (à définir avant « import cv2 »).
if os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
for _fonts in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts"):
    if os.path.isdir(_fonts):
        os.environ.setdefault("QT_QPA_FONTDIR", _fonts)
        break

from .liveness import build_challenges, eye_aspect_ratio, yaw_ratio  # noqa: E402
from .session import AuthSession  # noqa: E402


def identity_distance(distances, k: int = 3) -> float:
    """Distance d'identité entre un visage vu et les échantillons enregistrés.

    On fait la moyenne des `k` échantillons les plus proches, pas le seul plus proche :
    un visage ressemblant (frère, sœur) peut tomber très près d'UN échantillon par
    hasard, mais rarement près de plusieurs à la fois. Le vrai propriétaire, lui,
    est proche de tous ses échantillons.
    """
    d = np.sort(np.asarray(distances, dtype=float).ravel())
    if len(d) == 0:
        return float("inf")
    return float(d[: max(1, min(k, len(d)))].mean())


def is_refused(d_owner: float, d_blocked: float, margin: float) -> bool:
    """Vrai si le visage vu est plus proche d'un visage interdit que du tien (à `margin` près).

    Tu es accepté seulement si ta distance + la marge reste sous celle du visage interdit.
    """
    return d_blocked <= d_owner + margin


def usable_blocked(known, blocked, floor: float = 0.2):
    """Écarte les « visages interdits » qui sont en réalité le tien (distance < floor à
    l'un de tes échantillons) : sinon une erreur d'enregistrement te refuserait toi-même."""
    if blocked is None or len(blocked) == 0:
        return None
    known, blocked = np.asarray(known), np.asarray(blocked)
    keep = [b for b in blocked if np.linalg.norm(known - b, axis=1).min() >= floor]
    return np.array(keep) if keep else None


def measure_distances(cfg, known, frames: int = 12, timeout: float = 20.0, say=print, blocked=None):
    """Mesure la distance entre le visage devant la caméra et les échantillons
    enregistrés (pour choisir le seuil de tolérance). Retourne la liste des distances."""
    import time

    import cv2

    cap = _open_camera(cfg)
    if cap is None:
        raise RuntimeError("caméra introuvable")
    fr = _fr()
    if hasattr(fr, "preload"):
        fr.preload(landmarks=False)
    out, start = [], time.time()
    try:
        while len(out) < frames and time.time() - start < timeout:
            ok, frame = cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
            locs = _locate(fr, small)
            if len(locs) != 1:
                continue
            full = [(t * 2, r * 2, b * 2, left * 2) for t, r, b, left in locs]
            enc = fr.face_encodings(rgb, full)[0]
            d = identity_distance(fr.face_distance(known, enc))
            out.append(d)
            extra = ""
            if blocked is not None:
                db = identity_distance(fr.face_distance(blocked, enc))
                extra = f"  | visage interdit : {db:.2f}" + ("  → REFUSÉ" if is_refused(d, db, cfg.block_margin) else "")
            say(f"  {len(out):2d}/{frames}  distance {d:.2f}  "
                + ("✓ sous le seuil" if d < cfg.tolerance else "✗ au-dessus du seuil") + extra)
    finally:
        cap.release()
    return out


def _locate(fr, small):
    """Détection rapide sur image réduite : sans suréchantillonnage (4× plus rapide),
    avec un second essai suréchantillonné seulement si aucun visage n'est trouvé."""
    locs = fr.face_locations(small, 0)
    return locs if locs else fr.face_locations(small, 1)


def measure_antispoof(cfg, frames: int = 15, timeout: float = 25.0, say=print, antispoof=None):
    """Mesure le score « visage réel » de l'IA anti-usurpation devant la caméra.
    Retourne la liste des scores (0 à 1). RuntimeError si caméra ou modèle indisponible."""
    import cv2

    from .antispoof import AntiSpoof

    spoof = antispoof or AntiSpoof.load()
    cap = _open_camera(cfg)
    if cap is None:
        raise RuntimeError("caméra introuvable")
    fr = _fr()
    if hasattr(fr, "preload"):
        fr.preload(landmarks=False)
    out, start, too_small = [], time.time(), 0
    try:
        while len(out) < frames and time.time() - start < timeout:
            ok, frame = cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
            locs = _locate(fr, small)
            if len(locs) != 1:
                continue
            t, r, b, left = locs[0]
            score = spoof.score(rgb, (t * 2, r * 2, b * 2, left * 2))
            if score is None:
                too_small += 1
                if too_small == 1:
                    say("  visage trop petit pour l'analyse : rapproche-toi de la caméra")
                continue
            out.append(score)
            say(f"  {len(out):2d}/{frames}  score réel {score:.2f}  "
                + ("✓ réel" if score >= cfg.antispoof_threshold else "✗ photo/écran"))
    finally:
        cap.release()
    return out


def _fr():
    """Fonctions de reconnaissance : l'accès direct à dlib (démarrage bien plus rapide),
    sauf si `face_recognition` est déjà chargé (cas des tests, qui le remplacent)."""
    import sys

    loaded = sys.modules.get("face_recognition")
    if loaded is not None:
        return loaded
    from . import fastfr

    return fastfr


def _open_camera(cfg):
    import cv2

    cap = cv2.VideoCapture(cfg.camera_device or cfg.camera_index)
    if not cap.isOpened():
        cap.release()
        return None
    # MJPG : format compressé, bien plus fluide en USB que YUYV sur la plupart des webcams.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # pas d'images « vieilles » en attente : moins de retard
    for _ in range(3):  # laisse l'exposition automatique se stabiliser
        cap.read()
    return cap


def capture_samples(cfg, n=15, say=print):
    """Capture n échantillons, guidée : de face, puis tête à gauche, puis à droite.
    La fenêtre montre les points de reconnaissance et une jauge de rotation."""
    import cv2

    from .overlay import EnrollGuide, draw_hud

    face_recognition = _fr()

    cap = _open_camera(cfg)
    if cap is None:
        raise RuntimeError("caméra introuvable (voir [camera] index dans la config)")

    say("Regarde la caméra et suis les consignes : de face, puis tête à gauche, puis à droite. Q pour annuler.")
    guide = EnrollGuide(n, cfg.yaw_delta)
    samples, last = [], 0.0
    try:
        while not guide.done:
            ok, frame = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
            locs = [(t * 2, r * 2, b * 2, left * 2) for t, r, b, left in _locate(face_recognition, small)]
            marks, yaw = None, None
            if len(locs) == 1:
                marks = face_recognition.face_landmarks(rgb, locs)[0]
                chin = marks["chin"]
                yaw = yaw_ratio(marks["nose_tip"][2][0], chin[0][0], chin[-1][0])
                now = time.time()
                if now - last > 0.5 and guide.accepts(yaw):
                    samples.append(face_recognition.face_encodings(rgb, locs)[0])
                    guide.add()
                    last = now
            text = guide.progress_text() if len(locs) == 1 else "Un seul visage requis"
            draw_hud(frame, marks, yaw, text, guide.target, cfg.yaw_delta)
            cv2.imshow("FaceAuth - enregistrement", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if guide.skipped:
        say("Pose(s) non réalisée(s) : " + ", ".join(guide.skipped) + ".")
    return np.array(samples)


class Verifier:
    """Vérifie l'identité + les défis anti-photo, avec un délai maximum.

    Les défis sont demandés l'un après l'autre : chacun est annoncé, puis
    confirmé, avant de passer au suivant.
    """

    def __init__(self, cfg, known, say=print, show=False, blocked=None, antispoof=None):
        self.cfg = cfg
        self.known = np.asarray(known)
        self.blocked = usable_blocked(self.known, blocked)
        self.say = say
        self.show = show
        self.antispoof = antispoof  # injectable pour les tests ; sinon chargé si cfg.antispoof

    def run(self):
        """Retourne (succès: bool, raison: str)."""
        import threading

        cfg = self.cfg
        detectors = build_challenges(cfg.challenge, cfg.ear_threshold, cfg.yaw_delta)

        # La caméra s'ouvre (et s'échauffe) pendant que dlib et ses modèles se
        # chargent : les deux attentes se recouvrent au lieu de s'additionner.
        box = {}
        opener = threading.Thread(target=lambda: box.setdefault("cap", _open_camera(cfg)), daemon=True)
        opener.start()
        face_recognition = _fr()
        if hasattr(face_recognition, "preload"):
            # Le gros modèle à 68 points ne sert qu'aux défis (et à la fenêtre de test).
            face_recognition.preload(landmarks=bool(detectors) or self.show)

        opener.join()
        import cv2

        cap = box.get("cap")
        if cap is None:
            return False, "caméra introuvable"

        spoof = self.antispoof if cfg.antispoof else None
        if cfg.antispoof and spoof is None:
            from .antispoof import AntiSpoof

            try:
                spoof = AntiSpoof.load()
            except RuntimeError as exc:
                # Fonction activée mais inutilisable : on refuse (retour au mot de passe) plutôt que de l'ignorer.
                cap.release()
                return False, f"anti-usurpation indisponible : {exc}"

        start = time.time()
        session = AuthSession(detectors, cfg, start)
        # Le mode strict enchaîne trois défis : on lui laisse plus de temps.
        limit = cfg.timeout + (6.0 if cfg.challenge == "strict" else 0.0)
        frame_no = 0
        announced = None
        self.say("FaceAuth : regardez la caméra.")

        try:
            while time.time() - start < limit:
                ok, frame = cap.read()
                if not ok:
                    return False, "lecture caméra impossible"

                current = session.current
                if current is not None and current is not announced:
                    self.say(current.instruction)
                    announced = current

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Détection sur une image réduite de moitié : bien plus rapide.
                small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
                locs = _locate(face_recognition, small)
                show_marks = show_yaw = None

                if len(locs) == 1:
                    # 1) mesures du vivant, à partir des 68 repères de dlib
                    if detectors or self.show:
                        marks = face_recognition.face_landmarks(small, locs)[0]
                        ear = (
                            eye_aspect_ratio(marks["left_eye"])
                            + eye_aspect_ratio(marks["right_eye"])
                        ) / 2
                        chin = marks["chin"]
                        yaw = yaw_ratio(marks["nose_tip"][2][0], chin[0][0], chin[-1][0])
                        show_marks, show_yaw = marks, yaw
                    else:
                        # Aucun défi : pas besoin des 68 points (valeurs neutres).
                        ear, yaw = 0.3, 0.5

                    # 2) identité (toutes les N images : coûteux), en pleine résolution
                    dist, refused, live, live_score = None, False, None, None
                    # Une fois les défis validés, on vérifie l'identité à chaque image.
                    # Avant, avec bind_identity, ces reconnaissances ne compteraient pas :
                    # on les évite (elles ralentiraient la détection des clignements).
                    need_id = session.challenges_done or (
                        not cfg.bind_identity and frame_no % cfg.identity_every == 0
                    )
                    if need_id:
                        full = [(t * 2, r * 2, b * 2, left * 2) for t, r, b, left in locs]
                        enc = face_recognition.face_encodings(rgb, full)[0]
                        dist = identity_distance(face_recognition.face_distance(self.known, enc))
                        if self.blocked is not None:
                            d_blocked = identity_distance(face_recognition.face_distance(self.blocked, enc))
                            refused = is_refused(dist, d_blocked, cfg.block_margin)
                        # IA anti-usurpation : seulement sur une image qui compterait comme reconnue.
                        if spoof is not None and not refused and dist < cfg.tolerance:
                            live_score = spoof.score(rgb, full[0])
                            live = None if live_score is None else live_score >= cfg.antispoof_threshold
                    frame_no += 1

                    if session.feed(ear, yaw, dist, refused, live, live_score):
                        self.say("✓")

                if self.show:
                    from .overlay import draw_hud

                    cur = session.current
                    draw_hud(frame, show_marks, show_yaw,
                             f"reconnu: {session.matches}/{cfg.min_matches}"
                             + (f"  -  {cur.name}" if cur else ""),
                             None, cfg.yaw_delta, scale=2.0)
                    cv2.imshow("FaceAuth - test", frame)
                    cv2.waitKey(1)

                if session.succeeded:
                    return True, "ok"
                if session.no_face_expired(time.time()):
                    break
        finally:
            cap.release()
            if self.show:
                cv2.destroyAllWindows()

        return False, session.reason()
