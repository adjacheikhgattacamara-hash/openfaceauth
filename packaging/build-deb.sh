#!/usr/bin/env bash
# Construit openfaceauth_<version>_all.deb (Ubuntu / Debian). Usage : ./packaging/build-deb.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$HERE/pyproject.toml" | head -1)"
OUT="${1:-$HERE/dist}"
STAGE="$(mktemp -d)"
PKG="$STAGE/openfaceauth_${VERSION}_all"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$PKG/DEBIAN" "$PKG/usr/share/openfaceauth/src" "$PKG/usr/share/applications" \
         "$PKG/etc/faceauth" "$PKG/usr/share/doc/openfaceauth" \
         "$PKG/usr/share/icons/hicolor/512x512/apps"

# Sources installées dans le venv par postinst
cp -r "$HERE/src" "$HERE/pyproject.toml" "$HERE/README.md" "$HERE/LICENSE" \
      "$PKG/usr/share/openfaceauth/src/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +

install -m 644 "$HERE/config/faceauth.conf" "$PKG/etc/faceauth/faceauth.conf"
install -m 644 "$HERE/packaging/faceauth.desktop" "$PKG/usr/share/applications/faceauth.desktop"
install -m 644 "$HERE/src/faceauth/assets/icon.png" \
        "$PKG/usr/share/icons/hicolor/512x512/apps/openfaceauth.png"
install -m 644 "$HERE/LICENSE" "$PKG/usr/share/doc/openfaceauth/copyright"
install -m 644 "$HERE/CHANGELOG.md" "$PKG/usr/share/doc/openfaceauth/changelog"
install -m 644 "$HERE/THIRD_PARTY_NOTICES.md" "$PKG/usr/share/doc/openfaceauth/THIRD_PARTY_NOTICES.md"
install -m 644 "$HERE/SECURITY.md" "$PKG/usr/share/doc/openfaceauth/SECURITY.md"
echo "/etc/faceauth/faceauth.conf" > "$PKG/DEBIAN/conffiles"

for f in postinst prerm postrm; do
    install -m 755 "$HERE/packaging/$f" "$PKG/DEBIAN/$f"
done

cat > "$PKG/DEBIAN/control" <<CTRL
Package: openfaceauth
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-venv, python3-tk, v4l-utils, libpam-modules, pkexec | policykit-1
Suggests: cmake, build-essential, python3-dev, libopenblas-dev, liblapack-dev
Maintainer: Adja Cheikh Gatta Camara <adjacheikhgattacamara-hash@users.noreply.github.com>
Homepage: https://github.com/adjacheikhgattacamara-hash/openfaceauth
Description: Déverrouillage par reconnaissance faciale (PAM)
 FaceAuth ajoute la reconnaissance faciale avec une webcam ordinaire à sudo et à
 l'écran de connexion GNOME, avec détection du vivant. Le mot de passe reste
 toujours utilisable. Installation rapide (dlib précompilé).
CTRL

mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$PKG" "$OUT" >/dev/null
echo "Paquet : $OUT/openfaceauth_${VERSION}_all.deb"
