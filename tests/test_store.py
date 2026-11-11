import importlib
import os

import numpy as np
import pytest

import faceauth.store as store


def test_unreadable_dir_is_not_reported_as_absent(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("root ignore les permissions")
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("FACEAUTH_DATA", str(d))
    importlib.reload(store)
    np.save(d / "adja.npy", np.zeros((2, 128)))
    d.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            store.load("adja")
    finally:
        d.chmod(0o700)
    assert store.load("adja").shape == (2, 128)
    assert store.load("inconnu") is None


def test_profiles_are_merged_listed_and_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("FACEAUTH_DATA", str(tmp_path / "d"))
    importlib.reload(store)
    monkeypatch.setattr(store.os, "geteuid", lambda: 0)
    store.save("adja", np.zeros((3, 128)))
    store.save("adja", np.ones((2, 128)), "lunettes")
    store.save("bob.x", np.ones((1, 128)))
    assert store.load("adja").shape == (5, 128)  # principal + lunettes
    assert store.load("bob.x").shape == (1, 128)
    assert store.list_users() == ["adja", "bob.x"]
    assert store.list_profiles("adja") == ["principal", "lunettes"] or \
        sorted(store.list_profiles("adja")) == ["lunettes", "principal"]
    store.save("adja", np.ones((4, 128)), "lunettes")  # même profil : remplacé
    assert store.load("adja").shape == (7, 128)
    assert store.delete("adja") is True
    assert store.load("adja") is None and store.load("bob.x") is not None


def test_invalid_profile_name_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("FACEAUTH_DATA", str(tmp_path))
    importlib.reload(store)
    with pytest.raises(ValueError):
        store.path_for("adja", "../x")


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("FACEAUTH_DATA", str(tmp_path / "d"))
    importlib.reload(store)
    return tmp_path / "d"


def test_invalid_face_files_are_rejected(tmp_path, monkeypatch):
    d = _fresh(tmp_path, monkeypatch)
    for bad in (np.zeros((0, 128)), np.zeros((3, 64)), np.full((2, 128), np.nan), np.zeros(128)):
        with pytest.raises(ValueError):
            store.save("adja", bad)
    d.mkdir(parents=True, exist_ok=True)
    np.save(d / "adja.npy", np.zeros((2, 7)))  # fichier abîmé déjà présent
    with pytest.raises(ValueError):
        store.load("adja")


def test_save_is_atomic_and_private(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("écriture directe réservée à root")
    d = _fresh(tmp_path, monkeypatch)
    store.save("adja", np.zeros((3, 128)))
    assert [p.name for p in d.iterdir()] == ["adja.npy"]  # aucun fichier temporaire
    assert oct(os.stat(d / "adja.npy").st_mode & 0o777) == "0o600"
    assert oct(os.stat(d).st_mode & 0o777) == "0o700"


def test_blocked_faces_are_separate_listed_and_deleted(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("écriture directe réservée à root")
    _fresh(tmp_path, monkeypatch)
    store.save("adja", np.zeros((3, 128)))
    store.save_blocked("adja", "soeur1", np.ones((4, 128)))
    store.save_blocked("adja", "soeur2", np.ones((2, 128)))
    assert store.load("adja").shape == (3, 128)           # le visage interdit n'est PAS le tien
    assert store.load_blocked("adja").shape == (6, 128)
    assert store.list_blocked("adja") == ["soeur1", "soeur2"]
    assert store.list_users() == ["adja"]                 # « adja~soeur1 » n'est pas un utilisateur
    assert store.delete_blocked("adja", "soeur1") is True
    assert store.list_blocked("adja") == ["soeur2"]
    assert store.delete_blocked("adja", "inconnue") is False
    assert store.delete("adja") is True                   # tout supprimer retire aussi les interdits
    assert store.load_blocked("adja") is None
    with pytest.raises(ValueError):
        store.save_blocked("adja", "nom invalide!", np.ones((2, 128)))
