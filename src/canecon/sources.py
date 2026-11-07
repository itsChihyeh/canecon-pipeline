"""Series and API requests collected every day.

Codes were checked against the official APIs on 2026-11-07; see docs/sources.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATCAN_WDS = "https://www150.statcan.gc.ca/t1/wds/rest"
BOC_VALET = "https://www.bankofcanada.ca/valet"

# StatCan vectors: (vector id, table, short name)
STATCAN_VECTORS = [
    (65201210, "36-10-0434-01", "gdp_all_industries"),
    (1446859483, "20-10-0056-01", "retail_sales_total_sa"),
    (2062815, "14-10-0287-01", "unemployment_rate_sa"),
    (41690973, "18-10-0004-01", "cpi_all_items"),
]

# Bank of Canada Valet series codes
BOC_SERIES = [
    "V39079",  # target for the overnight rate
    "FXUSDCAD",  # USD/CAD daily average
    "BD.CDN.2YR.DQ.YLD",  # 2-year benchmark bond yield
    "BD.CDN.10YR.DQ.YLD",  # 10-year benchmark bond yield
]

# How many latest periods to request. Large enough to see revisions to
# earlier months (e.g. annual seasonal-adjustment revisions).
STATCAN_LATEST_N = 36
# Business days of Bank of Canada observations to request.
BOC_RECENT = 30


@dataclass(frozen=True)
class Request:
    """One HTTP request whose response is saved as a raw snapshot."""

    request_id: str
    source: str
    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    json_body: Any = None


def daily_requests() -> list[Request]:
    return [
        Request(
            request_id="statcan_vectors_latest",
            source="statcan_wds",
            method="POST",
            url=f"{STATCAN_WDS}/getDataFromVectorsAndLatestNPeriods",
            json_body=[
                {"vectorId": v, "latestN": STATCAN_LATEST_N}
                for v, _, _ in STATCAN_VECTORS
            ],
        ),
        Request(
            request_id="statcan_series_info",
            source="statcan_wds",
            method="POST",
            url=f"{STATCAN_WDS}/getSeriesInfoFromVector",
            json_body=[{"vectorId": v} for v, _, _ in STATCAN_VECTORS],
        ),
        Request(
            request_id="boc_observations_recent",
            source="boc_valet",
            method="GET",
            url=f"{BOC_VALET}/observations/{','.join(BOC_SERIES)}/json",
            params={"recent": BOC_RECENT},
        ),
    ]


# --- One-time backfill of official GDP vintages -------------------------------
# Table 36-10-0491: "Historical (real-time) releases of GDP at basic prices, by
# industry, monthly". Coordinate 1.1.1.1.<release> = Canada, SAAR, chained (2017)
# dollars, all industries, one vector per release. Same concept as v65201210.
GDP_SERIES_ID = "gdp_all_industries"
GDP_REALTIME_PID = 36100491
# latestN counts back from the table's last period, so old releases need a large N.
GDP_REALTIME_LATEST_N = 160
GDP_REALTIME_BATCH = 20


def gdp_realtime_metadata_request() -> Request:
    return Request(
        request_id="statcan_gdp_realtime_metadata",
        source="statcan_wds",
        method="POST",
        url=f"{STATCAN_WDS}/getCubeMetadata",
        json_body=[{"productId": GDP_REALTIME_PID}],
    )


def gdp_realtime_data_requests(release_members: list[int]) -> list[Request]:
    members = sorted(release_members)
    out = []
    for i in range(0, len(members), GDP_REALTIME_BATCH):
        batch = members[i : i + GDP_REALTIME_BATCH]
        out.append(
            Request(
                request_id=f"statcan_gdp_realtime_releases_{batch[0]:03d}_{batch[-1]:03d}",
                source="statcan_wds",
                method="POST",
                url=f"{STATCAN_WDS}/getDataFromCubePidCoordAndLatestNPeriods",
                json_body=[
                    {
                        "productId": GDP_REALTIME_PID,
                        "coordinate": f"1.1.1.1.{m}.0.0.0.0.0",
                        "latestN": GDP_REALTIME_LATEST_N,
                    }
                    for m in batch
                ],
            )
        )
    return out
