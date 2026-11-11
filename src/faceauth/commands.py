"""Commandes lancées par l'interface graphique (pures : testables sans écran)."""
FACEAUTH = "/usr/local/bin/faceauth"
ROOT = ["pkexec", "env", "PYTHONUNBUFFERED=1"]


def commands():
    """Commandes lancées par chaque bouton."""
    return {
        "enroll": [FACEAUTH, "enroll"],
        "test": ROOT + [FACEAUTH, "test"],
        "enable_sudo": ROOT + [FACEAUTH, "enable"],
        "enable_login": ROOT + [FACEAUTH, "enable", "gdm-password", "--force"],
        "disable_all": ROOT + ["sh", "-c",
                               f"{FACEAUTH} disable; {FACEAUTH} disable gdm-password"],
        "status": [FACEAUTH, "status"],
        "doctor": [FACEAUTH, "doctor"],
        "profiles": ROOT + [FACEAUTH, "profiles", "--json"],
    }


def profile_command(name: str):
    return [FACEAUTH, "enroll", "--profile", name]


def remove_profile_command(name: str):
    return ROOT + [FACEAUTH, "remove", "--profile", name]


def config_command(values: dict):
    """values : {"liveness.challenge": "strict", ...}"""
    return ROOT + [FACEAUTH, "config"] + [f"{k}={v}" for k, v in values.items()]
