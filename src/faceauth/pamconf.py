"""Activation / désactivation de FaceAuth dans un fichier /etc/pam.d/<service>."""
import os
import shutil
import tempfile

PAM_DIR = os.environ.get("FACEAUTH_PAM_DIR", "/etc/pam.d")
MARK = "# faceauth"
LINE = "auth sufficient pam_exec.so quiet stdout /usr/local/bin/faceauth-pam  " + MARK


def _path(service: str) -> str:
    if not service or "/" in service or service.startswith("."):
        raise ValueError(f"nom de service invalide : {service!r}")
    return os.path.join(PAM_DIR, service)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def _write_atomic(path, lines):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.writelines(lines)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)


def is_enabled(service: str) -> bool:
    path = _path(service)
    return os.path.exists(path) and any(MARK in line for line in _read(path))


def enable(service: str) -> bool:
    """Ajoute la ligne FaceAuth (avec sauvegarde). False si déjà présente."""
    path = _path(service)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    lines = _read(path)
    if any(MARK in line for line in lines):
        return False
    backup = path + ".faceauth.bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    # Insère après les commentaires d'en-tête (ex. « #%PAM-1.0 »).
    idx = 0
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].lstrip().startswith("#")):
        idx += 1
    lines.insert(idx, LINE + "\n")
    _write_atomic(path, lines)
    return True


def disable(service: str) -> bool:
    """Retire la ligne FaceAuth. False si elle n'y était pas."""
    path = _path(service)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    lines = _read(path)
    kept = [line for line in lines if MARK not in line]
    if len(kept) == len(lines):
        return False
    _write_atomic(path, kept)
    return True
