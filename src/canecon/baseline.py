"""A small scikit-learn baseline: can the first release tell us which way GDP growth will be revised?

Target: is the month's growth revised up between its first release and today
(`growth_revision_pp > 0` in `mart_growth_revisions`)?

Features, all known at the month's first release:
- `first_growth_pct`: the first-release month-over-month growth;
- `prev_early_revision_pp`: how much the previous month's growth had already moved between its
  own first release and this month's first release (`mart_growth_revision_path`).

Evaluation is walk-forward. To predict month M, the model is trained only on months whose
first release is at least `embargo_months` before M's first release, because a month's revision
is not known until later releases are out. Labels are today's revisions, so a training label is
"settled" only approximately; months whose first release is less than `embargo_months` before
the latest release in the data are not scored at all.

This is a baseline to compare against simple rules, not a forecasting tool: about a hundred
months, two features, and 2020 in the sample.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

FEATURES = ("first_growth_pct", "prev_early_revision_pp")

ROWS_SQL = """
with g as (
    select * from main.mart_growth_revisions
    where series_id = $series_id and growth_revision_pp is not null
)
select g.ref_period, g.first_published_at, g.first_growth_pct,
       coalesce(p.change_since_first_pp, 0) as prev_early_revision_pp,
       g.growth_revision_pp
from g
left join main.mart_growth_revision_path p
  on p.series_id = g.series_id
 and p.ref_period = g.ref_period - interval 1 month
 and p.released_at = g.first_published_at
order by g.first_published_at
"""


@dataclass(frozen=True)
class Row:
    ref_period: str
    first_published_at: datetime
    first_growth_pct: float
    prev_early_revision_pp: float
    revision_pp: float

    @property
    def up(self) -> int:
        return int(self.revision_pp > 0)


def load_rows(con: duckdb.DuckDBPyConnection, series_id: str = "gdp_all_industries") -> list[Row]:
    return [
        Row(str(r[0]), r[1], float(r[2]), float(r[3]), float(r[4]))
        for r in con.execute(ROWS_SQL, {"series_id": series_id}).fetchall()
    ]


def _months_before(a: datetime, b: datetime) -> int:
    """Whole calendar months from a to b."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def walk_forward(rows: list[Row], embargo_months: int = 36, min_train: int = 24) -> list[dict]:
    """One prediction per scorable month, each from a model fit only on earlier settled months."""
    from sklearn.linear_model import LogisticRegression

    latest = max(r.first_published_at for r in rows)
    out = []
    for target in rows:
        if _months_before(target.first_published_at, latest) < embargo_months:
            continue  # its own revision is not settled yet
        train = [r for r in rows if _months_before(r.first_published_at, target.first_published_at) >= embargo_months]
        if len(train) < min_train:
            continue
        y = [r.up for r in train]
        majority = int(sum(y) * 2 >= len(y))
        if len(set(y)) < 2:
            model_pred = y[0]
        else:
            model = LogisticRegression()
            model.fit([[getattr(r, f) for f in FEATURES] for r in train], y)
            model_pred = int(model.predict([[getattr(target, f) for f in FEATURES]])[0])
        out.append({
            "ref_period": target.ref_period,
            "n_train": len(train),
            "last_train_period": max(r.ref_period for r in train),
            "actual": target.up,
            "model": model_pred,
            "majority": majority,
            "always_up": 1,
        })
    return out


def score(preds: list[dict]) -> dict:
    n = len(preds)
    if not n:
        return {"n": 0}
    result = {"n": n, "share_up": round(sum(p["actual"] for p in preds) / n, 3)}
    for name in ("model", "majority", "always_up"):
        result[f"accuracy_{name}"] = round(sum(p[name] == p["actual"] for p in preds) / n, 3)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward baseline for the direction of GDP growth revisions.")
    parser.add_argument("--db", type=Path, default=Path("data/local/warehouse.duckdb"))
    parser.add_argument("--embargo-months", type=int, default=36)
    parser.add_argument("--out", type=Path, help="write per-month predictions here (JSON)")
    args = parser.parse_args(argv)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        rows = load_rows(con)
    finally:
        con.close()
    preds = walk_forward(rows, args.embargo_months)
    summary = score(preds)
    if preds:
        summary |= {"first_scored": preds[0]["ref_period"], "last_scored": preds[-1]["ref_period"]}
    print(json.dumps({"months_with_revision": len(rows), "embargo_months": args.embargo_months} | summary, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(preds, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
