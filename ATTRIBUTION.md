# Attribution

## Ideas from other projects

- **[calemccammon/data-engineer-finance-analytics](https://github.com/calemccammon/data-engineer-finance-analytics)**, read at commit `4daac05` on 2026-10-21 while planning this project. Two ideas came from it: the overall shape (Python collection into DuckDB, dbt models, an Evidence dashboard published to GitHub Pages) and checking every number in a language-model summary against the database before publishing it. The repository has no licence, so no code was copied. This project differs where it matters for revisions: that repository replaces its tables on each load, while this one keeps an append-only raw layer and every published value; and the brief check here matches each number to a named series, period and measure, not only to a value that exists somewhere in the data.

All code in this repository was written for it, with an AI coding assistant; see [docs/how-this-was-built.md](docs/how-this-was-built.md).

## Tools

Python, [httpx](https://github.com/encode/httpx), [DuckDB](https://github.com/duckdb/duckdb), [dbt-core](https://github.com/dbt-labs/dbt-core) with [dbt-duckdb](https://github.com/duckdb/dbt-duckdb), [pytest](https://github.com/pytest-dev/pytest), [Evidence](https://github.com/evidence-dev/evidence), [scikit-learn](https://github.com/scikit-learn/scikit-learn), [Dagster](https://github.com/dagster-io/dagster) and [uv](https://github.com/astral-sh/uv), each under its own licence. GitHub Actions runs the schedule, tests and deployment.

## Data

Adapted from Statistics Canada data. This does not constitute an endorsement by Statistics Canada of this product. Bank of Canada data: source Bank of Canada; values may be transformed as described in the docs. Terms and check dates: [docs/sources.md](docs/sources.md).
