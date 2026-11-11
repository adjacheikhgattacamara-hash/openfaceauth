# Contribuer

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest numpy
PYTHONPATH=src pytest
```

- La logique qui ne dépend pas de la caméra va dans `liveness.py` / `session.py` et doit être testée.
- Teste toute modification PAM sur `sudo` d'abord, avec un terminal root ouvert.
- Pour un bug de caméra, donne le modèle de webcam et la sortie de `faceauth doctor`.
