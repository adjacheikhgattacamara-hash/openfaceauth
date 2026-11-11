import importlib

import faceauth.pamconf as pamconf


def load(tmp_path, monkeypatch, content):
    monkeypatch.setenv("FACEAUTH_PAM_DIR", str(tmp_path))
    importlib.reload(pamconf)
    (tmp_path / "svc").write_text(content)
    return tmp_path / "svc"


def test_enable_inserts_after_header_and_backs_up(tmp_path, monkeypatch):
    f = load(tmp_path, monkeypatch, "#%PAM-1.0\n\n@include common-auth\n")
    assert pamconf.enable("svc") is True
    lines = f.read_text().splitlines()
    assert lines[0] == "#%PAM-1.0"
    assert "# faceauth" in lines[2] and lines[3] == "@include common-auth"
    assert (tmp_path / "svc.faceauth.bak").exists()
    assert pamconf.is_enabled("svc")


def test_enable_twice_is_noop_and_disable_restores(tmp_path, monkeypatch):
    f = load(tmp_path, monkeypatch, "#%PAM-1.0\n@include common-auth\n")
    pamconf.enable("svc")
    assert pamconf.enable("svc") is False
    assert pamconf.disable("svc") is True
    assert f.read_text() == "#%PAM-1.0\n@include common-auth\n"
    assert pamconf.disable("svc") is False


def test_invalid_service_names_are_rejected(tmp_path, monkeypatch):
    load(tmp_path, monkeypatch, "x\n")
    for bad in ("../passwd", "", ".hidden", "a/b"):
        try:
            pamconf.enable(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
