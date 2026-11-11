"""Habillage de la fenêtre caméra : points de reconnaissance et jauge de rotation.

Fonctions sans dépendance à dlib : elles reçoivent les repères du visage
(format `face_recognition.face_landmarks`) et dessinent avec OpenCV.
"""
import time

import numpy as np

CYAN = (255, 214, 55)   # BGR
GREEN = (124, 224, 37)
WHITE = (255, 255, 255)
DIM = (140, 120, 90)

# Contours reliés entre eux ; les autres repères sont dessinés en points.
LINES = {
    "chin": False, "left_eyebrow": False, "right_eyebrow": False, "nose_bridge": False,
    "nose_tip": False, "left_eye": True, "right_eye": True, "top_lip": True, "bottom_lip": True,
}


def draw_landmarks(frame, marks, scale=1.0, color=CYAN):
    """Dessine les points du visage (contours fins + points lumineux). `scale` ramène
    des repères calculés sur une image réduite vers la taille de `frame`."""
    import cv2

    for name, pts in marks.items():
        p = np.array([(int(x * scale), int(y * scale)) for x, y in pts], dtype=np.int32)
        if len(p) > 1:
            cv2.polylines(frame, [p], LINES.get(name, False), (120, 90, 30), 1, cv2.LINE_AA)
        for x, y in p:
            cv2.circle(frame, (int(x), int(y)), 2, color, -1, cv2.LINE_AA)
    return frame


POSES = {"face": "Regardez droit devant", "left": "Tournez la tete vers votre gauche",
         "right": "Tournez la tete vers votre droite"}


def pose_of(yaw, delta):
    """« face », « left » ou « right » selon l'orientation (mêmes conventions que liveness)."""
    if yaw is None:
        return None
    if yaw > 0.5 + delta * 0.7:
        return "left"
    if yaw < 0.5 - delta * 0.7:
        return "right"
    if abs(yaw - 0.5) < delta * 0.5:
        return "face"
    return None


def draw_gauge(frame, yaw, target=None, delta=0.15):
    """Jauge de rotation en bas de l'image : la gauche de la jauge = ta gauche."""
    import cv2

    h, w = frame.shape[:2]
    gw, gx, gy = 260, (w - 260) // 2, h - 34
    cv2.rectangle(frame, (gx, gy - 8), (gx + gw, gy + 8), (40, 30, 20), -1)
    zones = {"left": (0.0, 0.5 - delta * 0.7), "face": (0.5 - delta * 0.5, 0.5 + delta * 0.5),
             "right": (0.5 + delta * 0.7, 1.0)}
    for name, (a, b) in zones.items():
        col = GREEN if name == target else DIM
        x0 = gx + int(a * gw)
        x1 = gx + int(b * gw)
        cv2.rectangle(frame, (x0, gy - 8), (x1, gy + 8), col, 2 if name == target else 1)
    if yaw is not None:
        pos = 1.0 - min(1.0, max(0.0, yaw))   # inversé : tourner à gauche déplace le repère à gauche
        cv2.circle(frame, (gx + int(pos * gw), gy), 7, WHITE, -1, cv2.LINE_AA)
    cv2.putText(frame, "gauche", (gx - 62, gy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1, cv2.LINE_AA)
    cv2.putText(frame, "droite", (gx + gw + 8, gy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1, cv2.LINE_AA)
    return frame


class EnrollGuide:
    """Guide l'enregistrement : de face, puis tête tournée à gauche, puis à droite.
    Un échantillon n'est retenu que si la tête est réellement dans la pose demandée."""

    ORDER = ("face", "left", "right")

    def __init__(self, total, delta=0.15, stuck_after=20.0, now=time.time):
        base, extra = divmod(max(total, 3), 3)
        self.quota = {p: base + (1 if i < extra else 0) for i, p in enumerate(self.ORDER)}
        self.delta, self.stuck_after, self.now = delta, stuck_after, now
        self.counts = dict.fromkeys(self.ORDER, 0)
        self.stage = 0
        self.stage_start = now()
        self.skipped = []

    @property
    def target(self):
        return self.ORDER[self.stage] if self.stage < len(self.ORDER) else None

    @property
    def done(self):
        return self.stage >= len(self.ORDER)

    @property
    def total(self):
        return sum(self.counts.values())

    def accepts(self, yaw):
        self._skip_if_stuck()
        return not self.done and pose_of(yaw, self.delta) == self.target

    def add(self):
        self.counts[self.target] += 1
        if self.counts[self.target] >= self.quota[self.target]:
            self._advance()

    def _advance(self):
        self.stage += 1
        self.stage_start = self.now()

    def _skip_if_stuck(self):
        """Pose impossible (cou raide, caméra décalée...) : on passe à la suivante."""
        if not self.done and self.now() - self.stage_start > self.stuck_after:
            self.skipped.append(self.target)
            self._advance()

    @property
    def label(self):
        return POSES.get(self.target, "Termine")

    def progress_text(self):
        return f"{self.label}  {self.counts[self.target]}/{self.quota[self.target]}" if not self.done else "Termine"


def draw_hud(frame, marks, yaw, text, target=None, delta=0.15, scale=1.0, ok=True):
    """Points + jauge + consigne, en une seule fonction."""
    import cv2

    if marks:
        draw_landmarks(frame, marks, scale, GREEN if ok else CYAN)
    draw_gauge(frame, yaw, target, delta)
    cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, GREEN, 2, cv2.LINE_AA)
    return frame
