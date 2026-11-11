"""Décision d'authentification : logique pure (sans caméra), donc testable.

Une session suit les défis anti-photo, les reconnaissances d'identité et les
délais. Le Verifier (core.py) ne fait que lui fournir les mesures de la caméra.
"""


class AuthSession:
    def __init__(self, detectors, cfg, start: float):
        self.detectors = detectors
        self.cfg = cfg
        self.start = start
        self.face_frames = 0
        self.matches = 0
        self.refused = 0  # images plus proches d'un visage interdit que du tien
        self.spoofed = 0  # images reconnues mais jugées photo/écran par l'IA anti-usurpation
        self.live_unknown = 0  # images reconnues mais visage trop petit pour l'analyse
        self.live_best = None  # meilleur score « réel » observé
        self.best_distance = float("inf")
        self.stats = {"ear_min": float("inf"), "yaw_min": float("inf"), "yaw_max": float("-inf")}

    @property
    def current(self):
        """Défi en cours (None si tous sont validés)."""
        return next((d for d in self.detectors if not d.done), None)

    @property
    def challenges_done(self) -> bool:
        return all(d.done for d in self.detectors)

    def feed(self, ear, yaw, distance=None, refused=False, live=None, live_score=None) -> bool:
        """Enregistre une image avec exactement un visage.

        distance : distance d'identité si elle a été calculée sur cette image.
        refused : ce visage est plus proche d'un visage interdit que du tien.
        live : verdict de l'IA anti-usurpation (True réel, False photo/écran, None inconnu),
               pris en compte seulement si cfg.antispoof est actif.
        live_score : probabilité « réel » correspondante (pour le message d'échec).
        Retourne True si un défi vient d'être validé.
        """
        self.face_frames += 1
        self.stats["ear_min"] = min(self.stats["ear_min"], ear)
        self.stats["yaw_min"] = min(self.stats["yaw_min"], yaw)
        self.stats["yaw_max"] = max(self.stats["yaw_max"], yaw)

        just_done = False
        current = self.current
        if current is not None:
            current.update(ear, yaw)
            just_done = current.done

        if distance is not None:
            self.best_distance = min(self.best_distance, float(distance))
            # Liaison identité/défis : le visage reconnu doit être celui qui a
            # réalisé les défis, donc seules les reconnaissances faites APRÈS
            # les défis comptent (une vidéo pré-enregistrée ne peut pas prévoir
            # l'ordre tiré au hasard).
            if live_score is not None:
                self.live_best = live_score if self.live_best is None else max(self.live_best, live_score)
            if refused:
                self.refused += 1
            elif distance < self.cfg.tolerance and (
                self.challenges_done or not self.cfg.bind_identity
            ):
                if not self.cfg.antispoof:
                    self.matches += 1
                elif live is True:
                    self.matches += 1
                elif live is False:
                    # Une image jugée photo/écran annule la série : il faut des images réelles consécutives.
                    self.spoofed += 1
                    self.matches = 0
                else:
                    self.live_unknown += 1
        return just_done

    @property
    def succeeded(self) -> bool:
        return self.matches >= self.cfg.min_matches and self.challenges_done

    def no_face_expired(self, now: float) -> bool:
        """Aucun visage unique vu au bout de no_face_timeout : on rend la main
        au mot de passe sans attendre le délai complet."""
        return self.face_frames == 0 and now - self.start >= self.cfg.no_face_timeout

    def reason(self) -> str:
        if self.face_frames == 0:
            return "aucun visage unique détecté"
        current = self.current
        if current is not None:
            return "défi non réalisé : " + current.failure(self.stats)
        if self.cfg.antispoof and self.matches < self.cfg.min_matches:
            if self.spoofed:
                return (
                    f"usurpation suspectée (photo ou écran) : score réel {self.live_best:.2f}, "
                    f"seuil {self.cfg.antispoof_threshold:.2f}"
                )
            if self.live_unknown:
                return "visage trop petit pour l'analyse anti-usurpation : rapproche-toi de la caméra"
        if self.refused and self.matches < self.cfg.min_matches:
            return "visage refusé : plus proche d'un visage interdit que du tien"
        if self.matches < self.cfg.min_matches and self.best_distance < self.cfg.tolerance:
            return (
                f"visage reconnu (distance {self.best_distance:.2f}), mais pas assez longtemps "
                "après les défis : augmente [liveness] timeout"
            )
        if self.matches < self.cfg.min_matches:
            return (
                f"visage non reconnu (distance min {self.best_distance:.2f}, "
                f"seuil {self.cfg.tolerance:.2f})"
            )
        return "délai dépassé"
