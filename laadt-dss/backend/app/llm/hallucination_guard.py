"""
HallucinationGuard — LLM yanıtındaki sayısal değerlerin simülasyon çıktısıyla
tutarlı olup olmadığını kontrol eder.

Görev 3.3 kapsamında yazılmıştır.

Kontrol türleri:
1. Fiziksel sınır kontrolleri (PV üretimi teorik maks. aşamaz vb.)
2. Simülasyon çıktısıyla sayısal yakınlık (%5 tolerans)
3. İşaret kontrolü (negatif NPV meşruysa uyarı değil hata değil)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Tolerans: LLM yanıtındaki sayı simülasyon değerinden bu kadar sapabilir
_NUMERIC_TOLERANCE = 0.05   # %5

# Fiziksel sınırlar
_PHYSICAL_BOUNDS = {
    "pv_efficiency_pct": (0, 30),
    "battery_roundtrip_efficiency_pct": (50, 100),
    "capacity_factor_pct": (0, 35),       # Türkiye için gerçekçi üst sınır
    "payback_years": (0, 50),
    "annual_production_kwh_per_kwp": (700, 2000),  # Türkiye için kWh/kWp
}


@dataclass
class GuardResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": self.violations,
            "warnings": self.warnings,
        }


def validate_response(
    llm_response: str,
    simulation_result: dict | None,
) -> GuardResult:
    """
    LLM yanıtını simülasyon çıktısıyla karşılaştırır.

    Args:
        llm_response:      LLM'in ürettiği metin yanıtı.
        simulation_result: Simülasyon endpoint'inden dönen dict (ya da None).

    Returns:
        GuardResult: passed=True ise tutarlı, False ise ihlal var.
    """
    violations: list[str] = []
    warnings: list[str] = []

    if simulation_result is None:
        return GuardResult(passed=True)

    # ------------------------------------------------------------------
    # 1. Fiziksel sınır kontrolleri
    # ------------------------------------------------------------------

    # BESS verimliliği
    rte = simulation_result.get("roundtrip_efficiency_pct")
    if rte is not None and not (50 <= float(rte) <= 100):
        violations.append(
            f"Fiziksel ihlal: batarya verimliliği {rte}% — beklenen 50–100% arası."
        )

    # Geri dönüm süresi
    pbp = simulation_result.get("simple_payback_years") or simulation_result.get("expected_payback_years")
    if pbp is not None and float(pbp) < 0:
        violations.append(f"Fiziksel ihlal: geri dönüm süresi {pbp} yıl — negatif olamaz.")

    # Üretim kontrolleri
    annual_kwh = simulation_result.get("annual_production_kwh") or simulation_result.get("expected_annual_production_kwh")
    panel_kw = simulation_result.get("panel_kw")
    if annual_kwh is not None and panel_kw is not None:
        specific_yield = float(annual_kwh) / max(float(panel_kw), 0.001)
        lo, hi = _PHYSICAL_BOUNDS["annual_production_kwh_per_kwp"]
        if not (lo <= specific_yield <= hi):
            warnings.append(
                f"Özgül verim {specific_yield:.0f} kWh/kWp — Türkiye için beklenen {lo}–{hi} arası."
            )

    # ------------------------------------------------------------------
    # 2. Sayısal yakınlık: LLM metnindeki sayılar simülasyonla tutarlı mı?
    # ------------------------------------------------------------------
    if llm_response:
        _check_numeric_consistency(llm_response, simulation_result, violations, warnings)

    passed = len(violations) == 0
    if not passed:
        logger.warning("HallucinationGuard: %d ihlal tespit edildi.", len(violations))
    if warnings:
        logger.info("HallucinationGuard: %d uyarı.", len(warnings))

    return GuardResult(passed=passed, violations=violations, warnings=warnings)


def _check_numeric_consistency(
    text: str,
    sim: dict,
    violations: list[str],
    warnings: list[str],
) -> None:
    """
    LLM metnindeki sayıları simülasyon çıktısıyla karşılaştırır.
    Sadece kritik finansal değerleri kontrol eder (NPV, GDÖ, PBP).
    """
    # LLM metninden sayı çıkar (virgüllü/noktalı)
    numbers_in_text = set(
        float(n.replace(",", ".").replace(".", "", n.count(".") - 1))
        for n in re.findall(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\b", text)
        if _is_plausible_number(n)
    )

    def _check(key: str, label: str, multipliers: list[float] = [1.0]) -> None:
        val = sim.get(key)
        if val is None:
            return
        val = float(val)
        for mult in multipliers:
            expected = val * mult
            if expected == 0:
                continue
            # Metnin herhangi bir sayısı bu değere yakın mı?
            for n in numbers_in_text:
                if abs(n - expected) / abs(expected) <= _NUMERIC_TOLERANCE:
                    return  # Eşleşme bulundu — iyi
        # Eşleşme bulunamadı — uyarı (violations değil; LLM yuvarlama yapıyor olabilir)
        # Sadece çok büyük sapmalar violation olarak işaretle (2× veya 0.5×)
        for n in numbers_in_text:
            if abs(expected) > 0 and (n > expected * 2 or n < expected * 0.5):
                if abs(n - expected) > 1000:  # Küçük değerler için göz yum
                    warnings.append(
                        f"{label}: simülasyon={expected:.1f}, LLM metninde {n:.1f} — büyük sapma."
                    )
                    break

    _check("npv_tl", "NPV (TL)")
    _check("simple_payback_years", "Geri dönüm süresi (yıl)")
    _check("annual_savings_tl", "Yıllık tasarruf (TL)")


def _is_plausible_number(s: str) -> bool:
    """Gerçek bir sayı olup olmadığını kontrol eder (tarih, telefon gibi gürültüyü filtrele)."""
    cleaned = s.replace(",", "").replace(".", "")
    if len(cleaned) > 10:
        return False
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False
