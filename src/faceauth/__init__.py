"""FaceAuth : déverrouillage par reconnaissance faciale pour Linux (PAM)."""
import warnings

# face_recognition_models utilise encore pkg_resources : avertissement sans conséquence.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)

__version__ = "0.7.0"
