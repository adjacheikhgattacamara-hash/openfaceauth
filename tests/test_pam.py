"""Point d'entrée PAM : codes de sortie et chien de garde (jamais de blocage)."""
import dataclasses
import subprocess
import sys
import time

import numpy as np
import pytest

from faceauth import config, core, pam, store


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("PAM_TYPE", "auth")
    monkeypatch.setenv("PAM_USER", "adja")
    monkeypatch.setattr(pam, "_arm_watchdog", lambda seconds: None)
    monkeypatch.setattr(pam, "_log", lambda message: None)
    monkeypatch.setattr(config, "load_config", lambda *a, **k: config.Config())
    monkeypatch.setattr(store, "load", lambda user: np.zeros((3, 128)))
    monkeypatch.setattr(store, "load_blocked", lambda user: None)


class FakeVerifier:
    result = (True, "ok")

    def __init__(self, *a, **k):
        pass

    def run(self):
        return self.result


def test_success_returns_0(env, monkeypatch):
    monkeypatch.setattr(core, "Verifier", FakeVerifier)
    assert pam.main() == 0


def test_failed_face_returns_1(env, monkeypatch):
    class Failing(FakeVerifier):
        result = (False, "visage non reconnu")

    monkeypatch.setattr(core, "Verifier", Failing)
    assert pam.main() == 1


def test_disabled_returns_1(env, monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda *a, **k: dataclasses.replace(config.Config(), enabled=False))
    monkeypatch.setattr(core, "Verifier", FakeVerifier)
    assert pam.main() == 1


def test_non_auth_phase_returns_1(env, monkeypatch):
    monkeypatch.setenv("PAM_TYPE", "account")
    monkeypatch.setattr(core, "Verifier", FakeVerifier)
    assert pam.main() == 1


def test_missing_user_returns_1(env, monkeypatch):
    monkeypatch.delenv("PAM_USER")
    assert pam.main() == 1


def test_unknown_user_falls_back_to_password(env, monkeypatch):
    monkeypatch.setattr(store, "load", lambda user: None)
    assert pam.main() == 1


def test_any_internal_error_falls_back_to_password(env, monkeypatch):
    def boom(user):
        raise RuntimeError("fichier abîmé")

    monkeypatch.setattr(store, "load", boom)
    assert pam.main() == 1


def test_watchdog_kills_a_hung_process():
    """Un programme bloqué doit se terminer tout seul, avec un code d'échec."""
    code = (
        "import time\n"
        "from faceauth import pam\n"
        "pam._log = lambda m: None\n"
        "pam._arm_watchdog(1)\n"
        "time.sleep(30)\n"
    )
    start = time.time()
    proc = subprocess.run([sys.executable, "-c", code], timeout=15)
    assert proc.returncode != 0
    assert time.time() - start < 8
