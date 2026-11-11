"""Contrôle des réglages de sécurité : logique pure (testable), utilisée par `faceauth doctor`."""

OK, WARN, KO = "OK", "ATTENTION", "KO"


def security_findings(cfg, sudo_enabled: bool, has_blocked: bool = False):
    """Retourne une liste de (niveau, message) sur le niveau de protection réel.

    sudo_enabled : le visage est actif pour sudo (donc le visage seul peut donner root).
    """
    out = []
    if cfg.challenge == "none":
        out.append((KO if sudo_enabled else WARN,
                    "aucun défi : une simple photo de toi suffit à ouvrir "
                    "(sudo faceauth config liveness.challenge=both)"))
    elif cfg.challenge == "blink" and sudo_enabled:
        out.append((WARN, "un seul clignement : une courte vidéo de toi peut suffire "
                          "(liveness.challenge=both est plus sûr)"))
    if cfg.tolerance > 0.45:
        out.append((KO, f"seuil trop permissif ({cfg.tolerance:.2f}) : des proches qui te "
                        "ressemblent peuvent passer (recommandé : 0.40 ou moins)"))
    elif cfg.tolerance > 0.40:
        out.append((WARN, f"seuil {cfg.tolerance:.2f} : mesure avec « sudo faceauth measure » "
                          "pour vérifier que tes proches sont bien refusés"))
    if cfg.min_matches < 2:
        out.append((KO, "une seule image reconnue suffit (recommandé : recognition.min_matches=3)"))
    if not cfg.bind_identity and cfg.challenge != "none":
        out.append((WARN, "bind_identity désactivé : le visage reconnu n'est pas forcément "
                          "celui qui a fait les défis"))
    if getattr(cfg, "antispoof", False) and cfg.antispoof_threshold < 0.3:
        out.append((WARN, f"seuil anti-usurpation très bas ({cfg.antispoof_threshold:.2f}) : "
                          "une photo ou un écran risque de passer (recommandé : 0.5 ou plus)"))
    if sudo_enabled and not has_blocked:
        out.append((WARN, "le visage seul ouvre sudo (donc root) : si un proche te ressemble, "
                          "enregistre-le comme visage interdit (faceauth block NOM)"))
    if not out:
        out.append((OK, "réglages cohérents pour une webcam ordinaire"))
    return out
