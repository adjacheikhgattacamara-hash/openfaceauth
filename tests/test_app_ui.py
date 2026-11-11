"""Tests de l'interface : rendu de chaque page, flux du test, dialogues, coque tkinter simulée."""
import datetime
import sys
from types import SimpleNamespace
from unittest import mock

from faceauth import app as A
from faceauth import config, uikit


def make(**kw):
    status = lambda: {"title": "Système prêt", "sub": "Actif : sudo", "tone": "ok", "os": "Test OS",
                      "cfg": config.load_config("/inexistant")}
    calls = []
    a = A.App(0.5, status_fn=status, today=datetime.date(2026, 11, 12),
              spawn=lambda cmd, kind: calls.append((kind, cmd)), **kw)
    return a, calls


def test_every_page_renders():
    a, _ = make()
    a.profiles = ["principal", "lunettes"]
    for page in ("home", "profiles", "settings", "about"):
        a.go(page)
        assert a.image().size == (round(uikit.W * .5), round(uikit.H * .5))


def test_test_flow_updates_liveness():
    a, calls = make()
    a.act_test()
    assert calls[-1][0] == "test" and a.test_state == "busy"
    for line in ("FaceAuth : regardez la caméra.", "Fermez les yeux un instant, puis rouvrez-les.", "✓"):
        a.on_line(line)
    assert [i["state"] for i in a.live][0] == "done"
    a.on_line("SUCCÈS : visage validé.")
    a.on_done(0)
    assert a.test_state == "ok" and all(i["state"] == "done" for i in a.live) and a.busy is None


def test_failed_test_opens_dialog():
    a, _ = make()
    a.act_test()
    a.on_line("ÉCHEC : visage non reconnu.")
    a.on_done(1)
    assert a.test_state == "fail" and a.modal and "ÉCHEC" in a.modal["text"]


def test_second_action_is_refused_while_busy():
    a, calls = make()
    a.act_enroll()
    a.act_enroll()
    assert len(calls) == 1 and a.toast


def test_profiles_json_and_delete():
    a, calls = make()
    a.act_load_profiles()
    a.on_line('{"user": "adja", "profiles": ["principal", "voile"]}')
    a.on_done(0)
    assert a.profiles == ["principal", "voile"]
    a.act_delete_profile("voile")
    a.modal["buttons"][-1][2]()
    assert calls[-1][0] == "delete" and calls[-1][1][-2:] == ["--profile", "voile"]


def test_add_profile_validates_name():
    a, calls = make()
    a.act_add_profile()
    for ch in "Mon Profil!":
        a.key(ch, "x")
    a.key("", "Return")
    assert a.modal and a.modal["error"] and not calls
    a.modal["input"] = "lunettes"
    a.key("", "Return")
    assert calls[-1][0] == "profile" and calls[-1][1][-1] == "lunettes"


def test_settings_save_builds_command():
    a, calls = make()
    a.draft["challenge"] = "strict"
    a.act_save_settings()
    cmd = calls[-1][1]
    assert calls[-1][0] == "config" and "liveness.challenge=strict" in cmd and cmd[0] == "pkexec"


def test_cancelled_password_gives_toast_not_error_dialog():
    a, _ = make()
    a.act_run("doctor", "x") if False else a.run(["x"], "Activation", "enable_sudo")
    a.on_done(126)
    assert a.toast and a.modal is None


def test_clicks_reach_buttons():
    a, calls = make()
    a.frame()
    card = next(i for i in a._items if i.id == "card0")
    px, py = (card.x + 5) * a.scale, (card.y + 5) * a.scale
    a.press(px, py)
    a.release(px, py)
    assert calls and calls[-1][0] == "enroll"


def test_tk_shell_runs_with_a_fake_tkinter():
    tk = mock.MagicMock()
    root = tk.Tk.return_value
    root.winfo_screenwidth.return_value, root.winfo_screenheight.return_value = 1920, 1080
    with mock.patch.dict(sys.modules, {"tkinter": tk}):
        from faceauth import gui
        assert gui.main() == 0
    canvas = tk.Canvas.return_value
    handlers = {c.args[0]: c.args[1] for c in canvas.bind.call_args_list}
    ev = SimpleNamespace(x=300, y=200, delta=120, char="", keysym="Escape")
    for name in ("<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>", "<Leave>", "<MouseWheel>"):
        handlers[name](ev)
    tick = root.after.call_args_list[0].args[1]
    tick()


def test_set_values_keeps_comments(tmp_path):
    path = tmp_path / "f.conf"
    path.write_text("# commentaire\n[liveness]\n# défi\nchallenge = both\n")
    config.set_values(str(path), {"liveness.challenge": "strict", "recognition.tolerance": "0.4"})
    text = path.read_text()
    assert "# commentaire" in text and "# défi" in text and "challenge = strict" in text
    assert config.load_config(str(path)).tolerance == 0.4
    for bad in ({"camera.index": "1"}, {"liveness.challenge": "x"}):
        try:
            config.set_values(str(path), bad)
            raise AssertionError("aurait dû refuser")
        except ValueError:
            pass


def test_set_scale_redraws_at_new_size():
    a, _ = make()
    a.image()
    assert a.set_scale(0.8) is True and a.set_scale(0.8) is False
    assert a.image().size == (round(uikit.W * .8), round(uikit.H * .8))
