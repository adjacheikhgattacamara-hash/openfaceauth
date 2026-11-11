"""Teste la boucle de vérification avec une caméra et dlib simulés."""
import sys
import types

import numpy as np

import faceauth.core as core
from faceauth.config import Config
from faceauth.core import Verifier
from faceauth.liveness import TurnDetector

OPEN = [(0, 0), (3, 2), (7, 2), (10, 0), (7, -2), (3, -2)]
CLOSED = [(0, 0), (3, 0.2), (7, 0.2), (10, 0), (7, -0.2), (3, -0.2)]


class FakeCap:
    def isOpened(self):
        return True

    def set(self, *a):
        pass

    def read(self):
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self):
        pass


def make_fakes(distance, blink_at=(3, 4), nose_x=50):
    cv2 = types.SimpleNamespace(
        VideoCapture=lambda idx: FakeCap(),
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_FOURCC=6,
        CAP_PROP_FPS=5,
        CAP_PROP_BUFFERSIZE=38,
        VideoWriter_fourcc=lambda *a: 0,
        COLOR_BGR2RGB=4,
        FONT_HERSHEY_SIMPLEX=0,
        cvtColor=lambda img, code: img,
        resize=lambda img, size, fx, fy: img[::2, ::2],
        putText=lambda *a, **k: None,
        imshow=lambda *a, **k: None,
        waitKey=lambda *a, **k: -1,
        destroyAllWindows=lambda: None,
    )
    calls = {"n": 0}

    def face_landmarks(img, locs):
        calls["n"] += 1
        eye = CLOSED if calls["n"] in blink_at else OPEN
        return [{
            "left_eye": eye,
            "right_eye": eye,
            "chin": [(0, 90)] + [(50, 100)] * 15 + [(100, 90)],
            "nose_tip": [(nose_x, 60)] * 5,
        }]

    fr = types.SimpleNamespace(
        face_locations=lambda img, *a: [(10, 50, 50, 10)],
        face_landmarks=face_landmarks,
        face_encodings=lambda img, locs: [np.zeros(128)],
        face_distance=lambda known, enc: np.array([distance]),
    )
    return cv2, fr


def run(monkeypatch, distance, challenge="blink", blink_at=(3, 4), nose_x=50,
        timeout=0.5, messages=None):
    cv2, fr = make_fakes(distance, blink_at, nose_x)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    cfg = Config(challenge=challenge, identity_every=1, timeout=timeout)
    say = messages.append if messages is not None else (lambda m: None)
    return Verifier(cfg, np.zeros((3, 128)), say=say).run()


def test_success_with_blink(monkeypatch):
    assert run(monkeypatch, distance=0.1) == (True, "ok")


def test_success_without_challenge(monkeypatch):
    assert run(monkeypatch, distance=0.1, challenge="none") == (True, "ok")


def test_unknown_face_is_rejected(monkeypatch):
    ok, reason = run(monkeypatch, distance=0.9)
    assert not ok and reason.startswith("visage non reconnu") and "0.90" in reason


def test_photo_without_blink_is_rejected_with_details(monkeypatch):
    # visage reconnu, mais les yeux ne se ferment jamais : comme une photo
    ok, reason = run(monkeypatch, distance=0.1, blink_at=())
    assert not ok
    assert reason.startswith("défi non réalisé") and "clignement" in reason
    assert "0.40" in reason  # l'EAR minimum observé est indiqué


def test_turn_missing_is_reported(monkeypatch):
    ok, reason = run(monkeypatch, distance=0.1, challenge="both")
    assert not ok and "rotation" in reason and "clignement" not in reason


def test_turn_success(monkeypatch):
    monkeypatch.setattr(core, "build_challenges",
                        lambda *a, **k: [TurnDetector("right", 0.15, frames=2)])
    assert run(monkeypatch, distance=0.1, nose_x=10) == (True, "ok")


def test_challenges_are_announced_one_at_a_time(monkeypatch):
    messages = []
    run(monkeypatch, distance=0.1, challenge="both", messages=messages)
    assert messages[0] == "FaceAuth : regardez la caméra."
    assert "yeux" in messages[1]  # le clignement d'abord
    assert messages[2] == "✓"
    assert "Tournez la tête" in messages[3]  # puis seulement la rotation


def test_no_camera(monkeypatch):
    cv2, fr = make_fakes(0.1)
    cv2.VideoCapture = lambda idx: types.SimpleNamespace(isOpened=lambda: False, release=lambda: None)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    assert Verifier(Config(), np.zeros((1, 128)), say=lambda m: None).run() == (False, "caméra introuvable")


def test_strict_mode_announces_three_challenges_in_sequence(monkeypatch):
    messages = []
    ok, reason = run(monkeypatch, distance=0.1, challenge="strict", messages=messages)
    assert not ok  # la caméra simulée ne tourne jamais la tête
    assert messages[0] == "FaceAuth : regardez la caméra."


def test_no_face_returns_quickly(monkeypatch):
    import time as _t

    cv2, fr = make_fakes(0.1)
    fr.face_locations = lambda img, *a: []
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    cfg = Config(timeout=30.0, no_face_timeout=1.0)
    t0 = _t.time()
    ok, reason = Verifier(cfg, np.zeros((1, 128)), say=lambda m: None).run()
    assert not ok and reason == "aucun visage unique détecté"
    assert _t.time() - t0 < 5


def test_blocked_face_closer_than_owner_is_refused(monkeypatch):
    cv2, fr = make_fakes(0.1)
    # 3 échantillons à toi (distance 0.30), 2 échantillons interdits (distance 0.10)
    fr.face_distance = lambda known, enc: np.full(len(known), 0.30 if len(known) == 3 else 0.10)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    cfg = Config(challenge="none", identity_every=1, timeout=0.5)
    blocked = np.full((2, 128), 5.0)
    ok, reason = Verifier(cfg, np.zeros((3, 128)), say=lambda m: None, blocked=blocked).run()
    assert not ok and "interdit" in reason


def test_owner_is_accepted_even_with_blocked_faces(monkeypatch):
    cv2, fr = make_fakes(0.1)
    fr.face_distance = lambda known, enc: np.full(len(known), 0.15 if len(known) == 3 else 0.60)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    cfg = Config(challenge="none", identity_every=1, timeout=0.5)
    blocked = np.full((2, 128), 5.0)
    assert Verifier(cfg, np.zeros((3, 128)), say=lambda m: None, blocked=blocked).run() == (True, "ok")
