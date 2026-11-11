<p align="center"><img src="src/faceauth/assets/logo.png" alt="OpenFaceAuth logo" width="110"></p>

<h1 align="center">OpenFaceAuth</h1>

[Français](README.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

Face-recognition login for Linux (Ubuntu / Debian) using a plain webcam, no infrared sensor needed. Open source (MIT), one-command install, one config file.

It plugs into PAM as **an additional way to authenticate**: if your face is not recognised, the camera is missing or anything fails, your **usual password** still works.

## How it works

1. **Recognition**: your face is compared with enrolled samples (`face_recognition` / dlib).
2. **Liveness**: random challenges (blink, turn head left/right) defeat still photos, using dlib's 68 landmarks. In `strict` mode three challenges (blink, left, right) come in random order, so a pre-recorded video cannot match.
3. **Identity binding**: only recognitions made *after* the challenges count, so the face that did the challenges is the one that gets verified.
4. **Integration**: a `pam_exec` line on the chosen service (`sudo` by default; `gdm-password` for the GNOME login/lock screen).

## Optional AI anti-spoofing

The challenges (blink, turn) stop still photos. A **video replayed on a screen** is harder: a small neural network (MiniFASNetV2-SE, ONNX, ~600 KB) looks at skin texture (screen pixel grid, print halftone) and rejects what looks like a photo or a screen. It is an **extra layer** on top of the challenges, never a replacement.

```bash
faceauth antispoof                 # 1) in front of your real face: scores should be above the threshold
faceauth antispoof                 # 2) in front of a photo or a phone screen: below the threshold
sudo faceauth config liveness.antispoof=true liveness.antispoof_threshold=0.5
sudo faceauth test
```

- The model only runs on frames that would count as recognized (~11 ms); a frame judged photo/screen resets the streak.
- If enabled but unusable (`onnxruntime` missing, tampered model), FaceAuth **refuses** and falls back to the password; it never ignores it silently. `faceauth doctor` reports it.
- Limits: even lighting and a frontal face (±30°) work best; faces smaller than 64 px are not analysed; **3D masks and live-generated video are not covered**. If your real face is rejected, lower the threshold a little (0.4) or improve the lighting.
- Model: quantized MiniFASNetV2-SE from [facenox/face-antispoof-onnx](https://github.com/facenox/face-antispoof-onnx) (Apache-2.0), based on Minivision AI. See `THIRD_PARTY_NOTICES.md`.

## Security warning

A normal webcam has no depth sensing. This is **weaker** than Windows Hello (IR) or a fingerprint reader. Photos and pre-recorded videos are blocked by the challenges, but a live deepfake or a 3D mask may still work. For sensitive data keep password-only login, or enable FaceAuth for `sudo` only. Full-disk encryption (LUKS) is not affected and remains your real protection against offline access. See [SECURITY.md](SECURITY.md).

## Install from a package (no terminal)

Download `openfaceauth_<version>_all.deb` from the repository's **Releases** page and double-click it, or:

```bash
sudo apt install ./openfaceauth_0.7.0_all.deb
```

Needs Internet (prebuilt dlib wheel: seconds; falls back to compiling, 5 to 15 minutes, if no wheel fits). Then open **FaceAuth** from the applications menu: enroll, test, and enable it for `sudo` and/or the login screen. Admin rights are requested through a password dialog. Uninstall with `sudo apt remove openfaceauth` (PAM lines are removed automatically; `purge` also deletes enrolled faces).

> FaceAuth is built on PAM: Linux only (Ubuntu / Debian and derivatives), not Windows or macOS. Build it yourself with `./packaging/build-deb.sh`.

## Install from the command line

```bash
git clone https://github.com/adjacheikhgattacamara-hash/openfaceauth.git
cd openfaceauth
sudo ./install.sh        # prebuilt dlib wheel (compiles only as a fallback)
```

## Usage

```bash
faceauth enroll          # enroll your face (no sudo: a camera window opens; follow the on-screen prompts)
sudo faceauth test       # check you are recognised, challenges included
sudo faceauth enable     # enable for sudo
faceauth doctor          # diagnose dependencies, camera, PAM, enrollment, security level
sudo faceauth measure    # live distance to your enrolled face (to tune the tolerance)
faceauth block NAME      # enroll a look-alike relative as a BLOCKED face (with their consent)
faceauth status
```

**Before `enable`**: open a second terminal with `sudo -s` and keep it open. Test in another terminal with `sudo -k && sudo true`. To roll back: `sudo faceauth disable` or `sudo cp /etc/pam.d/sudo.faceauth.bak /etc/pam.d/sudo`.

### Login screen (GNOME)

```bash
sudo faceauth enable gdm-password --force
```

Keep a root terminal open and test with `Super+L` first. The face check runs *before* the password field appears (PAM steps are sequential); `no_face_timeout` sends you to the password quickly when nobody is in front of the camera. The GNOME keyring is not unlocked by your face. Fallback if locked out: `Ctrl+Alt+F3`, log in with your password, `sudo faceauth disable gdm-password`.

## Configuration

Everything lives in `/etc/faceauth/faceauth.conf`, re-read at each authentication.

| Option | Default | Effect |
|---|---|---|
| `[general] enabled` | `true` | `false` disables FaceAuth without touching PAM |
| `[general] log` | `true` | Results in `journalctl -t faceauth` |
| `[camera] index` / `device` | `0` / empty | Camera number, or device path (e.g. an IR camera) |
| `[recognition] tolerance` | `0.40` | Lower = stricter (0.35 to 0.6). Look-alike relatives can pass at 0.45: tune it with `sudo faceauth measure` |
| `[recognition] min_matches` | `3` | Recognised frames required |
| `[recognition] block_margin` | `0.05` | Margin for blocked faces: a face closer to a blocked face than to yours (within this margin) is refused |
| `[liveness] challenge` | `both` | `none`, `blink`, `turn`, `both`, `strict` |
| `[liveness] timeout` | `12` | Seconds before falling back to the password |
| `[liveness] no_face_timeout` | `4` | Seconds without a face before falling back immediately |
| `[liveness] bind_identity` | `true` | Count only recognitions made after the challenges |
| `[liveness] ear_threshold` | `0.21` | Blink threshold; lower it if blinks are missed |
| `[liveness] yaw_delta` | `0.15` | Head-turn amplitude required |
| `[liveness] antispoof` | `false` | `true` enables the AI anti-spoofing check (photo / screen) |
| `[liveness] antispoof_threshold` | `0.5` | Minimum "real face" probability (0.05 to 0.99); higher = stricter |

## Glasses, headscarf, beard, hairstyle

- **Glasses**: usually fine. Enroll with *and* without: `faceauth enroll` then `faceauth enroll --profile glasses`. Reflections can hide blinks: lower `ear_threshold` (0.18) or use `challenge = turn`.
- **Headscarf leaving the face visible** (eyes, nose, mouth and chin clear): works, but enroll *wearing it* (`--profile scarf`).
- **Covered face (nose, mouth or chin hidden)**: does not work, since the facial landmarks are required for recognition and challenges; the password takes over.
- All profiles are merged: a face is accepted if it matches any of them.

## Uninstall

```bash
sudo ./uninstall.sh
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest numpy
PYTHONPATH=src pytest
```

The decision logic (`liveness.py`, `session.py`, `config.py`, `pamconf.py`) does not need a camera and is unit-tested. CI runs the tests on every push.

## License

MIT, see [LICENSE](LICENSE).
