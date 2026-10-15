"""Cross-validated Peer Assessment Factor (PAF) mechanism.

Implementation of the mechanism developed in

    John Headley (2026), "Under What Conditions Does a Cross-Validated Peer
    Assessment Mechanism Induce Truthful Reporting and Eliminate Free-Riding
    in Student Group Work?", EC3009 BSc Economics Project,
    City, University of London.

Notation (Section 3 of the paper). A group of ``n`` students receives a common
group grade ``G``. Every student ``i`` rates every peer ``j != i`` on a 1-5
scale, giving an ``n x n`` rating matrix ``r`` whose diagonal is undefined
(``NaN``). Rows are raters, columns are the students being rated.

Standard PAF (Section 3.3, eq. 8)::

    R_j   = mean_{i != j} r_ij            average rating received by j
    R_bar = mean_j R_j                    group-average rating
    PAF_j = R_j / R_bar
    G_j   = G * PAF_j

Cross-validated PAF (Section 3.4, eqs. 11-15)::

    C_ij  = mean_{k != i, j} r_kj          consensus about j, excluding rater i
    d_ij  = r_ij - C_ij                     deviation of i's report from consensus
    w_ij  = max(0, 1 - alpha * |d_ij|)      credibility weight, alpha >= 0
    R_j^w = sum_{i != j} w_ij r_ij / sum_{i != j} w_ij
    PAF_j^w = R_j^w / mean_j R_j^w
    G_j   = G * PAF_j^w

With ``alpha = 0`` every weight equals one and the cross-validated PAF reduces
to the standard PAF. If every weight for a student is zero the plain mean of
the ratings received is used instead (the fallback in Appendix II). Both
mechanisms are budget balanced by construction: ``sum_j G_j = n * G``
(Proposition 3).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "STUDENTS",
    "TRUE_EFFORTS",
    "EXAMPLE_G",
    "EXAMPLE_HONEST",
    "EXAMPLE_COLLUSION",
    "consensus",
    "deviations",
    "credibility_weights",
    "average_ratings",
    "weighted_ratings",
    "standard_paf",
    "cross_validated_paf",
    "standard_grades",
    "cross_validated_grades",
    "is_budget_balanced",
    "alpha_star",
]

# --------------------------------------------------------------------------
# Worked example of Section 4.2 / Appendix I of the paper
# --------------------------------------------------------------------------

#: Students of the numerical example (Section 4.2).
STUDENTS = ("Alice", "Bob", "Chloé", "David")

#: True contributions theta_j. David is the free rider.
TRUE_EFFORTS = (4, 3, 4, 2)

#: Common group grade G (out of 100) used in the example.
EXAMPLE_G = 72.0

_nan = np.nan

#: Table 2 - every rater reports the true effort of each peer.
EXAMPLE_HONEST = np.array(
    [
        [_nan, 3.0, 4.0, 2.0],
        [4.0, _nan, 4.0, 2.0],
        [4.0, 3.0, _nan, 2.0],
        [4.0, 3.0, 4.0, _nan],
    ]
)

#: Table 3 - Alice inflates her rating of Bob from 3 to 5 (delta_AB = +2) and
#: Bob inflates his rating of Alice from 4 to 5 (delta_BA = +1).
EXAMPLE_COLLUSION = EXAMPLE_HONEST.copy()
EXAMPLE_COLLUSION[0, 1] = 5.0  # Alice -> Bob
EXAMPLE_COLLUSION[1, 0] = 5.0  # Bob -> Alice


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _as_rating_matrix(ratings) -> np.ndarray:
    """Validate and return ``ratings`` as a float ``n x n`` array with NaN diagonal."""
    r = np.array(ratings, dtype=float)
    if r.ndim != 2 or r.shape[0] != r.shape[1]:
        raise ValueError("ratings must be a square n x n matrix")
    n = r.shape[0]
    if n < 3:
        # The consensus C_ij averages over n - 2 raters; it needs n >= 3.
        raise ValueError("the mechanism needs at least three students")
    r = r.copy()
    np.fill_diagonal(r, np.nan)  # self-ratings are never used
    off_diag = ~np.eye(n, dtype=bool)
    if np.isnan(r[off_diag]).any():
        raise ValueError("every off-diagonal rating must be provided")
    return r


# --------------------------------------------------------------------------
# Standard PAF (Section 3.3)
# --------------------------------------------------------------------------


def average_ratings(ratings) -> np.ndarray:
    """Average rating received by each student, ``R_j = mean_{i != j} r_ij``."""
    r = _as_rating_matrix(ratings)
    return np.nanmean(r, axis=0)


def standard_paf(ratings) -> np.ndarray:
    """Standard peer assessment factor, ``PAF_j = R_j / R_bar`` (eq. 8)."""
    R = average_ratings(ratings)
    return R / R.mean()


def standard_grades(ratings, G: float) -> np.ndarray:
    """Individual grades under the standard PAF, ``G_j = G * PAF_j``."""
    return G * standard_paf(ratings)


# --------------------------------------------------------------------------
# Cross-validated PAF (Section 3.4)
# --------------------------------------------------------------------------


def consensus(ratings) -> np.ndarray:
    """Consensus estimates ``C_ij`` (eq. 11).

    ``C_ij`` is the mean rating of student ``j`` by every student other than
    ``i`` and ``j`` itself. Returned as an ``n x n`` array with NaN diagonal.
    """
    r = _as_rating_matrix(ratings)
    n = r.shape[0]
    C = np.full((n, n), np.nan)
    for j in range(n):
        for i in range(n):
            if i == j:
                continue
            others = [k for k in range(n) if k != i and k != j]
            C[i, j] = np.mean(r[others, j])
    return C


def deviations(ratings) -> np.ndarray:
    """Deviations from consensus ``d_ij = r_ij - C_ij`` (eq. 12)."""
    r = _as_rating_matrix(ratings)
    return r - consensus(r)


def credibility_weights(ratings, alpha: float) -> np.ndarray:
    """Credibility weights ``w_ij = max(0, 1 - alpha * |d_ij|)`` (eq. 13)."""
    if alpha < 0:
        raise ValueError("alpha must be non-negative")
    d = deviations(ratings)
    w = np.maximum(0.0, 1.0 - alpha * np.abs(d))
    np.fill_diagonal(w, np.nan)
    return w


def weighted_ratings(ratings, alpha: float) -> np.ndarray:
    """Cross-validated weighted ratings ``R_j^w`` (eq. 14).

    If all credibility weights for a student are zero, the plain mean of the
    ratings that student received is used instead (Appendix II).
    """
    r = _as_rating_matrix(ratings)
    w = credibility_weights(r, alpha)
    n = r.shape[0]
    R_w = np.zeros(n)
    for j in range(n):
        raters = [i for i in range(n) if i != j]
        weight_sum = np.sum(w[raters, j])
        if weight_sum > 0:
            R_w[j] = np.sum(w[raters, j] * r[raters, j]) / weight_sum
        else:
            R_w[j] = np.mean(r[raters, j])
    return R_w


def cross_validated_paf(ratings, alpha: float) -> np.ndarray:
    """Cross-validated PAF, ``PAF_j^w = R_j^w / mean_j R_j^w`` (eq. 15)."""
    R_w = weighted_ratings(ratings, alpha)
    return R_w / R_w.mean()


def cross_validated_grades(ratings, G: float, alpha: float) -> np.ndarray:
    """Individual grades under the cross-validated PAF, ``G_j = G * PAF_j^w``.

    This is the ``cross_validation_grades`` function of Appendix II of the
    paper. With ``alpha = 0`` it coincides with :func:`standard_grades`.
    """
    return G * cross_validated_paf(ratings, alpha)


# --------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------


def is_budget_balanced(grades, G: float, tol: float = 1e-9) -> bool:
    """Check Proposition 3: the grades sum to ``n * G``."""
    g = np.asarray(grades, dtype=float)
    return bool(abs(g.sum() - g.size * G) <= tol)


def alpha_star(delta: float) -> float:
    """Threshold ``alpha* = 1 / |delta|`` (eq. 20, Section 4.1).

    For a single rater inflating a report by ``delta`` while everyone else is
    honest, the dishonest report receives zero weight for every
    ``alpha >= alpha*``.
    """
    if delta == 0:
        raise ValueError("delta must be non-zero")
    return 1.0 / abs(delta)
