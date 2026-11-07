"""Monthly brief: facts, number check, retry and template fallback.

The warehouse here is a few hand-written vintage rows, and every expected number was worked
out by hand:

| series       | period     | value | published (UTC)        | note                       |
|--------------|------------|-------|------------------------|----------------------------|
| GDP          | 2025-08    | 100   | 2025-10-31             |                            |
| GDP          | 2026-07    | 200   | 2026-09-30             |                            |
| GDP          | 2026-08    | 202   | 2026-09-30, replaced   | first release              |
| GDP          | 2026-08    | 201   | 2026-10-31             | revision                   |
| retail       | 2026-07/08 | 400 / 401.2            | 2026-10-24       |                            |
| unemployment | 2026-07/08 | 6.5 / 6.7              | 2026-09-05       |                            |
| CPI          | 2025-08, 2026-07/08 | 160 / 164 / 164.4 | 2026-09-16  |                            |
| policy rate  | 07-31, 08-15, 08-29 | 2.75 / 2.75 / 2.50 | same day   | daily                      |

As of 2026-11-01: GDP m/m = 201/200 - 1 = 0.5%; retail = 401.2/400 - 1 = 0.3%;
unemployment 6.7, +0.2 pp; CPI y/y = 164.4/160 - 1 = 2.75% -> 2.8 (half to even),
m/m = 164.4/164 - 1 = 0.2439% -> 0.2; policy rate month end 2.50, change -0.25 pp.
As of 2026-10-15 the GDP revision is not out yet: m/m = 202/200 - 1 = 1.0%.
No bond yields are loaded, so they have no facts.
"""

from __future__ import annotations

import duckdb
import pytest

from canecon.brief import _round, month_facts, template_brief, verify, write_brief, MARKER, BARE_NUMBER

AFTER = "2026-11-01 00:00:00"
BEFORE_REVISION = "2026-10-15 00:00:00"

ROWS = [
    ("gdp_all_industries", "2025-08-01", 100, 1, "2025-10-31 12:30:00", None),
    ("gdp_all_industries", "2026-07-01", 200, 1, "2026-09-30 12:30:00", None),
    ("gdp_all_industries", "2026-08-01", 202, 1, "2026-09-30 12:30:00", "2026-10-31 12:30:00"),
    ("gdp_all_industries", "2026-08-01", 201, 2, "2026-10-31 12:30:00", None),
    ("retail_sales_total_sa", "2026-07-01", 400, 1, "2026-10-24 12:30:00", None),
    ("retail_sales_total_sa", "2026-08-01", 401.2, 1, "2026-10-24 12:30:00", None),
    ("unemployment_rate_sa", "2026-07-01", 6.5, 1, "2026-09-05 12:30:00", None),
    ("unemployment_rate_sa", "2026-08-01", 6.7, 1, "2026-09-05 12:30:00", None),
    ("cpi_all_items", "2025-08-01", 160, 1, "2026-09-16 12:30:00", None),
    ("cpi_all_items", "2026-07-01", 164, 1, "2026-09-16 12:30:00", None),
    ("cpi_all_items", "2026-08-01", 164.4, 1, "2026-09-16 12:30:00", None),
    ("policy_rate_target", "2026-07-31", 2.75, 1, "2026-07-31 20:00:00", None),
    ("policy_rate_target", "2026-08-15", 2.75, 1, "2026-08-15 20:00:00", None),
    ("policy_rate_target", "2026-08-29", 2.50, 1, "2026-08-29 20:00:00", None),
]

GOOD = (
    "In August 2026 real GDP grew [[gdp_all_industries|2026-08|mom_pct|0.5]]% and retail sales rose "
    "[[retail_sales_total_sa|2026-08|mom_pct|0.3]]%. Unemployment reached "
    "[[unemployment_rate_sa|2026-08|level|6.7]]%, up [[unemployment_rate_sa|2026-08|mom_pp|0.2]] points. "
    "Prices were [[cpi_all_items|2026-08|yoy_pct|2.8]]% higher than a year earlier, and the policy rate "
    "ended the month at [[policy_rate_target|2026-08|month_end|2.50]]%."
)


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute(
        "create table main.vintages (series_id varchar, ref_period date, value decimal(38,10), "
        "vintage_number integer, valid_from timestamp, valid_to timestamp, source_snapshot_sha256 varchar)"
    )
    c.executemany("insert into main.vintages values (?, ?, ?, ?, ?, ?, 'sha')", ROWS)
    c.execute("create table main.series_info as select * from (values "
              "('gdp_all_industries', 'Real GDP'), ('retail_sales_total_sa', 'Retail sales'), "
              "('unemployment_rate_sa', 'Unemployment rate'), ('cpi_all_items', 'CPI'), "
              "('policy_rate_target', 'Policy rate')) t(series_id, label)")
    yield c
    c.close()


def shown(facts):
    return {f.key: f.shown for f in facts}


def test_facts_match_hand_computed_values(con):
    assert shown(month_facts(con, "2026-08", AFTER)) == {
        ("gdp_all_industries", "2026-08", "mom_pct"): "0.5",
        ("retail_sales_total_sa", "2026-08", "mom_pct"): "0.3",
        ("unemployment_rate_sa", "2026-08", "level"): "6.7",
        ("unemployment_rate_sa", "2026-08", "mom_pp"): "0.2",
        ("cpi_all_items", "2026-08", "yoy_pct"): "2.8",
        ("cpi_all_items", "2026-08", "mom_pct"): "0.2",
        ("policy_rate_target", "2026-08", "month_end"): "2.50",
        ("policy_rate_target", "2026-08", "month_change_pp"): "-0.25",
    }


def test_facts_use_only_what_was_published_by_then(con):
    facts = shown(month_facts(con, "2026-08", BEFORE_REVISION))
    assert facts[("gdp_all_industries", "2026-08", "mom_pct")] == "1.0"
    # Retail for July and August was published on 2026-10-24, after 10-15.
    assert ("retail_sales_total_sa", "2026-08", "mom_pct") not in facts


def test_correct_brief_passes(con):
    check = verify(GOOD, month_facts(con, "2026-08", AFTER))
    assert check.ok, check.problems
    assert check.checked == 6


@pytest.mark.parametrize(
    "bad, why",
    [
        # A number that exists in the data, but for another series: a set-membership check passes it.
        (GOOD.replace("retail_sales_total_sa|2026-08|mom_pct|0.3", "retail_sales_total_sa|2026-08|mom_pct|0.5"), "expected 0.3"),
        # The right series and value, but another month.
        (GOOD.replace("gdp_all_industries|2026-08", "gdp_all_industries|2026-07"), "no such fact"),
        # Same value written with other decimals.
        (GOOD.replace("month_end|2.50", "month_end|2.5"), "expected 2.50"),
        # A number with no marker.
        (GOOD + " Exports rose 4.1%.", "outside a citation marker: '4.1%'"),
        (GOOD + " That is 3 months in a row.", "outside a citation marker: '3'"),
        ("Nothing much happened in August 2026.", "no numbers cited"),
        (GOOD.replace("]]% and", "] and", 1), "malformed"),
    ],
)
def test_wrong_numbers_fail(con, bad, why):
    check = verify(bad, month_facts(con, "2026-08", AFTER))
    assert not check.ok
    assert any(why in p for p in check.problems), check.problems


class Scripted:
    name = "scripted"

    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        draft = self.drafts.pop(0)
        if isinstance(draft, Exception):
            raise draft
        return draft


def test_retry_with_problems_then_publish(con):
    gen = Scripted(GOOD + " Exports rose 4.1%.", GOOD)
    result = write_brief(con, "2026-08", AFTER, gen)
    assert result.status == "llm_verified"
    assert len(result.attempts) == 2
    assert "4.1%" in gen.prompts[1]  # the retry is told what was wrong
    assert "[[" not in result.text and "grew 0.5% and" in result.text


def test_two_failures_fall_back_to_template(con):
    bad = GOOD.replace("|0.3]]", "|0.5]]")
    result = write_brief(con, "2026-08", AFTER, Scripted(bad, bad))
    assert result.status == "template_fallback"
    assert len(result.attempts) == 2
    assert "0.5]]" not in result.text and result.text == template_brief("2026-08", month_facts(con, "2026-08", AFTER))


def test_generator_error_falls_back_to_template(con):
    result = write_brief(con, "2026-08", AFTER, Scripted(RuntimeError("API down")))
    assert result.status == "template_fallback"
    assert "API down" in result.attempts[0]["error"]


def test_template_numbers_all_come_from_facts(con):
    facts = month_facts(con, "2026-08", AFTER)
    text = template_brief("2026-08", facts)
    numbers = [n.rstrip("%") for n in BARE_NUMBER.findall(text)]
    assert sorted(numbers) == sorted(f.shown for f in facts)
    assert not MARKER.search(text)


def test_no_facts_means_no_brief(con):
    result = write_brief(con, "2020-01", AFTER, Scripted(GOOD))
    assert result.status == "no_facts" and result.attempts == []


def test_small_negative_rounds_to_plain_zero():
    from decimal import Decimal

    assert f"{_round(Decimal('-0.04'), 1):.1f}" == "0.0"
