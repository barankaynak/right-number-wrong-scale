"""
turkey_parameters.py — Türkiye'ye özgü yük büyüklükleri (TEK KAYNAK-BELGELİ MODÜL).

Tasarım ilkesi: Kod içine "nereden geldiği belli olmayan" sayı gömülmez.
Tüm Türkiye mutlak değerleri burada, HER BİRİ kaynağıyla birlikte tanımlanır;
iş mantığı (load_profile, region_network, demand_model) bu modüle referans verir.

Kaynaklar aşağıda her sabitin yanında açıkça belirtilmiştir.
"""

# ─────────────────────────────────────────────────────────────────────────────
# KONUT — ortalama hane başı yıllık elektrik tüketimi
# ─────────────────────────────────────────────────────────────────────────────
# Türetme: EPDK 2024 mesken toplam tüketimi ≈ 75,09 milyar kWh
#          ÷ TÜİK 2024 hane (aile) sayısı ≈ 26,60 milyon  ≈ 2.824 kWh/hane/yıl
# Çapraz doğrulama:
#   - TEİAŞ 2011, 4 kişilik kentli orta-gelir aile: 3.036 kWh/yıl
#   - Kişi başı: 75 TWh ÷ 85M nüfus × 3,2 kişi/hane ≈ 2.800 kWh/hane
# NOT: 2013 TEDAŞ "1.528 kWh" değeri ABONE başınadır (boş/az kullanılan sayaçlar
#      ortalamayı düşürür) ve eskidir; oturulan hane için 2.800 kWh temsilîdir.
# Kaynak: EPDK Elektrik Piyasası 2024 sektör raporu; TÜİK hane istatistikleri 2024.
RESIDENTIAL_ANNUAL_KWH: float = 2800.0

# Alan-ölçeklemesi için referans konut büyüklüğü (m²): bu alandaki hane
# RESIDENTIAL_ANNUAL_KWH tüketir; daha büyük/küçük konut oransal ölçeklenir.
TYPICAL_DWELLING_M2: float = 120.0

# Türkiye şebeke ortalama CO2 emisyon faktörü (kg CO2/kWh) — grid emission
# Kaynak: TEİAŞ/IEA Türkiye şebeke ortalaması (~0,45 kg/kWh mertebesinde).
GRID_EMISSION_FACTOR_KG_PER_KWH: float = 0.45

# Yerel saat dilimi: PV TMY verisi UTC saatlerindedir, yük profilleri yerel saattedir.
# Türkiye 2016'dan beri yaz saati uygulamaz; tüm yıl UTC+3.
# Kaynak: IANA tz veritabanı, bölge "Europe/Istanbul".
LOCAL_TIMEZONE: str = "Europe/Istanbul"


# ─────────────────────────────────────────────────────────────────────────────
# ELEKTRİKLİ ARAÇ (EV) — ev şarjı büyüklükleri
# ─────────────────────────────────────────────────────────────────────────────
# EV yıllık ev-şarj enerjisi (kWh/araç/yıl):
#   ~15.000 km/yıl × ~0,18–0,20 kWh/km ≈ 2.700–3.000 kWh; ev-şarj payı ~%80.
#   UK pilotu (batarya >35 kWh): ~3.500 kWh/yıl.
#   ABD (37 mil/gün ≈ 21.700 km/yıl): verimli EV ~3.000, verimsiz ~6.800 kWh.
# Kaynak: NW Power & Conservation Council, Plug-In Electric Load Profiles (2021);
#         UK home-charging pilot çalışmaları.
EV_ANNUAL_KWH_HOME: float = 3000.0

# Tipik ev AC şarj cihazı gücü (kW): tek faz 32A ≈ 7,4 kW
# (3,7 kW / 7,4 kW / 11 kW yaygın; ev için 7,4 kW temsilî).
EV_CHARGER_KW: float = 7.4

# EV varsayılan yaygınlığı (hane oranı, 0–1). Türkiye filo (stok) EV payı 2025'te
# hâlâ düşük (~%2–3), ama akış hızlı: 2024 BEV binek satışın %8,3'ü → 2025 H1 ~%27.
# Öngörü: 2034'te filo ~%20. Bu yüzden bir SENARYO parametresidir (0/10/20/30…).
# Kaynak: S&P Global Mobility (2025); Türkiye 2024 EV +%300 stok artışı;
#         Climate Scorecard (2034 ~%20 filo öngörüsü).
EV_PENETRATION_DEFAULT: float = 0.03


# ─────────────────────────────────────────────────────────────────────────────
# MAHSUPLAŞMA (net metering) — netleme zaman aralığı, abone/paydaş tipine göre
# ─────────────────────────────────────────────────────────────────────────────
# Türkiye lisanssız üretim mahsuplaşma rejimi (5346 sayılı YEK Kanunu Md.6/A +
# EPDK Elektrik Piyasasında Lisanssız Elektrik Üretim Yönetmeliği): üretim ile
# tüketim, fatura döneminde karşılıklı mahsup edilir. Netleme aralığı abone
# tipine göre DEĞİŞİR:
#   - MESKEN (ev aboneleri): AYLIK mahsuplaşma — bir fatura dönemi (ay) içindeki
#     toplam üretim, aynı dönem tüketimini perakende bedeliyle mahsup eder; yalnız
#     dönem-net-fazlası ihraç (YEK) fiyatından değerlenir. Öğle üretimi akşam
#     tüketimini örttüğü için PV ekonomisi LEHİNE (öz-tüketim etkin olarak artar).
#   - TİCARETHANE / SANAYİ / İŞLETME: SAATLİK mahsuplaşma — her saat ayrı netlenir;
#     saatlik anlık fazla ihraç fiyatından satılır, perakendeye mahsup EDİLMEZ.
# Netleme aralığı SENARYO/paydaş parametresidir; ekonomik motor `netting_interval`
# argümanıyla 'hourly' | 'daily' | 'monthly' | 'annual' kabul eder (ayarlanabilir).
# Kaynak: 5346 sayılı Kanun Md.6/A; EPDK Lisanssız Üretim Yönetmeliği mahsuplaşma
#         hükümleri (mesken=aylık, ticari=saatlik uygulama).
NETTING_INTERVAL_BY_STAKEHOLDER: dict = {
    "residential": "monthly",
    "commercial": "hourly",
    "municipal": "hourly",
    "utility": "hourly",
}
DEFAULT_NETTING_INTERVAL: str = "hourly"


def netting_interval_for(stakeholder_type: str) -> str:
    """Paydaş/abone tipi → mahsuplaşma netleme aralığı.
    Mesken 'monthly' (aylık), ticarethane/işletme/belediye/utility 'hourly' (saatlik).
    Bilinmeyen tip → DEFAULT_NETTING_INTERVAL ('hourly')."""
    return NETTING_INTERVAL_BY_STAKEHOLDER.get(
        (stakeholder_type or "").strip().lower(), DEFAULT_NETTING_INTERVAL)


def annual_kwh_from_area(area_m2: float, base_kwh: float = RESIDENTIAL_ANNUAL_KWH,
                         typical_m2: float = TYPICAL_DWELLING_M2,
                         clamp_lo: float = 0.5, clamp_hi: float = 3.0) -> float:
    """Konut alanından yıllık tüketim tahmini: Türkiye ortalamasına çapalı,
    alanla oransal ölçeklenmiş (clamp'li). typical_m2 alanındaki hane base_kwh tüketir."""
    if area_m2 <= 0:
        return base_kwh
    factor = area_m2 / typical_m2
    factor = max(clamp_lo, min(clamp_hi, factor))
    return base_kwh * factor
