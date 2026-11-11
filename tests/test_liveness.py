import random

from faceauth.liveness import (
    BlinkDetector,
    TurnDetector,
    build_challenges,
    eye_aspect_ratio,
    yaw_ratio,
)

OPEN = [[0, 0], [3, 2], [7, 2], [10, 0], [7, -2], [3, -2]]
CLOSED = [[0, 0], [3, 0.2], [7, 0.2], [10, 0], [7, -0.2], [3, -0.2]]


def test_ear_open_vs_closed():
    assert eye_aspect_ratio(OPEN) > 0.3
    assert eye_aspect_ratio(CLOSED) < 0.1


def test_yaw_ratio_centered():
    assert yaw_ratio(50, 0, 100) == 0.5


def test_blink_needs_close_then_open():
    d = BlinkDetector(0.21)
    assert not d.update(0.3, 0.5)
    assert not d.update(0.1, 0.5)  # fermés : pas encore validé
    assert d.update(0.3, 0.5)  # rouverts : validé


def test_open_eyes_only_never_validates():
    d = BlinkDetector(0.21)
    for _ in range(20):
        d.update(0.3, 0.5)
    assert not d.done


def test_turn_right_requires_consecutive_frames():
    d = TurnDetector("right", 0.15, frames=3)
    d.update(None, 0.3)
    d.update(None, 0.5)  # retour de face : le compteur repart de zéro
    d.update(None, 0.3)
    d.update(None, 0.3)
    assert not d.done
    d.update(None, 0.3)
    assert d.done


def test_turn_left_is_opposite_direction():
    d = TurnDetector("left", 0.15, frames=1)
    d.update(None, 0.3)
    assert not d.done
    d.update(None, 0.7)
    assert d.done


def test_build_challenges_modes():
    assert build_challenges("none", 0.21, 0.15) == []
    assert len(build_challenges("blink", 0.21, 0.15)) == 1
    both = build_challenges("both", 0.21, 0.15, rng=random.Random(1))
    assert [type(c).__name__ for c in both] == ["BlinkDetector", "TurnDetector"]


def test_failure_messages_contain_measurements():
    stats = {"ear_min": 0.25, "yaw_min": 0.4, "yaw_max": 0.6}
    assert "0.25" in BlinkDetector(0.21).failure(stats)
    msg = TurnDetector("right", 0.15).failure(stats)
    assert "droite" in msg and "0.35" in msg
