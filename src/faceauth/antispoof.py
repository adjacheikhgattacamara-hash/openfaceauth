"""Détection d'usurpation (photo, écran) par un petit réseau de neurones.

Modèle : MiniFASNetV2-SE exporté en ONNX et quantifié INT8 (≈ 600 Ko), publié par
facenox/face-antispoof-onnx sous licence Apache-2.0 (architecture MiniFAS de
Minivision AI, Silent-Face-Anti-Spoofing, Apache-2.0). Voir THIRD_PARTY_NOTICES.md.

Il regarde la texture du visage (grille de pixels d'un écran, trame d'une
impression) et complète les défis (clignement, rotation) : c'est une couche en
plus, pas un remplacement. Il ne protège pas contre un masque 3D.
"""
import hashlib
import math
import os

MODEL_SHA256 = "fde20585635cae62ed1d41796f76b6f8bc4b92cd91ec1cf0f1bc6485d2d587a9"
INPUT_SIZE = 128      # le modèle attend du 128×128 RGB
EXPANSION = 1.5       # le modèle est entraîné sur des visages cadrés avec 50 % de marge
MIN_FACE = 64         # en dessous (en pixels), les artefacts ne sont plus visibles


def model_path() -> str:
    return os.path.join(os.path.dirname(__file__), "assets", "models", "antispoof.onnx")


def available():
    """(ok, raison) : onnxruntime est installé et le fichier du modèle est présent."""
    import importlib.util

    if importlib.util.find_spec("onnxruntime") is None:
        return False, "onnxruntime absent (pip install onnxruntime dans /opt/faceauth/venv)"
    if not os.path.exists(model_path()):
        return False, "fichier du modèle introuvable"
    return True, ""


def crop_face(rgb, loc, expansion: float = EXPANSION):
    """Carré centré sur le visage, élargi de `expansion`, bords réfléchis si le
    carré dépasse de l'image. loc = (haut, droite, bas, gauche). None si trop petit."""
    import cv2

    top, right, bottom, left = loc
    w, h = right - left, bottom - top
    if max(w, h) < MIN_FACE:
        return None
    size = int(max(w, h) * expansion)
    x = int(left + w / 2 - size / 2)
    y = int(top + h / 2 - size / 2)
    height, width = rgb.shape[:2]

    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + size), min(height, y + size)
    if x2 <= x1 or y2 <= y1:
        return None
    patch = rgb[y1:y2, x1:x2]
    pads = (max(0, -y), max(0, y + size - height), max(0, -x), max(0, x + size - width))
    if any(pads):
        try:
            patch = cv2.copyMakeBorder(patch, *pads, cv2.BORDER_REFLECT_101)
        except cv2.error:  # visage presque entièrement hors cadre : la réflexion est impossible
            patch = cv2.copyMakeBorder(patch, *pads, cv2.BORDER_REPLICATE)
    return patch


def preprocess(patch):
    """Recadrage carré -> tenseur float32 (1, 3, 128, 128) dans [0, 1]."""
    import cv2
    import numpy as np

    interpolation = cv2.INTER_LANCZOS4 if INPUT_SIZE > patch.shape[0] else cv2.INTER_AREA
    img = cv2.resize(patch, (INPUT_SIZE, INPUT_SIZE), interpolation=interpolation)
    return (img.transpose(2, 0, 1).astype(np.float32) / 255.0)[None]


class AntiSpoof:
    """score(rgb, loc) -> probabilité que le visage soit réel (0 à 1), ou None si trop petit."""

    def __init__(self, session):
        self.session = session
        self.input_name = session.get_inputs()[0].name

    @classmethod
    def load(cls, path=None):
        """Charge le modèle. RuntimeError si onnxruntime ou le modèle manque / est altéré."""
        path = path or model_path()
        try:
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError as exc:
            raise RuntimeError(f"modèle illisible ({exc})") from exc
        if digest != MODEL_SHA256:
            raise RuntimeError("le fichier du modèle ne correspond pas à l'empreinte attendue")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("onnxruntime absent (pip install onnxruntime)") from exc
        ort.set_default_logger_severity(3)  # pas d'avertissements dans le terminal ou PAM
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        opts.intra_op_num_threads = 2
        try:
            session = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"chargement du modèle impossible ({exc})") from exc
        return cls(session)

    def score(self, rgb, loc):
        patch = crop_face(rgb, loc)
        if patch is None:
            return None
        logits = self.session.run(None, {self.input_name: preprocess(patch)})[0][0]
        diff = float(logits[0]) - float(logits[1])  # réel − usurpation
        return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, diff))))
