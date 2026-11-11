"""Accès direct à dlib : les mêmes fonctions que `face_recognition`, mais sans
charger d'office tous ses modèles.

`import face_recognition` charge ses cinq modèles dès l'import (dont le détecteur
CNN, que FaceAuth n'utilise jamais) : environ 2,5 s sur un portable. Ici chaque
modèle n'est chargé que s'il sert, et le gros modèle à 68 points seulement quand
un défi (clignement / rotation) en a besoin.

Les résultats sont identiques à ceux de `face_recognition` : mêmes modèles, même
alignement à 5 points, donc les visages déjà enregistrés restent valables.
"""
import importlib.util
import os

import numpy as np

_cache = {}


def _model_path(name: str) -> str:
    # Sans passer par `face_recognition_models` (qui importe pkg_resources, lent).
    spec = importlib.util.find_spec("face_recognition_models")
    if spec is None or not spec.submodule_search_locations:
        raise ImportError("face_recognition_models est introuvable")
    return os.path.join(list(spec.submodule_search_locations)[0], "models", name)


def _get(key, build):
    if key not in _cache:
        _cache[key] = build()
    return _cache[key]


def _dlib():
    import dlib

    return dlib


def _detector():
    return _get("detector", lambda: _dlib().get_frontal_face_detector())


def _shape5():
    return _get("shape5", lambda: _dlib().shape_predictor(
        _model_path("shape_predictor_5_face_landmarks.dat")))


def _shape68():
    return _get("shape68", lambda: _dlib().shape_predictor(
        _model_path("shape_predictor_68_face_landmarks.dat")))


def _encoder():
    return _get("encoder", lambda: _dlib().face_recognition_model_v1(
        _model_path("dlib_face_recognition_resnet_model_v1.dat")))


def preload(landmarks: bool = True) -> None:
    """Charge les modèles à l'avance (pendant que la caméra démarre)."""
    _detector()
    _shape5()
    _encoder()
    if landmarks:
        _shape68()


def _rect(loc):
    top, right, bottom, left = loc
    return _dlib().rectangle(left, top, right, bottom)


def face_locations(img, number_of_times_to_upsample: int = 1):
    """Liste de (haut, droite, bas, gauche), comme face_recognition."""
    h, w = img.shape[:2]
    out = []
    for r in _detector()(img, number_of_times_to_upsample):
        out.append((max(r.top(), 0), min(r.right(), w), min(r.bottom(), h), max(r.left(), 0)))
    return out


def face_landmarks(img, locs):
    """68 repères par visage, regroupés comme dans face_recognition."""
    out = []
    for loc in locs:
        shape = _shape68()(img, _rect(loc))
        pts = [(p.x, p.y) for p in shape.parts()]
        out.append({
            "chin": pts[0:17],
            "nose_tip": pts[31:36],
            "left_eye": pts[36:42],
            "right_eye": pts[42:48],
        })
    return out


def face_encodings(img, locs, num_jitters: int = 1):
    """Empreinte à 128 valeurs par visage (alignement à 5 points)."""
    out = []
    for loc in locs:
        shape = _shape5()(img, _rect(loc))
        out.append(np.array(_encoder().compute_face_descriptor(img, shape, num_jitters)))
    return out


def face_distance(known, encoding):
    known = np.asarray(known)
    if len(known) == 0:
        return np.empty(0)
    return np.linalg.norm(known - encoding, axis=1)
