"""Daily collector: fetch API responses and store them as append-only raw snapshots.

Layout under the data directory:

    objects/<sha[:2]>/<sha>.json   response bytes exactly as received, named by SHA-256
    manifest.jsonl                 one line per request attempt in a run (lineage record)
    runs.jsonl                     one line per run with its overall status

Rules:
- Existing objects and lines are never modified or deleted.
- Identical content is stored once; each capture still gets its own manifest line.
- A run is "success" only if every request succeeded. Downstream layers must use
  only successful runs, so a partial failure never publishes half a dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

import httpx

from canecon.sources import (
    Request,
    daily_requests,
    gdp_realtime_data_requests,
    gdp_realtime_metadata_request,
)

RETRYABLE_STATUS = {409, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
TIMEOUT_SECONDS = 60.0
USER_AGENT = "canecon-pipeline (+https://github.com/itsChihyeh/canecon-pipeline)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_fingerprint(req: Request) -> str:
    """Stable hash of what was asked, so captures of the same request can be grouped."""
    canonical = json.dumps(
        {"method": req.method, "url": req.url, "params": req.params, "body": req.json_body},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_hex(canonical.encode())


@dataclass
class FetchResult:
    status_code: int | None
    content: bytes | None
    attempts: int
    error: str | None


def fetch_with_retry(
    client: httpx.Client,
    req: Request,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Send one request, retrying transient failures with exponential backoff."""
    last_error: str | None = None
    last_status: int | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.request(req.method, req.url, params=req.params or None, json=req.json_body)
        except httpx.TransportError as exc:
            last_error, last_status = f"{type(exc).__name__}: {exc}", None
        else:
            if resp.status_code == 200:
                return FetchResult(200, resp.content, attempt, None)
            last_status, last_error = resp.status_code, f"HTTP {resp.status_code}"
            if resp.status_code not in RETRYABLE_STATUS:
                return FetchResult(resp.status_code, resp.content, attempt, last_error)
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    return FetchResult(last_status, None, MAX_ATTEMPTS, last_error)


def validate(req: Request, content: bytes) -> str | None:
    """Return an error message if a 200 response is not usable, else None."""
    try:
        data = json.loads(content)
    except ValueError as exc:
        return f"invalid JSON: {exc}"
    if req.source == "statcan_wds":
        if not isinstance(data, list) or not data:
            return "expected a non-empty list"
        bad = [i for i, item in enumerate(data) if item.get("status") != "SUCCESS"]
        if bad:
            return f"items not SUCCESS at positions {bad}"
    elif req.source == "boc_valet":
        if not isinstance(data, dict) or "observations" not in data:
            return "missing 'observations'"
        if not data["observations"]:
            return "empty 'observations'"
    return None


class RawStore:
    """Append-only, content-addressed storage for raw responses."""

    def __init__(self, root: Path):
        self.root = root
        self.objects = root / "objects"
        self.manifest = root / "manifest.jsonl"
        self.runs = root / "runs.jsonl"

    def object_path(self, sha: str) -> Path:
        return self.objects / sha[:2] / f"{sha}.json"

    def put_object(self, content: bytes) -> tuple[str, bool]:
        """Store content once. Returns (sha256, created_new)."""
        sha = sha256_hex(content)
        path = self.object_path(sha)
        if path.exists():
            if sha256_hex(path.read_bytes()) != sha:
                raise RuntimeError(f"stored object {path} does not match its hash")
            return sha, False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp-{uuid.uuid4().hex}")
        tmp.write_bytes(content)
        os.replace(tmp, path)
        return sha, True

    @staticmethod
    def _append(path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def append_manifest(self, record: dict) -> None:
        self._append(self.manifest, record)

    def append_run(self, record: dict) -> None:
        self._append(self.runs, record)


def run_collection(
    store: RawStore,
    requests: Iterable[Request],
    client: httpx.Client,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = utc_now,
    kind: str = "daily",
) -> dict:
    run_id = f"{now()}_{uuid.uuid4().hex[:8]}"
    started_at = now()
    n_ok = 0
    n_requests = 0
    for req in requests:
        n_requests += 1
        captured_at = now()
        result = fetch_with_retry(client, req, sleep=sleep)
        sha = new_object = None
        error = result.error
        if result.content is not None:
            sha, new_object = store.put_object(result.content)
            if result.status_code == 200:
                error = validate(req, result.content)
        ok = result.status_code == 200 and error is None
        n_ok += ok
        store.append_manifest(
            {
                "run_id": run_id,
                "request_id": req.request_id,
                "request_fingerprint": request_fingerprint(req),
                "source": req.source,
                "method": req.method,
                "url": req.url,
                "params": req.params,
                "body": req.json_body,
                "captured_at": captured_at,
                "http_status": result.status_code,
                "attempts": result.attempts,
                "ok": ok,
                "error": error,
                "content_sha256": sha,
                "object_path": store.object_path(sha).relative_to(store.root).as_posix() if sha else None,
                "new_object": new_object,
            }
        )
    status = "success" if n_ok == n_requests else ("failed" if n_ok == 0 else "partial")
    summary = {
        "run_id": run_id,
        "kind": kind,
        "started_at": started_at,
        "finished_at": now(),
        "n_requests": n_requests,
        "n_ok": n_ok,
        "status": status,
    }
    store.append_run(summary)
    return summary


def last_manifest_row(store: RawStore) -> dict:
    with store.manifest.open(encoding="utf-8") as f:
        *_, last = f
    return json.loads(last)


def backfill_requests(store: RawStore) -> Iterator[Request]:
    """Fetch the 36-10-0491 metadata first, then one request per batch of releases.

    Stops after the metadata request if it failed, so the run is marked failed.
    """
    from canecon.parse import release_dates

    yield gdp_realtime_metadata_request()
    row = last_manifest_row(store)
    if not row["ok"]:
        return
    releases = release_dates((store.root / row["object_path"]).read_bytes())
    yield from gdp_realtime_data_requests(list(releases))


def backfill_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time backfill of official GDP vintages.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)
    store = RawStore(args.data_dir)
    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        summary = run_collection(store, backfill_requests(store), client, kind="backfill_gdp_realtime")
    print(json.dumps(summary))
    return 0 if summary["status"] == "success" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect raw API snapshots.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)
    store = RawStore(args.data_dir)
    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        summary = run_collection(store, daily_requests(), client)
    print(json.dumps(summary))
    return 0 if summary["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
