from faceauth.config import Config, load_config


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(str(tmp_path / "nope.conf")) == Config()


def test_values_are_read(tmp_path):
    f = tmp_path / "c.conf"
    f.write_text(
        "[recognition]\ntolerance = 0.5\nmin_matches = 3\n"
        "[liveness]\nchallenge = blink\ntimeout = 12\n[camera]\nindex = 2\n"
    )
    cfg = load_config(str(f))
    assert cfg.tolerance == 0.5
    assert cfg.min_matches == 3
    assert cfg.challenge == "blink"
    assert cfg.timeout == 12.0
    assert cfg.camera_index == 2


def test_invalid_values_fall_back(tmp_path):
    f = tmp_path / "c.conf"
    f.write_text("[liveness]\nchallenge = nimporte\ntimeout = 0\n[recognition]\ntolerance = abc\n")
    cfg = load_config(str(f))
    assert cfg.challenge == "both"
    assert cfg.timeout == 3.0  # plancher
    assert cfg.tolerance == 0.40


def test_shipped_config_is_valid():
    cfg = load_config("config/faceauth.conf")
    assert cfg == Config()


def test_new_options(tmp_path):
    f = tmp_path / "c.conf"
    f.write_text("[camera]\ndevice = /dev/video2\n[liveness]\nchallenge = strict\n"
                 "no_face_timeout = 2\nbind_identity = false\n")
    cfg = load_config(str(f))
    assert cfg.camera_device == "/dev/video2"
    assert cfg.challenge == "strict"
    assert cfg.no_face_timeout == 2.0
    assert cfg.bind_identity is False
