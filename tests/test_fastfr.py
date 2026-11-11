"""Accès direct à dlib : parties pures (sans modèles)."""
import numpy as np

from faceauth import fastfr


def test_face_distance_matches_euclidean():
    known = [np.zeros(128), np.ones(128)]
    d = fastfr.face_distance(known, np.zeros(128))
    assert d[0] == 0 and np.isclose(d[1], np.sqrt(128))


def test_face_distance_without_known_faces():
    assert len(fastfr.face_distance([], np.zeros(128))) == 0


def test_identity_distance_is_mean_of_closest_three():
    from faceauth.core import identity_distance

    # un seul échantillon très proche (0.10) ne suffit plus : 0.10, 0.50, 0.50 -> 0.37
    assert abs(identity_distance([0.9, 0.5, 0.10, 0.5, 0.8]) - (0.10 + 0.5 + 0.5) / 3) < 1e-9
    assert identity_distance([0.2]) == 0.2  # moins de 3 échantillons : moyenne de ce qu'il y a


def test_empty_samples_give_infinite_distance():
    from faceauth.core import identity_distance

    assert identity_distance([]) == float("inf")


def test_is_refused_when_closer_to_a_blocked_face():
    from faceauth.core import is_refused

    assert is_refused(0.38, 0.15, 0.05)        # une sœur : plus proche du visage interdit
    assert not is_refused(0.20, 0.45, 0.05)    # toi : nettement plus proche de toi
    assert is_refused(0.30, 0.33, 0.05)        # trop près pour trancher : refus par prudence


def test_blocked_face_that_is_actually_the_owner_is_ignored():
    from faceauth.core import usable_blocked

    owner = np.zeros((3, 128))
    same_as_owner = np.zeros((2, 128))         # distance 0 : c'est toi
    sister = np.full((2, 128), 0.1)            # distance ~1.13 : une autre personne
    assert usable_blocked(owner, same_as_owner) is None
    assert len(usable_blocked(owner, np.vstack([same_as_owner, sister]))) == 2
    assert usable_blocked(owner, None) is None
