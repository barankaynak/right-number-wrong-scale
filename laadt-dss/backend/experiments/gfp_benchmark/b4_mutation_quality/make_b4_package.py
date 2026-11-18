"""B4 — G4 mutasyon-kalitesi insan-kodlama paketi üreticisi (BİRLEŞİK: TR+EN+Mistral).

Danışman v2.12.6-2 "yayın-kapısı" + v2.17: H_G4 ve genelleme-koşularının (TR-primary,
EN, Mistral) enjeksiyonlarının %20'si, 2 bağımsız kodlayıcı tarafından AKICILIK +
KATEGORİ-UYGUNLUĞU açısından, guard'ın kararına KÖR olarak denetlenir. Bu script kör
kodlama-sayfasını + gizli guard-key'i `results/` ham JSONL'lerinden determinist
(seed=42) üretir.

Üç G4 seti (hepsi %20, kategori-oranıyla katmanlı):
- **tr** (primary, H_G4): donmuş `raw_g4_final_seed42_20260709T011118Z.jsonl` (109) —
  metni saklamadığından, `run_g4_final`'ın source+mutated ekli determinist yeniden-koşusu
  (`raw_g4_final_seed42_2026071*`) ile (qid,cat,model,config,repeat) eşleştirilerek
  OTANTİK metin alınır (97/109 örtüşür; örneklem yalnız otantik-metinliden).
- **en**: `raw_g4_final_en_seed42_*` (87) — source/mutated DOĞRUDAN taşır.
- **mistral**: `raw_g4_final_mistral-small3.2-24b_seed42_*` (66) — doğrudan taşır.

KÖR: kodlayıcı gfp/legacy tespit-bayraklarını GÖRMEZ (guard-key ayrı). set/dil GÖRÜNÜR
(akıcılık dile göre yargılanır). Metrik metne değil tespit-bayraklarına göre.

Kullanım: python -m experiments.gfp_benchmark.b4_mutation_quality.make_b4_package
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GFP = HERE.parent
RESULTS = GFP / "results"
SEED = 42
FRAC = 0.20

FROZEN_TR = RESULTS / "raw_g4_final_seed42_20260709T011118Z.jsonl"
CATS = ("value_fabrication", "unit_swap", "scale_swap", "small_int_fabrication")
CAT_LABEL = {
    "value_fabrication": "value-fabrication (grounded sayi ×[1.5-3.0] bozuldu)",
    "unit_swap": "unit-swap (birim degistirildi: TL<->kWh)",
    "scale_swap": "scale-swap (cumle bina->fider/mahalle; SAYI AYNEN)",
    "small_int_fabrication": "small-int (karar-kritik kucuk tamsayi degistirildi)",
}
SET_LABEL = {"tr": "TR (primary)", "en": "EN", "mistral": "Mistral (TR)"}
PREFIX = {"tr": "TR", "en": "EN", "mistral": "MI"}

_CTX = 110


def _diff_span(source: str, mutated: str) -> tuple[int, int]:
    """Ortak ön-ek uzunluğu i, ortak son-ek uzunluğu js."""
    i = 0
    while i < len(source) and i < len(mutated) and source[i] == mutated[i]:
        i += 1
    js = 0
    while (js < len(source) - i and js < len(mutated) - i
           and source[-1 - js] == mutated[-1 - js]):
        js += 1
    return i, js


def _changed_window(source: str, mutated: str) -> tuple[str, str]:
    """Değişim etrafında kısa (±_CTX) tek-satır bağlam-penceresi; >>...<< işaretli."""
    i, js = _diff_span(source, mutated)
    s_mid, m_mid = source[i:len(source) - js], mutated[i:len(mutated) - js]
    pre, post = source[:i], source[len(source) - js:]
    left = pre[-_CTX:].replace("\n", " ")
    right = post[:_CTX].replace("\n", " ")
    lead = "..." if len(pre) > _CTX else ""
    tail = "..." if len(post) > _CTX else ""
    src = f"{lead}{left}>>{s_mid}<<{right}{tail}".strip()
    mut = f"{lead}{left}>>{m_mid}<<{right}{tail}".strip()
    return re.sub(r"\s+", " ", src), re.sub(r"\s+", " ", mut)


def _mark_full(source: str, mutated: str) -> tuple[str, str]:
    """TAM metin (kırpma yok, newline'lar korunur), değişen bölüm >>...<< işaretli."""
    i, js = _diff_span(source, mutated)
    s = source[:i] + ">>" + source[i:len(source) - js] + "<<" + source[len(source) - js:]
    m = mutated[:i] + ">>" + mutated[i:len(mutated) - js] + "<<" + mutated[len(mutated) - js:]
    return s, m


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _latest(pat: str) -> Path | None:
    hits = sorted(glob.glob(str(RESULTS / pat)))
    return Path(hits[-1]) if hits else None


def _row(setname, r, src, mut):
    """kodlama+key satiri (otantik metinli)."""
    ss, ms = _changed_window(src, mut)
    fs, fm = _mark_full(src, mut)
    return {
        "set": setname, "category": r["category"],
        "qid": r.get("qid"), "model": r.get("model"),
        "config": r.get("config"), "repeat": r.get("repeat"),
        "source_sentence": ss, "mutated_sentence": ms,
        "full_original": fs, "full_mutated": fm,
        "gfp_ref_detected": r["gfp_ref_detected"],
        "legacy_primary_detected": r["legacy_primary_detected"],
        "legacy_s1_warn_detected": r.get("legacy_s1_warn_detected"),
        "legacy_s2_ceiling_detected": r.get("legacy_s2_ceiling_detected"),
    }


def build_tr_pool() -> dict:
    """TR-primary: donmuş 109'u source+mutated ekli yeniden-koşuyla eşleştir."""
    frozen = [r for r in _load(FROZEN_TR) if r["kind"] == "injected"]
    enr = _latest("raw_g4_final_seed42_2026071*.jsonl")  # source+mutated ekli tr yeniden-koşu
    enriched = {(r["qid"], r["category"], r["model"], r["config"], r.get("repeat")): r
                for r in _load(enr) if r["kind"] == "injected" and r.get("mutated")}
    pool = {c: [] for c in CATS}
    for r in frozen:
        e = enriched.get((r["qid"], r["category"], r["model"], r["config"], r.get("repeat")))
        if e:
            pool[r["category"]].append(_row("tr", r, e["source"], e["mutated"]))
    return pool


def build_direct_pool(setname: str, pat: str) -> dict:
    f = _latest(pat)
    pool = {c: [] for c in CATS}
    if not f:
        return pool
    for r in _load(f):
        if r["kind"] == "injected" and r.get("mutated"):
            pool[r["category"]].append(_row(setname, r, r["source"], r["mutated"]))
    return pool


def main() -> None:
    rng = random.Random(SEED)
    pools = {
        "tr": build_tr_pool(),
        "en": build_direct_pool("en", "raw_g4_final_en_seed42_*.jsonl"),
        "mistral": build_direct_pool("mistral", "raw_g4_final_mistral-small3.2-24b_seed42_*.jsonl"),
    }
    sample = []
    print("set        n_inj  ornek(kategori)")
    for s in ("tr", "en", "mistral"):
        p = pools[s]
        n_inj = sum(len(v) for v in p.values())
        picks = []
        for c in CATS:
            k = max(1, round(FRAC * len(p[c]))) if p[c] else 0
            k = min(k, len(p[c]))
            picks += rng.sample(p[c], k) if k else []
        rng.shuffle(picks)
        for i, row in enumerate(picks, 1):
            row["item_id"] = f"B4-{PREFIX[s]}-{i:02d}"
        sample += picks
        cat_n = {c: sum(1 for r in picks if r["category"] == c) for c in CATS}
        print(f"{SET_LABEL[s]:14} {n_inj:4}  {len(picks)} ({cat_n})")

    # ---- kör kodlama sayfası ----
    sheet = HERE / "B4_coding_sheet.csv"
    with sheet.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "set", "intended_category", "original_sentence",
                    "mutated_sentence", "full_original", "full_mutated",
                    "fluent_YN", "category_correct_YN", "coder_notes"])
        for r in sample:
            w.writerow([r["item_id"], SET_LABEL[r["set"]], CAT_LABEL[r["category"]],
                        r["source_sentence"], r["mutated_sentence"],
                        r["full_original"], r["full_mutated"], "", "", ""])

    # ---- gizli guard-key ----
    key = HERE / "B4_guard_key.csv"
    with key.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "set", "qid", "category", "model", "config", "repeat",
                    "gfp_ref_detected", "legacy_primary_detected",
                    "legacy_s1_warn_detected", "legacy_s2_ceiling_detected"])
        for r in sorted(sample, key=lambda x: x["item_id"]):
            w.writerow([r["item_id"], r["set"], r["qid"], r["category"], r["model"],
                        r["config"], r["repeat"], r["gfp_ref_detected"],
                        r["legacy_primary_detected"], r["legacy_s1_warn_detected"],
                        r["legacy_s2_ceiling_detected"]])

    sha = hashlib.sha256(sheet.read_bytes()).hexdigest()
    ksha = hashlib.sha256(key.read_bytes()).hexdigest()
    print(f"\nTOPLAM ornek: {len(sample)} satir (TR+EN+Mistral %20)")
    print(f"-> {sheet.name}  SHA-256 {sha}")
    print(f"-> {key.name}  SHA-256 {ksha}")
    print("DONMA: SHA-256'lari PREREGISTRATION §9 (B4-genisletme) yaz; sonra kodlama basla.")


if __name__ == "__main__":
    main()
