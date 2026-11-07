"""Rebuild the DuckDB raw tables from the append-only raw store.

The warehouse is always rebuilt from scratch from raw snapshots, so running this
any number of times gives the same tables (idempotent by construction).
Only captures from runs whose status is "success" are loaded.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from canecon.parse import (
    parse_boc_observations,
    parse_gdp_realtime,
    parse_statcan_vectors,
    release_dates,
)

OBS_COLUMNS = [
    "series_id",
    "source_kind",
    "ref_period",
    "value",
    "scalar_factor",
    "decimals",
    "published_at",
    "status_code",
    "symbol_code",
    "release_label",
    "captured_at",
    "run_id",
    "content_sha256",
    "object_path",
]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def observations_from_store(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    runs = read_jsonl(root / "runs.jsonl")
    manifest = read_jsonl(root / "manifest.jsonl")
    good_runs = {r["run_id"] for r in runs if r["status"] == "success"}

    rows: list[dict] = []
    releases_by_run: dict[str, dict] = {}
    for m in manifest:
        if not m["ok"] or m["run_id"] not in good_runs:
            continue
        content = (root / m["object_path"]).read_bytes()
        rid = m["request_id"]
        if rid == "statcan_vectors_latest":
            parsed = parse_statcan_vectors(content)
        elif rid == "boc_observations_recent":
            parsed = parse_boc_observations(content, m["captured_at"])
        elif rid == "statcan_gdp_realtime_metadata":
            releases_by_run[m["run_id"]] = release_dates(content)
            continue
        elif rid.startswith("statcan_gdp_realtime_releases_"):
            parsed = parse_gdp_realtime(content, releases_by_run[m["run_id"]])
        else:
            continue  # e.g. series info: metadata only
        for r in parsed:
            r.update(
                captured_at=m["captured_at"],
                run_id=m["run_id"],
                content_sha256=m["content_sha256"],
                object_path=m["object_path"],
            )
        rows.extend(parsed)
    return rows, manifest, runs


def load(root: Path, db_path: Path) -> int:
    rows, manifest, runs = observations_from_store(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema if not exists raw")
        con.execute(
            """
            create or replace table raw.observations (
                series_id varchar, source_kind varchar, ref_period date,
                value decimal(38, 10), scalar_factor integer, decimals integer,
                published_at timestamp, status_code integer, symbol_code integer,
                release_label varchar, captured_at timestamp, run_id varchar,
                content_sha256 varchar, object_path varchar
            )
            """
        )
        if rows:
            con.executemany(
                f"insert into raw.observations values ({', '.join('?' * len(OBS_COLUMNS))})",
                [[r[c].rstrip("Z") if c in ("published_at", "captured_at") else r[c] for c in OBS_COLUMNS] for r in rows],
            )
        con.execute(
            """
            create or replace table raw.captures (
                run_id varchar, request_id varchar, source varchar, url varchar,
                captured_at timestamp, http_status integer, attempts integer, ok boolean,
                error varchar, content_sha256 varchar, object_path varchar
            )
            """
        )
        if manifest:
            con.executemany(
                "insert into raw.captures values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [m["run_id"], m["request_id"], m["source"], m["url"], m["captured_at"].rstrip("Z"),
                     m["http_status"], m["attempts"], m["ok"], m["error"], m["content_sha256"], m["object_path"]]
                    for m in manifest
                ],
            )
        con.execute(
            """
            create or replace table raw.runs (
                run_id varchar, kind varchar, started_at timestamp, finished_at timestamp,
                n_requests integer, n_ok integer, status varchar
            )
            """
        )
        if runs:
            con.executemany(
                "insert into raw.runs values (?, ?, ?, ?, ?, ?, ?)",
                [
                    [r["run_id"], r.get("kind", "daily"), r["started_at"].rstrip("Z"), r["finished_at"].rstrip("Z"),
                     r["n_requests"], r["n_ok"], r["status"]]
                    for r in runs
                ],
            )
    finally:
        con.close()
    return len(rows)
