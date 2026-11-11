import os

import faceauth.store as store
from faceauth import cli, gui


def test_gui_commands_use_pkexec_for_root_actions_only():
    c = gui.commands()
    assert c["enroll"][0] == gui.FACEAUTH and "pkexec" not in c["enroll"]
    assert c["test"][0] == "pkexec"
    assert c["enable_login"][-3:] == ["enable", "gdm-password", "--force"]
    assert "gdm-password" in c["disable_all"][-1] and " disable;" in c["disable_all"][-1]
    assert gui.profile_command("lunettes")[-2:] == ["--profile", "lunettes"]


def test_current_user_prefers_sudo_user_then_pkexec(monkeypatch):
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.delenv("PKEXEC_UID", raising=False)
    monkeypatch.setenv("SUDO_USER", "adja")
    assert cli.current_user() == "adja"
    monkeypatch.delenv("SUDO_USER")
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    import pwd

    assert cli.current_user() == pwd.getpwuid(os.getuid()).pw_name


def test_escalation_uses_pkexec_without_terminal(monkeypatch):
    monkeypatch.setattr(store.shutil, "which", lambda n: "/usr/bin/pkexec")
    monkeypatch.setattr(store.sys.stdin, "isatty", lambda: False, raising=False)
    assert store._escalate() == ["pkexec"]
    monkeypatch.setattr(store.sys.stdin, "isatty", lambda: True, raising=False)
    assert store._escalate() == ["sudo"]


def test_logo_is_shipped_and_lines_are_classified():
    assert gui.logo_path() is not None and gui.logo_path().name == "logo.png"
    assert gui.classify("Erreur caméra") == "err"
    assert gui.classify("Visage reconnu") == "ok"
    assert gui.classify("look token") == ""
