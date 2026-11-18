"""Temmuz 2026 korpusunun yeniden-oynatım uyumluluğu (A23-3, A27).

`IRRADIANCE_SOURCE=clearsky` yalnız Temmuz 2026 korpusunu (G4/B4/A25) yeniden-oynatmak
için vardır. A27 ile aynı anahtar, Temmuz'daki eski simülatör davranışlarını da korur:
vergili fiyata KDV'nin ikinci kez eklenmesi, fatura→kWh dönüşümünde sabit 0,5 TL/kWh ve
UTC saatli PV'nin yerel-saat yüküne konumdan eşlenmesi. Üretim yolu (PVGIS TMY önbelleği)
bunların hiçbirini kullanmaz. Eşdeğerliği `regression_clearsky_replay` kanıtlar.
"""
from __future__ import annotations

import os


def july_2026_replay() -> bool:
    return os.environ.get("IRRADIANCE_SOURCE") == "clearsky"
