"""
MQTT client for IoT data ingestion.

Subscribes to sensor topics published by inverters, meters, and weather
stations. Each incoming message is written to TimescaleDB via timeseries_db.

Topic schema:
    dt/{asset_id}/pv/power          → Instantaneous PV output (W)
    dt/{asset_id}/pv/irradiance     → Solar irradiance (W/m²)
    dt/{asset_id}/bess/soc          → Battery state-of-charge (%)
    dt/{asset_id}/bess/soh          → Battery state-of-health (%)
    dt/{asset_id}/meter/import      → Grid import energy counter (kWh)
    dt/{asset_id}/meter/export      → Grid export energy counter (kWh)
    dt/{asset_id}/weather/temp      → Ambient temperature (°C)

Usage:
    client = MqttClient(broker_host="emqx", broker_port=1883)
    client.start()          # non-blocking — runs subscriber in background thread
    ...
    client.stop()
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False

from app.digital_twin.iot.timeseries_db import write_measurement

logger = logging.getLogger(__name__)

# Metric suffix → DB metric name mapping
_TOPIC_TO_METRIC: dict[str, str] = {
    "pv/power": "pv/power",
    "pv/irradiance": "pv/irradiance",
    "bess/soc": "bess/soc",
    "bess/soh": "bess/soh",
    "meter/import": "meter/import",
    "meter/export": "meter/export",
    "weather/temp": "weather/temp",
}


def _parse_topic(topic: str) -> tuple[str, str] | tuple[None, None]:
    """
    Parse 'dt/{asset_id}/{metric_path}' and return (asset_id, metric).
    Returns (None, None) on invalid format.
    """
    parts = topic.split("/", 2)
    if len(parts) != 3 or parts[0] != "dt":
        return None, None
    asset_id = parts[1]
    metric_path = parts[2]
    metric = _TOPIC_TO_METRIC.get(metric_path)
    if metric is None:
        return None, None
    return asset_id, metric


def _parse_payload(payload: bytes) -> float | None:
    """
    Accept plain numeric strings ("42.7") or JSON objects ({"value": 42.7}).
    Returns None on parse failure.
    """
    try:
        text = payload.decode("utf-8").strip()
        try:
            return float(text)
        except ValueError:
            data = json.loads(text)
            return float(data.get("value", data.get("v")))
    except Exception:
        return None


class MqttClient:
    """
    Wraps a paho-mqtt subscriber and persists incoming readings to TimescaleDB.

    When paho-mqtt is not installed the client runs in *simulation mode*:
    it still exposes the same API but generates synthetic sensor readings
    internally, which is sufficient for Phase 3 development without hardware.
    """

    def __init__(
        self,
        broker_host: str = "emqx",
        broker_port: int = 1883,
        client_id: str = "laadt-dss-subscriber",
        on_message_callback: Optional[Callable[[str, str, float], None]] = None,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self._on_message_callback = on_message_callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client = None

        if not PAHO_AVAILABLE:
            logger.warning(
                "paho-mqtt not installed — MqttClient will run in simulation mode. "
                "Install paho-mqtt for real broker connectivity."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the subscriber in a background daemon thread."""
        self._stop_event.clear()
        if PAHO_AVAILABLE:
            self._thread = threading.Thread(
                target=self._run_paho, daemon=True, name="mqtt-subscriber"
            )
        else:
            self._thread = threading.Thread(
                target=self._run_simulation, daemon=True, name="mqtt-sim"
            )
        self._thread.start()
        logger.info(
            "MqttClient started (mode=%s, broker=%s:%d)",
            "paho" if PAHO_AVAILABLE else "simulation",
            self.broker_host,
            self.broker_port,
        )

    def stop(self) -> None:
        """Signal the background thread to stop."""
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("MqttClient stopped")

    def publish_simulated_reading(
        self, asset_id: str, metric: str, value: float
    ) -> None:
        """
        Manually inject a reading (used by tests and the IoT data API endpoint).
        Writes directly to TimescaleDB without going through MQTT.
        """
        _persist(asset_id, metric, value)

    # ------------------------------------------------------------------
    # paho-mqtt mode
    # ------------------------------------------------------------------

    def _run_paho(self) -> None:
        import paho.mqtt.client as mqtt_lib

        # paho-mqtt 2.x requires explicit CallbackAPIVersion; fall back for 1.x
        try:
            client = mqtt_lib.Client(
                callback_api_version=mqtt_lib.CallbackAPIVersion.VERSION1,
                client_id=self.client_id,
            )
        except AttributeError:
            client = mqtt_lib.Client(client_id=self.client_id)  # paho 1.x
        self._client = client
        client.on_connect = self._on_connect
        client.on_message = self._on_message_paho
        client.on_disconnect = self._on_disconnect

        while not self._stop_event.is_set():
            try:
                client.connect(self.broker_host, self.broker_port, keepalive=60)
                client.loop_forever()
            except Exception as exc:
                logger.error("MQTT connection error: %s — retrying in 10s", exc)
                time.sleep(10)

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info("Connected to MQTT broker %s:%d", self.broker_host, self.broker_port)
            client.subscribe("dt/#", qos=1)
        else:
            logger.error("MQTT connection refused, rc=%d", rc)

    def _on_message_paho(self, client, userdata, msg) -> None:
        asset_id, metric = _parse_topic(msg.topic)
        if asset_id is None:
            return
        value = _parse_payload(msg.payload)
        if value is None:
            logger.warning("Unparseable payload on topic %s: %r", msg.topic, msg.payload)
            return
        _persist(asset_id, metric, value)
        if self._on_message_callback:
            self._on_message_callback(asset_id, metric, value)

    def _on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%d)", rc)

    # ------------------------------------------------------------------
    # Simulation mode (no real broker)
    # ------------------------------------------------------------------

    def _run_simulation(self) -> None:
        """
        Generates synthetic sensor readings for a demo asset every 60 seconds.
        Mimics a 10 kW PV system + 14.4 kWh LFP battery in Ankara.
        """
        import math
        import random

        asset_id = "demo_asset_001"
        soc = 50.0  # %
        soh = 98.0  # %

        tick = 0
        while not self._stop_event.wait(timeout=60):
            hour = (tick % 24)
            # Simple sinusoidal PV profile (peak at noon)
            irr = max(0.0, 800 * math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
            pv_power = irr * 10 * 0.18 * random.uniform(0.95, 1.05)  # ~10 kW peak

            # Naive SoC update
            if irr > 0:
                soc = min(95.0, soc + random.uniform(1, 3))
            else:
                soc = max(10.0, soc - random.uniform(0.5, 2))

            soh = max(80.0, soh - 0.00005)  # very slow calendar aging

            readings = [
                (asset_id, "pv/power", pv_power),
                (asset_id, "pv/irradiance", irr),
                (asset_id, "bess/soc", soc),
                (asset_id, "bess/soh", soh),
                (asset_id, "meter/import", max(0, random.uniform(0, 0.5))),
                (asset_id, "meter/export", max(0, pv_power / 1000 * 0.1)),
                (asset_id, "weather/temp", 20 + 5 * math.sin(math.pi * hour / 12) + random.gauss(0, 1)),
            ]

            for aid, metric, val in readings:
                try:
                    _persist(aid, metric, val)
                    if self._on_message_callback:
                        self._on_message_callback(aid, metric, val)
                except Exception as exc:
                    logger.debug("Simulation persist error: %s", exc)

            tick += 1
            logger.debug("Simulation tick %d: pv_power=%.1f W, soc=%.1f%%", tick, pv_power, soc)


def _persist(asset_id: str, metric: str, value: float) -> None:
    """Write a reading to TimescaleDB."""
    try:
        write_measurement(asset_id, metric, value, datetime.now(timezone.utc))
    except Exception as exc:
        logger.error("Failed to persist measurement %s/%s: %s", asset_id, metric, exc)
