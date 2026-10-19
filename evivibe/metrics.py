"""Agreement / stability metrics for validating automatic evaluation.

Pure-Python implementations (no NumPy / SciPy dependency) of the statistics
required by the experimental protocol:

* Spearman rho, Kendall tau-b      -- ranking agreement with experts
* ICC(2,1)                         -- absolute-agreement consistency
* MAE, RMSE                        -- calibration error
* run-to-run variance              -- evaluation stability
* severe-defect recall / false discovery rate -- safety of the verdicts

These back RQ1-RQ3 / H1-H3: comparing automatic scores against expert labels
and single-LLM baselines against the multi-reviewer ensemble.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _clean(xs: Sequence[float], ys: Sequence[float]) -> Tuple[List[float], List[float]]:
    if len(xs) != len(ys):
        raise ValueError("input sequences must have equal length")
    if len(xs) < 2:
        raise ValueError("need at least two paired observations")
    return [float(x) for x in xs], [float(y) for y in ys]


def _ranks(xs: List[float]) -> List[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _var(xs: Sequence[float]) -> float:
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    x, y = _clean(xs, ys)
    vx, vy = _var(x), _var(y)
    if vx == 0 or vy == 0:
        return 0.0
    m_x, m_y = _mean(x), _mean(y)
    cov = sum((a - m_x) * (b - m_y) for a, b in zip(x, y)) / len(x)
    return cov / math.sqrt(vx * vy)


# --------------------------------------------------------------------------
# rank correlation
# --------------------------------------------------------------------------

def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman's rho (ties handled via average ranks)."""
    x, y = _clean(xs, ys)
    return pearson(_ranks(x), _ranks(y))


def kendall_tau(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Kendall's tau-b with tie correction."""
    x, y = _clean(xs, ys)
    n = len(x)
    concordant = discordant = 0
    ties_x = ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = (x[i] > x[j]) - (x[i] < x[j])
            dy = (y[i] > y[j]) - (y[i] < y[j])
            prod = dx * dy
            if prod > 0:
                concordant += 1
            elif prod < 0:
                discordant += 1
            if dx == 0 and dy != 0:
                ties_x += 1
            if dy == 0 and dx != 0:
                ties_y += 1
    denom = math.sqrt((concordant + discordant + ties_x)
                      * (concordant + discordant + ties_y))
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------

def mae(xs: Sequence[float], ys: Sequence[float]) -> float:
    x, y = _clean(xs, ys)
    return sum(abs(a - b) for a, b in zip(x, y)) / len(x)


def rmse(xs: Sequence[float], ys: Sequence[float]) -> float:
    x, y = _clean(xs, ys)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(x, y)) / len(x))


# --------------------------------------------------------------------------
# intra-class correlation ICC(2,1): two-way random, single rater, absolute
# --------------------------------------------------------------------------

def icc_2_1(ratings: Sequence[Sequence[float]]) -> float:
    """ICC(2,1) over a (subjects x raters) matrix.

    ``ratings[i][j]`` is rater j's score for subject i.  Requires >= 2 subjects
    and >= 2 raters.  Used both for expert-vs-expert reliability (human
    baseline) and auto-vs-expert absolute agreement.
    """
    n = len(ratings)                 # subjects
    k = len(ratings[0])              # raters
    if n < 2 or k < 2:
        raise ValueError("ICC(2,1) needs >= 2 subjects and >= 2 raters")
    if any(len(row) != k for row in ratings):
        raise ValueError("ragged rating matrix")

    grand = _mean([v for row in ratings for v in row])
    ss_total = sum((v - grand) ** 2 for row in ratings for v in row)

    row_means = [_mean(row) for row in ratings]
    col_means = [_mean([ratings[i][j] for i in range(n)]) for j in range(k)]
    ss_rows = k * sum((m - grand) ** 2 for m in row_means)
    ss_cols = n * sum((m - grand) ** 2 for m in col_means)
    ss_error = ss_total - ss_rows - ss_cols
    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    denom = (ms_rows + (k - 1) * ms_error
             + k * (ms_cols - ms_error) / n)
    if denom == 0:
        return 1.0 if ms_rows == 0 else 0.0
    return (ms_rows - ms_error) / denom


# --------------------------------------------------------------------------
# stability & defect-level statistics
# --------------------------------------------------------------------------

def run_variance(runs: Sequence[float]) -> float:
    """Variance of repeated evaluations of the same work (H3)."""
    if len(runs) < 2:
        return 0.0
    return _var([float(r) for r in runs])


def defect_recall(truth: Sequence[str], predicted: Sequence[str]) -> float:
    """Recall of severe defects: |truth ∩ predicted| / |truth|."""
    t, p = set(truth), set(predicted)
    if not t:
        return 1.0
    return len(t & p) / len(t)


def false_discovery_rate(truth: Sequence[str], predicted: Sequence[str]) -> float:
    """FDR: fraction of predicted severe defects not in the ground truth."""
    t, p = set(truth), set(predicted)
    if not p:
        return 0.0
    return len(p - t) / len(p)


def agreement_summary(
    auto_scores: Sequence[float],
    expert_scores: Sequence[float],
) -> Dict[str, float]:
    """Standard agreement block reported for every evaluation experiment."""
    return {
        "n": len(auto_scores),
        "spearman": round(spearman(auto_scores, expert_scores), 4),
        "kendall_tau": round(kendall_tau(auto_scores, expert_scores), 4),
        "pearson": round(pearson(auto_scores, expert_scores), 4),
        "mae": round(mae(auto_scores, expert_scores), 4),
        "rmse": round(rmse(auto_scores, expert_scores), 4),
    }
