"""Commande `faceauth`."""
import argparse
import getpass
import os
import sys

from . import __version__, pamconf, store
from .config import config_path, load_config

# Services PAM courants. Seuls les services « sudo » sont activés sans --force :
# modifier l'écran de connexion demande plus de précautions (voir le README).
SAFE_SERVICES = {"sudo", "polkit-1"}
PAM_BIN = "/usr/local/bin/faceauth-pam"
SERVICES_TO_SHOW = ["sudo", "polkit-1", "gdm-password", "lightdm", "sddm"]


def current_user() -> str:
    """Utilisateur réel, même sous sudo ou pkexec."""
    if os.environ.get("SUDO_USER"):
        return os.environ["SUDO_USER"]
    uid = os.environ.get("PKEXEC_UID")
    if uid and uid.isdigit():
        import pwd

        try:
            return pwd.getpwuid(int(uid)).pw_name
        except KeyError:
            pass
    return getpass.getuser()


def _need_root(action: str) -> bool:
    if os.geteuid() != 0:
        print(f"Cette action demande les droits root : sudo faceauth {action}")
        return False
    return True


def cmd_enroll(args) -> int:
    from .core import capture_samples

    cfg = load_config()
    user = args.user or current_user()
    if os.geteuid() == 0 and not os.environ.get("SUDO_USER"):
        print("Lance plutôt cette commande sans sudo (la fenêtre caméra a besoin de ta session).")
    try:
        samples = capture_samples(cfg, args.samples)
    except RuntimeError as exc:
        print(f"Erreur : {exc}")
        return 1
    if len(samples) < 5:
        print("Pas assez d'échantillons, rien n'a été enregistré.")
        return 1
    try:
        dest = store.save(user, samples, args.profile)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    suffix = f" (profil « {args.profile} »)" if args.profile else ""
    print(f"{len(samples)} échantillons enregistrés pour « {user} »{suffix} ({dest}).")
    print("Étape suivante : sudo faceauth test")
    return 0


def cmd_test(args) -> int:
    from .core import Verifier

    cfg = load_config()
    user = args.user or current_user()
    try:
        known = store.load(user)
    except PermissionError:
        print("Les données sont réservées à root : sudo faceauth test")
        return 1
    except ValueError as exc:
        print(f"Erreur : {exc} -> refais « faceauth enroll ».")
        return 1
    if known is None:
        print(f"Aucun visage enregistré pour « {user} » : faceauth enroll")
        return 1
    try:
        blocked = store.load_blocked(user)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    ok, reason = Verifier(cfg, known, show=args.show, blocked=blocked).run()
    print("SUCCÈS : visage validé." if ok else f"ÉCHEC : {reason}.")
    return 0 if ok else 1


def cmd_measure(args) -> int:
    from statistics import median

    from .core import measure_distances

    cfg = load_config()
    user = args.user or current_user()
    try:
        known = store.load(user)
    except PermissionError:
        print("Les données sont réservées à root : sudo faceauth measure")
        return 1
    if known is None:
        print(f"Aucun visage enregistré pour « {user} » : faceauth enroll")
        return 1
    print("Regarde la caméra, visage de face. La mesure prend quelques secondes.")
    try:
        dists = measure_distances(cfg, known, frames=args.frames, blocked=store.load_blocked(user))
    except RuntimeError as exc:
        print(f"Erreur : {exc}")
        return 1
    if not dists:
        print("Aucun visage unique détecté : rapproche-toi et améliore l'éclairage.")
        return 1
    print(f"\nRésultat : min {min(dists):.2f} | médiane {median(dists):.2f} | max {max(dists):.2f}"
          f"   (seuil actuel : {cfg.tolerance:.2f})")
    print("Pour régler le seuil : mesure-toi, puis mesure chaque personne qui ne doit PAS entrer.")
    print("Le seuil doit être au-dessus de TON max et au-dessous du MIN des autres :")
    print("  sudo faceauth config recognition.tolerance=0.40")
    return 0


def cmd_antispoof(args) -> int:
    """Mesure le score de l'IA anti-usurpation (visage réel, puis photo / écran)."""
    from statistics import median

    from .antispoof import available
    from .core import measure_antispoof

    cfg = load_config()
    ok, why = available()
    if not ok:
        print(f"Anti-usurpation indisponible : {why}")
        return 1
    print("Regarde la caméra, visage de face et bien éclairé. Puis recommence devant une photo ou un écran.")
    try:
        scores = measure_antispoof(cfg, frames=args.frames)
    except RuntimeError as exc:
        print(f"Erreur : {exc}")
        return 1
    if not scores:
        print("Aucun visage unique exploitable : rapproche-toi et améliore l'éclairage.")
        return 1
    print(f"\nRésultat : min {min(scores):.2f} | médiane {median(scores):.2f} | max {max(scores):.2f}"
          f"   (seuil actuel : {cfg.antispoof_threshold:.2f}, "
          f"fonction {'activée' if cfg.antispoof else 'désactivée'})")
    print("Ton visage réel doit rester au-dessus du seuil ; une photo ou un écran doit rester en dessous.")
    print("Pour l'activer ou régler le seuil :")
    print("  sudo faceauth config liveness.antispoof=true liveness.antispoof_threshold=0.5")
    return 0


def cmd_block(args) -> int:
    """Enregistre le visage d'un proche comme « visage interdit » (avec son accord)."""
    from .core import capture_samples

    cfg = load_config()
    user = args.user or current_user()
    if os.geteuid() == 0 and not os.environ.get("SUDO_USER"):
        print("Lance plutôt cette commande sans sudo (la fenêtre caméra a besoin de ta session).")
    print(f"Visage interdit « {args.name} » : la personne doit être seule devant la caméra,")
    print("et d'accord. Ce visage ne pourra plus rien déverrouiller, même s'il te ressemble.")
    try:
        samples = capture_samples(cfg, args.samples)
    except RuntimeError as exc:
        print(f"Erreur : {exc}")
        return 1
    if len(samples) < 5:
        print("Pas assez d'échantillons, rien n'a été enregistré.")
        return 1
    try:
        dest = store.save_blocked(user, args.name, samples)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    print(f"{len(samples)} échantillons enregistrés comme visage interdit « {args.name} » ({dest}).")
    print("Vérifie avec : sudo faceauth measure  (la personne, puis toi)")
    return 0


def cmd_unblock(args) -> int:
    user = args.user or current_user()
    try:
        removed = store.delete_blocked(user, args.name)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    print("Visage interdit supprimé." if removed else "Aucun visage interdit de ce nom.")
    return 0 if removed else 1


def cmd_enable(args) -> int:
    if not _need_root(f"enable {args.service}"):
        return 1
    if args.service not in SAFE_SERVICES and not args.force:
        print(
            f"« {args.service} » est un écran de connexion. Risques : le trousseau de clés\n"
            "GNOME ne sera pas déverrouillé et une panne caméra peut gêner la connexion.\n"
            "Garde un terminal root ouvert, puis relance avec --force."
        )
        return 1
    if not os.access(PAM_BIN, os.X_OK):
        print(f"{PAM_BIN} est introuvable : relance sudo ./install.sh (ou faceauth doctor).")
        return 1
    try:
        changed = pamconf.enable(args.service)
    except FileNotFoundError as exc:
        print(f"Service PAM introuvable : {exc}")
        return 1
    print("Activé." if changed else "Déjà activé.")
    print("Garde ce terminal ouvert et teste dans un AUTRE terminal (sudo -k puis sudo true).")
    return 0


def cmd_doctor(args) -> int:
    """Vérifie l'installation et dit quoi corriger."""
    import glob

    problems = 0

    def check(label, ok, hint=""):
        nonlocal problems
        print(f"  [{'OK' if ok else 'KO'}] {label}" + ("" if ok else f" -> {hint}"))
        if not ok:
            problems += 1

    print(f"FaceAuth {__version__} : diagnostic")
    for module, hint in (("cv2", "pip install opencv-python"),
                         ("dlib", "relance sudo ./install.sh"),
                         ("face_recognition_models", "relance sudo ./install.sh")):
        try:
            __import__(module)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        check(f"module Python {module}", ok, hint)

    patterns = ("/lib*/security/pam_exec.so", "/usr/lib*/security/pam_exec.so",
                "/lib/*/security/pam_exec.so", "/usr/lib/*/security/pam_exec.so")
    check("module PAM pam_exec.so", any(glob.glob(p) for p in patterns),
          "installe le paquet libpam-modules")
    check("/usr/local/bin/faceauth-pam", os.access(PAM_BIN, os.X_OK), "relance sudo ./install.sh")

    cfg = load_config()
    print(f"  [..] configuration : {config_path()}"
          + ("" if os.path.exists(config_path()) else " (absente : valeurs par défaut)"))

    try:
        from .core import _open_camera

        cap = _open_camera(cfg)
        ok = cap is not None
        if cap is not None:
            cap.release()
    except Exception:  # noqa: BLE001
        ok = False
    check("caméra accessible", ok,
          "voir [camera] index / device ; liste : v4l2-ctl --list-devices")

    user = current_user()
    try:
        enrolled = store.load(user) is not None
        check(f"visage enregistré pour « {user} »", enrolled, "faceauth enroll")
    except PermissionError:
        print("  [..] visage enregistré : illisible sans sudo (lance : sudo faceauth doctor)")
    except ValueError as exc:
        check("fichier de visage valide", False, f"{exc} ; refais faceauth enroll")

    from .antispoof import available as antispoof_available

    spoof_ok, spoof_why = antispoof_available()
    if cfg.antispoof:
        check("anti-usurpation (onnxruntime + modèle)", spoof_ok, spoof_why)
    else:
        print("  [..] anti-usurpation par IA : désactivée"
              + (" (sudo faceauth config liveness.antispoof=true)" if spoof_ok else f" ({spoof_why})"))

    # Niveau de protection réel (pas seulement « ça marche »)
    from .audit import KO, WARN, security_findings

    try:
        sudo_on = pamconf.is_enabled("sudo")
    except (OSError, ValueError):
        sudo_on = False
    try:
        has_blocked = bool(store.list_blocked(user))
    except (OSError, ValueError):
        has_blocked = False
    print("Sécurité :")
    for level, message in security_findings(cfg, sudo_on, has_blocked):
        print(f"  [{level}] {message}")
        if level == KO:
            problems += 1
        elif level == WARN:
            pass

    print("Tout est en ordre." if not problems else f"{problems} problème(s) à corriger.")
    return 1 if problems else 0


def cmd_disable(args) -> int:
    if not _need_root(f"disable {args.service}"):
        return 1
    try:
        changed = pamconf.disable(args.service)
    except FileNotFoundError as exc:
        print(f"Service PAM introuvable : {exc}")
        return 1
    print("Désactivé." if changed else "Pas activé.")
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    print(f"FaceAuth {__version__}")
    print(f"Configuration : {config_path()}")
    print(f"  défi={cfg.challenge}  tolérance={cfg.tolerance}  délai={cfg.timeout}s  actif={cfg.enabled}")
    try:
        users = store.list_users()
        if users:
            details = []
            for u in users:
                profiles = store.list_profiles(u)
                details.append(f"{u} [{', '.join(profiles)}]" if len(profiles) > 1 else u)
            print("Visages enregistrés : " + ", ".join(details))
        else:
            print("Visages enregistrés : aucun")
    except PermissionError:
        print("Visages enregistrés : (lance avec sudo pour voir)")
    print("Services PAM :")
    for service in SERVICES_TO_SHOW:
        try:
            state = "activé" if pamconf.is_enabled(service) else "non activé"
        except OSError:
            continue
        print(f"  {service:14} {state}")
    return 0


def cmd_remove(args) -> int:
    user = args.user or current_user()
    try:
        removed = store.delete(user, args.profile)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    what = f"Profil « {args.profile} »" if args.profile else "Visage"
    print(f"{what} de « {user} » supprimé." if removed
          else f"Aucun enregistrement à supprimer pour « {user} ».")
    return 0 if removed or not args.profile else 1


def cmd_profiles(args) -> int:
    """Liste les profils de l'utilisateur (root requis) ; --json pour l'interface."""
    import json

    user = args.user or current_user()
    try:
        profiles = store.list_profiles(user)
    except PermissionError:
        print("Les données sont réservées à root : sudo faceauth profiles")
        return 1
    if args.json:
        print(json.dumps({"user": user, "profiles": profiles}, ensure_ascii=False))
    else:
        print(", ".join(profiles) if profiles else "aucun profil")
    return 0


def cmd_config(args) -> int:
    """Modifie des réglages en gardant les commentaires : faceauth config liveness.challenge=strict"""
    from .config import config_path, set_values

    if not _need_root("config ..."):
        return 1
    values = {}
    for item in args.settings:
        key, sep, value = item.partition("=")
        if not sep:
            print(f"Format attendu : section.clé=valeur (reçu : {item!r})")
            return 1
        values[key.strip()] = value
    try:
        set_values(config_path(), values)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1
    print("Réglages enregistrés.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faceauth", description="Déverrouillage par reconnaissance faciale pour Linux."
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("enroll", help="enregistrer ton visage (sans sudo)")
    p.add_argument("--user")
    p.add_argument("--profile", help="ajoute un profil (ex. lunettes, voile) au lieu de remplacer")
    p.add_argument("--samples", type=int, default=15, help="nombre de captures (défaut 15)")
    p.set_defaults(func=cmd_enroll)

    p = sub.add_parser("test", help="tester la reconnaissance (sudo)")
    p.add_argument("--user")
    p.add_argument("--show", action="store_true",
                   help="afficher la fenêtre caméra (peut échouer sous sudo)")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("measure", help="mesurer les distances pour régler le seuil (sudo)")
    p.add_argument("--user")
    p.add_argument("--frames", type=int, default=12, help="nombre de mesures (défaut 12)")
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("block", help="interdire le visage d'un proche qui te ressemble")
    p.add_argument("name", help="nom pour s'y retrouver (a-z, 0-9, _ et -)")
    p.add_argument("--user")
    p.add_argument("--samples", type=int, default=15, help="nombre de captures (défaut 15)")
    p.set_defaults(func=cmd_block)

    p = sub.add_parser("unblock", help="retirer un visage interdit (sudo demandé)")
    p.add_argument("name")
    p.add_argument("--user")
    p.set_defaults(func=cmd_unblock)

    p = sub.add_parser("antispoof", help="tester l'IA anti-usurpation (visage réel vs photo/écran)")
    p.add_argument("--frames", type=int, default=15, help="nombre de mesures (défaut 15)")
    p.set_defaults(func=cmd_antispoof)

    p = sub.add_parser("enable", help="activer sur un service PAM (sudo)")
    p.add_argument("service", nargs="?", default="sudo")
    p.add_argument("--force", action="store_true", help="autoriser un écran de connexion")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("doctor", help="diagnostiquer l'installation")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("disable", help="désactiver sur un service PAM (sudo)")
    p.add_argument("service", nargs="?", default="sudo")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("status", help="afficher l'état")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("remove", help="supprimer un visage enregistré")
    p.add_argument("--user")
    p.add_argument("--profile", help="ne supprimer que ce profil (« principal » = enregistrement de base)")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("profiles", help="lister les profils enregistrés (sudo)")
    p.add_argument("--user")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("config", help="modifier des réglages (sudo)")
    p.add_argument("settings", nargs="+", metavar="section.clé=valeur")
    p.set_defaults(func=cmd_config)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
