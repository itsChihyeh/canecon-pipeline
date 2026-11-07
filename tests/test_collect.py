"""Collector tests. Inputs are recorded real responses; expected values are written by hand."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from canecon.collect import RawStore, fetch_with_retry, run_collection, validate
from canecon.sources import Request, daily_requests

FIXTURES = Path(__file__).parent / "fixtures"
STATCAN = (FIXTURES / "statcan_vectors_latest_2026-11-07.json").read_bytes()
SERIES_INFO = (FIXTURES / "statcan_series_info_2026-11-07.json").read_bytes()
BOC = (FIXTURES / "boc_observations_recent_2026-11-07.json").read_bytes()

# Hashes written down from the recording, not computed by the code under test.
STATCAN_SHA = "3ec700544c5eca5825d91fc3849f282c49692e7e00d423524942bfb6e2287979"
BOC_SHA = "99969647d015e17f9fd2c6e0629e101c54546b9ff876a8e76832b9b723fe940d"


def fixture_for(url: str) -> bytes:
    if "getDataFromVectorsAndLatestNPeriods" in url:
        return STATCAN
    if "getSeriesInfoFromVector" in url:
        return SERIES_INFO
    return BOC


def scripted_client(responses: dict[str, list]) -> tuple[httpx.Client, list[str]]:
    """Client whose responses per URL keyword come from a list (status code or exception)."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        for key, queue in responses.items():
            if key in url:
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(item, Exception):
                    raise item
                if item == 200:
                    return httpx.Response(200, content=fixture_for(url))
                return httpx.Response(item, content=b"error")
        return httpx.Response(200, content=fixture_for(url))

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def no_sleep(_: float) -> None:
    pass


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_fixture_hashes_match_recording():
    assert hashlib.sha256(STATCAN).hexdigest() == STATCAN_SHA
    assert hashlib.sha256(BOC).hexdigest() == BOC_SHA


def test_successful_run_stores_each_response_with_lineage(tmp_path):
    store = RawStore(tmp_path)
    client, _ = scripted_client({})
    summary = run_collection(store, daily_requests(), client, sleep=no_sleep)

    assert summary["status"] == "success"
    assert summary["n_ok"] == 3
    rows = read_jsonl(store.manifest)
    assert [r["request_id"] for r in rows] == [
        "statcan_vectors_latest",
        "statcan_series_info",
        "boc_observations_recent",
    ]
    statcan_row = rows[0]
    assert statcan_row["content_sha256"] == STATCAN_SHA
    assert statcan_row["object_path"] == f"objects/3e/{STATCAN_SHA}.json"
    # The stored object is the exact bytes received.
    assert (tmp_path / statcan_row["object_path"]).read_bytes() == STATCAN


def test_rerun_with_same_content_adds_no_new_objects(tmp_path):
    store = RawStore(tmp_path)
    for _ in range(3):
        client, _ = scripted_client({})
        run_collection(store, daily_requests(), client, sleep=no_sleep)

    objects = sorted(p.name for p in (tmp_path / "objects").rglob("*.json"))
    assert len(objects) == 3  # three distinct responses, stored once each
    rows = read_jsonl(store.manifest)
    assert len(rows) == 9  # every capture is still recorded
    assert [r["new_object"] for r in rows] == [True] * 3 + [False] * 6
    assert len(read_jsonl(store.runs)) == 3


def test_existing_objects_are_never_rewritten(tmp_path):
    store = RawStore(tmp_path)
    sha, created = store.put_object(b'{"a": 1}')
    assert created
    path = store.object_path(sha)
    mtime = path.stat().st_mtime_ns
    _, created_again = store.put_object(b'{"a": 1}')
    assert not created_again
    assert path.stat().st_mtime_ns == mtime


def test_tampered_object_is_detected(tmp_path):
    store = RawStore(tmp_path)
    sha, _ = store.put_object(b'{"a": 1}')
    store.object_path(sha).write_bytes(b'{"a": 2}')
    with pytest.raises(RuntimeError):
        store.put_object(b'{"a": 1}')


def test_retry_then_success_with_exponential_backoff():
    sleeps: list[float] = []
    client, calls = scripted_client({"getDataFromVectors": [500, 409, 200]})
    req = daily_requests()[0]
    result = fetch_with_retry(client, req, sleep=sleeps.append)
    assert result.status_code == 200
    assert result.attempts == 3
    assert sleeps == [2.0, 4.0]
    assert len(calls) == 3


def test_network_error_is_retried():
    client, _ = scripted_client({"getDataFromVectors": [httpx.ConnectError("boom"), 200]})
    result = fetch_with_retry(client, daily_requests()[0], sleep=no_sleep)
    assert result.status_code == 200
    assert result.attempts == 2


def test_non_retryable_status_stops_immediately():
    client, calls = scripted_client({"getDataFromVectors": [404]})
    result = fetch_with_retry(client, daily_requests()[0], sleep=no_sleep)
    assert result.status_code == 404
    assert result.attempts == 1
    assert len(calls) == 1


def test_persistent_failure_marks_run_partial_and_saves_nothing_for_it(tmp_path):
    store = RawStore(tmp_path)
    client, _ = scripted_client({"valet": [503]})
    summary = run_collection(store, daily_requests(), client, sleep=no_sleep)

    assert summary["status"] == "partial"
    assert summary["n_ok"] == 2
    boc_row = read_jsonl(store.manifest)[2]
    assert boc_row["ok"] is False
    assert boc_row["attempts"] == 4
    assert boc_row["http_status"] == 503
    assert boc_row["content_sha256"] is None


def test_all_requests_failing_marks_run_failed(tmp_path):
    store = RawStore(tmp_path)
    client, _ = scripted_client({"statcan": [503], "valet": [503]})
    summary = run_collection(store, daily_requests(), client, sleep=no_sleep)
    assert summary["status"] == "failed"
    assert summary["n_ok"] == 0


def test_statcan_item_failure_inside_200_is_not_ok():
    body = json.dumps([{"status": "SUCCESS", "object": {}}, {"status": "FAILED", "object": "x"}])
    req = daily_requests()[0]
    assert validate(req, body.encode()) == "items not SUCCESS at positions [1]"


def test_recorded_responses_pass_validation():
    reqs = {r.request_id: r for r in daily_requests()}
    assert validate(reqs["statcan_vectors_latest"], STATCAN) is None
    assert validate(reqs["statcan_series_info"], SERIES_INFO) is None
    assert validate(reqs["boc_observations_recent"], BOC) is None


def test_invalid_json_is_not_ok():
    req = Request("x", "boc_valet", "GET", "https://example.test")
    assert validate(req, b"<html>maintenance</html>").startswith("invalid JSON")
