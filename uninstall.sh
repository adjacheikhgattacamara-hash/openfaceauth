#!/usr/bin/env bash
# Désinstallation de FaceAuth (retire d'abord les lignes PAM).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Lance avec sudo : sudo ./uninstall.sh"
    exit 1
fi

echo "==> Retrait des lignes FaceAuth dans /etc/pam.d"
for f in /etc/pam.d/*; do
    if [[ -f "$f" ]] && grep -q "# faceauth" "$f"; then
        sed -i '/# faceauth/d' "$f"
        echo "    nettoyé : $f"
    fi
done

echo "==> Suppression des fichiers"
rm -f /usr/local/bin/faceauth /usr/local/bin/faceauth-pam
rm -rf /opt/faceauth

read -r -p "Supprimer aussi les visages enregistrés et la config ? [o/N] " answer
if [[ "${answer,,}" == "o" ]]; then
    rm -rf /var/lib/faceauth /etc/faceauth
    echo "    données et config supprimées"
fi
echo "FaceAuth est désinstallé."
