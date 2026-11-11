# Third-party notices

## Face anti-spoofing model (`src/faceauth/assets/models/antispoof.onnx`)

- **Source**: <https://github.com/facenox/face-antispoof-onnx> (`models/best_model_quantized.onnx`, INT8, ~600 KB).
- **License**: Apache License 2.0 (full text in `src/faceauth/assets/models/LICENSE-antispoof-model.txt`).
- **Architecture**: MiniFASNetV2-SE, from the *Silent-Face-Anti-Spoofing* project by Minivision AI (Apache-2.0): <https://github.com/minivision-ai/Silent-Face-Anti-Spoofing>.
- **Changes**: none. The file is bundled unmodified; its SHA-256 is checked at load time (`antispoof.py`).
- **Training data**: the upstream project reports training and evaluation on CelebA-Spoof. The terms of use of that dataset (research use; please verify) may also apply to models trained on it. **Check them before any commercial redistribution.** FaceAuth itself is MIT-licensed; the model keeps its own license.

## Python dependencies (installed by pip, not bundled)

dlib (Boost Software License), face_recognition_models, OpenCV, NumPy, Pillow, ONNX Runtime (MIT). Each keeps its own license.
