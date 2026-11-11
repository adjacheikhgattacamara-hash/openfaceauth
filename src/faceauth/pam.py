"""Point d'entrée appelé par pam_exec. Code de sortie : 0 = visage validé, 1 = échec.

Toute erreur (caméra absente, bibliothèque manquante...) renvoie 1, pour que PAM
retombe sur le mot de passe : FaceAuth ne doit jamais te bloquer dehors.
"""
import os
import sys
import syslog


def _log(message: str) -> None:
    syslog.openlog("faceauth", 0, syslog.LOG_AUTH)
    syslog.syslog(syslog.LOG_INFO, message)


def _arm_watchdog(seconds: float) -> None:
    """Dernier recours : quoi qu'il arrive (caméra USB bloquée, bibliothèque qui boucle...),
    le programme s'arrête et rend la main au mot de passe. Sans ça, `sudo` ou l'écran de
    connexion pourraient attendre indéfiniment une caméra qui ne répond plus."""
    import signal
    import threading

    seconds = max(1, int(seconds))

    def give_up():
        try:
            _log("délai absolu dépassé : retour au mot de passe")
        finally:
            os._exit(1)

    timer = threading.Timer(seconds, give_up)
    timer.daemon = True
    timer.start()
    # Filet de plus : SIGALRM sans gestionnaire, le noyau tue le processus même s'il est
    # bloqué dans un appel système (un code de sortie non nul = échec = mot de passe).
    try:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(seconds + 3)
    except (ValueError, OSError):
        pass


def main() -> int:
    try:
        from .config import load_config

        cfg = load_config()
        if not cfg.enabled:
            return 1
        _arm_watchdog(cfg.timeout + (6.0 if cfg.challenge == "strict" else 0.0) + 15.0)

        if os.environ.get("PAM_TYPE", "auth") != "auth":
            return 1

        user = os.environ.get("PAM_USER")
        if not user:
            return 1

        from . import store

        known = store.load(user)
        if known is None:  # utilisateur non enregistré : mot de passe direct
            return 1

        from .core import Verifier

        ok, reason = Verifier(cfg, known, say=lambda m: print(m, flush=True),
                              blocked=store.load_blocked(user)).run()
        if cfg.log:
            _log(f"utilisateur={user} résultat={'succès' if ok else 'échec'} ({reason})")
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001 - on veut tout rattraper ici
        try:
            _log(f"erreur interne : {exc!r}")
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
