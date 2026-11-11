"""Anti-usurpation dans la session et la boucle de vérification."""
import numpy as np

from faceauth.config import Config, load_config, set_values
from faceauth.core import Verifier
from faceauth.session import AuthSession
from test_verifier import make_fakes

import sys


def session(**kw):
    cfg = Config(challenge="none", antispoof=True, **kw)
    return AuthSession([], cfg, 0.0)


def feed(s, live, score, dist=0.1):
    s.feed(0.3, 0.5, dist, False, live, score)


# --- session ---------------------------------------------------------------

def test_real_frames_succeed():
    s = session()
    for _ in range(3):
        feed(s, True, 0.9)
    assert s.succeeded


def test_spoof_frame_resets_the_streak():
    s = session()
    feed(s, True, 0.9)
    feed(s, True, 0.9)
    feed(s, False, 0.1)
    assert s.matches == 0 and s.spoofed == 1
    assert not s.succeeded
    assert s.reason().startswith("usurpation suspectée")
    assert "0.90" in s.reason()  # meilleur score vu


def test_unknown_verdict_does_not_count():
    s = session()
    for _ in range(5):
        feed(s, None, None)
    assert s.matches == 0 and not s.succeeded
    assert "trop petit" in s.reason()


def test_verdict_is_ignored_when_feature_is_off():
    s = AuthSession([], Config(challenge="none", antispoof=False), 0.0)
    for _ in range(3):
        s.feed(0.3, 0.5, 0.1, False, False, 0.0)
    assert s.succeeded


# --- Verifier ---------------------------------------------------------------

class FakeSpoof:
    def __init__(self, score):
        self.value = score
        self.calls = 0

    def score(self, rgb, loc):
        self.calls += 1
        return self.value


def verify(monkeypatch, spoof, distance=0.1, antispoof=True):
    cv2, fr = make_fakes(distance)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "face_recognition", fr)
    cfg = Config(challenge="none", identity_every=1, timeout=0.5, antispoof=antispoof)
    return Verifier(cfg, np.zeros((3, 128)), antispoof=spoof).run()


def test_verifier_accepts_real_face(monkeypatch):
    assert verify(monkeypatch, FakeSpoof(0.95)) == (True, "ok")


def test_verifier_rejects_photo_or_screen(monkeypatch):
    ok, reason = verify(monkeypatch, FakeSpoof(0.05))
    assert not ok and reason.startswith("usurpation suspectée")


def test_verifier_reports_face_too_small(monkeypatch):
    ok, reason = verify(monkeypatch, FakeSpoof(None))
    assert not ok and "trop petit" in reason


def test_verifier_skips_model_for_unrecognised_face(monkeypatch):
    spoof = FakeSpoof(0.95)
    ok, _ = verify(monkeypatch, spoof, distance=0.9)
    assert not ok and spoof.calls == 0


def test_verifier_does_not_call_model_when_disabled(monkeypatch):
    spoof = FakeSpoof(0.0)
    assert verify(monkeypatch, spoof, antispoof=False) == (True, "ok")
    assert spoof.calls == 0


def test_verifier_fails_closed_when_model_unavailable(monkeypatch):
    from faceauth.antispoof import AntiSpoof

    def boom(*a, **k):
        raise RuntimeError("onnxruntime absent")

    monkeypatch.setattr(AntiSpoof, "load", classmethod(lambda cls, path=None: boom()))
    ok, reason = verify(monkeypatch, None)
    assert not ok and reason.startswith("anti-usurpation indisponible")


# --- config / audit ---------------------------------------------------------

def test_config_parses_and_clamps(tmp_path):
    conf = tmp_path / "f.conf"
    conf.write_text("[liveness]\nantispoof = true\nantispoof_threshold = 5\n")
    cfg = load_config(str(conf))
    assert cfg.antispoof is True and cfg.antispoof_threshold == 0.99
    assert load_config(str(tmp_path / "absent.conf")).antispoof is False


def test_config_command_accepts_the_new_keys(tmp_path):
    conf = tmp_path / "f.conf"
    conf.write_text("[liveness]\nchallenge = both\n")
    set_values(str(conf), {"liveness.antispoof": "true", "liveness.antispoof_threshold": "0.6"})
    cfg = load_config(str(conf))
    assert cfg.antispoof and cfg.antispoof_threshold == 0.6


def test_audit_warns_on_very_low_threshold():
    from faceauth.audit import WARN, security_findings

    findings = security_findings(Config(antispoof=True, antispoof_threshold=0.1), sudo_enabled=False)
    assert any(level == WARN and "anti-usurpation" in msg for level, msg in findings)
