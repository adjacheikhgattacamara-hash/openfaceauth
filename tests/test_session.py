import random

from faceauth.config import Config
from faceauth.liveness import BlinkDetector, TurnDetector, build_challenges
from faceauth.session import AuthSession


def make(detectors, **cfg):
    return AuthSession(detectors, Config(min_matches=2, **cfg), start=0.0)


def test_no_challenge_needs_min_matches():
    s = make([])
    s.feed(0.3, 0.5, 0.1)
    assert not s.succeeded
    s.feed(0.3, 0.5, 0.1)
    assert s.succeeded


def test_matches_before_challenges_do_not_count_when_bound():
    s = make([BlinkDetector(0.21)])
    for _ in range(5):
        s.feed(0.3, 0.5, 0.1)  # reconnu, mais pas encore de clignement
    assert s.matches == 0 and not s.succeeded
    s.feed(0.1, 0.5, 0.1)
    s.feed(0.3, 0.5, 0.1)  # clignement validé sur cette image
    s.feed(0.3, 0.5, 0.1)
    s.feed(0.3, 0.5, 0.1)
    assert s.succeeded


def test_matches_count_early_when_not_bound():
    s = make([BlinkDetector(0.21)], bind_identity=False)
    s.feed(0.3, 0.5, 0.1)
    s.feed(0.3, 0.5, 0.1)
    assert s.matches == 2 and not s.succeeded  # il manque encore le clignement


def test_wrong_face_never_succeeds_and_reports_distance():
    s = make([])
    for _ in range(5):
        s.feed(0.3, 0.5, 0.8)
    assert not s.succeeded
    assert "non reconnu" in s.reason() and "0.80" in s.reason()


def test_no_face_fail_fast():
    s = make([], no_face_timeout=4.0)
    assert not s.no_face_expired(3.9)
    assert s.no_face_expired(4.0)
    assert s.reason() == "aucun visage unique détecté"
    s.feed(0.3, 0.5)
    assert not s.no_face_expired(10.0)  # un visage a été vu : on attend le délai normal


def test_missing_challenge_is_reported():
    s = make([TurnDetector("left", 0.15)])
    s.feed(0.3, 0.5, 0.1)
    assert s.reason().startswith("défi non réalisé")


def test_feed_reports_challenge_completion():
    s = make([BlinkDetector(0.21)])
    assert not s.feed(0.3, 0.5)
    assert not s.feed(0.1, 0.5)
    assert s.feed(0.3, 0.5)


def test_strict_mode_has_three_challenges_in_random_order():
    orders = set()
    for seed in range(30):
        ch = build_challenges("strict", 0.21, 0.15, rng=random.Random(seed))
        assert len(ch) == 3
        orders.add(tuple(getattr(c, "side", "blink") for c in ch))
    assert len(orders) > 1  # l'ordre varie
    assert all(set(o) == {"blink", "left", "right"} for o in orders)


def test_recognised_too_late_gives_actionable_message():
    s = make([BlinkDetector(0.21)])
    s.feed(0.3, 0.5, 0.18)  # reconnu, mais avant les défis : ne compte pas
    s.feed(0.1, 0.5)
    s.feed(0.3, 0.5)  # défi validé, plus de temps
    assert not s.succeeded
    assert "reconnu" in s.reason() and "timeout" in s.reason()


def test_refused_face_never_counts_as_a_match():
    s = make([])
    for _ in range(5):
        s.feed(0.3, 0.5, 0.1, refused=True)
    assert s.matches == 0 and not s.succeeded
    assert "interdit" in s.reason()
