import numpy as np

from app.simulation.loads import standard_profiles


def generate_load_profile(stakeholder_type: str, annual_consumption_kwh: float) -> np.ndarray:
    """
    Paydaş tipine göre 8760 saatlik yük profili (kWh, toplam = annual_consumption_kwh).

    Profil ŞEKİLLERİ bilimsel/atıflanabilir kaynaklardan gelir (bkz. loads/standard_profiles.py):
      - residential → BDEW/VDEW H0 standart yük profili (demandlib)
      - commercial  → BDEW/VDEW G0 (genel ticari) standart yük profili (demandlib)
      - municipal   → belgelenmiş sentetik sokak-aydınlatması (gece) profili — BDEW gap
      - utility     → kompozit dağıtım profili (utility_profile.py)
    Mutlak büyüklük yıllık tüketimden gelir (ev senaryosunda faturadan türetilir).
    """
    if stakeholder_type == "utility":
        from app.simulation.profiles.utility_profile import generate_utility_profile
        return generate_utility_profile(annual_consumption_kwh=annual_consumption_kwh)

    return standard_profiles.profile_for(stakeholder_type, annual_consumption_kwh)
