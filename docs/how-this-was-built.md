# How this was built

This project was built with an AI coding assistant (Claude Code). Being clear about who did what is part of the project.

## What the AI did

- Wrote nearly all of the code: the collector, the loader, the dbt models and tests, the Evidence pages, the GitHub Actions workflows.
- Checked the data sources against the official APIs and documentation (series codes, licences, which tables keep historical vintages), recorded in [sources.md](sources.md) with check dates.
- Ran every command behind the numbers in the docs and kept the outputs; wrote the docs.
- Found and fixed the bugs in [bug-log.md](bug-log.md). Two of them only showed up against the live APIs, which is why the project runs live checks and does not rely on recorded responses alone.

## What the owner did

- Chose the problem and the goal: a second portfolio project that shows Python, SQL modelling and a public deployment, using only official public data.
- Set the rules the work had to follow: no invented numbers (every figure must come from a command that was run), the seven correctness constraints to test first (separate reference, release and capture times; append-only raw layer with SHA-256 lineage; idempotent reruns; revisions that ignore scale and rounding; point-in-time queries without look-ahead; no partial publishes; tests on recorded responses with hand-computed expectations), privacy limits, and what not to use (Spark, Kafka, paid services).
- Approved each step that is public or hard to undo: creating the public repository, every push, turning on GitHub Pages. USD/CAD stays off the dashboard until the owner decides on its licence question.

## Checks that do not depend on trusting the AI

- 40 tests (`uv run pytest -q`), including hand-computed revision and point-in-time scenarios, DST edge cases, idempotent rebuilds, fault injection and the public-data filter of the export. During development, deliberate breakages of the revision logic were caught by these tests.
- 26 data quality checks on the real data, run on every build.
- The idempotency check on GitHub Actions and the live catch-up run in [reliability.md](reliability.md).
- Every number in [analysis.md](analysis.md) has the query that produced it and the `data` commit it was run on.

## Still to do

- The owner's walkthrough of the code (explaining each model and query without notes) is scheduled after the core of the project is finished.
- Collection started on 2026-11-07 with runs started by hand; the daily schedule has no history yet, so there is no measured success rate.
