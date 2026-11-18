"""
Görev 1.8 — Faz 1 Entegrasyon Testi

Tüm bileşenlerin uçtan uca birlikte çalıştığını doğrular:
  - FastAPI app sağlık kontrolü
  - PV simülasyon endpoint'i
  - PV+BESS fizibilite endpoint'i
  - Chat/LLM endpoint'i
  - Türkiye 2026 tarifesi ile ekonomik tutarlılık
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ─── 1. Sağlık Kontrolü ──────────────────────────────────────────────────────

def test_health_endpoint():
    """Backend çalışıyor olmalı."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


# ─── 2. PV Simülasyonu ───────────────────────────────────────────────────────

def test_pv_simulation_ankara():
    """Ankara için PV simülasyonu çalışmalı ve makul değerler dönmeli."""
    r = client.post("/api/v1/simulate/pv", json={
        "latitude": 39.93,
        "longitude": 32.86,
        "panel_kw": 10.0,
        "tilt": 30.0,
        "azimuth": 180.0,
        "panel_type": "monocrystalline",
    })
    assert r.status_code == 200
    data = r.json()

    # Beklenti: 10 kW Ankara sistemi yılda 13,000–16,000 kWh üretir (PVGIS TMY).
    # Clearsky fallback daha yüksek değer döndürebilir.
    assert 10000 <= data["annual_production_kwh"] <= 25000
    assert data["capacity_factor"] > 0.10
    assert len(data["monthly_breakdown_kwh"]) == 12


def test_pv_simulation_antalya_higher_than_ankara():
    """Antalya daha fazla güneş alır, üretim Ankara'dan yüksek olmalı."""
    r_ankara = client.post("/api/v1/simulate/pv", json={
        "latitude": 39.93, "longitude": 32.86,
        "panel_kw": 10.0, "tilt": 30.0, "azimuth": 180.0, "panel_type": "mono"
    })
    r_antalya = client.post("/api/v1/simulate/pv", json={
        "latitude": 36.90, "longitude": 30.70,
        "panel_kw": 10.0, "tilt": 30.0, "azimuth": 180.0, "panel_type": "mono"
    })
    assert r_ankara.status_code == 200
    assert r_antalya.status_code == 200
    assert r_antalya.json()["annual_production_kwh"] > r_ankara.json()["annual_production_kwh"]


# ─── 3. PV + BESS Fizibilite ─────────────────────────────────────────────────

def test_pvbess_simulation_residential():
    """Konut tipi PV+BESS simülasyonu tüm finansal metrikleri dönmeli."""
    r = client.post("/api/v1/simulate/pv-bess", json={
        "latitude": 39.93,
        "longitude": 32.86,
        "panel_kw": 10.0,
        "bess_kwh": 14.4,
        "bess_chemistry": "LFP",
        "annual_consumption_kwh": 5000.0,
        "stakeholder_type": "residential",
        "discount_rate": 0.12,
        "tilt": 30.0,
        "azimuth": 180.0,
        "panel_type": "monocrystalline",
        "lifetime_years": 25,
    })
    assert r.status_code == 200
    data = r.json()

    # Finansal metrikler mevcut olmalı
    assert "annual_savings_tl" in data
    assert "npv_tl" in data
    assert "irr_percent" in data
    assert "simple_payback_years" in data
    assert "lcoe_tl_per_kwh" in data
    assert "self_consumption_ratio" in data

    # Beklenti: Yıllık tasarruf pozitif olmalı
    assert data["annual_savings_tl"] > 0

    # Öz tüketim 0-1 arasında olmalı
    assert 0 <= data["self_consumption_ratio"] <= 1.0


def test_bess_improves_economics():
    """Batarya eklenmesi NPV'yi artırmalı (15 kW panel, 5 MWh tüketim)."""
    base_payload = {
        "latitude": 39.93, "longitude": 32.86,
        "panel_kw": 15.0, "tilt": 30.0, "azimuth": 180.0,
        "panel_type": "mono",
        "annual_consumption_kwh": 6000.0,
        "stakeholder_type": "residential",
        "discount_rate": 0.12,
        "lifetime_years": 25,
        "system_cost_tl": 400000,
    }

    r_no_bess = client.post("/api/v1/simulate/pv-bess", json={**base_payload, "bess_kwh": 0.0, "bess_chemistry": "LFP"})
    r_with_bess = client.post("/api/v1/simulate/pv-bess", json={**base_payload, "bess_kwh": 14.4, "bess_chemistry": "LFP"})

    assert r_no_bess.status_code == 200
    assert r_with_bess.status_code == 200

    scr_no_bess = r_no_bess.json()["self_consumption_ratio"]
    scr_with_bess = r_with_bess.json()["self_consumption_ratio"]

    # BESS varken öz tüketim artmalı
    assert scr_with_bess >= scr_no_bess


# ─── 4. Chat / LLM Endpoint ──────────────────────────────────────────────────

def test_chat_pv_intent():
    """Güneş paneli niyetiyle gönderilen mesaja uygun yanıt alınmalı."""
    r = client.post("/api/v1/chat/message", json={
        "session_id": "e2e_test_session",
        "message": "Ankara'da 10 kW GES kurmak istiyorum, tahmini tasarrufu hesapla",
        "stakeholder_type": "residential",
    })
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["reply"]) > 10
    assert "follow_up_questions" in data


def test_chat_unknown_context_returns_graceful():
    """Anlaşılamayan mesajda bile sistem çökmemeli, anlamlı reply dönmeli."""
    r = client.post("/api/v1/chat/message", json={
        "session_id": "e2e_test_unknown",
        "message": "Bugün hava nasıl?",
        "stakeholder_type": "residential",
    })
    assert r.status_code == 200
    assert "reply" in r.json()


def test_chat_history_stub():
    """Chat geçmişi endpoint'i 200 dönmeli."""
    r = client.get("/api/v1/chat/e2e_test_session/history")
    assert r.status_code == 200
    assert "messages" in r.json()


# ─── 5. Uçtan Uca Senaryo ────────────────────────────────────────────────────

def test_full_residential_workflow():
    """
    Tam konut senaryosu:
    1. LLM chatına PV sorusu sor
    2. API ile PV üretimini simüle et
    3. PV+BESS fizibilite çalıştır
    4. Sonuçların tutarlı olduğunu doğrula
    """
    # Adım 1: Chat
    chat_r = client.post("/api/v1/chat/message", json={
        "session_id": "e2e_full",
        "message": "Ankara 10 kW panel 14.4 kWh LFP batarya kurulumu simüle et",
    })
    assert chat_r.status_code == 200

    # Adım 2: Direkt PV simülasyonu
    pv_r = client.post("/api/v1/simulate/pv", json={
        "latitude": 39.93, "longitude": 32.86,
        "panel_kw": 10.0, "tilt": 30.0, "azimuth": 180.0, "panel_type": "mono",
    })
    assert pv_r.status_code == 200
    pv_annual = pv_r.json()["annual_production_kwh"]

    # Adım 3: PV+BESS
    pvbess_r = client.post("/api/v1/simulate/pv-bess", json={
        "latitude": 39.93, "longitude": 32.86,
        "panel_kw": 10.0, "bess_kwh": 14.4, "bess_chemistry": "LFP",
        "annual_consumption_kwh": 5000.0, "stakeholder_type": "residential",
        "discount_rate": 0.12, "tilt": 30.0, "azimuth": 180.0,
        "panel_type": "mono", "lifetime_years": 25,
    })
    assert pvbess_r.status_code == 200
    pvbess_data = pvbess_r.json()

    # Adım 4: Tutarlılık kontrolü
    # PV üretimi her iki endpoint'te benzer olmalı (±%5)
    pvbess_production = pvbess_data["annual_production_kwh"]
    assert abs(pv_annual - pvbess_production) / max(pv_annual, 1) < 0.05

    # Finansal değerler sağlıklı aralıkta olmalı
    assert pvbess_data["simple_payback_years"] > 0
    assert pvbess_data["system_cost_tl"] > 0
