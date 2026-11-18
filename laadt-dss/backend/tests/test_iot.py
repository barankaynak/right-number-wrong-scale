"""
Tests for Task 3.1 — IoT data ingestion layer.

Tests run against the real PostgreSQL container (same as all other Phase tests).
TimescaleDB extension may not be installed; tests cover the plain-table fallback.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def init_schema():
    """Ensure the iot_measurements table exists before each test."""
    from app.digital_twin.iot.timeseries_db import init_timeseries_schema
    import app.api.routes.iot as iot_routes
    iot_routes._schema_ready = False  # force re-init
    init_timeseries_schema()


# ---------------------------------------------------------------------------
# timeseries_db tests
# ---------------------------------------------------------------------------

class TestTimeseriesDb:
    def test_write_and_read_roundtrip(self):
        from app.digital_twin.iot.timeseries_db import write_measurement, read_timeseries

        now = datetime.now(timezone.utc)
        write_measurement("test_asset", "pv/power", 1234.5, now)

        start = now - timedelta(seconds=5)
        end = now + timedelta(seconds=5)
        df = read_timeseries("test_asset", "pv/power", start, end)

        assert len(df) >= 1
        assert abs(df["value"].iloc[-1] - 1234.5) < 0.01

    def test_get_latest(self):
        from app.digital_twin.iot.timeseries_db import write_measurement, get_latest

        now = datetime.now(timezone.utc)
        write_measurement("asset_latest", "weather/temp", 22.7, now)

        value, ts = get_latest("asset_latest", "weather/temp")
        assert value is not None
        assert abs(value - 22.7) < 0.01
        assert ts is not None

    def test_get_latest_missing_returns_none(self):
        from app.digital_twin.iot.timeseries_db import get_latest

        value, ts = get_latest("nonexistent_asset_xyz", "pv/power")
        assert value is None
        assert ts is None

    def test_empty_timeseries_returns_empty_df(self):
        from app.digital_twin.iot.timeseries_db import read_timeseries

        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        past_end = datetime(2000, 1, 2, tzinfo=timezone.utc)
        df = read_timeseries("no_such_asset", "bess/soc", past, past_end)
        assert df.empty

    def test_bulk_write(self):
        from app.digital_twin.iot.timeseries_db import (
            write_measurements_bulk, read_timeseries,
        )

        now = datetime.now(timezone.utc)
        rows = [
            {"asset_id": "bulk_asset", "metric": "bess/soc", "value": float(50 + i), "time": now + timedelta(seconds=i)}
            for i in range(5)
        ]
        write_measurements_bulk(rows)

        df = read_timeseries(
            "bulk_asset", "bess/soc",
            now - timedelta(seconds=1),
            now + timedelta(seconds=10),
        )
        assert len(df) >= 5


# ---------------------------------------------------------------------------
# inverter_apis tests
# ---------------------------------------------------------------------------

class TestInverterApis:
    @pytest.mark.parametrize("vendor", ["solaredge", "huawei", "fronius"])
    def test_get_adapter_returns_valid_output(self, vendor):
        from app.digital_twin.iot.inverter_apis import get_adapter

        adapter = get_adapter(vendor)
        output = adapter.get_current_output("test_system")

        assert "power_w" in output
        assert "daily_kwh" in output
        assert "string_data" in output
        assert isinstance(output["string_data"], list)
        assert output["power_w"] >= 0

    @pytest.mark.parametrize("vendor", ["solaredge", "huawei", "fronius"])
    def test_daily_summary_has_required_keys(self, vendor):
        from app.digital_twin.iot.inverter_apis import get_adapter

        adapter = get_adapter(vendor)
        summary = adapter.get_daily_summary("test_system")

        assert "date" in summary
        assert "energy_kwh" in summary
        assert "performance_ratio_pct" in summary
        assert summary["energy_kwh"] >= 0

    def test_unknown_vendor_raises(self):
        from app.digital_twin.iot.inverter_apis import get_adapter

        with pytest.raises(ValueError, match="Unknown inverter vendor"):
            get_adapter("unknown_brand")

    def test_list_supported_vendors(self):
        from app.digital_twin.iot.inverter_apis import list_supported_vendors

        vendors = list_supported_vendors()
        assert "solaredge" in vendors
        assert "huawei" in vendors
        assert "fronius" in vendors


# ---------------------------------------------------------------------------
# mqtt_client tests
# ---------------------------------------------------------------------------

class TestMqttClient:
    def test_topic_parser(self):
        from app.digital_twin.iot.mqtt_client import _parse_topic

        asset_id, metric = _parse_topic("dt/asset_001/pv/power")
        assert asset_id == "asset_001"
        assert metric == "pv/power"

    def test_topic_parser_invalid(self):
        from app.digital_twin.iot.mqtt_client import _parse_topic

        assert _parse_topic("invalid/topic") == (None, None)
        assert _parse_topic("dt/asset/unknown/metric") == (None, None)

    def test_payload_parser_numeric_string(self):
        from app.digital_twin.iot.mqtt_client import _parse_payload

        assert _parse_payload(b"42.7") == pytest.approx(42.7)

    def test_payload_parser_json(self):
        from app.digital_twin.iot.mqtt_client import _parse_payload

        assert _parse_payload(b'{"value": 55.3}') == pytest.approx(55.3)

    def test_payload_parser_invalid_returns_none(self):
        from app.digital_twin.iot.mqtt_client import _parse_payload

        assert _parse_payload(b"not_a_number") is None

    def test_publish_simulated_reading_persists(self):
        from app.digital_twin.iot.mqtt_client import MqttClient
        from app.digital_twin.iot.timeseries_db import get_latest

        client = MqttClient()
        client.publish_simulated_reading("mqtt_test_asset", "weather/temp", 28.1)

        value, ts = get_latest("mqtt_test_asset", "weather/temp")
        assert value is not None
        assert abs(value - 28.1) < 0.1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestIoTApi:
    def test_ingest_single(self, client):
        payload = {
            "readings": [
                {"asset_id": "api_asset", "metric": "pv/power", "value": 5000.0}
            ]
        }
        resp = client.post("/api/v1/iot/ingest", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ingested"] == 1

    def test_ingest_batch(self, client):
        readings = [
            {"asset_id": "batch_api_asset", "metric": "bess/soc", "value": float(60 + i)}
            for i in range(3)
        ]
        resp = client.post("/api/v1/iot/ingest", json={"readings": readings})
        assert resp.status_code == 200
        assert resp.json()["ingested"] == 3

    def test_latest_readings_endpoint(self, client):
        # Seed data first
        client.post(
            "/api/v1/iot/ingest",
            json={"readings": [{"asset_id": "latest_api_asset", "metric": "pv/irradiance", "value": 750.0}]},
        )
        resp = client.get("/api/v1/iot/latest_api_asset/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        irr_entry = next((d for d in data if d["metric"] == "pv/irradiance"), None)
        assert irr_entry is not None
        assert irr_entry["value"] == pytest.approx(750.0, rel=0.01)

    def test_inverter_current_endpoint(self, client):
        resp = client.get("/api/v1/iot/inverter/solaredge/current?system_id=sys_001")
        assert resp.status_code == 200
        body = resp.json()
        assert "power_w" in body
        assert "string_data" in body

    def test_inverter_unknown_vendor_400(self, client):
        resp = client.get("/api/v1/iot/inverter/unknown_vendor/current?system_id=x")
        assert resp.status_code == 400

    def test_timeseries_endpoint(self, client):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=5)).isoformat()
        end = (now + timedelta(minutes=1)).isoformat()

        # Seed
        client.post(
            "/api/v1/iot/ingest",
            json={"readings": [{"asset_id": "ts_api_asset", "metric": "meter/import", "value": 1.5}]},
        )

        resp = client.get(
            "/api/v1/iot/ts_api_asset/timeseries",
            params={"metric": "meter/import", "start": start, "end": end},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 1
        assert len(body["data"]) == body["count"]
