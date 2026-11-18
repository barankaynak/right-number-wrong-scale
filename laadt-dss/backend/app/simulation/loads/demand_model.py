"""
demand_model.py — Yük akışı için tepe talep + eş-zamanlılık (diversity) modeli.

Kaynak-belgeli, parametreli, dağıtım planlama literatürüne dayalı:
  - Velander formülü (hane tepe gücü, yıllık enerjiden):
        Pmax1 = k1·E + k2·√E
    konut katsayıları k1 = 0.33e-3 h⁻¹, k2 = 0.05.
    Kaynak: Velander (1935); Dickert & Schegner, "Residential Load Models for
    Network Planning Purposes", TU Dresden / IEEE MEPS 2011.
  - Eş-zamanlılık (coincidence) faktörü (Rusck 1956):
        cf(N) = c∞ + (1 − c∞)/√N
    c∞ = ortalama/tepe oranı (N→∞ limiti). pandapower "Dickert LV Networks"
    aynı modeli c∞ = 0.10 ile kullanır.
    Kaynak: Rusck, S. (1956), ASEA Journal 29:59-61; Dickert & Schegner 2011;
    Fürst et al., CIRED 2020.

Kullanım (LV şebeke): bir trafoya bağlı N hanenin her birinin yük-akışındaki yükü
= bireysel_tepe × cf(N)  ≈ hane başı ADMD (after-diversity maximum demand).
Böylece trafo, tek tek tepelerin toplamını değil, gerçekçi EŞ-ZAMANLI tepeyi görür.
"""

import math

# Velander konut katsayıları (Dickert & Schegner 2011)
VELANDER_K1: float = 0.33e-3   # h⁻¹  (E=3500 kWh → 1.155 kW terimi)
VELANDER_K2: float = 0.05      # (E=3500 kWh → 2.958 kW terimi) → Pmax1 ≈ 4.1 kW

# Rusck eş-zamanlılık limiti c∞ (ortalama/tepe). pandapower Dickert LV = 0.10.
COINCIDENCE_C_INF: float = 0.10


def velander_peak_kw(annual_kwh: float, k1: float = VELANDER_K1, k2: float = VELANDER_K2) -> float:
    """Tek hanenin (diversite ÖNCESİ) bireysel tepe gücü, yıllık enerjiden.
    Velander: Pmax1 = k1·E + k2·√E. Örn. E=2800 → ~3.57 kW; E=3500 → ~4.11 kW."""
    if annual_kwh <= 0:
        return 0.0
    return k1 * annual_kwh + k2 * math.sqrt(annual_kwh)


def coincidence_factor(n: int, c_inf: float = COINCIDENCE_C_INF) -> float:
    """Rusck eş-zamanlılık faktörü cf(N) = c∞ + (1−c∞)/√N.
    n=1 → 1.0 (tek hane), n arttıkça c∞'ye iner. Örn. N=40 → ~0.242."""
    if n <= 1:
        return 1.0
    return c_inf + (1.0 - c_inf) / math.sqrt(n)


def admd_kw(annual_kwh: float, k1: float = VELANDER_K1) -> float:
    """After-Diversity Maximum Demand (hane başı, N→∞ limiti) ≈ k1·E.
    Örn. E=2800 → ~0.92 kW/hane (Dickert 'basic' satırı ~0.4–1.2 kW ile uyumlu)."""
    return k1 * annual_kwh


def diversified_household_kw(annual_kwh: float, n: int, c_inf: float = COINCIDENCE_C_INF) -> float:
    """N hane bir trafoyu paylaşırken HER hanenin yük-akışına konacak
    diversite-sonrası yükü: bireysel_tepe × cf(N).
    Toplandığında trafo eş-zamanlı tepeyi görür (N × bu değer)."""
    return velander_peak_kw(annual_kwh) * coincidence_factor(n, c_inf)


def coincident_peak_kw(annual_kwh_per_household: float, n: int, c_inf: float = COINCIDENCE_C_INF) -> float:
    """N özdeş hanenin trafoda oluşturduğu toplam eş-zamanlı tepe (kW)
    = N × bireysel_tepe × cf(N)."""
    return n * diversified_household_kw(annual_kwh_per_household, n, c_inf)


if __name__ == "__main__":
    # Bilimsel değerlerin duman testi (literatürle uyum)
    assert abs(velander_peak_kw(3500) - 4.11) < 0.05, velander_peak_kw(3500)
    assert abs(velander_peak_kw(2800) - 3.57) < 0.05, velander_peak_kw(2800)
    assert abs(coincidence_factor(40) - 0.242) < 0.01, coincidence_factor(40)
    assert abs(admd_kw(2800) - 0.924) < 0.01, admd_kw(2800)
    print("velander(2800) =", round(velander_peak_kw(2800), 3), "kW")
    print("cf(40) =", round(coincidence_factor(40), 3))
    print("admd(2800) =", round(admd_kw(2800), 3), "kW/hane")
    print("diversified(2800, N=40) =", round(diversified_household_kw(2800, 40), 3), "kW/hane")
    print("OK")
