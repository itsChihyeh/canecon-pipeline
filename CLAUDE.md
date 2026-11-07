# CanEcon Vintage Pipeline: working rules for Claude

- Read `docs/brief.md` first if it exists locally (private, gitignored). It is the plan and acceptance criteria. It is never committed.
- Talk to the owner in Chinese, briefly. Code, README and docs in this repo are in English.
- The owner directs and reviews; AI writes most code. After each phase, quiz the owner (3-5 questions in Chinese, starting from the smallest example) and record pass / stuck points in the job-search project tracker, not here.
- Honesty: no invented metrics, users, awards or experience. Every number in README or docs must come from a command that was actually run, with environment and raw output kept.
- Privacy: this repo will be public. Do not copy anything from `..\找工作` (resume, grades, contact details, applications). Secrets only in environment variables or GitHub Secrets.
- Ask the owner before creating the public GitHub repo, before any paid service (LLM API, cloud), and before pushing.
- Progress log for the owner lives in `C:\Users\zhiye\Documents\找工作\projects\tracker.md`, section "副项目 A". Append only to that section.
- Data source facts (series codes, licences, limits, vintage availability) are in `docs/sources.md`, with check dates. Re-check official pages before relying on them.
- Core constraints to test before implementing: reference period / release time / capture time kept separate; raw layer append-only with SHA-256 lineage; idempotent reruns; revision detection that ignores scale/rounding; point-in-time queries with no look-ahead; failures never publish partial data; tests use recorded responses and hand-computed expectations.
