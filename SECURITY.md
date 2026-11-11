# Security policy

## What FaceAuth protects (and what it does not)

FaceAuth lets you unlock `sudo` and, optionally, the GNOME login screen with an ordinary webcam. **The password always remains usable.**

| Layer | Stops | Does not stop |
|---|---|---|
| Face recognition (dlib) | strangers | look-alikes (use `faceauth block`, lower `tolerance`) |
| Challenges (blink, turn; `strict` = 3 random challenges) | still photos, pre-recorded video (`strict`) | live-generated video (deepfake) |
| Optional AI anti-spoofing (MiniFASNet) | photos and screens (texture cues) | 3D masks, high-quality prosthetics, live deepfakes |

An ordinary RGB webcam has no depth sensor and no infrared: this is **less secure than Windows Hello (IR) or a fingerprint reader**. For sensitive systems keep the password, or enable FaceAuth for `sudo` only, with `challenge = strict` and `antispoof = true`.

## Design choices that matter

- Fail-safe: any error, timeout or missing camera returns control to the password (`faceauth-pam` has an absolute watchdog).
- If an enabled protection cannot run (anti-spoofing model missing or altered), authentication is **refused**, not silently downgraded.
- Enrolled faces are stored in `/var/lib/faceauth` (root only, mode 700). They are biometric data: `apt purge openfaceauth` deletes them.
- Test on `sudo` first and keep a root terminal open before enabling the login screen.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem. Use GitHub's private reporting:
<https://github.com/adjacheikhgattacamara-hash/openfaceauth/security/advisories/new>

Include your Ubuntu/Python versions, the configuration (`faceauth doctor` output) and steps to reproduce. You will get an answer as soon as possible; this is a volunteer project, with no guaranteed response time.
