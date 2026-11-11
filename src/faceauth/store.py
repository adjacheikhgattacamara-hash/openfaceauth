"""Stockage des visages enregistrés, dans un dossier réservé à root.

Les données sont chez root (et non dans le home de l'utilisateur) : sinon un
programme lancé avec les droits de l'utilisateur pourrait remplacer ton visage
par un autre, puis utiliser sudo sans mot de passe.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

DATA_DIR = os.environ.get("FACEAUTH_DATA", "/var/lib/faceauth")
_USER_RE = re.compile(r"^[a-z_][a-z0-9_.-]*$")


def _escalate():
    """Préfixe d'élévation : pkexec (fenêtre graphique) hors terminal, sinon sudo."""
    if shutil.which("pkexec") and not sys.stdin.isatty():
        return ["pkexec"]
    return ["sudo"]


_PROFILE_RE = re.compile(r"^[a-z0-9_-]+$")


def path_for(user: str, profile=None) -> str:
    """Fichier d'un utilisateur : <user>.npy, ou <user>@<profil>.npy (« @ » ne peut
    pas apparaître dans un nom d'utilisateur, donc pas d'ambiguïté)."""
    if not _USER_RE.match(user):
        raise ValueError(f"nom d'utilisateur invalide : {user!r}")
    if profile is None:
        return os.path.join(DATA_DIR, f"{user}.npy")
    if not _PROFILE_RE.match(profile):
        raise ValueError(f"nom de profil invalide : {profile!r} (a-z, 0-9, _ et -)")
    return os.path.join(DATA_DIR, f"{user}@{profile}.npy")


def _checked(arr, origin="échantillons"):
    """Vérifie qu'un tableau est bien une liste d'empreintes de visage (n, 128), finies."""
    arr = np.asarray(arr)
    if arr.ndim != 2 or arr.shape[1] != 128 or len(arr) == 0 or not np.isfinite(arr).all():
        raise ValueError(f"fichier de visage invalide ou abîmé : {origin}")
    return arr.astype(float, copy=False)


def _load_file(path):
    try:
        return _checked(np.load(path, allow_pickle=False), path)
    except (OSError, EOFError) as exc:
        raise ValueError(f"fichier de visage illisible : {path} ({exc})") from exc


def _files_for(user: str):
    path_for(user)  # valide le nom
    if not os.path.isdir(DATA_DIR):
        return []
    mine = {f"{user}.npy"} | {n for n in os.listdir(DATA_DIR)
                             if n.startswith(f"{user}@") and n.endswith(".npy")}
    return sorted(os.path.join(DATA_DIR, n) for n in mine
                  if os.path.exists(os.path.join(DATA_DIR, n)))


def load(user: str):
    """Retourne tous les échantillons de l'utilisateur (tous profils réunis),
    ou None s'il n'y en a pas."""
    path_for(user)
    # os.path.exists() renvoie False (sans erreur) si le dossier est interdit :
    # on le signale pour ne pas confondre « illisible » et « absent ».
    if os.path.isdir(DATA_DIR) and not os.access(DATA_DIR, os.X_OK):
        raise PermissionError(DATA_DIR)
    arrays = [_load_file(f) for f in _files_for(user)]
    if not arrays:
        return None
    return np.concatenate(arrays)


def _write_root(dest: str, samples) -> None:
    """Écriture atomique réservée à root : fichier temporaire (0600) puis renommage, donc un
    arrêt en pleine sauvegarde ne laisse jamais un enregistrement tronqué."""
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".tmp-", suffix=".npy")  # mode 0600
    try:
        with os.fdopen(fd, "wb") as f:
            np.save(f, samples)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _save_to(dest: str, samples) -> str:
    samples = _checked(samples, "échantillons à enregistrer")
    if os.geteuid() == 0:
        _write_root(dest, samples)
        return dest
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "samples.npy")
        with open(src, "wb") as f:
            np.save(f, samples)
        subprocess.run(
            _escalate() + ["install", "-D", "-m", "600", "-o", "root", "-g", "root", src, dest],
            check=True,
        )
    return dest


def save(user: str, samples, profile=None) -> str:
    """Enregistre les échantillons ; passe par sudo si on n'est pas root.
    Un profil (ex. « lunettes ») s'ajoute aux autres ; sans profil, on remplace
    l'enregistrement principal."""
    return _save_to(path_for(user, profile), samples)


# -- visages interdits : des visages qui ne doivent JAMAIS déverrouiller (proches qui
#    te ressemblent). Fichiers <user>~<nom>.npy ; « ~ » est interdit dans un nom d'utilisateur.
def path_for_blocked(user: str, name: str) -> str:
    path_for(user)
    if not _PROFILE_RE.match(name):
        raise ValueError(f"nom invalide : {name!r} (a-z, 0-9, _ et -)")
    return os.path.join(DATA_DIR, f"{user}~{name}.npy")


def _blocked_files(user: str):
    path_for(user)
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(os.path.join(DATA_DIR, n) for n in os.listdir(DATA_DIR)
                  if n.startswith(f"{user}~") and n.endswith(".npy"))


def save_blocked(user: str, name: str, samples) -> str:
    return _save_to(path_for_blocked(user, name), samples)


def load_blocked(user: str):
    """Tous les visages interdits de l'utilisateur (réunis), ou None."""
    path_for(user)
    if os.path.isdir(DATA_DIR) and not os.access(DATA_DIR, os.X_OK):
        raise PermissionError(DATA_DIR)
    arrays = [_load_file(f) for f in _blocked_files(user)]
    return np.concatenate(arrays) if arrays else None


def list_blocked(user: str):
    return [os.path.basename(f)[:-4].split("~", 1)[1] for f in _blocked_files(user)]


def delete_blocked(user: str, name: str) -> bool:
    target = path_for_blocked(user, name)
    if os.geteuid() == 0:
        if os.path.exists(target):
            os.remove(target)
            return True
        return False
    out = subprocess.run(
        _escalate() + ["find", DATA_DIR, "-maxdepth", "1", "-name", os.path.basename(target),
                       "-print", "-delete"],
        check=True, capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def delete(user: str, profile=None) -> bool:
    """Supprime les enregistrements de l'utilisateur : un seul profil si `profile`
    est donné (« principal » = l'enregistrement de base), sinon tout."""
    path_for(user)
    if profile is not None:
        target = path_for(user, None if profile == "principal" else profile)
        if os.geteuid() == 0:
            if os.path.exists(target):
                os.remove(target)
                return True
            return False
        out = subprocess.run(
            _escalate() + ["find", DATA_DIR, "-maxdepth", "1", "-name", os.path.basename(target),
                           "-print", "-delete"],
            check=True, capture_output=True, text=True,
        )
        return bool(out.stdout.strip())
    if os.geteuid() == 0:
        files = _files_for(user) + _blocked_files(user)
        for f in files:
            os.remove(f)
        return bool(files)
    out = subprocess.run(
        _escalate() + ["find", DATA_DIR, "-maxdepth", "1", "(", "-name", f"{user}.npy",
         "-o", "-name", f"{user}@*.npy", "-o", "-name", f"{user}~*.npy", ")", "-print", "-delete"],
        check=True, capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def list_users():
    """Liste les utilisateurs enregistrés (lecture du dossier : root requis)."""
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted({re.split(r"[@~]", n[:-4])[0] for n in os.listdir(DATA_DIR)
                   if n.endswith(".npy") and not n.startswith(".")})


def list_profiles(user: str):
    """Noms des profils de l'utilisateur (« principal » pour l'enregistrement de base)."""
    names = []
    for f in _files_for(user):
        base = os.path.basename(f)[:-4]
        names.append(base.split("@", 1)[1] if "@" in base else "principal")
    return names
