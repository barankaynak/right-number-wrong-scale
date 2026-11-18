"""
ProvenanceGuard — GFP (Grounding Fidelity Protocol) çekirdek uygulaması (A1).

Makalenin ölçtüğü mekanizma: LLM yanıtındaki HER sayısal iddia, simülasyon
kökenine karşı makine-doğrulanabilir olmalı. Eski `hallucination_guard`
(nokta-bazlı regex, yalnız loglar) G4 deneyinin BASELINE'ı olarak korunur;
bu modül onun yerine geçen 5-alan+confidence provenance-graph guard'ıdır.

Provenance kaydı (5 alan + bonus):
  1. source_function  — sayıyı üreten araç/fonksiyon (veya "input" = kullanıcı girdisi)
  2. parameters       — aracın çağrı parametreleri
  3. stakeholder      — hangi paydaş bağlamında üretildi
  4. scale            — SAYININ GEÇERLİ OLDUĞU FİZİKSEL ÖLÇEK (building/feeder/policy)
                        → "doğru sayı / yanlış ölçek" ihlalini yakalayan alan
  5. timestamp/vintage— üretim zamanı + veri tarihi (ör. tarife TARIFF_DATA_DATE)
  +  confidence       — kaynağın güvenilirlik bayrağı (A0 tarife bayraklarından taşınır:
                        two_independent / official_doc / estimated / model:*)

Kararlar (claim başına): GROUNDED | UNGROUNDED | SCALE_VIOLATION | UNIT_MISMATCH | IGNORED.
v4.2 (A21): BOŞ graf (araç çağrılmamış tek-tur) da değerlendirilir — her sayı
UNGROUNDED ya da IGNORED; düzeltme talimatı ve güvenli özet boş-graf varyantıyla.
Rapor ham sayımları verir; GFS metrik formülü/ağırlıkları A2 ön-kayıtta
sabitlenir (burada formül DONDURULMAZ — ön-kayıt ilkesi).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Ölçekler ────────────────────────────────────────────────────────────────
SCALE_BUILDING = "building"
SCALE_FEEDER = "feeder"
SCALE_POLICY = "policy"

# Araç → ürettiği sayıların geçerli olduğu ölçek
TOOL_SCALE: dict[str, str] = {
    "simulate_pv_bess": SCALE_BUILDING,
    "run_monte_carlo": SCALE_BUILDING,
    "configure_pv_system": SCALE_BUILDING,
    "update_pv_parameter": SCALE_BUILDING,
    "run_pv_simulation": SCALE_BUILDING,
    "configure_bess_system": SCALE_BUILDING,
    "update_bess_parameter": SCALE_BUILDING,
    "run_bess_simulation": SCALE_BUILDING,
    "simulate_grid_impact": SCALE_FEEDER,
    "build_custom_network": SCALE_FEEDER,
    "update_network_element": SCALE_FEEDER,
    "run_loadflow_on_network": SCALE_FEEDER,
    "run_policy_scenario": SCALE_POLICY,
}

# Cümledeki ölçek ipuçları (TR ağırlıklı). Boş küme → ölçek iddiası yok → ihlal yok.
# A1-r3 KALİBRASYON v2 (2026-07-08): geniş terimler ("şebeke", "gerilim", "dağıtım",
# "bölgede", çıplak "toplam") YANLIŞ-POZİTİF üretiyordu — "şebekeden alım", "toplam
# sistem maliyeti" meşru bina-cümleleridir. Sözlük dar-kesin ifadelere çekildi;
# FP denetimi: tests → experiments/gfp_benchmark/dev_corpus.json (G1 setinden AYRI).
# Bu sözlük A2 ön-kayıtta versiyonuyla dondurulur (SCALE_DICT_VERSION).
SCALE_DICT_VERSION = "v4-bilingual-2026-07-10"
# v3 (ORTA-9c): bina-tipi kelime dağarcığı genişletildi ("daire","fabrika","atölye",
# "depo","ofis","otel","dükkan") — benchmark cross-tuzaklarının (res-11 'daire',
# com-10 'fabrika') sözlük-dışına düşmemesi için; iki-yönlü dev-korpus (FP+FN) test-kilitli.
# v4 (CROSS-LINGUAL, prereg-v2.0): İngilizce koşul için EN terimler EKLENDİ (TR korunur).
# Guard dil-agnostiktir — cümlede hangi dilin terimi geçerse onu yakalar. EN sözlük dar-
# kesin tutuldu: çıplak "grid" YOK ("buying from the grid" bina-bağlamıdır, FP üretir) —
# fider ölçeği yalnız "feeder/distribution grid/hosting/voltage rise/transformer/
# neighbourhood/penetration" gibi kesin terimlerle. EN dev-korpus (FP+FN) test-kilitli.
_BUILDING_WORDS = ("ev", "hane", "bina", "site", "konut", "apartman", "tesis",
                   "daire", "fabrika", "atölye", "depo", "ofis", "otel",
                   "dükkan", "işletme",
                   # EN (tekil + çoğul — agregasyon deseni "all the factories" için)
                   "home", "house", "household", "building", "residence",
                   "apartment", "flat", "villa", "facility", "factory",
                   "workshop", "warehouse", "office", "hotel", "shop", "store",
                   "business", "premises",
                   "homes", "houses", "households", "buildings", "residences",
                   "apartments", "flats", "villas", "facilities", "factories",
                   "workshops", "warehouses", "offices", "hotels", "shops",
                   "businesses")
_SCALE_KEYWORDS: dict[str, tuple[str, ...]] = {
    SCALE_BUILDING: ("bina", "çatı", "evin", "eviniz", "hane", "konut",
                     "işletme", "tesis", "müstakil", "daire", "fabrika",
                     "atölye", "depo", "ofis", "otel", "dükkan",
                     # EN
                     "your home", "your house", "your building", "your roof",
                     "rooftop", "your bill", "your system", "household",
                     "single home", "detached", "residence", "your flat",
                     "your apartment", "your facility", "your factory",
                     "your office", "your hotel", "your shop", "your premises"),
    SCALE_FEEDER: ("fider", "feeder", "trafo", "transformatör", "hosting",
                   "hat yüklen", "dağıtım şebekesi", "şebeke kapasit",
                   "şebeke etkisi", "gerilim düş", "gerilim yükselm",
                   "gerilim profil", "mahalle", "penetrasyon",
                   # EN (çıplak "grid" YOK — bina-bağlamı FP'si)
                   "distribution grid", "distribution network", "grid capacity",
                   "hosting capacity", "voltage rise", "voltage drop",
                   "voltage profile", "transformer", "substation", "neighbourhood",
                   "neighborhood", "penetration", "line loading", "reverse power",
                   "across the feeder", "feeder-wide", "the whole street"),
    SCALE_POLICY: ("politika", "teşvik", "devlet", "ulusal", "bütçe",
                   "mekanizma", "sübvansiyon", "subvansiyon", "ülke",
                   # EN
                   "policy", "incentive", "subsidy", "government", "national",
                   "nationwide", "state budget", "mechanism", "countrywide",
                   "across the country"),
}
# Bina-ölçeği sayının çoklu-binaya çarpılıp genellendiğini ima eden agregasyon
# deseni: "toplam/tüm/bütün + (sayı) + <bina-tipi kelime>" | "genelinde" | "N daire/ev/..."
# (çıplak "toplam" DEĞİL — "toplam yatırım/üretim" tek-sistem bağlamında meşrudur)
_AGGREGATION_RE = re.compile(
    r"(toplam|tüm|bütün|all|every|entire|combined|each)\s+(the\s+|these\s+|those\s+)?"
    r"(\d+[\s.]*)?(" + "|".join(_BUILDING_WORDS) + r")"
    r"|genelinde|across the|neighbourhood-wide|neighborhood-wide|feeder-wide"
    r"|multiplied by|multiply by|scaled on top|on top of")
# NOT: çıplak "N daire/ev" deseni AGREGASYON SAYILMAZ — "40 daire var ama bu hesap
# yalnız sizin daireniz için" gibi doğru-ölçek uyarıları meşrudur (dc-27 FP probe'u).

# Eşleşmeyen ama bağlamsal/soysal sayılar (yıl, liste no, ömür, saat) — bloklamaz
_IGNORABLE_INTS = {1, 2, 3, 4, 12, 24, 25, 100, 365, 8760}
_YEAR_RANGE = (1990, 2100)

# ORTA-9d düzeltmesi (G4 small_int kaçağı): "geri ödeme 3 yıl" gibi KARAR-KRİTİK
# küçük tamsayılar ignorable DEĞİLDİR — cümlede payback-işareti varsa ve yıl-birimli
# iddia hiçbir kayıtla eşleşmiyorsa UNGROUNDED sayılır. ("25 yıllık ömür" gibi
# payback-işaretsiz bağlamlar ignorable kalır.)
_PAYBACK_CUES = ("geri ödeme", "geri dönüş", "geri dönüm", "amorti", "payback",
                 "öder", "ödeme süre", "ertele",
                 # EN
                 "pay back", "pays for itself", "pays back", "recoup", "recover the",
                 "break even", "break-even", "amortize", "amortise", "defer",
                 "deferral", "payback period")   # karar-kritik yıl iddiaları
# ("kendini 3 yılda öder" → "öder"; "2 yıl erteleyebilirsiniz" → "ertele")

# Bina-tipi kelimesi hemen takip eden sayı VARLIK SAYISIDIR ("40 daire", "30 ev") —
# fiziksel iddia değil; eşleşmiyorsa IGNORED (agregasyon tespiti cümle-düzeyinde
# zaten yapılır, sayının kendisi bloklanmaz).
_COUNT_CONTEXT_RE = re.compile(r"^\s*(" + "|".join(
    ("daire", "ev", "hane", "bina", "konut", "site", "apartman", "tesis",
     "fabrika", "atölye", "depo", "ofis", "otel", "dükkan", "işletme",
     # EN (sayıyı hemen izleyen çoğul bina-tipi: "40 flats", "500 households")
     "homes", "houses", "households", "flats", "apartments", "buildings",
     "residences", "businesses", "offices", "factories", "workshops",
     "warehouses", "hotels", "shops", "premises", "villas")) + r")", re.IGNORECASE)

# Sayısal eşleşme toleransı (LLM yuvarlaması): göreli %2 veya küçük değerde mutlak 0,5
_REL_TOL = 0.02
_ABS_TOL_SMALL = 0.5
_SMALL_VALUE = 30.0

# Sonuç anahtarına göre birim + güvenilirlik (A0 confidence bayrakları buraya taşınır)
def _tariff_vintage() -> str:
    try:
        from app.simulation.economic.tariffs.turkey_2026 import TARIFF_DATA_DATE
        return TARIFF_DATA_DATE
    except Exception:
        return "unknown"


_KEY_META: dict[str, tuple[str, str]] = {
    # key → (unit, confidence)
    "npv_tl": ("TL", "tariff:two_independent"),
    "annual_savings_tl": ("TL", "tariff:two_independent"),
    "system_cost_tl": ("TL", "capex:estimated"),
    "lcoe_tl_per_kwh": ("TL/kWh", "tariff:two_independent"),
    "simple_payback_years": ("yıl", "tariff:two_independent"),
    "discounted_payback_years": ("yıl", "tariff:two_independent"),
    "irr_percent": ("%", "tariff:two_independent"),
    "annual_production_kwh": ("kWh", "model:pvgis"),
    "total_grid_import_kwh": ("kWh", "model:pvgis"),
    "total_grid_export_kwh": ("kWh", "model:pvgis"),
    "self_consumption_ratio": ("oran", "model:dispatch"),
    "max_voltage_pu": ("pu", "model:pandapower"),
    "min_voltage_pu": ("pu", "model:pandapower"),
    "max_line_loading_pct": ("%", "model:pandapower"),
    "hosting_capacity_pct": ("%", "model:pandapower"),
    "max_transformer_loading_pct": ("%", "model:pandapower"),
    "transformer_deferral_years": ("yıl", "model:pandapower"),
    "avoided_upgrade_cost_tl": ("TL", "model:pandapower"),
    "total_losses_kw": ("kW", "model:pandapower"),
    # policy engine (run_policy_scenario sonuç yaprakları)
    "best_npv_tl": ("TL", "tariff:two_independent"),
    "state_cost_tl": ("TL", "model:policy"),
    "state_cost_per_kw_tl": ("TL", "model:policy"),
    "triggered_investment_tl": ("TL", "model:policy"),
    "annual_co2_reduction_tons": ("ton", "model:policy"),
    # monte carlo yüzdelikleri
    "npv_p10": ("TL", "model:mc"), "npv_p50": ("TL", "model:mc"),
    "npv_p90": ("TL", "model:mc"),
    "payback_p10": ("yıl", "model:mc"), "payback_p50": ("yıl", "model:mc"),
    "payback_p90": ("yıl", "model:mc"),
}
_FINANCIAL_KEYS = {k for k, (_, c) in _KEY_META.items() if c.startswith("tariff")}

# Araç GİRDİ parametrelerinin birimleri (A1-r2: girdiler de unit taşısın)
_ARG_UNITS: dict[str, str] = {
    "panel_kw": "kW", "bess_kwh": "kWh",
    "annual_consumption_kwh": "kWh", "monthly_bill_tl": "TL",
    "base_investment_tl": "TL", "annual_savings_tl": "TL",
    "lifetime_years": "yıl", "pv_penetration_pct": "%",
    "bess_penetration_pct": "%", "discount_rate": "oran",
}

# A1-r2: metindeki sayının hemen çevresinden birim çıkarımı. Sıra ÖNEMLİ
# (önce bileşik birimler). None → birim belirsiz → yalnız değerle eşleş.
_UNIT_PATTERNS: list[tuple[str, str]] = [
    (r"tl\s*/\s*kwh|₺\s*/\s*kwh", "TL/kWh"),
    (r"kwh|kilovat[- ]?saat|kilowatt[- ]?hour", "kWh"),
    (r"kwp|\bkw\b|kilovat|kilowatt", "kW"),
    (r"\btl\b|₺|lira", "TL"),
    (r"\byıl|\byears?\b|\byr\b", "yıl"),   # kanonik birim "yıl"; EN yüzey formu tanınır
    (r"\bpu\b", "pu"),
]


def _infer_claim_unit(sentence: str, start: int, end: int) -> str | None:
    """Sayının çevresinden birim çıkar — EN YAKIN birim kazanır (desen-önceliği
    değil; '3,3 kW panel + 4,8 kWh' cümlesinde 3,3'ün birimi kW'dir, kWh değil).
    Eşitlikte daha uzun eşleşme kazanır (TL/kWh > TL, kWh > kW).
    A15 (cross-lingual parser düzeltmesi): (1) ÖNCE ve SONRA BİRLİKTE değerlendirilir —
    bitişik para-simgesi (₺, önde) uzaktaki 'years'e yenilmez ('₺33,956 over 25 years'
    → TL, yıl DEĞİL); (2) tablo-hücresi/satır sınırı (`|`, newline) AŞILMAZ — yandaki
    hücrenin birimi sızmaz ('0.1039 | 9,635 kWh' → 0.1039'un birimi kWh DEĞİLdir)."""
    after = re.split(r"[|\n]", sentence[end:end + 30])[0].lower()
    before = re.split(r"[|\n]", sentence[max(0, start - 15):start])[-1].lower()

    best: tuple[int, int, str] | None = None   # (uzaklık, -uzunluk, birim)
    for pat, unit in _UNIT_PATTERNS:            # SONRA: uzaklık = eşleşmenin başlangıcı
        m = re.search(pat, after)
        if m:
            cand = (m.start(), -(m.end() - m.start()), unit)
            if best is None or cand < best:
                best = cand
    for pat, unit in _UNIT_PATTERNS:            # ÖNCE: uzaklık = birimin sonundan sayıya
        m = None
        for m in re.finditer(pat, before):
            pass                                # sondaki (sayıya en yakın) eşleşme
        if m:
            dist = len(before) - m.end()
            cand = (dist, -(m.end() - m.start()), unit)
            if best is None or cand < best:
                best = cand
    return best[2] if best else None


def _units_compatible(claim_unit: str | None, record_unit: str) -> bool:
    """Birim uyumu: iddia birimi bilinmiyorsa veya kayıt birimi boşsa uyumlu;
    % iddiası oran kaydıyla uyumlu; aksi halde tam eşleşme."""
    if claim_unit is None or not record_unit:
        return True
    if claim_unit == "%" and record_unit in ("%", "oran"):
        return True
    return claim_unit == record_unit


@dataclass
class ProvenanceRecord:
    key: str                 # sonuç anahtarı (nokta-yollu) veya "input:<param>"
    value: float
    source_function: str     # araç adı ("input" = kullanıcı/araç girdisi)
    parameters: dict
    stakeholder: str
    scale: str               # building | feeder | policy
    timestamp: str
    vintage: str             # veri tarihi (finansal → tarife tarihi)
    unit: str = ""
    confidence: str = "model"

    def to_dict(self) -> dict:
        return {
            "key": self.key, "value": self.value,
            "source_function": self.source_function,
            "parameters": self.parameters,
            "stakeholder": self.stakeholder, "scale": self.scale,
            "timestamp": self.timestamp, "vintage": self.vintage,
            "unit": self.unit, "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProvenanceRecord":
        return cls(
            key=d["key"], value=float(d["value"]),
            source_function=d.get("source_function", "?"),
            parameters=d.get("parameters", {}) or {},
            stakeholder=d.get("stakeholder", "residential"),
            scale=d.get("scale", SCALE_BUILDING),
            timestamp=d.get("timestamp", ""), vintage=d.get("vintage", ""),
            unit=d.get("unit", ""), confidence=d.get("confidence", "model"),
        )


@dataclass
class ClaimCheck:
    text: str                # cümle içindeki ham sayı ifadesi
    value: float
    verdict: str             # GROUNDED | UNGROUNDED | SCALE_VIOLATION | IGNORED
    sentence: str = ""
    matched_key: str | None = None
    record_scale: str | None = None
    claimed_scales: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text, "value": self.value, "verdict": self.verdict,
            "matched_key": self.matched_key, "record_scale": self.record_scale,
            "claimed_scales": self.claimed_scales,
            "sentence": self.sentence[:160],
        }


@dataclass
class ProvenanceReport:
    claims: list[ClaimCheck] = field(default_factory=list)
    passed: bool = True
    violations: list[str] = field(default_factory=list)
    ambiguous_matches: int = 0   # toleransta >1 kayıtla eşleşen iddia sayısı (telemetri)

    @property
    def counts(self) -> dict:
        c = {"GROUNDED": 0, "UNGROUNDED": 0, "SCALE_VIOLATION": 0,
             "UNIT_MISMATCH": 0, "IGNORED": 0}
        for cl in self.claims:
            c[cl.verdict] += 1
        return c

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "counts": self.counts,
            "ambiguous_matches": self.ambiguous_matches,
            "violations": self.violations,
            "claims": [c.to_dict() for c in self.claims],
            # GFS formülü A2 ön-kayıtta sabitlenir; burada yalnız HAM bileşenler verilir.
            "note": "raw components only — GFS weights fixed at pre-registration (A2)",
        }


# ── Sayı çıkarımı (TR/EN format toleranslı) ─────────────────────────────────

_NUM_RE = re.compile(
    r"(?P<pct>%\s*)?(?P<num>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?P<pct2>\s*%)?(?:\s*(?P<mag>bin|milyon|milyar|thousand|million|billion|[kKM])\b)?"
)
_MAG = {"bin": 1e3, "k": 1e3, "K": 1e3, "milyon": 1e6, "M": 1e6, "milyar": 1e9,
        "thousand": 1e3, "million": 1e6, "billion": 1e9}   # EN büyüklükler


def _candidate_values(token: str, mag: str | None) -> list[float]:
    """Bir sayı token'ı için olası değerler (TR '1.234,56' vs EN '1,234.56'
    belirsizliği → her iki yorum da adaydır; provenance'la eşleşen kazanır)."""
    cands: set[float] = set()
    t = token
    if "." in t and "," in t:
        # sağdaki ayraç ondalık
        if t.rfind(",") > t.rfind("."):
            cands.add(float(t.replace(".", "").replace(",", ".")))
        else:
            cands.add(float(t.replace(",", "")))
    elif "," in t:
        parts = t.split(",")
        if len(parts) == 2:                               # tek virgül → ondalık ADAY
            cands.add(float(t.replace(",", ".")))         # ("3,24"; "0,968"; "1,043" pu)
        cands.add(float(t.replace(",", "")))              # "1,234" → binlik aday
    elif "." in t:
        parts = t.split(".")
        # tek nokta → ondalık ADAY (EN: "0.968"=0.968, "8.5"=8.5, "219.000"=219.0)
        if len(parts) == 2:
            cands.add(float(t))
        # 3-basamaklı gruplar → binlik ADAY (TR: "219.000"=219000)
        if all(len(p) == 3 for p in parts[1:]):
            cands.add(float(t.replace(".", "")))
        if not cands:
            cands.add(float(t.replace(".", "")))
    else:
        cands.add(float(t))
    mult = _MAG.get(mag or "", 1.0)
    return [c * mult for c in cands]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _sentence_scales(sentence: str) -> list[str]:
    low = sentence.lower()
    scales = [s for s, kws in _SCALE_KEYWORDS.items() if any(k in low for k in kws)]
    # Agregasyon deseni ("tüm 40 haneye kurarsak…") bina-ötesi genellemeyi ima eder;
    # bina kelimesi agregasyon nesnesi olduğundan building'i iddia SAYMAZ.
    if _AGGREGATION_RE.search(low):
        if SCALE_BUILDING in scales:
            scales.remove(SCALE_BUILDING)
        if SCALE_FEEDER not in scales and SCALE_POLICY not in scales:
            scales.append(SCALE_FEEDER)
    return scales


def _matches(v: float, rv: float) -> bool:
    if rv == 0:
        return abs(v) < 1e-9
    if abs(rv) <= 1.5:
        # ORAN/pu kayıtları (0-1 bandı): 0.5 mutlak tolerans SAÇMADIR — her
        # %-iddiası /100'le her orana 'eşleşirdi' (G4 pilotunda %35,1↔0.538
        # çarpışması böyle kaçtı). Sıkı: %2 göreli veya 0.01 mutlak.
        tol = max(_REL_TOL * abs(rv), 0.01)
    elif abs(rv) < _SMALL_VALUE:
        tol = max(_ABS_TOL_SMALL, _REL_TOL * abs(rv))   # yıl/kW yuvarlaması
    else:
        tol = _REL_TOL * abs(rv)
    return abs(v - rv) <= tol


# ── Provenance grafı ────────────────────────────────────────────────────────

class ProvenanceGraph:
    """Bir sohbet turundaki TÜM araç çağrılarının sayısal çıktı ve girdilerini
    provenance kayıtları olarak tutar; LLM final metnini bunlara karşı denetler."""

    MAX_LEAVES_PER_TOOL = 300   # cashflow listeleri vb. için üst sınır

    MAX_SESSION_RECORDS = 600   # oturum-kalıcı kayıt üst sınırı (A1-r1)

    def __init__(self) -> None:
        self.records: list[ProvenanceRecord] = []

    @property
    def has_records(self) -> bool:
        return bool(self.records)

    # ---- oturum kalıcılığı (A1-r1: G2 blocker düzeltmesi) --------------------
    # Graf tur-başına sıfırlanırsa, önceki turun DOĞRU sayıları sonraki turda
    # sahte-UNGROUNDED olur — G2'nin ölçeceği etkiyle aynı yönde artefakt.
    def load_records(self, dicts: list[dict]) -> None:
        for d in dicts or []:
            try:
                self.records.append(ProvenanceRecord.from_dict(d))
            except Exception:
                continue

    def records_as_dicts(self) -> list[dict]:
        return [r.to_dict() for r in self.records[-self.MAX_SESSION_RECORDS:]]

    def add_tool_result(self, tool_name: str, args: dict, stakeholder: str,
                        result: dict | None) -> None:
        scale = TOOL_SCALE.get(tool_name, SCALE_BUILDING)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tariff_vintage = _tariff_vintage()

        def _add(key: str, val: float, source: str) -> None:
            leaf = key.split(".")[-1]
            if source == "input":
                unit, conf = _ARG_UNITS.get(leaf.replace("input:", ""), ""), "input"
            else:
                unit, conf = _KEY_META.get(leaf, ("", "model"))
            vintage = tariff_vintage if leaf in _FINANCIAL_KEYS else ts[:10]
            self.records.append(ProvenanceRecord(
                key=key, value=float(val), source_function=source,
                parameters={k: v for k, v in (args or {}).items()
                            if isinstance(v, (int, float, str))},
                stakeholder=stakeholder, scale=scale,
                timestamp=ts, vintage=vintage, unit=unit, confidence=conf,
            ))

        # Girdi parametreleri de temellendirilmiş sayılardır ("10 kW sistem" gibi)
        for k, v in (args or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                _add(f"input:{k}", v, "input")

        # Sonucun sayısal yaprakları (özyinelemeli, sınırlı)
        count = 0

        def _walk(obj, path: str) -> None:
            nonlocal count
            if count >= self.MAX_LEAVES_PER_TOOL:
                return
            if isinstance(obj, bool) or obj is None:
                return
            if isinstance(obj, (int, float)):
                _add(path, obj, tool_name)
                count += 1
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("error", "status"):
                        continue
                    _walk(v, f"{path}.{k}" if path else k)
            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj):
                    _walk(v, f"{path}[{i}]")

        if isinstance(result, dict) and result.get("status") != "simulation_failed":
            _walk(result, "")

    # ---- denetim -----------------------------------------------------------

    def check_response(self, text: str) -> ProvenanceReport:
        report = ProvenanceReport()
        # v4.2 (A21): boş graf da denetlenir — kayıt yoksa her sayı UNGROUNDED/IGNORED
        if not text:
            return report

        for sentence in _split_sentences(text):
            claimed = _sentence_scales(sentence)
            for m in _NUM_RE.finditer(sentence):
                token = m.group("num")
                is_pct = bool(m.group("pct") or m.group("pct2"))
                cands = _candidate_values(token, m.group("mag"))
                if is_pct:
                    # yüzde iddiası, kayıtta 0-1 ORAN olarak durabilir (%53,8 ↔ 0.538)
                    cands = cands + [c / 100.0 for c in cands]
                claim_unit = "%" if is_pct else _infer_claim_unit(
                    sentence, m.start(), m.end())

                # A1-r2: iki geçişli eşleştirme — önce BİRİM-UYUMLU kayıtlar;
                # yalnız birim-ÇELİŞEN kayıt eşleşiyorsa → UNIT_MISMATCH
                # ("doğru sayı / yanlış kaynak": üretim-kWh'si tasarruf-TL diye sunulmuş)
                matched: ProvenanceRecord | None = None
                matched_val = None
                unit_conflict: ProvenanceRecord | None = None
                n_compatible = 0
                for v in cands:
                    for r in self.records:
                        if not _matches(v, r.value):
                            continue
                        if _units_compatible(claim_unit, r.unit):
                            n_compatible += 1
                            if matched is None:
                                matched = r
                                matched_val = v
                        elif unit_conflict is None:
                            unit_conflict = r
                            matched_val = matched_val if matched else v
                    if matched:
                        break
                if n_compatible > 1:
                    report.ambiguous_matches += 1   # telemetri: çakışan eşleşme

                if matched is None and unit_conflict is not None:
                    report.claims.append(ClaimCheck(
                        text=m.group(0).strip(), value=matched_val,
                        verdict="UNIT_MISMATCH", sentence=sentence,
                        matched_key=unit_conflict.key,
                        record_scale=unit_conflict.scale,
                        claimed_scales=claimed,
                    ))
                    continue

                if matched is None:
                    v0 = cands[0]
                    year_like = (v0 == int(v0) and _YEAR_RANGE[0] <= v0 <= _YEAR_RANGE[1]
                                 and not is_pct and "." not in token and "," not in token)
                    # Karar-kritik payback iddiası: küçük-tamsayı muafiyeti GEÇERSİZ.
                    # Pencere ±25 karakter (cümle-düzeyi, bileşik cümlede "25 yıllık
                    # ömür"ü yanlış bloklardı); yıl-sayıları (2026) ve ≥100 hariç.
                    window = sentence[max(0, m.start() - 25):m.end() + 25].lower()
                    payback_claim = (claim_unit == "yıl" and v0 < 100 and not year_like
                                     and any(cue in window for cue in _PAYBACK_CUES))
                    count_context = bool(_COUNT_CONTEXT_RE.match(sentence[m.end():]))
                    ignorable = not payback_claim and (
                        count_context or
                        (v0 == int(v0) and int(v0) in _IGNORABLE_INTS) or
                        year_like
                    )
                    report.claims.append(ClaimCheck(
                        text=m.group(0).strip(), value=v0,
                        verdict="IGNORED" if ignorable else "UNGROUNDED",
                        sentence=sentence, claimed_scales=claimed,
                    ))
                    continue

                # Ölçek denetimi: kayıt building iken cümle feeder/policy iddia ediyorsa vb.
                verdict = "GROUNDED"
                if claimed and matched.scale not in claimed:
                    verdict = "SCALE_VIOLATION"
                report.claims.append(ClaimCheck(
                    text=m.group(0).strip(), value=matched_val,
                    verdict=verdict, sentence=sentence,
                    matched_key=matched.key, record_scale=matched.scale,
                    claimed_scales=claimed,
                ))

        for c in report.claims:
            if c.verdict == "UNGROUNDED":
                report.violations.append(
                    f"UNGROUNDED: '{c.text}' — hiçbir araç çıktısında/girdisinde yok "
                    f"(cümle: {c.sentence[:80]}…)")
            elif c.verdict == "SCALE_VIOLATION":
                report.violations.append(
                    f"SCALE_VIOLATION: '{c.text}' ({c.matched_key}, ölçek={c.record_scale}) "
                    f"cümlede {c.claimed_scales} ölçeği iddia ediliyor — sayı bu ölçekte "
                    f"doğrulanmamıştır (cümle: {c.sentence[:80]}…)")
            elif c.verdict == "UNIT_MISMATCH":
                report.violations.append(
                    f"UNIT_MISMATCH: '{c.text}' değeri kaynakta '{c.matched_key}' olarak "
                    f"üretilmiş — metin farklı bir birim/nicelik olarak sunuyor "
                    f"(cümle: {c.sentence[:80]}…)")
        report.passed = not report.violations
        return report

    # ---- bloklama yedeği ----------------------------------------------------

    # (key, TR-etiket, EN-etiket, fmt) — CROSS-LINGUAL: safe_summary dile göre seçer
    _SUMMARY_KEYS = [
        ("npv_tl", "Net bugünkü değer", "Net present value", "{:,.0f} TL"),
        ("annual_savings_tl", "Yıllık tasarruf", "Annual savings", "{:,.0f} TL"),
        ("simple_payback_years", "Basit geri ödeme", "Simple payback", "{:.1f} yıl"),
        ("irr_percent", "İç verim oranı", "Internal rate of return", "%{:.1f}"),
        ("annual_production_kwh", "Yıllık üretim", "Annual production", "{:,.0f} kWh"),
        ("self_consumption_ratio", "Öz-tüketim oranı", "Self-consumption ratio", "%{:.1f}"),
        ("hosting_capacity_pct", "Hosting kapasitesi", "Hosting capacity", "%{:.1f}"),
        ("max_line_loading_pct", "Maks. hat yüklenmesi", "Max line loading", "%{:.1f}"),
    ]

    # v4.2 (A21): boş-graf bloğu — SAYI İÇERMEZ (kendi denetiminden geçer)
    _EMPTY_GRAPH_SUMMARY = {
        "tr": ("Henüz bir simülasyon çalıştırılmadığı için doğrulanmış bir rakam "
               "veremiyorum. Konum, kurulu güç ya da aylık fatura gibi girdileri "
               "paylaşırsanız ilgili simülasyonu çalıştırabilirim.\n\n"
               "Not: Yanıt, içerdiği sayılar hiçbir simülasyon çıktısına dayanmadığı "
               "için (provenance guard) bu mesajla değiştirilmiştir."),
        "en": ("No simulation has been run yet, so I cannot give verified figures. "
               "If you share inputs such as the location, the installed capacity or "
               "the monthly bill, I can run the relevant simulation.\n\n"
               "Note: the response was replaced with this message because its numbers "
               "do not originate from any simulation output (provenance guard)."),
    }

    def safe_summary(self, tool_result: dict | None, lang: str = "tr") -> str:
        """Deterministik, yalnız-temellendirilmiş-sayı içeren yedek yanıt.
        Guard blokladığında LLM metni yerine bu döner (asla temelsiz sayı sızmaz).
        lang: 'tr' | 'en' (cross-lingual koşul)."""
        en = lang == "en"
        if not self.records:
            # v4.2 (A21): araç çağrılmamış tur — simülasyon yapılmış gibi gösterme
            return self._EMPTY_GRAPH_SUMMARY["en" if en else "tr"]
        header =("Simulation results (verified values):" if en
                  else "Simülasyon sonuçları (doğrulanmış değerler):")
        lines = [header]
        src = tool_result or {}
        for key, tr_label, en_label, fmt in self._SUMMARY_KEYS:
            val = src.get(key)
            if val is None:
                continue
            v = float(val)
            if key == "self_consumption_ratio" and v <= 1.0:
                v *= 100.0
            val_str = fmt.format(v)
            if en:                                   # birim yerelleştir: "yıl"->"years", "%X"->"X%"
                val_str = val_str.replace(" yıl", " years")
                if val_str.startswith("%"):
                    val_str = val_str[1:] + "%"
            lines.append(f"• {(en_label if en else tr_label)}: {val_str}")
        if len(lines) == 1:
            lines.append("• (no summarizable numeric field found)" if en
                         else "• (özetlenebilir sayısal alan bulunamadı)")
        lines.append("")
        lines.append(
            "Note: the response was replaced with a deterministic summary because the "
            "numeric verification (provenance guard) could not match the LLM text's "
            "values to the simulation source." if en else
            "Not: Yanıt, sayısal doğrulama (provenance guard) LLM metnindeki "
            "değerleri simülasyon kaynağıyla eşleyemediği için deterministik "
            "özetle değiştirilmiştir.")
        return "\n".join(lines)

    def corrective_instruction(self, report: ProvenanceReport, lang: str = "tr") -> str:
        """Bloklama öncesi tek düzeltme denemesi için sisteme eklenecek talimat."""
        v = "\n".join(f"- {x}" for x in report.violations[:8])
        if not self.records:
            # v4.2 (A21): araç çıktısı yok → "araç çıktısındaki sayıları kullan" denemez.
            # Düzeltme denemesi metin-only (araç yürütülmez) → modelden sayısız yanıt istenir.
            if lang == "en":
                return (
                    "NUMERIC VERIFICATION WARNING: no simulation has been run in this "
                    "conversation, so the numbers in your last response cannot be verified "
                    f"against any simulation output:\n{v}\n"
                    "Rewrite the response without stating numerical results: say which "
                    "simulation you can run and which inputs you need from the user. "
                    "Do not call a tool in this reply.")
            return (
                "SAYISAL DOĞRULAMA UYARISI: Bu konuşmada henüz simülasyon çalıştırılmadı; "
                "son yanıtındaki sayılar hiçbir simülasyon çıktısına dayanmadığı için "
                f"doğrulanamıyor:\n{v}\n"
                "Yanıtı sayısal sonuç vermeden yeniden yaz: hangi simülasyonu "
                "çalıştırabileceğini ve bunun için kullanıcıdan hangi girdilere ihtiyacın "
                "olduğunu söyle. Bu yanıtta araç çağırma.")
        if lang == "en":
            return (
                "NUMERIC VERIFICATION WARNING: the following numbers in your last "
                f"response do not match the simulation output or are used at the wrong "
                f"scale:\n{v}\n"
                "Rewrite the response using ONLY the numbers from the tool output, in the "
                "scale context they were produced. Do not invent numbers, do not generalize scale.")
        return (
            "SAYISAL DOĞRULAMA UYARISI: Son yanıtındaki şu sayılar simülasyon "
            f"çıktısıyla eşleşmiyor veya yanlış ölçekte kullanılmış:\n{v}\n"
            "Yanıtı YALNIZCA araç (tool) çıktısındaki sayıları, ürettikleri ölçek "
            "bağlamında kullanarak yeniden yaz. Yeni sayı üretme, ölçek genelleme yapma.")
