"""Lecture de la configuration (/etc/faceauth/faceauth.conf)."""
import configparser
import os
import re
from dataclasses import dataclass

DEFAULT_PATH = "/etc/faceauth/faceauth.conf"
CHALLENGES = ("none", "blink", "turn", "both", "strict")


@dataclass(frozen=True)
class Config:
    enabled: bool = True
    log: bool = True
    camera_index: int = 0
    camera_device: str = ""
    no_face_timeout: float = 4.0
    bind_identity: bool = True
    tolerance: float = 0.40
    min_matches: int = 3
    block_margin: float = 0.05
    identity_every: int = 4
    challenge: str = "both"
    timeout: float = 12.0
    ear_threshold: float = 0.21
    yaw_delta: float = 0.15
    antispoof: bool = False
    antispoof_threshold: float = 0.5


def config_path() -> str:
    """Chemin du fichier de config (surchargeable avec FACEAUTH_CONFIG)."""
    return os.environ.get("FACEAUTH_CONFIG", DEFAULT_PATH)


def _num(parser, section, key, cast, default):
    try:
        return cast(parser.get(section, key))
    except (configparser.Error, ValueError):
        return default


def _bool(parser, section, key, default):
    try:
        return parser.getboolean(section, key, fallback=default)
    except ValueError:
        return default


def load_config(path=None) -> Config:
    """Charge la config. Fichier absent ou valeur invalide : valeurs par défaut."""
    parser = configparser.ConfigParser()
    try:
        parser.read(path or config_path(), encoding="utf-8")
    except configparser.Error:
        return Config()

    d = Config()
    challenge = parser.get("liveness", "challenge", fallback=d.challenge).strip().lower()
    if challenge not in CHALLENGES:
        challenge = d.challenge

    tolerance = _num(parser, "recognition", "tolerance", float, d.tolerance)
    if not 0.1 <= tolerance <= 0.9:
        tolerance = d.tolerance

    return Config(
        enabled=_bool(parser, "general", "enabled", d.enabled),
        log=_bool(parser, "general", "log", d.log),
        camera_index=_num(parser, "camera", "index", int, d.camera_index),
        camera_device=parser.get("camera", "device", fallback=d.camera_device).strip(),
        no_face_timeout=max(1.0, _num(parser, "liveness", "no_face_timeout", float, d.no_face_timeout)),
        bind_identity=_bool(parser, "liveness", "bind_identity", d.bind_identity),
        tolerance=tolerance,
        min_matches=max(1, _num(parser, "recognition", "min_matches", int, d.min_matches)),
        identity_every=max(1, _num(parser, "recognition", "identity_every", int, d.identity_every)),
        block_margin=min(0.5, max(0.0, _num(parser, "recognition", "block_margin", float, d.block_margin))),
        challenge=challenge,
        timeout=max(3.0, _num(parser, "liveness", "timeout", float, d.timeout)),
        ear_threshold=_num(parser, "liveness", "ear_threshold", float, d.ear_threshold),
        yaw_delta=_num(parser, "liveness", "yaw_delta", float, d.yaw_delta),
        antispoof=_bool(parser, "liveness", "antispoof", d.antispoof),
        antispoof_threshold=min(0.99, max(0.05, _num(
            parser, "liveness", "antispoof_threshold", float, d.antispoof_threshold))),
    )


# Réglages modifiables depuis l'interface : (section, clé) -> validateur
def _v_bool(v):
    return v.lower() in ("true", "false")


def _v_float(lo, hi):
    def check(v):
        try:
            return lo <= float(v) <= hi
        except ValueError:
            return False
    return check


def _v_int(lo, hi):
    def check(v):
        try:
            return lo <= int(v) <= hi
        except ValueError:
            return False
    return check


EDITABLE = {
    ("general", "enabled"): _v_bool,
    ("liveness", "challenge"): lambda v: v in CHALLENGES,
    ("liveness", "timeout"): _v_float(3, 60),
    ("liveness", "antispoof"): _v_bool,
    ("liveness", "antispoof_threshold"): _v_float(0.05, 0.99),
    ("recognition", "tolerance"): _v_float(0.1, 0.9),
    ("recognition", "min_matches"): _v_int(1, 10),
    ("recognition", "block_margin"): _v_float(0.0, 0.5),
}


def set_values(path: str, values: dict) -> None:
    """Modifie des clés du fichier de config en conservant tous les commentaires.

    `values` : {"section.clé": "valeur"}. Lève ValueError si une clé n'est pas
    modifiable ou si une valeur est invalide.
    """
    parsed = {}
    for dotted, value in values.items():
        section, _, key = dotted.partition(".")
        check = EDITABLE.get((section, key))
        if check is None:
            raise ValueError(f"réglage non modifiable : {dotted}")
        value = str(value).strip()
        if not check(value):
            raise ValueError(f"valeur invalide pour {dotted} : {value!r}")
        parsed[(section, key)] = value

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        lines = []

    for (section, key), value in parsed.items():
        in_section, last_in_section, done = False, None, False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_section and not done:
                    break
                in_section = stripped[1:-1].strip() == section
                if in_section:
                    last_in_section = i
                continue
            if in_section:
                if stripped and not stripped.startswith(("#", ";")):
                    last_in_section = i
                if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                    lines[i] = f"{key} = {value}"
                    done = True
                    break
        if done:
            continue
        if last_in_section is None:  # section absente : on l'ajoute à la fin
            if lines and lines[-1].strip():
                lines.append("")
            lines += [f"[{section}]", f"{key} = {value}"]
        else:
            lines.insert(last_in_section + 1, f"{key} = {value}")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)
