"""
Türkiye Elektrik Tarifesi — KAYNAK-BELGELİ GROUND TRUTH (A0 / SCIENTIFIC_REVIEW KRİTİK-6)
==========================================================================================
Bu modül makalenin (GFP/GFS) sayısal ground-truth'udur: HER sabit resmî kaynağa veya
≥2 bağımsız kaynağa bağlanır ve confidence bayrağı taşır. Doğrulama süreci:
3 paralel araştırma + her iddiaya bağımsız çürütme-doğrulaması (2026-07-03 workflow).

VERİ TARİHİ: 4 Nisan 2026 çeyreklik tarife (EN GÜNCEL DOĞRULANABİLİR — Temmuz 2026
çeyrek güncellemesi hiçbir kaynakta bulunamadı; EPDK sitesi programatik okunamıyor).
Sonraki çeyrekte fiyatlar değişmiş olabilir → TARIFF_DATA_DATE'e bakın.

KAYNAKLAR (özet):
  [K1] EPDK Kurul Kararı No.10707 (31.12.2021, RG) + ek kararlar 10818/10819/10820 —
       mesken kademeli tarife yapısı; eşik 1 Mart 2022'den beri GÜNLÜK ORTALAMA 8 kWh.
  [K2] CK Boğaziçi/gazelektrik + akillitarife + piagrid (bağımsız, tutarlı) —
       4 Nisan 2026 mesken birim fiyatları (aktif 0,4941/1,8958; dağıtım 2,4249 sabit;
       vergisiz toplam 2,92/4,32; vergili 3,24/4,86). confidence: two_independent.
  [K3] 7346 sayılı Cumhurbaşkanı Kararı (RG 7 Temmuz 2023) — KDV: mesken+tarımsal
       sulama %10, diğer gruplar %20 (10 Temmuz 2023'ten beri).
  [K4] 2464 sayılı Belediye Gelirleri Kanunu Madde 38 (GİB teyitli) — BTV/ETV:
       mesken+ticarethane %5; imalat/taşıma/soğutma vb. %1.
  [K5] 7346 sayılı KANUN (RG 25.12.2021, S.31700) — TRT payı VE Enerji Fonu
       1 Ocak 2022'den itibaren KALDIRILDI (ikisi de; faturada yer almaz).
  [K6] 5346 sayılı Kanun Madde 6/A + I Sayılı Cetvel (e) (mevzuat.gov.tr PDF, birincil
       metin okundu) — lisanssız çatı GES ihtiyaç fazlası enerji, abone grubunun
       PERAKENDE TEK-ZAMANLI AKTİF ENERJİ BEDELİ üzerinden alınır (DAĞITIM BEDELİ HARİÇ).
  [K7] Lisanssız Elektrik Üretim Yönetmeliği Md.26 (2 Nisan 2026 değişikliği, RG 33212) —
       mesken mahsup periyodu AYLIK (limitsiz); ticari/sanayi 1 Mayıs 2026'dan itibaren
       SAATLİK mahsup + yıllık üretim ≤ tüketimin 2 katı (aşan kısım YEKDEM'e bedelsiz).
  [K8] TOU pencereleri (iki bağımsız kaynak; resmî tebliğ no BULUNAMADI):
       gündüz 06-17, puant 17-22, gece 22-06 (güncel sayaçlarda yıl boyu sabit).
  [K9] TR tarife bileşen-yapısı araştırması (2026-07, birincil-kaynak + çürütme,
       ≥2 bağımsız çapraz-doğrulama): (a) 1 Oca 2016'dan beri iletim+kayıp-kaçak+sayaç
       DAĞITIM bedeline gömülü; perakende-satış-hizmet AKTİF enerjiye gömülü — AG
       tüketici faturasında ayrı iletim satırı YOK. (b) İletim ayrı (kW-güç bazlı) yalnız
       doğrudan-TEİAŞ sanayi çift-terimli — EPDK Kurul Kararı 14204 (30.12.2025, yür.
       1.1.2026), 15 il-bazlı bölge. (c) Ticarethane AG = KADEMESİZ düz oran (aktif≈3,262
       + dağıtım≈2,479, KDV %20) — conflicting, flagged. (d) Mesken 2-kademe günlük-8kWh
       + 4 Nis 2026 değerleri GÜNCEL (4-kademe-aylık iddiası = 2022-öncesi, çürütüldü).
       Çözülemeyen: mesken çeyrek-tarifesi numaralı Kurul Kararı (yalnız tarih teyitli);
       sanayi güç bedeli TL/kW-ay (not_found); Enerji Fonu %1 durumu (A0 ile çelişki).

VERGİ MODELİ (yayınlanan vergili rakamlardan doğrulanmış):
  vergili = (aktif × (1+BTV) + dağıtım) × (1+KDV)
  Kontrol: (0,4941×1,05+2,4249)×1,10 = 3,238 ≈ 3,24 ✓
           (1,8958×1,05+2,4249)×1,10 = 4,857 ≈ 4,86 ✓
  (BTV yalnız aktif enerji bileşenine, KDV BTV-dahil toplam üzerine — iki kademede de
   yayınlanan değerleri ±0,01 TL/kWh ile üretir.)
"""

# ─────────────────────────────────────────────────────────────────────────────
# Meta — veri güncelliği
# ─────────────────────────────────────────────────────────────────────────────
TARIFF_DATA_DATE = "2026-04-04"      # yürürlük: 4 Nisan 2026 çeyreği [K2]
TARIFF_DATA_NOTE = ("Temmuz 2026 çeyrek güncellemesi doğrulanamadı; en güncel "
                    "doğrulanabilir veri 4 Nisan 2026'dır.")

# ─────────────────────────────────────────────────────────────────────────────
# Vergiler [K3][K4][K5]
# ─────────────────────────────────────────────────────────────────────────────
VAT_RATE_RESIDENTIAL = 0.10   # mesken + tarımsal sulama [K3]
VAT_RATE_OTHER = 0.20         # ticarethane/sanayi/diğer [K3]
BTV_RATE_STANDARD = 0.05      # mesken + ticarethane, aktif enerji üzerinden [K4]
BTV_RATE_INDUSTRIAL_USE = 0.01  # imalat/taşıma/soğutma vb. kullanım [K4]
# TRT payı: 1 Ocak 2022'den beri YOK [K5] — koda EKLENMEZ (teyitli).
# ⚠️ ENERJİ FONU (%1, matrah=yalnız aktif enerji) — ÇELİŞKİ [ÇÖZÜLMEDİ]: A0 (2026-07-03)
# TRT ile birlikte Enerji Fonu'nun da kaldırıldığını buldu [K5]; 2026-07 tarife
# araştırması ise Enerji Fonu %1'in DURDUĞUNU buldu. Etki cüzi (~0,005 TL/kWh; vergili
# fiyatı ±0,003 değiştirir, yayınlanan 3,24/4,86 ile hâlâ ±0,01 uyumlu). Şu an KODA
# EKLENMEDİ (A0/K5 esas alındı + invert_tiered_bill kesinliği korunur). Q1-makale
# öncesi 3291 sayılı Kanun + 7346 Kanun VERBATİM ile çözülmeli.
ENERGY_FUND_RATE_UNRESOLVED = 0.01  # matrah=aktif enerji; koda dahil DEĞİL (çelişki, bkz. üst)

# Geriye-uyum: modül genelinde "VAT_RATE" mesken oranıdır (sizing.invert_tiered_bill
# mesken faturasını çözerken bunu soyar).
VAT_RATE = VAT_RATE_RESIDENTIAL


def _incl_tax_residential(active_tl: float, dist_tl: float) -> float:
    """Mesken vergili birim fiyat: (aktif×(1+BTV) + dağıtım) × (1+KDV)."""
    return (active_tl * (1 + BTV_RATE_STANDARD) + dist_tl) * (1 + VAT_RATE_RESIDENTIAL)


# ─────────────────────────────────────────────────────────────────────────────
# Mesken kademeli tarife [K1][K2]
# ─────────────────────────────────────────────────────────────────────────────
# Eşik GÜNLÜK ORTALAMA 8 kWh'dir (fatura dönemi gün sayısı × 8); "aylık 240" yalnızca
# 30 günlük dönemin eşdeğeridir. Kademe DİLİMLİDİR (marjinal): eşik üstü HER kWh
# yüksek kademeden faturalanır (eşik altı kısım düşük kademede kalır).
RESIDENTIAL_DAILY_THRESHOLD_KWH = 8.0    # [K1]
_DEFAULT_BILLING_DAYS = 30

# Bileşenler (TL/kWh, vergisiz) [K2] — dağıtım bedeli HER İKİ kademede sabittir.
RESIDENTIAL_ACTIVE_ENERGY_TL = {"tier1": 0.4941, "tier2": 1.8958}
#
# ⚡ İLETİM (TEİAŞ) BEDELİ — nerede? [K9]: 1 Ocak 2016'dan beri AG tüketici
# faturasında **iletim sistem kullanım bedeli + kayıp-kaçak + sayaç okuma** ayrı
# satır DEĞİL; hepsi "dağıtım bedeli" içine GÖMÜLÜDÜR. Yani DISTRIBUTION_TL_PER_KWH
# = dağıtım-sistem + iletim-pass-through + kayıp-kaçak + sayaç. (Perakende satış
# hizmet bedeli ise "aktif enerji" içine gömülüdür.) EPDK, AG tüketici tarifesinde
# iletim alt-payını AYRI yayınlamaz — iletim tarifesi yalnız YUKARI-AKIŞTA TEİAŞ için
# ayrı belirlenir (EPDK Kurul Kararı 14204, 30.12.2025). İletim'in AYRI (kW-güç bazlı)
# satır olduğu TEK durum: doğrudan TEİAŞ şebekesine bağlı büyük sanayi (bkz. INDUSTRIAL_*).
# → İletim bedeli EKSİK DEĞİL; toplam vergili fiyat (3,24/4,86) içinde yakalıdır.
DISTRIBUTION_TL_PER_KWH = 2.4249
DISTRIBUTION_BUNDLES = ("iletim (TEİAŞ pass-through)", "kayıp-kaçak", "sayaç okuma")

# GERİYE-UYUMLU şekil (sizing.invert_tiered_bill bu listeyi jenerik yürütür):
# rate = KDV-öncesi taban (aktif×1,05 + dağıtım); calculate_tiered_bill ×(1+VAT_RATE) uygular.
# Böylece fatura = yayınlanan vergili rakamlarla (3,24/4,86 TL/kWh) ±0,01 uyumludur ve
# invert_tiered_bill(calculate_tiered_bill(x)) == x kesin kalır.
_T1_PRE_VAT = RESIDENTIAL_ACTIVE_ENERGY_TL["tier1"] * (1 + BTV_RATE_STANDARD) + DISTRIBUTION_TL_PER_KWH
_T2_PRE_VAT = RESIDENTIAL_ACTIVE_ENERGY_TL["tier2"] * (1 + BTV_RATE_STANDARD) + DISTRIBUTION_TL_PER_KWH
RESIDENTIAL_TIERS = [
    {"limit_kwh": RESIDENTIAL_DAILY_THRESHOLD_KWH * _DEFAULT_BILLING_DAYS,  # 240 (30 gün)
     "rate_tl_per_kwh": round(_T1_PRE_VAT, 4)},                              # ≈2,9437
    {"limit_kwh": float("inf"),
     "rate_tl_per_kwh": round(_T2_PRE_VAT, 4)},                              # ≈4,4155
]

# Yayınlanan vergili nihai değerler (kontrol/raporlama için) [K2]
RESIDENTIAL_INCL_TAX_TL = {"tier1": 3.24, "tier2": 4.86}

# ─────────────────────────────────────────────────────────────────────────────
# Ticarethane — DÜZ ORAN (kademesiz) [K9, confidence: conflicting → flagged]
# ─────────────────────────────────────────────────────────────────────────────
# Araştırma (2026-07, iki-bağımsız yapı / tek-kaynak mutlak değer): ticarethane
# AG tek-terimli KADEMESİZ düz orandır (kademe yalnız MESKENE özgü); Q2-2026
# aktif enerji ≈ 3,262 + dağıtım ≈ 2,479 (KDV %20, BTV %5). Bir kaynak (piagrid)
# iki-kademeli all-in (5,35/5,93) verdi → CONFLICTING; düz-oran tercih edildi ama
# COMMERCIAL_RATE_ESTIMATED=True kalır (numaralı Kurul Kararı ile teyit bekliyor).
# Önceki değer mesken-kademe2 kopyasıydı (açıkça yanlış); bu daha iyi ama flagged.
COMMERCIAL_RATE_ESTIMATED = True
COMMERCIAL_DAILY_THRESHOLD_KWH = 30.0
COMMERCIAL_ACTIVE_ENERGY_TL = 3.262            # düz oran, KDV-hariç [K9 conflicting]
COMMERCIAL_DISTRIBUTION_TL_PER_KWH = 2.479     # iletim gömülü [K9 conflicting]
# KDV-öncesi taban (aktif×(1+BTV) + dağıtım); calculate_* ×(1+VAT_RATE_OTHER=%20) uygular
FLAT_RATE_TL_PER_KWH = round(
    COMMERCIAL_ACTIVE_ENERGY_TL * (1 + BTV_RATE_STANDARD) + COMMERCIAL_DISTRIBUTION_TL_PER_KWH, 4
)  # ≈ 5,9040 (KDV-öncesi); vergili ≈ 7,08 TL/kWh

# ─────────────────────────────────────────────────────────────────────────────
# SANAYİ ÇİFT-TERİMLİ (OG/YG) — iletim'in AYRI (kW-güç bazlı) olduğu TEK yapı [K9]
# ─────────────────────────────────────────────────────────────────────────────
# Doğrudan TEİAŞ şebekesine bağlı büyük sanayi çift-terimli tarifede: (enerji kWh) +
# (dağıtım kWh) + **güç bedeli** (anlaşma gücü, TL/kW-ay) + iletim sistem kullanım
# bedeli AYRI. İletim, 15 il-bazlı tarife bölgesi × rezerve/pik kapasite (kW) üzerinden
# cost-of-service tahsis edilir (EPDK Kurul Kararı 14204, 30.12.2025, yür. 1.1.2026).
# ⚠️ Güç bedeli ve zona-özel iletim TL/kW-ay değerleri EPDK PDF'inde — MAKİNE-OKUNAMADI
# (not_found). Çapa: ~11,43 TL/kW-ay (2023) → ~20 (2024) → 2026 daha yüksek (tahmini).
# DSS kapsamı AG tek-terimli; bu yapı yalnız BELGE + gelecek genişleme içindir.
INDUSTRIAL_TWO_TERM_ILETIM_SEPARATE = True
INDUSTRIAL_DEMAND_CHARGE_TL_PER_KW_MONTH = None   # not_found — EPDK Q2/Q3-2026 PDF'inden çekilecek
INDUSTRIAL_TARIFF_REGIONS = 15                    # il-bazlı iletim tarife bölgesi [K9]

# ─────────────────────────────────────────────────────────────────────────────
# Üç-zamanlı (TOU) tarife [K8][K2] — KDV hariç toplamlar, CK Boğaziçi bölgesi
# ─────────────────────────────────────────────────────────────────────────────
# Resmî tebliğ numarası bulunamadı (pencere saatleri two_independent). Kış/eski-sayaç
# 1 saat kayması var (07-18/18-23/23-07) — varsayılan: yıl boyu sabit pencereler.
TOU_WINDOWS = {
    "day":   {"start_hour": 6,  "end_hour": 17, "rate_tl_per_kwh_ex_vat": 4.38},
    "peak":  {"start_hour": 17, "end_hour": 22, "rate_tl_per_kwh_ex_vat": 6.17},
    "night": {"start_hour": 22, "end_hour": 6,  "rate_tl_per_kwh_ex_vat": 2.94},
}


def tou_rate_for_hour(hour: int, include_vat: bool = True) -> float:
    """Saat (0-23) için mesken TOU birim fiyatı (TL/kWh). include_vat=True → ×(1+KDV%10).
    Not: yayınlanan TOU toplamlarında BTV kırılımı bilinmediğinden yalnız KDV eklenir
    (yaklaşıklık, ~%2 alt-sınır sapması olabilir)."""
    if 6 <= hour < 17:
        rate = TOU_WINDOWS["day"]["rate_tl_per_kwh_ex_vat"]
    elif 17 <= hour < 22:
        rate = TOU_WINDOWS["peak"]["rate_tl_per_kwh_ex_vat"]
    else:
        rate = TOU_WINDOWS["night"]["rate_tl_per_kwh_ex_vat"]
    return rate * (1 + VAT_RATE_RESIDENTIAL) if include_vat else rate


# ─────────────────────────────────────────────────────────────────────────────
# Lisanssız üretim / mahsuplaşma [K6][K7]
# ─────────────────────────────────────────────────────────────────────────────
# ESKİ 1:1 varsayımı (export = perakende satış fiyatı) KALDIRILDI — mevzuata göre
# ihtiyaç fazlası yalnız AKTİF ENERJİ bedeli üzerinden ödenir (dağıtım bedeli HARİÇ),
# yani tüketim fiyatının çok altındadır.
NET_METERING_PERIOD_RESIDENTIAL = "monthly"        # limitsiz [K7]
NET_METERING_PERIOD_NON_RESIDENTIAL = "hourly"     # 1 Mayıs 2026'dan itibaren [K7]
ANNUAL_GENERATION_CAP_RATIO_NON_RESIDENTIAL = 2.0  # yıllık üretim ≤ 2× tüketim [K7]

# Net-fazla (aylık mahsup SONRASI kalan) satış bedeli: abone grubunun perakende
# tek-zamanlı AKTİF enerji bedeli [K6]. Net-ihracatçı ayda net tüketim ~0 olacağından
# kademe-1 aktif bedeli uygulanır varsayımı (kademe belirsizliği fact-sheet'te not edildi).
EXPORT_SURPLUS_RATE_TL_PER_KWH = RESIDENTIAL_ACTIVE_ENERGY_TL["tier1"]  # 0,4941
EXPORT_RATE_TL_PER_KWH = EXPORT_SURPLUS_RATE_TL_PER_KWH  # geriye-uyumlu ad

# NOT (feasibility motoruna): aylık mahsupta ay-içi ihracat, ay-içi ithalatı kWh-kWh
# dengeler (perakende fiyat değerinde); yalnız NET fazla bu düşük bedeli alır.
# economic_engine şu an saatlik self-consumption + sabit export_rate kullanır —
# aylık-mahsup modellemesi ayrı iş kalemidir (bkz. SCIENTIFIC_REVIEW aksiyonları).


# ─────────────────────────────────────────────────────────────────────────────
# API (geriye-uyumlu)
# ─────────────────────────────────────────────────────────────────────────────

def get_simple_tariff() -> dict:
    """economic_engine ile uyumlu basit (flat) tarife sözlüğü.

    day/night: mesken MARJİNAL perakende fiyatı, vergili (kademe-2; eşik üstü hane
    için öz-tüketilen her kWh'nin gerçek değeri). export: net-fazla aktif enerji
    bedeli [K6] (vergisiz ödeme). Kademe-altı haneler ve aylık-mahsup inceliği için
    calculate_tiered_bill / NET_METERING_* sabitlerine bakın.
    """
    marginal_incl_tax = round(_incl_tax_residential(
        RESIDENTIAL_ACTIVE_ENERGY_TL["tier2"], DISTRIBUTION_TL_PER_KWH), 4)  # ≈4,857
    return {
        "day_rate_tl_per_kwh": marginal_incl_tax,
        "night_rate_tl_per_kwh": marginal_incl_tax,
        "export_rate_tl_per_kwh": EXPORT_RATE_TL_PER_KWH,
        "vat_rate": VAT_RATE_RESIDENTIAL,
        "vat_included": True,   # A27: day/night fiyatı zaten KDV-dahil
    }


def calculate_tiered_bill(monthly_consumption_kwh: float,
                          days_in_month: int = _DEFAULT_BILLING_DAYS) -> float:
    """Mesken aylık fatura (TL, vergiler DAHİL) — dilimli/marjinal kademe [K1][K2].

    Eşik = days_in_month × 8 kWh (günlük-ortalama esaslı [K1]). days_in_month=30
    varsayılanıyla RESIDENTIAL_TIERS'taki 240 kWh eşiğiyle birebir aynıdır
    (sizing.invert_tiered_bill bu varsayılanla kesin terstir).
    """
    threshold = RESIDENTIAL_DAILY_THRESHOLD_KWH * days_in_month
    tier1_kwh = min(monthly_consumption_kwh, threshold)
    tier2_kwh = max(0.0, monthly_consumption_kwh - threshold)
    pre_vat = tier1_kwh * RESIDENTIAL_TIERS[0]["rate_tl_per_kwh"] \
        + tier2_kwh * RESIDENTIAL_TIERS[1]["rate_tl_per_kwh"]
    return pre_vat * (1 + VAT_RATE)


if __name__ == "__main__":
    # Vergi modeli yayınlanan değerleri üretmeli [K2]
    t1 = _incl_tax_residential(RESIDENTIAL_ACTIVE_ENERGY_TL["tier1"], DISTRIBUTION_TL_PER_KWH)
    t2 = _incl_tax_residential(RESIDENTIAL_ACTIVE_ENERGY_TL["tier2"], DISTRIBUTION_TL_PER_KWH)
    assert abs(t1 - RESIDENTIAL_INCL_TAX_TL["tier1"]) < 0.01, t1
    assert abs(t2 - RESIDENTIAL_INCL_TAX_TL["tier2"]) < 0.01, t2
    # 300 kWh / 30 gün: 240×2,9437 + 60×4,4155 = 971,4 ×1,10 ≈ 1068,5 TL
    bill = calculate_tiered_bill(300)
    expected = (240 * RESIDENTIAL_TIERS[0]["rate_tl_per_kwh"]
                + 60 * RESIDENTIAL_TIERS[1]["rate_tl_per_kwh"]) * 1.10
    assert abs(bill - expected) < 0.01
    # TOU pencereleri 24 saati kapsamalı
    assert all(tou_rate_for_hour(h, include_vat=False) > 0 for h in range(24))
    print(f"[OK] vergili kademe fiyatları: {t1:.3f} / {t2:.3f} TL/kWh (yayınlanan 3,24/4,86)")
    print(f"[OK] 300 kWh fatura: {bill:.2f} TL | export: {EXPORT_RATE_TL_PER_KWH} TL/kWh")
