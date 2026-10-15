"""Reproduce the numerical example of the paper (Table 4 / Appendix I).

Scenario: n = 4, G = 72, students Alice, Bob, Chloé and David with true
efforts (4, 3, 4, 2). Alice inflates her rating of Bob by +2 and Bob inflates
his rating of Alice by +1.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paf_mechanism as paf  # noqa: E402

G = paf.EXAMPLE_G
HONEST = paf.EXAMPLE_HONEST
COLLUSION = paf.EXAMPLE_COLLUSION
N = 4


def rounded(x):
    return list(np.round(x, 1))


# --- Table 4 -----------------------------------------------------------------


def test_standard_paf_honest_ratings():
    # Appendix I, Scenario 1
    assert rounded(paf.standard_grades(HONEST, G)) == [88.6, 66.5, 88.6, 44.3]


def test_standard_paf_with_collusion():
    # Appendix I, Scenario 2: R = (4.33, 3.67, 4.00, 2.00), R_bar = 3.50.
    # The paper's table prints 77.5 for Bob; 72 * 3.67 / 3.50 = 75.4 and the
    # column then sums to 288 as the paper's own budget check requires
    # (with 77.5 it would sum to 290).
    assert rounded(paf.standard_grades(COLLUSION, G)) == [89.1, 75.4, 82.3, 41.1]


def test_cross_validated_alpha_0_5():
    # Appendix I, Scenario 3a
    assert rounded(paf.cross_validated_grades(COLLUSION, G, 0.5)) == [92.4, 65.2, 86.9, 43.5]


def test_cross_validated_alpha_0_99():
    # Appendix I, Scenario 3b: R_bar^w = 3.25245, so Chloé = 72 * 4 / 3.25245
    # = 88.55, which rounds to 88.5 (the paper's table prints 88.6).
    assert rounded(paf.cross_validated_grades(COLLUSION, G, 0.99)) == [88.8, 66.4, 88.5, 44.3]


@pytest.mark.parametrize(
    "grades",
    [
        paf.standard_grades(HONEST, G),
        paf.standard_grades(COLLUSION, G),
        paf.cross_validated_grades(COLLUSION, G, 0.5),
        paf.cross_validated_grades(COLLUSION, G, 0.99),
    ],
)
def test_budget_balance(grades):
    # Proposition 3: every column of Table 4 sums to 4 * 72 = 288.
    assert paf.is_budget_balanced(grades, G)
    assert round(float(np.sum(grades)), 6) == 288.0


# --- Intermediate quantities of Appendix I -------------------------------------


def test_average_ratings_with_collusion():
    assert rounded(paf.average_ratings(COLLUSION)) == [4.3, 3.7, 4.0, 2.0]
    assert np.isclose(paf.average_ratings(COLLUSION).mean(), 3.5)


def test_credibility_weights_alpha_0_5():
    # Scenario 3a: w_BA = 0.5, w_CA = w_DA = 0.75, w_AB = 0, w_CB = w_DB = 0.5,
    # all weights on Chloé and David equal to 1.
    w = paf.credibility_weights(COLLUSION, 0.5)
    A, B, C, D = range(4)
    assert w[B, A] == 0.5
    assert w[C, A] == 0.75 and w[D, A] == 0.75
    assert w[A, B] == 0.0
    assert w[C, B] == 0.5 and w[D, B] == 0.5
    assert np.all(w[[A, B, D], C] == 1.0)
    assert np.all(w[[A, B, C], D] == 1.0)
    assert np.isnan(np.diag(w)).all()


def test_weighted_ratings_alpha_0_5():
    # R^w = (4.25, 3.00, 4.00, 2.00), R_bar^w = 3.3125
    R_w = paf.weighted_ratings(COLLUSION, 0.5)
    assert np.allclose(R_w, [4.25, 3.0, 4.0, 2.0])
    assert np.isclose(R_w.mean(), 3.3125)


def test_credibility_weights_alpha_0_99():
    w = paf.credibility_weights(COLLUSION, 0.99)
    A, B, C, D = range(4)
    assert np.isclose(w[B, A], 0.01)
    assert np.isclose(w[C, A], 0.505) and np.isclose(w[D, A], 0.505)
    assert w[A, B] == 0.0
    assert np.isclose(w[C, B], 0.01) and np.isclose(w[D, B], 0.01)


# --- Structural properties -----------------------------------------------------


def test_alpha_zero_reduces_to_standard_paf():
    assert np.allclose(paf.cross_validated_grades(COLLUSION, G, 0.0), paf.standard_grades(COLLUSION, G))
    assert np.all(paf.credibility_weights(COLLUSION, 0.0)[~np.eye(N, dtype=bool)] == 1.0)


def test_honest_ratings_are_never_discounted():
    # With honest reports every rating equals the consensus, so w_ij = 1 for any alpha.
    for alpha in (0.0, 0.5, 0.99, 5.0):
        w = paf.credibility_weights(HONEST, alpha)
        assert np.all(w[~np.eye(N, dtype=bool)] == 1.0)
        assert rounded(paf.cross_validated_grades(HONEST, G, alpha)) == [88.6, 66.5, 88.6, 44.3]


@pytest.mark.parametrize("delta", [1, 2, 3, 4])
def test_unilateral_deviation_is_neutralised_at_alpha_star(delta):
    # Section 4.1 / Table 1: a single rater inflating by delta gets weight zero
    # for alpha >= alpha* = 1 / |delta|, and a positive weight just below it.
    r = HONEST.copy()
    r[3, 1] = r[3, 1] + delta  # David inflates his rating of Bob (3 -> 3 + delta)
    a_star = paf.alpha_star(delta)
    assert a_star == pytest.approx({1: 1.0, 2: 0.5, 3: 1 / 3, 4: 0.25}[delta])
    assert paf.credibility_weights(r, a_star)[3, 1] == 0.0
    assert paf.credibility_weights(r, 0.9 * a_star)[3, 1] > 0.0
    # Once neutralised, grades coincide with the honest baseline.
    assert rounded(paf.cross_validated_grades(r, G, a_star)) == [88.6, 66.5, 88.6, 44.3]


def test_fallback_to_plain_mean_when_all_weights_are_zero():
    # Three raters disagree so strongly that every weight is zero at a large alpha.
    # Bob is rated 1, 4 and 5: each report is at least one unit away from the
    # consensus of the other two, so every w_iB is zero when alpha = 10.
    r = np.array(
        [
            [np.nan, 1.0, 4.0, 2.0],
            [4.0, np.nan, 4.0, 2.0],
            [4.0, 4.0, np.nan, 2.0],
            [4.0, 5.0, 4.0, np.nan],
        ]
    )
    w = paf.credibility_weights(r, 10.0)
    assert np.all(w[[0, 2, 3], 1] == 0.0)
    assert np.isclose(paf.weighted_ratings(r, 10.0)[1], np.mean([1.0, 4.0, 5.0]))


def test_invalid_inputs():
    with pytest.raises(ValueError):
        paf.credibility_weights(COLLUSION, -0.1)
    with pytest.raises(ValueError):
        paf.standard_grades(np.ones((2, 2)), G)
    with pytest.raises(ValueError):
        paf.alpha_star(0)
