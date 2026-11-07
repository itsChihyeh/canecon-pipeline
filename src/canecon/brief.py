"""Monthly economic brief: a language model writes the prose, the program checks every number.

Flow for one reference month M, as known at time T:

1. `month_facts` computes the numbers from point-in-time vintages (`canecon.pit.as_of`), so
   nothing published after T is used.
2. A generator (an LLM, or a scripted stand-in in tests) writes a short English brief. Every
   number must be written as a citation marker bound to one series, one period and one
   measure: `[[series_id|YYYY-MM|measure|value]]`.
3. `verify` checks each marker against the fact for that same series, period and measure,
   with the exact number of decimals the fact is stated with. Any number written outside a
   marker (other than a four-digit year) fails the brief. Checking only that a number appears
   somewhere in the data is not enough: 0.3 may be right for GDP in August and wrong for
   retail sales in July.
4. If the check fails, the generator gets one retry with the list of problems. If it fails
   again, nothing written by the model is published and a fixed template is used instead.

The pipeline and the dashboard never depend on this module.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Protocol

import duckdb

from canecon.pit import as_of

# Which measures each series gets, and how many decimals each is stated with.
# Monthly series are described for month M; daily series by their last value in M.
MEASURES: dict[str, list[tuple[str, int]]] = {
    "gdp_all_industries": [("mom_pct", 1)],
    "retail_sales_total_sa": [("mom_pct", 1)],
    "unemployment_rate_sa": [("level", 1), ("mom_pp", 1)],
    "cpi_all_items": [("yoy_pct", 1), ("mom_pct", 1)],
    "policy_rate_target": [("month_end", 2), ("month_change_pp", 2)],
    "gov_bond_yield_2y": [("month_end", 2), ("month_change_pp", 2)],
    "gov_bond_yield_10y": [("month_end", 2), ("month_change_pp", 2)],
}

MEASURE_TEXT = {
    "mom_pct": "change from the previous month, percent",
    "yoy_pct": "change from the same month a year earlier, percent",
    "level": "level, percent",
    "mom_pp": "change from the previous month, percentage points",
    "month_end": "last value of the month, percent",
    "month_change_pp": "change in the last value from the previous month, percentage points",
}

MARKER = re.compile(r"\[\[([a-z0-9_]+)\|(\d{4}-\d{2})\|([a-z_]+)\|(-?\d+(?:\.\d+)?)\]\]")
# After markers are removed, the only digits allowed are four-digit years.
# A year may end a sentence ("in May 2026."); "2026.5" is still a number.
BARE_NUMBER = re.compile(r"(?<![\w.])(?!(?:19|20)\d{2}(?!\.?\d))-?\d[\d,]*(?:\.\d+)?%?")

MAX_ATTEMPTS = 2  # first try + one retry


@dataclass(frozen=True)
class Fact:
    series_id: str
    label: str
    period: str  # YYYY-MM
    measure: str
    decimals: int
    value: Decimal  # rounded to `decimals`

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.series_id, self.period, self.measure)

    @property
    def shown(self) -> str:
        return f"{self.value:.{self.decimals}f}"


@dataclass
class Verification:
    ok: bool
    checked: int = 0
    problems: list[str] = field(default_factory=list)


@dataclass
class BriefResult:
    month: str
    as_of: str
    status: str  # "llm_verified" or "template_fallback" or "no_facts"
    text: str
    attempts: list[dict]
    facts: list[dict]
    generator: str


class Generator(Protocol):
    name: str

    def __call__(self, prompt: str) -> str: ...


def _month_start(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, 1)


def _shift(d: date, months: int) -> date:
    i = d.year * 12 + d.month - 1 + months
    return date(i // 12, i % 12 + 1, 1)


def _round(x: Decimal, decimals: int) -> Decimal:
    r = x.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN)
    return abs(r) if r.is_zero() else r  # never "-0.0"


def month_facts(con: duckdb.DuckDBPyConnection, month: str, as_of_utc: str) -> list[Fact]:
    """Facts for reference month `month` (YYYY-MM), using only what was published by `as_of_utc`.

    A fact is left out when a value it needs is not known at that time.
    """
    known: dict[str, dict[date, Decimal]] = {}
    for series_id, ref_period, value, *_ in as_of(con, as_of_utc):
        known.setdefault(series_id, {})[ref_period] = Decimal(str(value))
    labels = dict(con.execute("select series_id, label from main.series_info").fetchall())

    m0 = _month_start(month)
    m1, m12, next_m = _shift(m0, -1), _shift(m0, -12), _shift(m0, 1)
    facts: list[Fact] = []
    for series_id, measures in MEASURES.items():
        values = known.get(series_id, {})
        for measure, decimals in measures:
            raw: Decimal | None = None
            if measure in ("level", "mom_pct", "mom_pp", "yoy_pct"):
                cur = values.get(m0)
                base = values.get(m12 if measure == "yoy_pct" else m1)
                if measure == "level":
                    raw = cur
                elif cur is not None and base is not None:
                    raw = (cur / base - 1) * 100 if measure.endswith("pct") else cur - base
            else:  # daily series: last observation in the month

                def last_in(series_values: dict[date, Decimal], start: date, end: date) -> Decimal | None:
                    days = [d for d in series_values if start <= d < end]
                    return series_values[max(days)] if days else None

                end_m0, end_m1 = last_in(values, m0, next_m), last_in(values, m1, m0)
                if measure == "month_end":
                    raw = end_m0
                elif end_m0 is not None and end_m1 is not None:
                    raw = end_m0 - end_m1
            if raw is not None:
                facts.append(
                    Fact(series_id, labels.get(series_id, series_id), month, measure, decimals, _round(raw, decimals))
                )
    return facts


def build_prompt(month: str, facts: list[Fact], problems: list[str] | None = None) -> str:
    table = "\n".join(
        f"- {f.label} ({f.series_id}), {f.period}, {f.measure} = {f.shown}  [{MEASURE_TEXT[f.measure]}]" for f in facts
    )
    month_name = _month_start(month).strftime("%B %Y")
    prompt = f"""Write a short economic brief for Canada about {month_name}, in English, 80 to 150 words, one paragraph.

Use only the numbers below. Do not add any other number, forecast or cause that is not in the list.
Write every number as a citation marker [[series_id|period|measure|value]], copying the value
exactly as listed (same digits and decimals), for example [[{facts[0].series_id}|{facts[0].period}|{facts[0].measure}|{facts[0].shown}]].
Write the unit after the marker in words or with %. Write months as words, not numbers. You may
leave numbers out, but never write a digit outside a marker except a four-digit year.

Numbers:
{table}
"""
    if problems:
        prompt += "\nYour previous draft failed the number check:\n" + "\n".join(f"- {p}" for p in problems)
        prompt += "\nWrite the brief again and fix every problem.\n"
    return prompt


def verify(text: str, facts: list[Fact]) -> Verification:
    """Check every number in `text` against the fact for the same series, period and measure."""
    by_key = {f.key: f for f in facts}
    result = Verification(ok=True)
    for m in MARKER.finditer(text):
        series_id, period, measure, shown = m.groups()
        result.checked += 1
        fact = by_key.get((series_id, period, measure))
        if fact is None:
            result.problems.append(
                f"{m.group(0)}: no such fact (series {series_id}, period {period}, measure {measure})"
            )
        elif shown != fact.shown:
            result.problems.append(f"{m.group(0)}: expected {fact.shown} for {series_id} {period} {measure}")
    leftover = MARKER.sub(" ", text)
    for m in BARE_NUMBER.finditer(leftover):
        result.problems.append(f"number outside a citation marker: '{m.group(0)}'")
    if "[[" in leftover or "]]" in leftover:
        result.problems.append("malformed citation marker")
    if result.checked == 0:
        result.problems.append("no numbers cited")
    result.ok = not result.problems
    return result


def render(text: str) -> str:
    """Replace citation markers by their values for publication."""
    return MARKER.sub(lambda m: m.group(4), text).strip()


def template_brief(month: str, facts: list[Fact]) -> str:
    """Fixed wording used when the model's draft cannot be verified. Every number comes from `facts`."""
    month_name = _month_start(month).strftime("%B %Y")
    units = {"mom_pct": "%", "yoy_pct": "%", "level": "%", "month_end": "%", "mom_pp": " pp", "month_change_pp": " pp"}
    parts = [f"{f.label} {MEASURE_TEXT[f.measure].split(',')[0]}: {f.shown}{units[f.measure]}" for f in facts]
    return f"Canada, {month_name} (automatic summary, not reviewed). " + "; ".join(parts) + "."


def write_brief(con: duckdb.DuckDBPyConnection, month: str, as_of_utc: str, generator: Generator | None) -> BriefResult:
    facts = month_facts(con, month, as_of_utc)
    fact_dicts = [asdict(f) | {"value": f.shown} for f in facts]
    if not facts:
        return BriefResult(month, as_of_utc, "no_facts", "", [], [], getattr(generator, "name", "none"))
    attempts: list[dict] = []
    problems: list[str] | None = None
    if generator is not None:
        for n in range(1, MAX_ATTEMPTS + 1):
            prompt = build_prompt(month, facts, problems)
            try:
                draft = generator(prompt)
            except Exception as exc:  # the brief must never break the pipeline
                attempts.append({"attempt": n, "error": f"{type(exc).__name__}: {exc}"})
                break
            check = verify(draft, facts)
            attempt = {"attempt": n, "draft": draft, "checked": check.checked, "problems": check.problems}
            usage = getattr(generator, "last_usage", None)
            if usage:
                attempt["usage"] = usage
            attempts.append(attempt)
            if check.ok:
                return BriefResult(
                    month, as_of_utc, "llm_verified", render(draft), attempts, fact_dicts, generator.name
                )
            problems = check.problems
    return BriefResult(
        month,
        as_of_utc,
        "template_fallback",
        template_brief(month, facts),
        attempts,
        fact_dicts,
        getattr(generator, "name", "none"),
    )


class DeepSeekGenerator:
    """DeepSeek's chat API through the OpenAI SDK (DeepSeek's API is OpenAI-compatible).

    Needs DEEPSEEK_API_KEY and the `ai` extra (`uv sync --extra ai`). Token usage of the last
    call is kept in `last_usage` so the cost of every brief can be counted.
    """

    BASE_URL = "https://api.deepseek.com"

    def __init__(self, model: str = "deepseek-flash", api_key: str | None = None, http_client=None) -> None:
        import os

        from openai import OpenAI  # optional dependency

        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        self.client = OpenAI(api_key=key, base_url=self.BASE_URL, http_client=http_client, max_retries=2)
        self.model = model
        self.name = f"deepseek:{model}"
        self.last_usage: dict | None = None

    def __call__(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}},
        )
        u = response.usage
        self.last_usage = (
            None if u is None else {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}
        )
        return response.choices[0].message.content or ""


def months_between(first: str, last: str) -> list[str]:
    out, d, end = [], _month_start(first), _month_start(last)
    while d <= end:
        out.append(d.strftime("%Y-%m"))
        d = _shift(d, 1)
    return out


def main(argv: list[str] | None = None, make_generator: Callable[[str], Generator] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write monthly briefs and check every number.")
    parser.add_argument("--db", type=Path, default=Path("data/local/warehouse.duckdb"))
    parser.add_argument("--month", required=True, help="YYYY-MM, or FIRST:LAST for a range")
    parser.add_argument("--as-of", help="UTC 'YYYY-MM-DD HH:MM:SS' (default: now)")
    parser.add_argument("--model", help="DeepSeek model, e.g. deepseek-flash; without it only the template is written")
    parser.add_argument("--out", type=Path, default=Path("data/local/briefs"))
    args = parser.parse_args(argv)

    as_of_utc = args.as_of or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    first, _, last = args.month.partition(":")
    months = months_between(first, last or first)
    generator = None
    if args.model:
        generator = (make_generator or DeepSeekGenerator)(args.model)

    con = duckdb.connect(str(args.db), read_only=True)
    args.out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    try:
        for month in months:
            result = write_brief(con, month, as_of_utc, generator)
            counts[result.status] = counts.get(result.status, 0) + 1
            for att in result.attempts:
                for k, v in att.get("usage", {}).items():
                    counts[k] = counts.get(k, 0) + v
            (args.out / f"{month}.json").write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
            print(f"{month}: {result.status} ({len(result.attempts)} attempt(s), {len(result.facts)} facts)")
    finally:
        con.close()
    print("summary:", json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
