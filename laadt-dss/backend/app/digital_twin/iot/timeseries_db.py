"""
TimescaleDB wrapper for IoT time-series data.

Uses the existing PostgreSQL connection (with TimescaleDB extension enabled).
Each metric is stored in the `iot_measurements` hypertable partitioned by time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

HYPERTABLE_DDL = """
CREATE TABLE IF NOT EXISTS iot_measurements (
    time        TIMESTAMPTZ     NOT NULL,
    asset_id    TEXT            NOT NULL,
    metric      TEXT            NOT NULL,
    value       DOUBLE PRECISION NOT NULL
);
"""

HYPERTABLE_CALL = """
SELECT create_hypertable(
    'iot_measurements', 'time',
    if_not_exists => TRUE
);
"""

INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_iot_asset_metric_time
    ON iot_measurements (asset_id, metric, time DESC);
"""


def init_timeseries_schema() -> None:
    """
    Create the hypertable and index if they do not exist.
    Falls back gracefully when TimescaleDB extension is not installed
    (plain PostgreSQL table is created instead — adequate for development).
    """
    # Step 1: create the table in its own committed transaction
    with engine.begin() as conn:
        conn.execute(text(HYPERTABLE_DDL))

    # Step 2: attempt TimescaleDB hypertable promotion in a separate transaction
    # so that failure does NOT abort the outer transaction.
    try:
        with engine.begin() as conn:
            conn.execute(text(HYPERTABLE_CALL))
    except Exception:
        logger.warning(
            "TimescaleDB extension not found; using plain PostgreSQL table "
            "for iot_measurements. Install TimescaleDB for production."
        )

    # Step 3: create the index (always succeeds on plain PG too)
    with engine.begin() as conn:
        conn.execute(text(INDEX_DDL))


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_measurement(
    asset_id: str,
    metric: str,
    value: float,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Insert a single measurement into the hypertable.

    Args:
        asset_id:  Unique asset identifier (e.g. "asset_001").
        metric:    Metric name, one of the standard topics below:
                     pv/power, pv/irradiance, bess/soc, bess/soh,
                     meter/import, meter/export, weather/temp
        value:     Numeric reading.
        timestamp: UTC datetime; defaults to now.
    """
    ts = timestamp or datetime.now(timezone.utc)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO iot_measurements (time, asset_id, metric, value) "
                "VALUES (:t, :a, :m, :v)"
            ),
            {"t": ts, "a": asset_id, "m": metric, "v": value},
        )
        conn.commit()


def write_measurements_bulk(rows: list[dict]) -> None:
    """
    Bulk insert a list of measurement dicts.
    Each dict must have keys: asset_id, metric, value, and optionally time.
    """
    now = datetime.now(timezone.utc)
    records = [
        {
            "t": r.get("time", now),
            "a": r["asset_id"],
            "m": r["metric"],
            "v": r["value"],
        }
        for r in rows
    ]
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO iot_measurements (time, asset_id, metric, value) "
                "VALUES (:t, :a, :m, :v)"
            ),
            records,
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_timeseries(
    asset_id: str,
    metric: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Return all readings for (asset_id, metric) in [start, end] as a DataFrame.

    Columns: time (UTC-aware datetime index), value (float).
    """
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT time, value FROM iot_measurements "
                "WHERE asset_id = :a AND metric = :m "
                "  AND time >= :s AND time <= :e "
                "ORDER BY time ASC"
            ),
            {"a": asset_id, "m": metric, "s": start, "e": end},
        )
        rows = result.fetchall()

    if not rows:
        return pd.DataFrame(columns=["time", "value"])

    df = pd.DataFrame(rows, columns=["time", "value"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df


def get_latest(asset_id: str, metric: str) -> tuple[float, datetime] | tuple[None, None]:
    """
    Return the most recent (value, timestamp) for the given asset+metric.
    Returns (None, None) if no data exists.
    """
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT value, time FROM iot_measurements "
                "WHERE asset_id = :a AND metric = :m "
                "ORDER BY time DESC LIMIT 1"
            ),
            {"a": asset_id, "m": metric},
        )
        row = result.fetchone()

    if row is None:
        return None, None
    return float(row[0]), row[1]


def get_daily_aggregates(
    asset_id: str,
    metric: str,
    start: datetime,
    end: datetime,
    agg: str = "sum",
) -> pd.DataFrame:
    """
    Return daily aggregates (sum or avg) for a metric.

    Args:
        agg: 'sum' or 'avg'
    Returns:
        DataFrame with columns: date, value
    """
    agg_func = "SUM" if agg == "sum" else "AVG"
    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"SELECT DATE(time AT TIME ZONE 'UTC') AS date, "
                f"{agg_func}(value) AS value "
                f"FROM iot_measurements "
                f"WHERE asset_id = :a AND metric = :m "
                f"  AND time >= :s AND time <= :e "
                f"GROUP BY date ORDER BY date ASC"
            ),
            {"a": asset_id, "m": metric, "s": start, "e": end},
        )
        rows = result.fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "value"])
    return pd.DataFrame(rows, columns=["date", "value"])
