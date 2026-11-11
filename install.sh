#!/usr/bin/env bash
# Installation de FaceAuth sur Ubuntu / Debian.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Lance avec sudo : sudo ./install.sh"
    exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX=/opt/faceauth

echo "==> Dépendances système"
apt-get update
apt-get install -y python3 python3-venv python3-pip python3-tk v4l-utils

echo "==> Environnement Python dans $PREFIX/venv"
python3 -m venv "$PREFIX/venv"
# setuptools < 81 : face_recognition_models a encore besoin de pkg_resources.
"$PREFIX/venv/bin/pip" install --upgrade pip wheel "setuptools<81"
# dlib précompilé ; repli sur la compilation (5 à 15 minutes) si aucun wheel ne convient.
if ! "$PREFIX/venv/bin/pip" install dlib-bin; then
    echo "    pas de wheel dlib-bin : compilation de dlib"
    apt-get install -y python3-dev cmake build-essential libopenblas-dev liblapack-dev
    "$PREFIX/venv/bin/pip" install dlib
fi
"$PREFIX/venv/bin/pip" install "$HERE"
# IA anti-usurpation (optionnelle) : un échec n'empêche pas l'installation.
"$PREFIX/venv/bin/pip" install onnxruntime \
    || echo "    onnxruntime non installé : anti-usurpation par IA indisponible"

echo "==> Fichiers système"
install -d -m 700 /var/lib/faceauth
install -d -m 755 /etc/faceauth
if [[ ! -f /etc/faceauth/faceauth.conf ]]; then
    install -m 644 "$HERE/config/faceauth.conf" /etc/faceauth/faceauth.conf
else
    echo "    /etc/faceauth/faceauth.conf existe déjà : conservé"
fi
ln -sf "$PREFIX/venv/bin/faceauth" /usr/local/bin/faceauth
ln -sf "$PREFIX/venv/bin/faceauth-pam" /usr/local/bin/faceauth-pam

cat <<'EOF'

FaceAuth est installé. Suite :
  1. faceauth enroll          (sans sudo : enregistre ton visage)
  2. sudo faceauth test       (vérifie que tu es reconnu)
  3. sudo faceauth enable     (active pour sudo ; garde un terminal root ouvert !)
Configuration : /etc/faceauth/faceauth.conf
EOF
