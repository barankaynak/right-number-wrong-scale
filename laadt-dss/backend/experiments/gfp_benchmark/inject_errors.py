"""
G4 hata-enjeksiyon aracı — guard recall/precision ölçümü.

Temellendirilmiş (grounded) bir yanıta KONTROLLÜ hata enjekte eder ve iki
guard'ın (GFP provenance vs. legacy regex) yakalama oranını karşılaştırır.

Enjeksiyon kategorileri (PREREGISTRATION §G4):
    value_fabrication      : temellendirilmiş sayı ×[1.5–3.0] bozulur
    unit_swap              : birim değiştirilir (TL↔kWh) — "doğru sayı/yanlış nicelik"
    scale_swap             : cümle bina→şebeke/mahalle çerçevesine yeniden yazılır,
                             SAYI AYNEN kalır — "doğru sayı/yanlış ölçek" (GFP çekirdeği)
    small_int_fabrication  : küçük tamsayı değiştirilir ("7 yıl"→"3 yıl") —
                             _IGNORABLE_INTS kaçağını ölçer (bilinen sınır, A1-r4)

Deterministiktir (--seed). PİLOT modu dev-korpus üzerinde mekanizmayı doğrular;
NİHAİ G4 koşusu, ön-kayıt gereği G1 koşusundan gelen grounded yanıtlar üzerinde
yapılır (dev-korpus kalibrasyon setidir, test seti DEĞİLDİR — kontaminasyon notu).
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

CATEGORIES = ("value_fabrication", "unit_swap", "scale_swap", "small_int_fabrication")

_NUM = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def _fmt_tr(x: float) -> str:
    if x == int(x) and abs(x) >= 1000:
        return f"{int(x):,}".replace(",", ".")
    if x == int(x):
        return str(int(x))
    return f"{x:.1f}".replace(".", ",")


def _fmt_en(x: float) -> str:
    """İngilizce sayı formatı (virgül-binlik, nokta-ondalık)."""
    if x == int(x):
        return f"{int(x):,}"
    return f"{x:,.1f}"


def _fmt(x: float, lang: str = "tr") -> str:
    return _fmt_en(x) if lang == "en" else _fmt_tr(x)


# scale_swap: bina-çerçevesi → şebeke/mahalle çerçevesi (SAYI AYNEN); dile göre
_SCALE_SWAPS = {
    "tr": [("eviniz", "mahalledeki tüm 40 ev"), ("evin", "mahalledeki tüm 40 ev"),
           ("Çatınıza", "Mahalledeki trafo bölgesine"),
           ("binanız", "fider genelinde"), ("Sistem", "Mahalle genelinde sistem"),
           ("işletmeniz", "bölgedeki dağıtım şebekesi"),
           ("Tesisiniz", "Fider üzerindeki tüm tesisler")],
    "en": [("your home", "all 40 homes in the neighbourhood"),
           ("your house", "all 40 houses in the neighbourhood"),
           ("your building", "the whole feeder"),
           ("your roof", "the neighbourhood transformer district"),
           ("your facility", "the distribution grid in the region"),
           ("your business", "all businesses on the feeder"),
           ("your system", "the neighbourhood-wide system"),
           ("your factory", "all factories in the industrial zone")],
}


def inject(text: str, category: str, rng: random.Random, lang: str = "tr") -> str | None:
    """Metne tek bir hata enjekte eder; uygulanamıyorsa None. lang: 'tr' | 'en'."""
    if category == "value_fabrication":
        ms = list(_NUM.finditer(text))
        big = [m for m in ms if len(m.group(0)) >= 4]      # anlamlı büyük sayılar
        if not big:
            return None
        m = rng.choice(big)
        try:
            val = float(m.group(0).replace(".", "").replace(",", "."))
        except ValueError:
            return None
        new = val * rng.uniform(1.5, 3.0)
        return text[:m.start()] + _fmt(new, lang) + text[m.end():]

    if category == "unit_swap":                            # dil-nötr (TL↔kWh)
        if "kWh" in text:
            return text.replace("kWh", "TL", 1)
        if "TL" in text:
            return text.replace("TL", "kWh", 1)
        return None

    if category == "scale_swap":
        # Bina çerçevesi → şebeke/mahalle çerçevesi; SAYILAR AYNEN KALIR
        for old, new in _SCALE_SWAPS.get(lang, _SCALE_SWAPS["tr"]):
            if old in text:
                return text.replace(old, new, 1)
        return None

    if category == "small_int_fabrication":                # "7 yıl" / "7 years"
        m = re.search(r"\b([4-9]|1[0-9]|2[0-4])\s*(yıl|years?)", text)
        if not m:
            return None
        cur = int(m.group(1))
        alt = rng.choice([x for x in (2, 3, 12, 25) if x != cur])
        return text[:m.start(1)] + str(alt) + text[m.end(1):]

    raise ValueError(category)


def run_pilot(seed: int, per_category: int) -> Path:
    """Dev-korpus üzerinde mekanizma pilotu: her kategoriden N enjeksiyon +
    N bozulmamış kontrol; iki guard'ın kararları kaydedilir."""
    from app.llm.provenance_guard import ProvenanceGraph
    from app.llm.hallucination_guard import validate_response

    corpus = json.loads((HERE / "dev_corpus.json").read_text(encoding="utf-8"))
    fixtures = corpus["fixtures"]
    rng = random.Random(seed)
    RESULTS.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS / f"raw_g4_pilot_seed{seed}_{ts}.jsonl"

    def _guards(entry, text):
        fx = fixtures[entry["fixture"]]
        g = ProvenanceGraph()
        g.add_tool_result(fx["tool_name"], fx["args"], fx["stakeholder"], fx["result"])
        prov = g.check_response(text)
        legacy = validate_response(text, fx["result"])
        return {
            "prov_detected": not prov.passed,
            "prov_counts": prov.counts,
            "prov_violations": prov.violations,
            # legacy guard 'violations' ÜRETMİYORSA warnings'i de tespit SAYMA —
            # baseline'ın gerçek bloklama-kararı violations'tır
            "legacy_detected": not legacy.passed,
            "legacy_warnings": len(legacy.warnings),
        }

    n_inj = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for cat in CATEGORIES:
            done = 0
            for entry in corpus["replies"]:
                if done >= per_category:
                    break
                mutated = inject(entry["text"], cat, rng)
                if mutated is None or mutated == entry["text"]:
                    continue
                done += 1
                n_inj += 1
                rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "kind": "injected", "category": cat, "corpus_id": entry["id"],
                       "original": entry["text"], "mutated": mutated,
                       **_guards(entry, mutated)}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # Kontroller (precision): bozulmamış yanıtlar
        for entry in corpus["replies"]:
            rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "kind": "control", "category": None, "corpus_id": entry["id"],
                   "original": entry["text"], "mutated": entry["text"],
                   **_guards(entry, entry["text"])}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"{n_inj} enjeksiyon + {len(corpus['replies'])} kontrol → {out_path}")
    return out_path


def summarize(path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    summary: dict = {}
    for cat in CATEGORIES:
        inj = [r for r in rows if r["kind"] == "injected" and r["category"] == cat]
        if not inj:
            continue
        summary[cat] = {
            "n": len(inj),
            "prov_recall": round(sum(r["prov_detected"] for r in inj) / len(inj), 3),
            "legacy_recall": round(sum(r["legacy_detected"] for r in inj) / len(inj), 3),
        }
    ctrl = [r for r in rows if r["kind"] == "control"]
    if ctrl:
        summary["controls"] = {
            "n": len(ctrl),
            "prov_fp_rate": round(sum(r["prov_detected"] for r in ctrl) / len(ctrl), 3),
            "legacy_fp_rate": round(sum(r["legacy_detected"] for r in ctrl) / len(ctrl), 3),
        }
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-category", type=int, default=8)
    a = ap.parse_args()
    p = run_pilot(a.seed, a.per_category)
    print(json.dumps(summarize(p), ensure_ascii=False, indent=1))
