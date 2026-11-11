"""Détection du vivant : logique pure (sans caméra), donc testable."""
import random

import numpy as np

# Les points viennent des 68 repères de dlib (face_recognition.face_landmarks).
# Pour le yaw : le premier point du menton est le côté droit du sujet (à gauche
# sur l'image brute), le dernier est son côté gauche.


def eye_aspect_ratio(pts) -> float:
    """EAR : ~0.3 yeux ouverts, <0.2 yeux fermés. pts = 6 points (x, y)."""
    pts = np.asarray(pts, dtype=float)
    a = np.linalg.norm(pts[1] - pts[5])
    b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3])
    if c == 0:
        return 0.0
    return float((a + b) / (2.0 * c))


def yaw_ratio(nose_x: float, face_right_x: float, face_left_x: float) -> float:
    """Position du nez entre les deux bords du visage : ~0.5 de face."""
    width = face_left_x - face_right_x
    if width == 0:
        return 0.5
    return float((nose_x - face_right_x) / width)


class BlinkDetector:
    """Réussit quand les yeux se ferment puis se rouvrent."""

    name = "blink"

    def __init__(self, ear_threshold: float):
        self.threshold = ear_threshold
        self.closed = False
        self.done = False
        self.instruction = "Fermez les yeux un instant, puis rouvrez-les."

    def update(self, ear, yaw) -> bool:
        if ear is not None:
            if ear < self.threshold:
                self.closed = True
            elif self.closed:
                self.done = True
        return self.done

    def failure(self, stats) -> str:
        return (
            f"clignement non détecté (EAR minimum vu {stats['ear_min']:.2f}, "
            f"seuil {self.threshold:.2f})"
        )


class TurnDetector:
    """Réussit quand la tête reste tournée du côté demandé quelques images."""

    name = "turn"

    def __init__(self, side: str, delta: float, frames: int = 3):
        if side not in ("left", "right"):
            raise ValueError("side doit être 'left' ou 'right'")
        self.side = side
        self.delta = delta
        self.frames = frames
        self.count = 0
        self.done = False
        self.word = "gauche" if side == "left" else "droite"
        self.instruction = f"Tournez la tête vers votre {self.word}."

    def update(self, ear, yaw) -> bool:
        if yaw is not None and not self.done:
            hit = yaw > 0.5 + self.delta if self.side == "left" else yaw < 0.5 - self.delta
            self.count = self.count + 1 if hit else 0
            if self.count >= self.frames:
                self.done = True
        return self.done

    def failure(self, stats) -> str:
        need = f"> {0.5 + self.delta:.2f}" if self.side == "left" else f"< {0.5 - self.delta:.2f}"
        return (
            f"rotation vers votre {self.word} non détectée "
            f"(yaw vu de {stats['yaw_min']:.2f} à {stats['yaw_max']:.2f}, requis {need})"
        )


def build_challenges(mode: str, ear_threshold: float, yaw_delta: float, rng=random):
    """Construit la liste des défis selon le mode de la config."""
    challenges = []
    if mode == "strict":
        # Clignement + rotation à gauche + rotation à droite, dans un ordre tiré
        # au hasard : une vidéo enregistrée ne peut pas le deviner.
        challenges = [
            BlinkDetector(ear_threshold),
            TurnDetector("left", yaw_delta),
            TurnDetector("right", yaw_delta),
        ]
        rng.shuffle(challenges)
        return challenges
    if mode in ("blink", "both"):
        challenges.append(BlinkDetector(ear_threshold))
    if mode in ("turn", "both"):
        challenges.append(TurnDetector(rng.choice(["left", "right"]), yaw_delta))
    return challenges
