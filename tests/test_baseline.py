"""Walk-forward baseline: no training month may be one whose revision was not out yet."""

from __future__ import annotations

from datetime import datetime

from canecon.baseline import Row, score, walk_forward


def rows(n: int, rule) -> list[Row]:
    """n months released on the 1st of consecutive months from 2015-01; label from rule(i)."""
    out = []
    for i in range(n):
        y, m = divmod(i, 12)
        growth = -0.2 if i % 2 else 0.3
        out.append(Row(f"{2015 + y}-{m + 1:02d}", datetime(2015 + y, m + 1, 1), growth, 0.0, rule(i, growth)))
    return out


def test_training_months_respect_the_embargo():
    data = rows(60, lambda i, g: 0.1 if g < 0 else -0.1)
    preds = walk_forward(data, embargo_months=12, min_train=6)
    # Months i = 0..59, released monthly. The latest is 59, so i <= 47 can be scored (59 - i >= 12).
    # Month i trains on j <= i - 12, that is i - 11 months; at least 6 needs i >= 17.
    # So the first scored month is 17 (2016-06), trained on months 0..5 (up to 2015-06).
    first = preds[0]
    assert first["ref_period"] == "2016-06" and first["n_train"] == 6 and first["last_train_period"] == "2015-06"
    assert preds[-1]["ref_period"] == "2018-12"  # month 47; months 48..59 are not settled
    for p in preds:
        y, m = map(int, p["ref_period"].split("-"))
        ly, lm = map(int, p["last_train_period"].split("-"))
        assert (y - ly) * 12 + (m - lm) >= 12


def test_model_learns_a_clear_rule_and_baselines_do_not():
    # Revised up exactly when first growth is negative: alternating months, so the majority
    # class and "always up" are right about half the time and the model should be right every time.
    # Scored months 17..47: 31 months, of which the 16 odd ones are revised up.
    preds = walk_forward(rows(60, lambda i, g: 0.1 if g < 0 else -0.1), embargo_months=12, min_train=6)
    s = score(preds)
    assert s["n"] == 31
    assert s["accuracy_model"] == 1.0
    assert s["accuracy_always_up"] == round(16 / 31, 3)
