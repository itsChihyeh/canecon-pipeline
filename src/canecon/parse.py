"""Turn raw API responses into flat observation rows.

Each row keeps the three times apart:
- ref_period:   the period the number describes (e.g. 2026-08-01 for August)
- published_at: when the source made this value public (UTC)
- captured_at:  when our collector received the response (UTC)
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from canecon.sources import BOC_SERIES, GDP_SERIES_ID, STATCAN_VECTORS

EASTERN = ZoneInfo("America/Toronto")
STATCAN_RELEASE_HOUR = (8, 30)  # StatCan publishes at 08:30 Eastern

VECTOR_TO_SERIES = {v: name for v, _, name in STATCAN_VECTORS}
BOC_TO_SERIES = {
    "V39079": "policy_rate_target",
    "BD.CDN.2YR.DQ.YLD": "gov_bond_yield_2y",
    "BD.CDN.10YR.DQ.YLD": "gov_bond_yield_10y",
}
assert set(BOC_TO_SERIES) == set(BOC_SERIES)


def eastern_to_utc(local: datetime) -> str:
    """'2026-10-30T08:30' (Eastern, naive) -> '2026-10-30T12:30:00Z'."""
    aware = local.replace(tzinfo=EASTERN)
    return aware.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def decimals_of(value: str) -> int:
    d = Decimal(value)
    exp = d.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def parse_statcan_vectors(content: bytes) -> list[dict]:
    """getDataFromVectorsAndLatestNPeriods response -> rows for known vectors."""
    rows = []
    for item in json.loads(content):
        obj = item["object"]
        series_id = VECTOR_TO_SERIES.get(obj["vectorId"])
        if series_id is None:
            continue
        for p in obj["vectorDataPoint"]:
            if p["value"] is None or p["releaseTime"] is None:
                continue
            rows.append(
                {
                    "series_id": series_id,
                    "source_kind": "statcan_live",
                    "ref_period": p["refPer"],
                    "value": str(Decimal(str(p["value"]))),
                    "scalar_factor": int(p["scalarFactorCode"]),
                    "decimals": int(p["decimals"]),
                    "published_at": eastern_to_utc(datetime.fromisoformat(p["releaseTime"])),
                    "status_code": p.get("statusCode"),
                    "symbol_code": p.get("symbolCode"),
                    "release_label": None,
                }
            )
    return rows


def parse_boc_observations(content: bytes, captured_at: str) -> list[dict]:
    """Valet observations -> rows. Valet gives no release time, so we use capture time.

    That is conservative for point-in-time queries: a value is never treated as known
    before we actually saw it.
    """
    data = json.loads(content)
    rows = []
    for obs in data["observations"]:
        for code, series_id in BOC_TO_SERIES.items():
            cell = obs.get(code)
            if not cell or cell.get("v") in (None, ""):
                continue
            rows.append(
                {
                    "series_id": series_id,
                    "source_kind": "boc_live",
                    "ref_period": obs["d"],
                    "value": cell["v"],
                    "scalar_factor": 0,
                    "decimals": decimals_of(cell["v"]),
                    "published_at": captured_at,
                    "status_code": None,
                    "symbol_code": None,
                    "release_label": None,
                }
            )
    return rows


def release_dates(metadata_content: bytes) -> dict[int, date]:
    """Cube metadata for 36-10-0491 -> {release member id: release date}."""
    obj = json.loads(metadata_content)[0]["object"]
    release_dim = next(d for d in obj["dimension"] if d["dimensionNameEn"] == "Release")
    out = {}
    for m in release_dim["member"]:
        out[int(m["memberId"])] = datetime.strptime(m["memberNameEn"], "%B %d, %Y").date()
    return out


def parse_changed_cubes(content: bytes) -> list[dict]:
    """getChangedCubeList/<day> -> [{product_id, release_time (UTC)}]."""
    return [
        {
            "product_id": int(o["productId"]),
            "release_time": eastern_to_utc(datetime.fromisoformat(o["releaseTime"])),
        }
        for o in json.loads(content)["object"]
    ]


COORD_RE = re.compile(r"^1\.1\.1\.1\.(\d+)\.")


def parse_gdp_realtime(content: bytes, releases: dict[int, date]) -> list[dict]:
    """36-10-0491 coordinate response -> one vintage per (release, ref_period).

    The points' own releaseTime is when the table was last refreshed, not when that
    vintage was published, so the release date comes from the Release dimension.
    """
    rows = []
    for item in json.loads(content):
        obj = item["object"]
        m = COORD_RE.match(obj["coordinate"])
        if not m:
            continue
        member = int(m.group(1))
        rel = releases[member]
        published = eastern_to_utc(datetime(rel.year, rel.month, rel.day, *STATCAN_RELEASE_HOUR))
        for p in obj["vectorDataPoint"]:
            if p["value"] is None:
                continue
            rows.append(
                {
                    "series_id": GDP_SERIES_ID,
                    "source_kind": "statcan_realtime_table",
                    "ref_period": p["refPer"],
                    "value": str(Decimal(str(p["value"]))),
                    "scalar_factor": int(p["scalarFactorCode"]),
                    "decimals": int(p["decimals"]),
                    "published_at": published,
                    "status_code": p.get("statusCode"),
                    "symbol_code": p.get("symbolCode"),
                    "release_label": rel.isoformat(),
                }
            )
    return rows
