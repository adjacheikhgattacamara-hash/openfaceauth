<p align="center"><img src="src/faceauth/assets/logo.png" alt="Logo OpenFaceAuth" width="110"></p>

<h1 align="center">OpenFaceAuth</h1>

[English version](README.en.md) · [Changelog](CHANGELOG.md) · [Sécurité](SECURITY.md)

Déverrouillage par **reconnaissance faciale** pour Linux (Ubuntu / Debian), avec une simple webcam, sans capteur infrarouge. Open source (MIT), installable en une commande, configurable dans un seul fichier.

Il s'appuie sur PAM : FaceAuth est **un moyen d'authentification supplémentaire**. Si le visage n'est pas reconnu, si la caméra est absente ou si une erreur survient, le **mot de passe habituel** prend le relais.

## Fonctionnement

1. **Reconnaissance** : comparaison de ton visage avec les échantillons enregistrés (`face_recognition` / dlib).
2. **Détection du vivant** : un défi tiré au hasard (cligner des yeux, tourner la tête à gauche ou à droite) bloque les photos fixes. Il s'appuie sur les 68 repères du visage de dlib, donc aucune dépendance en plus.
3. **Anti-usurpation par IA (optionnel)** : un petit réseau de neurones (MiniFASNet, ONNX, ≈ 600 Ko) juge si le visage est réel ou une photo / un écran. Voir [Anti-usurpation par IA](#anti-usurpation-par-ia-optionnel).
4. **Intégration** : un appel `pam_exec` sur le service choisi (`sudo` par défaut).

## Avertissement de sécurité

Une webcam ordinaire ne voit pas la profondeur. Ce système est **moins sûr** que Windows Hello (infrarouge) ou une empreinte digitale :

- Une photo est bloquée par les défis. Le mode `strict` (ordre aléatoire de trois défis) rend une vidéo pré-enregistrée inutilisable, mais **une vidéo générée en direct** (deepfake) ou un masque 3D peut encore tromper le système.
- Pour des données vraiment sensibles, garde le mot de passe, ou n'active FaceAuth que pour `sudo`.
- N'active **jamais** FaceAuth sur l'écran de connexion sans avoir testé sur `sudo` et gardé un terminal root ouvert.

## Installation par paquet (sans terminal)

Télécharge `openfaceauth_<version>_all.deb` depuis la page **Releases** du dépôt, puis double-clique dessus (Logiciels / Centre d'applications), ou en une commande :

```bash
sudo apt install ./openfaceauth_0.7.0_all.deb
```

L'installation demande Internet (dlib précompilé : quelques secondes ; repli sur la compilation, 5 à 15 minutes, si aucun wheel ne convient). Ensuite, ouvre **FaceAuth** depuis le menu des applications : enregistre ton visage, teste, puis active-le pour `sudo` et/ou l'écran de connexion. Les droits administrateur sont demandés par une fenêtre de mot de passe. Pour désinstaller : `sudo apt remove openfaceauth` (les lignes PAM sont retirées automatiquement ; `purge` supprime aussi les visages enregistrés).

> FaceAuth repose sur PAM : il fonctionne sous Linux uniquement (Ubuntu / Debian et dérivés), pas sous Windows ni macOS.

Construire le paquet soi-même : `./packaging/build-deb.sh`.

## Installation en ligne de commande

```bash
git clone https://github.com/adjacheikhgattacamara-hash/openfaceauth.git
cd openfaceauth
sudo ./install.sh
```

dlib est installé en wheel précompilé ; sinon il est compilé (5 à 15 minutes).

## Utilisation

```bash
faceauth enroll        # enregistre ton visage (SANS sudo) : fenêtre caméra guidée, points du visage et jauge gauche/droite
sudo faceauth test     # vérifie que tu es reconnu, défis compris
sudo faceauth enable   # active pour sudo
faceauth status        # état de l'installation
faceauth doctor        # diagnostic : dépendances, caméra, PAM, visage enregistré, niveau de sécurité
```

**Avant `enable`** : ouvre un second terminal avec `sudo -s` et laisse-le ouvert. Teste ensuite dans un autre terminal avec `sudo -k && sudo true`. Si quelque chose tourne mal, `sudo faceauth disable` (ou `sudo cp /etc/pam.d/sudo.faceauth.bak /etc/pam.d/sudo`) rétablit la situation.

| Commande | Rôle |
|---|---|
| `faceauth enroll [--samples N] [--user NOM]` | Enregistrer un visage |
| `sudo faceauth test [--show]` | Tester dans le terminal (`--show` : fenêtre caméra, peut échouer sous sudo) |
| `sudo faceauth enable [service]` | Activer sur un service PAM (défaut : `sudo`) |
| `sudo faceauth disable [service]` | Désactiver |
| `faceauth remove` | Supprimer son visage |
| `faceauth status` | Voir la config, les visages et les services activés |
| `faceauth doctor` | Diagnostiquer l'installation et le niveau de sécurité, et dire quoi corriger |
| `sudo faceauth measure` | Mesurer en direct la distance entre le visage devant la caméra et le tien (pour régler le seuil) |
| `faceauth block NOM` | Enregistrer le visage d'un proche qui te ressemble comme **visage interdit** (avec son accord) |
| `faceauth unblock NOM` | Retirer un visage interdit |

### Plusieurs utilisateurs

Chaque personne lance `faceauth enroll` depuis son propre compte. Les visages sont stockés dans `/var/lib/faceauth/<utilisateur>.npy`, un dossier réservé à root.

## Configuration

Tout se règle dans `/etc/faceauth/faceauth.conf`, relu à chaque authentification (rien à redémarrer).

| Option | Défaut | Effet |
|---|---|---|
| `[general] enabled` | `true` | `false` désactive FaceAuth sans toucher à PAM |
| `[general] log` | `true` | Résultats dans `journalctl -t faceauth` |
| `[camera] index` | `0` | Numéro de la caméra (`v4l2-ctl --list-devices`) |
| `[camera] device` | vide | Chemin du périphérique (ex. `/dev/video2`, caméra IR) ; prioritaire sur `index` |
| `[recognition] tolerance` | `0.40` | Plus bas = plus strict (0.35 à 0.6). Des proches qui te ressemblent peuvent passer à 0.45 : règle-le avec `sudo faceauth measure` |
| `[recognition] min_matches` | `3` | Images reconnues nécessaires |
| `[recognition] block_margin` | `0.05` | Marge pour les visages interdits : un visage plus proche d'un visage interdit que du tien (à cette marge près) est refusé |
| `[recognition] identity_every` | `4` | Analyse de l'identité toutes les N images |
| `[liveness] challenge` | `both` | `none`, `blink`, `turn`, `both` ou `strict` (3 défis, ordre aléatoire) |
| `[liveness] no_face_timeout` | `4` | Sans visage détecté au bout de N s, retour immédiat au mot de passe |
| `[liveness] bind_identity` | `true` | Seules les reconnaissances faites **après** les défis comptent |
| `[liveness] timeout` | `12` | Secondes avant retour au mot de passe |
| `[liveness] ear_threshold` | `0.21` | Seuil de clignement : baisse-le s'il n'est pas détecté |
| `[liveness] yaw_delta` | `0.15` | Amplitude de rotation de tête demandée |
| `[liveness] antispoof` | `false` | `true` active l'IA anti-usurpation (photo / écran) |
| `[liveness] antispoof_threshold` | `0.5` | Probabilité minimale « visage réel » (0.05 à 0.99) ; plus haut = plus strict |

## Anti-usurpation par IA (optionnel)

Les défis (clignement, rotation) arrêtent les photos. Une **vidéo rejouée sur un écran** est plus difficile : l'IA regarde la texture du visage (grille de pixels de l'écran, trame d'une impression) et refuse ce qui ressemble à une photo ou à un écran. C'est une couche **en plus** des défis, jamais à leur place.

```bash
faceauth antispoof                 # 1) devant ton vrai visage : les scores doivent dépasser le seuil
faceauth antispoof                 # 2) devant une photo ou un écran de téléphone : sous le seuil
sudo faceauth config liveness.antispoof=true liveness.antispoof_threshold=0.5
sudo faceauth test
```

- Le modèle ne tourne que sur les images qui compteraient comme reconnues (≈ 11 ms) ; une image jugée photo/écran remet la série à zéro.
- Si la fonction est activée mais inutilisable (`onnxruntime` absent, modèle altéré), FaceAuth **refuse** et retombe sur le mot de passe : il ne l'ignore jamais en silence. `faceauth doctor` le signale.
- Limites : éclairage uniforme et visage de face (±30°) donnent les meilleurs résultats ; un visage plus petit que 64 px n'est pas analysé ; **les masques 3D et les vidéos générées en direct ne sont pas couverts**. Si ton vrai visage est refusé, baisse un peu le seuil (0.4) ou améliore la lumière.
- Modèle : MiniFASNetV2-SE quantifié, de [facenox/face-antispoof-onnx](https://github.com/facenox/face-antispoof-onnx) (Apache-2.0), d'après Minivision AI. Détails dans `THIRD_PARTY_NOTICES.md`.

## Écran de connexion et verrouillage

```bash
sudo faceauth enable gdm-password --force    # GNOME (Ubuntu par défaut)
```

À savoir avant de le faire :

- Le **trousseau de clés GNOME** n'est pas déverrouillé par le visage : tu devras peut-être retaper le mot de passe pour certaines applications.
- Si la caméra est occupée ou absente, tu retombes sur le mot de passe après le délai.
- Garde toujours un terminal root ouvert pendant le test.
- **Le visage est vérifié avant l'affichage du champ mot de passe** (PAM exécute les étapes l'une après l'autre). Pour limiter l'attente, `no_face_timeout` renvoie vite au mot de passe si personne n'est devant la caméra.
- Le verrouillage de session (`Super+L`) utilise le même service : teste-le d'abord ainsi, sans te déconnecter.
- Secours si l'écran est bloqué : `Ctrl+Alt+F3`, connexion avec le mot de passe, puis `sudo faceauth disable gdm-password`.

## Dépannage

- **Caméra introuvable** : `v4l2-ctl --list-devices`, puis ajuste `[camera] index`.
- **Visage non reconnu** : refais `faceauth enroll` avec plus de variété d'éclairage, ou monte légèrement `tolerance` (mesure d'abord avec `sudo faceauth measure`).
- **Clignement non détecté** : baisse `ear_threshold` (0.18), ou passe `challenge = turn`.
- **Rotation de tête de mauvais côté** : le sens est celui de *ton* corps (« votre droite »). Si cela ne colle pas avec ta caméra, ouvre une issue avec le modèle de ta webcam.
- **`No module named pkg_resources`** : `/opt/faceauth/venv/bin/pip install "setuptools<81"`.

## Lunettes, voile, barbe, coiffure

- **Lunettes** : fonctionne en général. Enregistre-toi avec **et** sans : `faceauth enroll` puis `faceauth enroll --profile lunettes`. Les reflets peuvent gêner le clignement : baisse `ear_threshold` (0.18) ou utilise `challenge = turn`.
- **Voile qui laisse le visage visible** (yeux, nez, bouche et menton dégagés) : fonctionne, mais enregistre-toi **avec** le voile (`--profile voile`), car la reconnaissance se fait sur le visage tel qu'il apparaît.
- **Visage couvert (nez, bouche ou menton cachés)** : ne fonctionne pas. Les repères du visage (menton, nez) sont nécessaires à la reconnaissance et aux défis ; le mot de passe prend alors le relais.
- Tous les profils sont réunis : le visage est accepté s'il ressemble à l'un d'eux. Plus il y a de profils, plus il faut rester prudent sur `tolerance`.

## Désinstallation

```bash
sudo ./uninstall.sh
```

Les lignes PAM sont retirées automatiquement avant la suppression des fichiers.

## Développement

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest numpy
PYTHONPATH=src pytest
```

La logique de détection du vivant (`liveness.py`) et la configuration (`config.py`) ne dépendent pas de la caméra et sont testées unitairement.

## Idées de contributions

- Modèle anti-spoofing dédié (Silent-Face-Anti-Spoofing) en plus des défis.
- Support des caméras infrarouges quand elles existent.
- Paquet `.deb` et PPA.
- Interface graphique d'enregistrement.

## Licence

MIT, voir [LICENSE](LICENSE).
