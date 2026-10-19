import math

from evivibe.metrics import (agreement_summary, false_discovery_rate,
                               icc_2_1, kendall_tau, mae, pearson, rmse,
                               run_variance, spearman, defect_recall)


def test_spearman_perfect():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_spearman_known_value():
    # classic Galton-ish example: rho ~ 0.6786 for these ranks? use a
    # hand-checkable case instead
    x = [1, 2, 2, 4]
    y = [1, 3, 3, 4]
    # ranks x = [1, 2.5, 2.5, 4], y = [1, 2.5, 2.5, 4] -> rho = 1
    assert abs(spearman(x, y) - 1.0) < 1e-9


def test_spearman_orthogonal():
    assert abs(spearman([1, 2, 3, 4, 5], [3, 1, 4, 2, 5])
               - pearson([1, 2, 3, 4, 5], [3, 1, 4, 2, 5])) < 1e-9


def test_kendall_tau_basic():
    assert kendall_tau([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    # 8 concordant, 2 discordant pairs -> (8-2)/10 = 0.6
    assert abs(kendall_tau([1, 2, 3, 4, 5], [1, 3, 2, 5, 4]) - 0.6) < 1e-9


def test_kendall_tau_ties():
    tau = kendall_tau([1, 1, 2], [1, 2, 2])
    assert -1.0 <= tau <= 1.0


def test_mae_rmse():
    assert mae([1, 2, 3], [1, 2, 5]) == 2 / 3
    assert rmse([0, 0], [3, 4]) == math.sqrt((9 + 16) / 2)


def test_icc_perfect_agreement():
    ratings = [[80, 80, 80], [60, 60, 60], [90, 90, 90]]
    assert icc_2_1(ratings) > 0.99


def test_icc_disagreement():
    ratings = [[80, 60, 90], [60, 90, 80], [90, 80, 60]]
    assert icc_2_1(ratings) < 0.5


def test_run_variance():
    assert run_variance([5.0, 5.0, 5.0]) == 0.0
    assert run_variance([1.0, 3.0]) == 1.0
    assert run_variance([2.0]) == 0.0


def test_defect_stats():
    truth = ["a", "b", "c"]
    pred = ["a", "b", "x"]
    assert defect_recall(truth, pred) == 2 / 3
    assert false_discovery_rate(truth, pred) == 1 / 3
    assert defect_recall([], []) == 1.0


def test_agreement_summary_shape():
    s = agreement_summary([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
    assert set(s) == {"n", "spearman", "kendall_tau", "pearson", "mae", "rmse"}
    assert s["n"] == 5
    assert math.isfinite(s["spearman"])
