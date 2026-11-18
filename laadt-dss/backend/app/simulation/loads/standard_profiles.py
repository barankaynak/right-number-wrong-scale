"""
standard_profiles.py — 8760 saatlik NORMALİZE yük profili ŞEKİLLERİ (kaynak-belgeli).

Konut ve ticari profil şekilleri BDEW/VDEW standart yük profillerinden (SLP)
`demandlib` (oemof) ile üretilir — koda elle "sihirli sayı" gömülmez; değerler
bakımlı, atıflanabilir bir kütüphaneden gelir.

Kaynaklar:
  - BDEW/VDEW Repräsentative Lastprofile (H0 hane, G0-G6 ticari, L0-L2 tarım),
    1000 kWh/yıl'a normalize, 96 çeyrek-saatlik × 3 mevsim × 3 gün-tipi.
  - Uygulama: oemof `demandlib` (BDEW SLP Python implementasyonu).
  - Konut yüksek-çözünürlük alternatifi: CREST/Richardson (Energy & Buildings 2010).

Kullanım: profile_for(stakeholder_type, annual_kwh) → 8760 saatlik kWh dizisi
(toplamı = annual_kwh). Şekil BDEW'den, mutlak büyüklük yıllık tüketimden gelir.

NOT (dürüstlük): BDEW profilleri Alman gün-tipi/tatil takvimine dayalıdır; şekli
Türkiye'ye uyarlarken (çalışma saatleri/iklim) küçük sapma olabilir. Belediye
sokak-aydınlatması profili BDEW'de YOKTUR → belgelenmiş sentetik (gece) profil.
"""

import warnings
from functools import lru_cache

import numpy as np

# Sabit referans yıl: 2023 artık yıl DEĞİL → tam 8760 saat (365×24).
_REF_YEAR = 2023
_HOURS = 8760


@lru_cache(maxsize=8)
def _bdew_shape(slp_type: str) -> tuple:
    """BDEW SLP'nin normalize (toplam=1) 8760 saatlik şekli. demandlib ile bir kez
    hesaplanır, cache'lenir. Dönüş: tuple (hashable cache için)."""
    from demandlib import bdew  # lazy import — demandlib yoksa fallback devreye girer
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # demandlib pandas dtype FutureWarning'lerini bastır
        e_slp = bdew.ElecSlp(_REF_YEAR, holidays={})
        df = e_slp.get_profile({slp_type: 1000.0})
        # 15-dk güç → saatlik (göreli); sonra toplam=1'e normalize et
        hourly = df[slp_type].resample("h").sum().to_numpy(dtype=float)
    if hourly.shape[0] != _HOURS:
        hourly = hourly[:_HOURS] if hourly.shape[0] > _HOURS else np.pad(hourly, (0, _HOURS - hourly.shape[0]))
    total = hourly.sum()
    if total <= 0:
        hourly = np.ones(_HOURS)
        total = float(_HOURS)
    return tuple((hourly / total).tolist())


def bdew_profile(slp_type: str, annual_kwh: float) -> np.ndarray:
    """BDEW SLP şekli × yıllık tüketim → 8760 saatlik kWh (toplam = annual_kwh)."""
    shape = np.asarray(_bdew_shape(slp_type), dtype=float)
    return shape * annual_kwh


def _fallback_residential(annual_kwh: float) -> np.ndarray:
    """demandlib yoksa: belgelenmiş basit konut şekli (akşam pik ~19:00)."""
    daily = np.array([
        0.3, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.8, 0.7, 0.6, 0.5, 0.5,
        0.5, 0.5, 0.5, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5, 1.3, 0.8, 0.5,
    ])
    daily = daily / daily.sum()
    yearly = np.tile(daily, 365)
    days = np.arange(365)
    seasonal = 1.0 + 0.2 * np.sin(2 * np.pi * (days - 172) / 365)  # yazın soğutma
    yearly = yearly * np.repeat(seasonal, 24)
    return yearly / yearly.sum() * annual_kwh


def municipal_profile(annual_kwh: float) -> np.ndarray:
    """Belediye/sokak-aydınlatması — BDEW'de karşılığı YOK → belgelenmiş sentetik
    gece profili (18:00–06:00 açık, gündüz ~0). Kaynak boşluğu makalede belirtilir."""
    daily = np.array([
        1.5, 1.5, 1.5, 1.5, 1.5, 1.2, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1,
        0.1, 0.1, 0.1, 0.1, 0.1, 0.8, 1.2, 1.5, 1.5, 1.5, 1.5, 1.5,
    ])
    daily = daily / daily.sum()
    yearly = np.tile(daily, 365)
    return yearly / yearly.sum() * annual_kwh


def profile_for(stakeholder_type: str, annual_kwh: float) -> np.ndarray:
    """Paydaş tipi → 8760 saatlik yük profili (kWh, toplam = annual_kwh).
    residential→BDEW H0, commercial→BDEW G0, municipal→sentetik gece,
    diğer→H0. (utility load_profile.py'de ayrı ele alınır.)"""
    try:
        if stakeholder_type == "residential":
            return bdew_profile("h0", annual_kwh)
        if stakeholder_type == "commercial":
            return bdew_profile("g0", annual_kwh)
        if stakeholder_type == "municipal":
            return municipal_profile(annual_kwh)
        return bdew_profile("h0", annual_kwh)
    except Exception as exc:
        # A23: sessiz fallback YOK — demandlib başarısızsa sentetik profile düşülmez
        raise RuntimeError(f"BDEW yük profili üretilemedi ({stakeholder_type}): {exc!r}") from exc


if __name__ == "__main__":
    for t in ("residential", "commercial", "municipal"):
        p = profile_for(t, 2800.0)
        byhour = p.reshape(-1, 24).mean(axis=0)
        print(f"{t:<12} sum={round(p.sum(),1)} len={len(p)} peak_hour={int(np.argmax(byhour))}")
