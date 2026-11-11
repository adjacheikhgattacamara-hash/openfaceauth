"""Tests de l'IA anti-usurpation : recadrage, prétraitement, score, intégrité du modèle."""
import numpy as np
import pytest

from faceauth import antispoof
from faceauth.antispoof import AntiSpoof, crop_face, preprocess

cv2 = pytest.importorskip("cv2")


def image(h=480, w=640):
    return np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)


class FakeSession:
    def __init__(self, logits):
        self.logits = np.array([logits], dtype=np.float32)
        self.seen = None

    def get_inputs(self):
        return [type("I", (), {"name": "input"})()]

    def run(self, _outputs, feed):
        self.seen = feed["input"]
        return [self.logits]


def test_crop_is_square_with_margin():
    patch = crop_face(image(), (100, 300, 300, 100))  # visage 200×200
    assert patch.shape[:2] == (300, 300)  # 200 × 1,5


def test_crop_at_border_stays_square():
    patch = crop_face(image(), (0, 120, 120, 0))  # visage collé au coin haut-gauche
    assert patch.shape[:2] == (180, 180)


def test_crop_too_small_is_none():
    assert crop_face(image(), (10, 50, 50, 10)) is None  # 40 px < 64


def test_preprocess_shape_and_range():
    tensor = preprocess(crop_face(image(), (100, 300, 300, 100)))
    assert tensor.shape == (1, 3, 128, 128)
    assert tensor.dtype == np.float32
    assert 0.0 <= tensor.min() and tensor.max() <= 1.0


def test_score_real_and_spoof_probabilities():
    loc = (100, 300, 300, 100)
    assert AntiSpoof(FakeSession([3.0, -3.0])).score(image(), loc) > 0.99
    assert AntiSpoof(FakeSession([-3.0, 3.0])).score(image(), loc) < 0.01
    assert AntiSpoof(FakeSession([0.0, 0.0])).score(image(), loc) == pytest.approx(0.5)


def test_score_small_face_is_none_and_model_not_called():
    session = FakeSession([3.0, -3.0])
    assert AntiSpoof(session).score(image(), (10, 50, 50, 10)) is None
    assert session.seen is None


def test_load_rejects_altered_model(tmp_path):
    bad = tmp_path / "antispoof.onnx"
    bad.write_bytes(b"pas un modele")
    with pytest.raises(RuntimeError, match="empreinte"):
        AntiSpoof.load(str(bad))


def test_load_missing_file(tmp_path):
    with pytest.raises(RuntimeError, match="illisible"):
        AntiSpoof.load(str(tmp_path / "absent.onnx"))


def test_bundled_model_loads_and_runs():
    pytest.importorskip("onnxruntime")
    model = AntiSpoof.load()
    score = model.score(image(), (100, 300, 300, 100))
    assert 0.0 <= score <= 1.0


def test_available_reports_missing_onnxruntime(monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    ok, why = antispoof.available()
    assert not ok and "onnxruntime" in why
