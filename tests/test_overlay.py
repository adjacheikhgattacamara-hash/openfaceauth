"""Points de reconnaissance, jauge de rotation et guide d'enregistrement."""
import math

import numpy as np

from faceauth import overlay


def fake_marks(cx=320, cy=240, yaw_shift=0):
    """Repères de visage synthétiques au format face_recognition."""
    def arc(n, rx, ry, a0, a1, ox=0, oy=0):
        return [(cx + ox + rx * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))) + yaw_shift,
                 cy + oy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]
    return {
        "chin": arc(17, 95, 120, 170, 10, 0, 0), "left_eyebrow": arc(5, 40, 8, 200, 340, -50, -60),
        "right_eyebrow": arc(5, 40, 8, 200, 340, 50, -60), "nose_bridge": arc(4, 2, 30, 270, 90, 0, -30),
        "nose_tip": arc(5, 18, 6, 180, 0, 0, 25), "left_eye": arc(6, 18, 7, 0, 360, -50, -38),
        "right_eye": arc(6, 18, 7, 0, 360, 50, -38), "top_lip": arc(12, 32, 8, 200, 340, 0, 60),
        "bottom_lip": arc(8, 30, 12, 20, 160, 0, 62),
    }


def test_landmarks_are_drawn():
    frame = np.zeros((480, 640, 3), np.uint8)
    overlay.draw_hud(frame, fake_marks(), 0.5, "Test", "face")
    assert frame.sum() > 0
    # les 4 coins restent vides : seul le visage et la jauge sont dessinés
    assert frame[:20, -20:].sum() == 0


def test_scale_moves_points():
    small = np.zeros((480, 640, 3), np.uint8)
    big = np.zeros((480, 640, 3), np.uint8)
    marks = fake_marks(160, 120)
    overlay.draw_landmarks(small, marks, 1.0)
    overlay.draw_landmarks(big, marks, 2.0)
    assert small[:240, :320].sum() > 0 and big[:240, :320].sum() < small[:240, :320].sum()


def test_pose_zones_follow_liveness_convention():
    assert overlay.pose_of(0.5, 0.15) == "face"
    assert overlay.pose_of(0.7, 0.15) == "left"     # yaw > 0.5 + delta : « gauche »
    assert overlay.pose_of(0.3, 0.15) == "right"
    assert overlay.pose_of(0.58, 0.15) is None      # entre deux zones : rien
    assert overlay.pose_of(None, 0.15) is None


def test_guide_only_accepts_the_requested_pose():
    t = [0.0]
    g = overlay.EnrollGuide(15, 0.15, now=lambda: t[0])
    assert g.quota == {"face": 5, "left": 5, "right": 5}
    assert not g.accepts(0.75)                      # tête tournée alors qu'on veut « face »
    for _ in range(5):
        assert g.accepts(0.5)
        g.add()
    assert g.target == "left" and not g.accepts(0.5) and g.accepts(0.75)
    for _ in range(5):
        g.add()
    assert g.target == "right"
    for _ in range(5):
        g.add()
    assert g.done and g.total == 15


def test_guide_skips_an_impossible_pose():
    t = [0.0]
    g = overlay.EnrollGuide(15, 0.15, stuck_after=20, now=lambda: t[0])
    for _ in range(5):
        g.add()
    t[0] = 25.0
    assert not g.accepts(0.5)       # « gauche » abandonnée après 20 s
    assert g.skipped == ["left"] and g.target == "right"


def test_guide_handles_uneven_totals():
    assert sum(overlay.EnrollGuide(16).quota.values()) == 16
