import dataclasses

from faceauth.audit import KO, OK, WARN, security_findings
from faceauth.config import Config


def levels(cfg, sudo=True, blocked=True):
    return [lvl for lvl, _ in security_findings(cfg, sudo, blocked)]


def test_default_config_is_consistent():
    assert levels(Config(), sudo=False, blocked=False) == [OK]


def test_no_challenge_with_sudo_is_ko_and_without_is_warning():
    cfg = dataclasses.replace(Config(), challenge="none")
    assert KO in levels(cfg, sudo=True)
    assert KO not in levels(cfg, sudo=False)


def test_loose_tolerance_and_single_match_are_ko():
    cfg = dataclasses.replace(Config(), tolerance=0.5, min_matches=1)
    assert levels(cfg).count(KO) == 2


def test_borderline_tolerance_is_a_warning():
    cfg = dataclasses.replace(Config(), tolerance=0.43)
    assert WARN in levels(cfg, sudo=False)


def test_sudo_without_blocked_faces_gets_a_hint():
    assert WARN in levels(Config(), sudo=True, blocked=False)
    assert levels(Config(), sudo=True, blocked=True) == [OK]
