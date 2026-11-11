# Changelog

## 0.7.0

- **IA anti-usurpation (optionnelle)** : un réseau MiniFASNetV2-SE (ONNX INT8, ≈ 600 Ko, Apache-2.0) juge si le visage est réel ou une photo / un écran. Activation : `sudo faceauth config liveness.antispoof=true` ; seuil réglable (`antispoof_threshold`, 0.5 par défaut). Il complète les défis et ne tourne que sur les images qui compteraient comme reconnues (≈ 11 ms). Une image jugée usurpation remet la série de reconnaissances à zéro.
- Nouvelle commande `faceauth antispoof` : mesure le score devant ton visage, puis devant une photo ou un écran, pour régler le seuil.
- Sécurité : si la fonction est activée mais inutilisable (`onnxruntime` absent, empreinte du modèle incorrecte), l'authentification est refusée (retour au mot de passe) au lieu d'ignorer la protection. Le modèle est vérifié par SHA-256 au chargement.
- `faceauth doctor` contrôle `onnxruntime` et le modèle ; l'audit signale un seuil anti-usurpation trop bas.
- `onnxruntime` est installé par `postinst` / `install.sh` ; un échec n'empêche pas l'installation (extra `antispoof` pour pip).
- Ajout de `SECURITY.md` (modèle de menace, limites, signalement) et `THIRD_PARTY_NOTICES.md` (licences du modèle).

## 0.6.1

- Détection du visage ~4× plus rapide : image réduite sans suréchantillonnage (second essai suréchantillonné seulement si aucun visage n'est trouvé). L'enregistrement des échantillons profite aussi de la détection réduite.
- Pendant les défis (avec `bind_identity`), plus de calcul d'empreinte inutile : détection des clignements plus fiable et vérification plus rapide.
- Installation sans compilation : dlib est installé en wheel précompilé (`dlib-bin`), avec repli sur la compilation. La dépendance `face_recognition` (jamais importée) est remplacée par `face_recognition_models` ; les paquets de compilation passent en `Suggests`.
- `postinst` : un seul `pip install` du paquet ; `.ruff_cache/` ignoré.

## 0.6.0
- **Plus de blocage possible** : `faceauth-pam` a un chien de garde absolu (`timeout` + 15 s). Une caméra USB qui ne répond plus rend la main au mot de passe au lieu de bloquer `sudo` ou l'écran de connexion.
- **Visages interdits** : `faceauth block NOM` enregistre un proche qui te ressemble ; un visage plus proche d'un visage interdit que du tien est refusé (`block_margin`). Un « visage interdit » qui est en fait le tien est ignoré automatiquement. `faceauth unblock NOM` pour le retirer.
- `faceauth doctor` contrôle aussi le niveau de sécurité réel (pas de défi, seuil trop permissif, une seule image, visage seul sur sudo) et vérifie les modules réellement utilisés (dlib, modèles).
- Fichiers de visages : validation (forme, valeurs finies) et écriture atomique (plus d'enregistrement tronqué si l'écriture est interrompue).
- Tests : chemin PAM (codes de sortie, chien de garde), visages interdits, audit de sécurité, stockage ; CI sur Python 3.14.
- Documentation mise à jour (seuil 0.40, 3 images, nouvelles commandes).

## 0.5.6
- Redimensionnement de la fenêtre fluide : l'image est étirée instantanément pendant qu'on tire, puis redessinée nette dès qu'on relâche.
- Redessin 2 à 3 fois plus rapide (flous calculés sur une version réduite, sur-échantillonnage constant en grande taille).

## 0.5.5
- Reconnaissance plus sûre : la distance d'identité est la moyenne des 3 échantillons les plus proches (et non plus le seul plus proche), seuil par défaut 0.40 (au lieu de 0.45), 3 images reconnues nécessaires (au lieu de 2). Un proche qui te ressemble ne passe plus par hasard près d'un seul échantillon.
- Nouvelle commande `sudo faceauth measure` : mesure les distances en direct pour choisir le seuil (toi, puis les personnes qui ne doivent pas entrer).

## 0.5.4
- Nouvelle icône de l'application (visage + repères de reconnaissance), pour le menu des applications et la fenêtre. Le logo ACGC Innov'Bot reste affiché dans l'interface.
- L'installation et la désinstallation rafraîchissent le cache d'icônes et le menu : fini l'ancienne icône qui reste affichée.

## 0.5.3
- Démarrage nettement plus rapide : FaceAuth appelle dlib directement et ne charge que les modèles dont il a besoin (le détecteur CNN, jamais utilisé, n'est plus chargé ; le gros modèle à 68 points seulement quand un défi en a besoin). Résultats identiques : les visages déjà enregistrés restent valables.
- Sans défi (`challenge = none`), les 68 points ne sont plus calculés du tout.

## 0.5.2
- Démarrage plus rapide : la caméra s'ouvre pendant le chargement de dlib et de ses modèles au lieu d'attendre la fin.

## 0.5.1
- Fenêtre redimensionnable (et agrandissable), centrée, plus grande par défaut sur un écran d'ordinateur ; F11 = plein écran, Échap = quitter le plein écran. Le dessin s'adapte à la taille de la fenêtre.
- Caméra plus réactive : format MJPG, tampon réduit à 1 image, 3 images d'échauffement au lieu de 5.
- Le message d'échec ne cite plus que le défi réellement en cours.

## 0.5.0
- Enregistrement guidé : de face, puis tête tournée à gauche, puis à droite. Un échantillon n'est retenu que si la tête est vraiment dans la pose demandée (une pose impossible est abandonnée au bout de 20 s).
- Fenêtre caméra avec les points de reconnaissance du visage (68 repères) et une jauge de rotation gauche / droite, aussi dans `faceauth test --show`.
- Nouvelle interface « tableau de bord » dessinée avec Pillow (polices Poppins embarquées) : barre latérale, état du système, visuel de scan animé, cartes Enregistrer / Tester / Activer, profils, détection du vivant suivie en direct pendant le test, mot de passe de secours, journal intégré.
- Pages Profils (liste, ajout, suppression), Paramètres (défis, tolérance, délai, activation) et À propos.
- Nouvelles commandes : `faceauth profiles --json`, `faceauth remove --profile NOM`, `faceauth config section.clé=valeur` (les commentaires du fichier de config sont conservés).
- Logo ACGC Innov'Bot dans l'interface, l'icône de fenêtre et le menu des applications.

## 0.4.0
- Paquet Debian/Ubuntu (`.deb`) : installation en un clic, sans terminal.
- Interface graphique `faceauth-gui` (enregistrer, tester, activer sudo / écran de connexion, tout désactiver, diagnostic) avec entrée dans le menu des applications.
- Les droits administrateur passent par une fenêtre pkexec quand il n'y a pas de terminal.

## 0.3.0
- Profils d'enregistrement : `faceauth enroll --profile lunettes` ajoute des échantillons (lunettes, voile, barbe...) sans écraser les autres ; `faceauth remove` supprime tout.
- Correction : `faceauth remove` ne trouvait pas les données sans sudo.

## 0.2.2
- Mode strict : 6 s de délai supplémentaires ; identité vérifiée à chaque image une fois les défis validés (corrige des échecs « visage non reconnu » alors que la distance était bonne).
- Message d'échec explicite quand le visage est reconnu trop tard.

## 0.2.1
- `faceauth doctor` / `test` : distinguent « visage illisible sans sudo » de « aucun visage enregistré ».

## 0.2.0
- Mode `strict` : clignement + rotation gauche + rotation droite dans un ordre aléatoire.
- Liaison identité/défis (`bind_identity`) : seules les reconnaissances faites après les défis comptent.
- Retour rapide au mot de passe si aucun visage n'est vu (`no_face_timeout`).
- Option `[camera] device` (chemin du périphérique, caméras IR).
- Enregistrement guidé (face, gauche, droite).
- Nouvelle commande `faceauth doctor`.
- Messages d'échec plus utiles (distance mesurée / seuil).
- `faceauth-pam` ignore les types PAM autres que `auth`.
- Logique de décision isolée dans `session.py` ; tests pour `session` et `pamconf` ; CI GitHub Actions.
- README en anglais.

## 0.1.2
- Défis annoncés un par un, messages de diagnostic.
