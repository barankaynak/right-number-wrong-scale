"""
ev_load.py — Elektrikli araç (EV) ev-şarj yükü modeli (kaynak-belgeli).

Haneleri çeşitlendirir: bir kısmında EV var (penetrasyon), kalanında yok.
EV'li hane, taban tüketimine ek olarak:
  - yıllık ~3.000 kWh (turkey_parameters.EV_ANNUAL_KWH_HOME),
  - ~7,4 kW şarj gücü,
  - AKŞAM pikiyle çakışan şarj (ort. fişe takma ~17:06) getirir.

EV eş-zamanlılık (demand factor):
  MDPI World Electric Vehicle Journal 16(9):537 (2025) — konut EVCS ≤6,6 kW için
  demand factor 1→274 araçta 0,5 → 0,31; 6,6–22 kW için 0,5 → 0,22.
  Bunu Rusck-benzeri df_ev(n) = c∞_ev + (0.5 − c∞_ev)/√n ile modelliyoruz;
  ev-tipi ≤7,4 kW için c∞_ev = 0.30 (n=1 → 0.50, n=274 → ~0.31 ile uyumlu).

Şarj zamanlaması: ort. fişe takma 17:06 / çıkarma 08:54 (ScienceDirect 2025,
İsveç gerçek-veri) → mesken akşam pikiyle çakışır (şebeke için en kötü durum),
bu yüzden EV tepe katkısı taban tepeye EKLENİR.
"""

import math

import numpy as np

from app.simulation.loads.turkey_parameters import (
    EV_ANNUAL_KWH_HOME, EV_CHARGER_KW,
)

# EV ev-şarjı demand-factor limiti (≤7,4 kW ev cihazı), MDPI 2025 ile uyumlu
EV_DEMAND_C_INF: float = 0.30
EV_DEMAND_SINGLE: float = 0.50   # tek şarj cihazının demand factor'ü (n=1)

# Tek hanenin GÜNLÜK EV şarj şekli (24 saatlik göreli ağırlık) — kontrolsüz akşam şarjı.
# Fişe takma ~17:00, akşam pikinde (18–20) yoğun, gece azalan kuyruk, gündüz (evde yok) ~0.
# Kaynak: ScienceDirect 2025 (İsveç gerçek-veri) ort. fişe takma 17:06 / çıkarma 08:54 →
# mesken akşam pikiyle çakışır. Bu şekil PV üretimiyle örtüşmez (öğle üretimi, akşam şarj),
# dolayısıyla ev fizibilitesinde bataryayı değerli kılar (fiziksel olarak doğru).
_EV_HOURLY_WEIGHTS = np.array([
    # 00    01    02    03    04    05    06    07    08    09    10    11
    0.35, 0.30, 0.25, 0.20, 0.15, 0.10, 0.10, 0.05, 0.02, 0.00, 0.00, 0.00,
    # 12    13    14    15    16    17    18    19    20    21    22    23
    0.00, 0.00, 0.00, 0.00, 0.20, 0.70, 1.00, 1.00, 0.95, 0.85, 0.70, 0.50,
], dtype=float)


def ev_annual_kwh() -> float:
    """EV başına yıllık ev-şarj enerjisi (kWh)."""
    return EV_ANNUAL_KWH_HOME


def ev_demand_factor(n_ev: int) -> float:
    """N_ev EV-şarj cihazı için demand factor.
    df_ev(n) = c∞_ev + (0.5 − c∞_ev)/√n. n=1 → 0.50, n=274 → ~0.312."""
    if n_ev <= 1:
        return EV_DEMAND_SINGLE
    return EV_DEMAND_C_INF + (EV_DEMAND_SINGLE - EV_DEMAND_C_INF) / math.sqrt(n_ev)


def ev_coincident_peak_kw(n_ev: int, charger_kw: float = EV_CHARGER_KW) -> float:
    """N_ev EV-hanenin trafoda oluşturduğu toplam eş-zamanlı şarj tepesi (kW)
    = N_ev × şarj_gücü × df_ev(N_ev)."""
    if n_ev <= 0:
        return 0.0
    return n_ev * charger_kw * ev_demand_factor(n_ev)


def ev_diversified_household_kw(n_ev: int, charger_kw: float = EV_CHARGER_KW) -> float:
    """EV-hane başına yük-akışına konacak diversite-sonrası şarj yükü (kW)
    = şarj_gücü × df_ev(N_ev). Toplandığında ev_coincident_peak_kw'ye eşittir."""
    if n_ev <= 0:
        return 0.0
    return charger_kw * ev_demand_factor(n_ev)


def ev_household_count(n_households: int, penetration: float) -> int:
    """Penetrasyona göre EV'li hane sayısı (yuvarlanmış)."""
    return int(round(max(0.0, min(1.0, penetration)) * n_households))


def ev_charging_profile(annual_kwh: float = EV_ANNUAL_KWH_HOME) -> np.ndarray:
    """Tek hanenin 8760 saatlik EV şarj yükü (kWh), toplam = annual_kwh.

    Günlük akşam-yoğun şekil (_EV_HOURLY_WEIGHTS) 365 güne yayılır ve toplam
    yıllık enerjiye normalize edilir. Ev fizibilitesinde taban (BDEW) yüküne
    EKLENİR — EV enerjisi konut şeklini değil, kendi akşam şeklini alır
    (öğle PV üretimiyle örtüşmez → öz-tüketim/batarya etkisi doğru yansır)."""
    if annual_kwh <= 0:
        return np.zeros(8760, dtype=float)
    daily = _EV_HOURLY_WEIGHTS / _EV_HOURLY_WEIGHTS.sum()  # günlük şekil, toplam=1
    yearly = np.tile(daily, 365)                            # 8760 saat, göreli
    return yearly / yearly.sum() * annual_kwh               # yıllık toplam garanti


if __name__ == "__main__":
    assert abs(ev_demand_factor(1) - 0.50) < 1e-9
    assert abs(ev_demand_factor(274) - 0.312) < 0.01, ev_demand_factor(274)
    print("ev_demand_factor(1) =", ev_demand_factor(1))
    print("ev_demand_factor(10) =", round(ev_demand_factor(10), 3))
    print("ev_demand_factor(274) =", round(ev_demand_factor(274), 3))
    print("ev_diversified/hane (N_ev=10) =", round(ev_diversified_household_kw(10), 3), "kW")
    prof = ev_charging_profile(3000.0)
    byhour = prof.reshape(-1, 24).mean(axis=0)
    assert abs(prof.sum() - 3000.0) < 1e-6, prof.sum()
    assert len(prof) == 8760
    print("ev_charging_profile: sum =", round(float(prof.sum()), 1),
          "peak_hour =", int(np.argmax(byhour)), "(akşam)")
    print("OK")
