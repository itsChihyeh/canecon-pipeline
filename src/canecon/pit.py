"""Point-in-time queries: what was known at time T, with no look-ahead."""

from __future__ import annotations

import duckdb

AS_OF_SQL = """
select series_id, ref_period, value, vintage_number, valid_from, source_snapshot_sha256
from main.vintages
where valid_from <= $as_of
  and (valid_to is null or valid_to > $as_of)
  and ($series_id is null or series_id = $series_id)
order by series_id, ref_period
"""


def as_of(con: duckdb.DuckDBPyConnection, as_of_utc: str, series_id: str | None = None) -> list[tuple]:
    """Values as they were known at `as_of_utc` (ISO timestamp, UTC).

    A vintage counts only if it was published at or before T and not yet replaced at T.
    Values published after T are never used.
    """
    return con.execute(AS_OF_SQL, {"as_of": as_of_utc, "series_id": series_id}).fetchall()
