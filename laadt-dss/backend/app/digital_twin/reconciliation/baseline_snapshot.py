"""
BaselineSnapshot — pre-investment simulation expectation store.

Manages the `asset_baselines` table:
    id          SERIAL PRIMARY KEY
    asset_id    TEXT NOT NULL
    version     INTEGER NOT NULL DEFAULT 1
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    sim_params  JSONB NOT NULL   -- original simulation inputs
    sim_results JSONB NOT NULL   -- expected outputs
    is_active   BOOLEAN NOT NULL DEFAULT TRUE

Unique constraint: one active baseline per asset_id.

sim_results fields (from pv-bess simulation):
  - expected_annual_production_kwh
  - expected_annual_savings_tl
  - expected_payback_years
  - expected_npv_tl
  - expected_irr_pct
  - expected_soh_curve: list of {year, soh_pct} (25 years)
  - assumptions: dict (tariff, panel_efficiency, etc.)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS asset_baselines (
    id          SERIAL PRIMARY KEY,
    asset_id    TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sim_params  JSONB NOT NULL,
    sim_results JSONB NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
"""

_INDEX_ASSET_DDL = """
CREATE INDEX IF NOT EXISTS idx_baselines_asset_id
    ON asset_baselines (asset_id);
"""

_INDEX_ACTIVE_DDL = """
CREATE INDEX IF NOT EXISTS idx_baselines_asset_active
    ON asset_baselines (asset_id, is_active);
"""


def init_baseline_schema() -> None:
    """Create the asset_baselines table and indexes if they do not exist."""
    with engine.begin() as conn:
        conn.execute(text(_TABLE_DDL))

    with engine.begin() as conn:
        conn.execute(text(_INDEX_ASSET_DDL))

    with engine.begin() as conn:
        conn.execute(text(_INDEX_ACTIVE_DDL))


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def create_baseline(asset_id: str, sim_params: dict, sim_results: dict) -> int:
    """
    Create a new baseline for the given asset.

    Deactivates any existing active baseline for the asset, then inserts a
    new record with version = max(previous_versions) + 1.

    Returns:
        The id of the newly created baseline record.
    """
    with engine.begin() as conn:
        # Deactivate any existing active baseline
        conn.execute(
            text(
                "UPDATE asset_baselines SET is_active = FALSE "
                "WHERE asset_id = :asset_id AND is_active = TRUE"
            ),
            {"asset_id": asset_id},
        )

        # Determine next version number
        row = conn.execute(
            text(
                "SELECT COALESCE(MAX(version), 0) FROM asset_baselines "
                "WHERE asset_id = :asset_id"
            ),
            {"asset_id": asset_id},
        ).fetchone()
        next_version = (row[0] if row else 0) + 1

        # Insert new baseline
        # Note: use CAST(:x AS jsonb) — SQLAlchemy text() parser cannot handle
        # the PostgreSQL shorthand :param::type (:: conflicts with bind-param syntax).
        result = conn.execute(
            text(
                "INSERT INTO asset_baselines "
                "  (asset_id, version, sim_params, sim_results, is_active) "
                "VALUES (:asset_id, :version, "
                "        CAST(:sim_params AS jsonb), CAST(:sim_results AS jsonb), TRUE) "
                "RETURNING id"
            ),
            {
                "asset_id": asset_id,
                "version": next_version,
                "sim_params": json.dumps(sim_params),
                "sim_results": json.dumps(sim_results),
            },
        )
        new_id = result.fetchone()[0]

    logger.info(
        "Created baseline v%d for asset '%s' (id=%d)", next_version, asset_id, new_id
    )
    return new_id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_active_baseline(asset_id: str) -> Optional[dict]:
    """
    Return the active baseline record for the asset, or None if not found.

    The returned dict has keys:
        id, asset_id, version, created_at, sim_params, sim_results, is_active
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, asset_id, version, created_at, "
                "       sim_params, sim_results, is_active "
                "FROM asset_baselines "
                "WHERE asset_id = :asset_id AND is_active = TRUE "
                "ORDER BY version DESC LIMIT 1"
            ),
            {"asset_id": asset_id},
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "asset_id": row[1],
        "version": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
        "sim_params": row[4] if isinstance(row[4], dict) else json.loads(row[4]),
        "sim_results": row[5] if isinstance(row[5], dict) else json.loads(row[5]),
        "is_active": row[6],
    }


def list_baselines(asset_id: str) -> list[dict]:
    """
    Return all baseline versions for the asset, ordered newest-first.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, asset_id, version, created_at, "
                "       sim_params, sim_results, is_active "
                "FROM asset_baselines "
                "WHERE asset_id = :asset_id "
                "ORDER BY version DESC"
            ),
            {"asset_id": asset_id},
        ).fetchall()

    return [
        {
            "id": row[0],
            "asset_id": row[1],
            "version": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "sim_params": row[4] if isinstance(row[4], dict) else json.loads(row[4]),
            "sim_results": row[5] if isinstance(row[5], dict) else json.loads(row[5]),
            "is_active": row[6],
        }
        for row in rows
    ]
