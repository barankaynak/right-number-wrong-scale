"""A26 — Canlı ölçek-iddiası ve sözlük-geçerliliği: tuzak sorularında tabakalı insan-kodlu
cümle-düzeyi ölçek (n≈250) + opsiyonel Jev ölçeklendirici [PRE-OUTCOME; prereg-v3.2].

Hedef konum: experiments/gfp_benchmark/ (koşu sürerken uvicorn --reload nedeniyle
laadt-dss/prereg_staging/ altında donduruldu; koşu sonrası bayt-özdeş taşınır).

Komutlar:
  build    (konteyner) grounded_noguard × tuzak yanıtları → cümle popülasyonu → tabakalar
           (S2 → S1 → S3) → seed-42 örneklem/permütasyon → kodlama paketleri + gizli anahtar
  jev      (ana makine) kodlanacak cümlelerde Jev Choice (asserted_scale) + Noul (aggregation)
           [--scale-out] yalnız dondurulmuş κ-kapısı (multi κ ≥ 0.6, a26_results.json'dan)
           geçtiyse kalan tuzak + tuzak-dışı grounded_noguard cümlelerine (ayrı dosya/blok)
  analyze  (konteyner) iki kodlayıcı CSV'si (+ varsa konsensüs) → κ, tabaka-özgü Wilson,
           Horvitz–Thompson + yanıt-kümeli bootstrap, S2 restatement, T2, parametrik
           agregasyon, A22-1 yol çaprazı, Jev bloğu → a26_results.json + .md
Çıktı dizini: results/<GFP_RUN_DIR>/a26/. Sözlük/parser değişmez; yeniden-skorlama yok
(in-run `provenance.claims` izden okunur). Jev çıktısı insan paketine sızmaz.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

if globals().get("__file__", "<stdin>").endswith(".py"):
    HERE = Path(__file__).resolve().parent
else:                                              # stdin ile duman-testi
    HERE = Path(os.environ.get("GFP_BENCH_DIR", "/app/experiments/gfp_benchmark"))
OUT = HERE / "results" / os.environ.get("GFP_RUN_DIR", "") / "a26"
SEED = 42
BOOT_SEED, BOOT_N = 20261014, 1000
N_TOTAL, N3_MIN, S1_CAP = 250, 100, 150
VARS = ("scale_building_YN", "scale_multi_feeder_YN", "scale_policy_YN", "aggregation_YN",
        "unsure_YN")
SCALE_CLASSES = {
    "building": "One installation: a single home, flat, roof, business or 'the system' asked about.",
    "multi_feeder": "Several buildings, a street, neighbourhood, feeder, transformer, region or a "
                    "grid quantity (hosting capacity, penetration, feeder voltage).",
    "policy": "National, provincial or programme level: incentive budgets, cost to the state.",
    "none": "No spatial scale asserted: a general price, rate, date or explanation of method.",
}


# ── build ─────────────────────────────────────────────────────────────────────

def _population():
    from app.llm.provenance_guard import _split_sentences
    from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    smoke_all = os.environ.get("GFP_SMOKE_ALL_QUESTIONS") == "1"   # yalnız duman-testi
    traps = {q["id"] for q in qs if smoke_all or q.get("scale_focus") == "cross"}
    pop, nontrap, excluded = [], [], defaultdict(int)
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        cond = f"{lang}|{model}"
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in sorted(rows, key=lambda r: (r["question"]["id"], r.get("repeat", 0))):
            if r.get("config") != "grounded_noguard":
                continue
            is_trap = r["question"]["id"] in traps
            if r.get("fallback") or r.get("error"):
                excluded[cond] += is_trap
                continue
            claims = (r.get("provenance") or {}).get("claims") or []
            q = r["question"]
            for si, sent in enumerate(_split_sentences(r.get("reply") or "")):
                cs = [c for c in claims if c.get("sentence") == sent[:160]]
                if not any(c.get("verdict") != "IGNORED" for c in cs):
                    continue
                lex = sorted({s for c in cs for s in (c.get("claimed_scales") or [])})
                sim_building = [c for c in cs if c.get("record_scale") == "building"
                                and c.get("matched_key")
                                and not str(c["matched_key"]).startswith("input:")]
                (pop if is_trap else nontrap).append({
                    "condition": cond, "lang": lang, "qid": q["id"],
                    "repeat": r.get("repeat", 0), "sent_idx": si, "sentence": sent,
                    "question_text": q["question_en"] if lang == "en" else q["question_tr"],
                    "lexicon_scales": lex,
                    "matched_keys": sorted({str(c["matched_key"]) for c in cs if c.get("matched_key")}),
                    "record_scales": sorted({c["record_scale"] for c in cs if c.get("record_scale")}),
                    "echo_flag": any(str(c.get("matched_key") or "").startswith("input:") for c in cs),
                    # T2: S2 eşleşmeleri iddia-düzeyinde, karşılıklı dışlayıcı
                    # (≤100 tamsayı → oran |v|≤1.5 → diğer)
                    "s2_matches": [_t2_class(float(c["value"])) for c in sim_building
                                   if c.get("value") is not None],
                    "sim_match": any(c.get("matched_key") and not str(c["matched_key"])
                                     .startswith("input:") for c in cs),
                    "fragment_flag": len(re.findall(r"[^\W\d_]{2,}", sent)) < 2,
                    "s2_eligible": bool(sim_building),
                    "s1_eligible": bool(set(lex) & {"feeder", "policy"}),
                })
    return pop, nontrap, dict(excluded)


def _t2_class(v: float) -> str:
    if v.is_integer() and 0 <= v <= 100:
        return "small_int"
    if abs(v) <= 1.5:
        return "ratio"
    return "other"


def _largest_remainder(target: int, sizes: dict) -> dict:
    total = sum(sizes.values())
    if total <= target:
        return dict(sizes)
    raw = {k: target * v / total for k, v in sizes.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[:target - sum(out.values())]:
        out[k] += 1
    return {k: min(out[k], sizes[k]) for k in sizes}


def build() -> None:
    rng = random.Random(SEED)
    pop, nontrap, excluded = _population()
    for i, s in enumerate(pop):
        s["uid"] = i
    for i, s in enumerate(nontrap):
        s["uid"] = f"n{i}"
    s2 = [s for s in pop if s["s2_eligible"]]
    s1_pool = [s for s in pop if s["s1_eligible"] and not s["s2_eligible"]]
    s3_pool = [s for s in pop if not s["s1_eligible"] and not s["s2_eligible"]]
    s1 = s1_pool if len(s1_pool) <= S1_CAP else rng.sample(s1_pool, S1_CAP)
    n3 = max(N3_MIN, N_TOTAL - len(s1) - len(s2))
    by_cond = defaultdict(list)
    for s in s3_pool:
        by_cond[s["condition"]].append(s)
    alloc = _largest_remainder(n3, {c: len(v) for c, v in by_cond.items()})
    s3 = []
    for c in sorted(alloc):
        s3 += rng.sample(by_cond[c], alloc[c])
    for s in s2:
        s["stratum"], s["pi"] = "S2", 1.0
    for s in s1:
        s["stratum"], s["pi"] = "S1", (1.0 if len(s1_pool) <= S1_CAP else S1_CAP / len(s1_pool))
    for s in s3:
        s["stratum"] = "S3"
        s["pi"] = alloc[s["condition"]] / len(by_cond[s["condition"]])
    items = s2 + s1 + s3
    rng.shuffle(items)
    OUT.mkdir(parents=True, exist_ok=True)
    for k in (1, 2):
        # utf-8-sig: Excel (TR) Türkçe karakterleri doğru göstersin
        with (OUT / f"coding_package_coder{k}.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["item_id", "lang", "question_text", "sentence", *VARS])
            for i, s in enumerate(items, 1):
                w.writerow([f"S{i:03d}", s["lang"], s["question_text"], s["sentence"],
                            "", "", "", "", ""])
    with (OUT / "coding_key.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "uid", "stratum", "pi", "condition", "qid", "repeat", "sent_idx",
                    "lexicon_scales", "matched_keys", "record_scales", "echo_flag",
                    "sim_match", "s2_matches", "fragment_flag"])
        for i, s in enumerate(items, 1):
            w.writerow([f"S{i:03d}", s["uid"], s["stratum"], round(s["pi"], 6), s["condition"],
                        s["qid"], s["repeat"], s["sent_idx"], "|".join(s["lexicon_scales"]),
                        "|".join(s["matched_keys"]), "|".join(s["record_scales"]),
                        int(s["echo_flag"]), int(s["sim_match"]), "|".join(s["s2_matches"]),
                        int(s["fragment_flag"])])
    fields = ("uid", "condition", "qid", "repeat", "sent_idx", "lang", "question_text",
              "sentence", "lexicon_scales", "s1_eligible", "s2_eligible", "sim_match")
    for name, rows in (("population.jsonl", pop), ("population_nontrap.jsonl", nontrap)):
        with (OUT / name).open("w", encoding="utf-8") as fh:   # HT ve Jev ölçeklendirmesi
            for s in rows:
                fh.write(json.dumps({k: s[k] for k in fields}, ensure_ascii=False) + "\n")
    summary = {"N_population": len(pop), "N_nontrap_sentences": len(nontrap),
               "excluded_trap_responses_fallback_or_error": excluded,
               "pool_sizes": {"S1": len(s1_pool), "S2": len(s2), "S3": len(s3_pool)},
               "sampled": {"S1": len(s1), "S2": len(s2), "S3": len(s3)},
               "S3_allocation": alloc, "n_items": len(items),
               "fragments_in_sample": sum(s["fragment_flag"] for s in items)}
    (OUT / "population.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    built = ("coding_package_coder1.csv", "coding_package_coder2.csv", "coding_key.csv",
             "population.json", "population.jsonl", "population_nontrap.jsonl")
    digest = {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() for n in built}
    (OUT / "build_hashes.json").write_text(json.dumps(digest, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


# ── jev ───────────────────────────────────────────────────────────────────────

JEV_MODEL = "jev-1.13.0"
JEV_THRESHOLD = 0.8


def _jev_call(client, name: str, arguments: dict) -> dict:
    res = client.request("tools/call", {"name": name, "arguments": arguments})
    text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    if res.get("isError"):
        raise RuntimeError(text)
    return json.loads(text)


def _jev_request(batch: list[dict]) -> dict:
    return {
        "jev_classify": {
            "items": [{"id": f"x{i}", "text": f"Question: {b['question_text']}\nSentence: "
                                              f"{b['sentence']}"[:2000]}
                      for i, b in enumerate(batch)],
            "classes": [{"id": k, "description": v} for k, v in SCALE_CLASSES.items()],
            "purpose": "Code the spatial scale the sentence asserts (not whether its number is correct).",
        },
        "jev_noul": {
            "propositions": [
                f'In the sentence "{b["sentence"]}" (answering the question "{b["question_text"]}"), '
                f"a per-building quantity is multiplied or generalised to several buildings, a "
                f"neighbourhood or a feeder."[:2000] for b in batch],
            "auto_accept": JEV_THRESHOLD,
        },
    }


def _jev_labels(resp: dict, n: int) -> list[dict]:
    # jev-1.13.0: classify → results[{id, classification, top_probability, …}];
    # noul → results[{id: "proposition<i>", probability, …}] (gönderim sırasıyla)
    c_by = {r["id"]: r for r in resp["jev_classify"]["results"]}
    n_by = {r["id"]: r for r in resp["jev_noul"]["results"]}
    if len(c_by) != n or len(n_by) != n:
        raise RuntimeError(f"eksik yanıt: classify {len(c_by)}, noul {len(n_by)}, parti {n}")
    out = []
    for i in range(n):
        c, nl = c_by[f"x{i}"], n_by[f"proposition{i}"]
        scale = (c.get("classification") if float(c.get("top_probability") or 0) >= JEV_THRESHOLD
                 else "none")                                   # eşik altı → çekimser = none
        out.append({"scale_building_YN": scale == "building",
                    "scale_multi_feeder_YN": scale == "multi_feeder",
                    "scale_policy_YN": scale == "policy",
                    "aggregation_YN": float(nl.get("probability") or 0) >= JEV_THRESHOLD})
    return out


def _gate() -> dict:
    """Dondurulmuş κ-kapısı: Jev multi (= multi_feeder ∨ aggregation) vs insan multi,
    konsensüs varsa ona, yoksa katı (AND) etikete karşı; `a26_results.json`'dan okunur."""
    res = OUT / "a26_results.json"
    if not res.exists():
        sys.exit("a26_results.json yok: önce `jev` (kodlanan) + `analyze` koşulmalı")
    g = json.loads(res.read_text(encoding="utf-8")).get("jev", {}).get("coded", {}).get("gate")
    if not g or g.get("kappa") is None:
        sys.exit("κ-kapısı hesaplanamadı (Jev kodlanan koşusu/analyze eksik)")
    return g


def jev(scale_out: bool = False) -> None:
    sys.path.insert(0, str(HERE))
    from jev_g4 import McpClient                   # ana makine, standart kütüphane + Node
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY tanımlı değil")
    gate = None
    if not scale_out:
        log = OUT / "a26_jev_coded.jsonl"
        src = [{"id": r["item_id"], "question_text": r["question_text"], "sentence": r["sentence"]}
               for r in csv.DictReader((OUT / "coding_package_coder1.csv").open(encoding="utf-8-sig"))]
    else:
        gate = _gate()
        if gate["status"] != "complete" or gate["kappa"] < 0.6:
            sys.exit(f"κ-kapısı geçilmedi ({gate}): ölçeklendirme yapılmaz")
        log = OUT / "a26_jev_scaleout.jsonl"
        coded = {r["uid"] for r in csv.DictReader((OUT / "coding_key.csv").open(encoding="utf-8-sig"))}
        src = []
        for name in ("population.jsonl", "population_nontrap.jsonl"):
            for d in map(json.loads, (OUT / name).read_text(encoding="utf-8").splitlines()):
                if str(d["uid"]) not in coded:
                    src.append({"id": f"u{d['uid']}", "question_text": d["question_text"],
                                "sentence": d["sentence"]})
    header = {"header": True, "jev_model_expected": JEV_MODEL, "threshold": JEV_THRESHOLD,
              "kappa_gate": gate, "n_sentences": len(src)}
    done = set()
    if log.exists():                               # devam: üzerine yazma yok, aynı ayarlar şart
        lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines[0] != header:
            sys.exit(f"{log.name} farklı ayarlarla başlamış; devam edilmez")
        done = {i for r in lines if r.get("labels") for i in r["ids"]}
    todo = [b for b in src if b["id"] not in done]
    client, n_calls = McpClient(), 0
    with log.open("a", encoding="utf-8") as fh:
        if not done and log.stat().st_size == 0:
            fh.write(json.dumps(header) + "\n")
        for i in range(0, len(todo), 32):
            if n_calls + 2 > 3000:
                fh.write(json.dumps({"cap_reached": True, "n_calls": n_calls}) + "\n")
                break
            batch = todo[i:i + 32]
            req, resp, labels, err = _jev_request(batch), None, None, None
            for _ in range(3):
                try:
                    resp = {name: _jev_call(client, name, args) for name, args in req.items()}
                    labels = _jev_labels(resp, len(batch))
                    break
                except Exception as exc:
                    err, resp, labels = repr(exc), None, None
            n_calls += 2
            fh.write(json.dumps({"ids": [b["id"] for b in batch], "request": req, "response": resp,
                                 "labels": labels, "verifier_error": None if labels else err},
                                ensure_ascii=False) + "\n")
    client.close()
    print(f"{len(todo)}/{len(src)} cümle -> {log.name} ({n_calls} çağrı)")


def _jev_read(log: Path) -> tuple[dict, dict]:
    pred, meta, n_err_batches, models = {}, {}, 0, set()
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if "ids" not in r:
            meta.update(r)
            continue
        if not r.get("labels"):
            n_err_batches += 1
            continue
        models |= {v.get("model") for v in r["response"].values()}
        pred.update(zip(r["ids"], r["labels"]))
    n = meta.get("n_sentences") or 0
    unlabeled = n - len(pred)
    meta.update({"n_labeled": len(pred), "n_unlabeled": unlabeled,
                 "n_error_batches": n_err_batches, "models_seen": sorted(models),
                 "status": "incomplete" if (meta.get("cap_reached") or not n or unlabeled / n > 0.10)
                 else "complete"})
    return pred, meta


# ── analyze ───────────────────────────────────────────────────────────────────

def _kappa(a: list[str], b: list[str]) -> dict:
    pairs = [(x, y) for x, y in zip(a, b) if x in ("Y", "N") and y in ("Y", "N")]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "kappa": None, "raw_agreement": None}
    po = sum(x == y for x, y in pairs) / n
    pa = sum(x == "Y" for x, _ in pairs) / n
    pb = sum(y == "Y" for _, y in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return {"n": n, "kappa": None if pe == 1 else round((po - pe) / (1 - pe), 4),
            "raw_agreement": round(po, 4)}


def _wilson(k: int, n: int) -> list | None:
    if n == 0:
        return None
    z, p = 1.959964, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def _ratio_boot(items: list[dict], num, den) -> dict:
    """HT-ağırlıklı oran + yanıt-kümeli bootstrap (küme = koşul × soru × tekrar)."""
    def est(sample):
        d = sum(i["w"] for i in sample if den(i))
        return (sum(i["w"] for i in sample if num(i)) / d) if d else None
    point = est(items)
    clusters = defaultdict(list)
    for i in items:
        clusters[(i["condition"], i["qid"], i["repeat"])].append(i)
    keys = sorted(clusters)
    rng = random.Random(BOOT_SEED)
    reps = []
    for _ in range(BOOT_N):
        v = est([x for k in rng.choices(keys, k=len(keys)) for x in clusters[k]])
        if v is not None:
            reps.append(v)
    reps.sort()
    ci = ([round(reps[int(0.025 * len(reps))], 4), round(reps[math.ceil(0.975 * len(reps)) - 1], 4)]
          if reps else None)
    return {"point": None if point is None else round(point, 4), "ci95": ci, "B": len(reps)}


def _read_coding(path: str, ids: list[str]) -> dict:
    """Excel (TR) dönüşlerine dayanıklı: BOM, ';' ayırıcı, küçük harf; boş unsure = N."""
    text = Path(path).read_text(encoding="utf-8-sig")
    head = text.splitlines()[0] if text else ""
    delim = ";" if head.count(";") > head.count(",") else ","
    rows = {}
    for r in csv.DictReader(text.splitlines(), delimiter=delim):
        r = {k.strip(): (v or "").strip().upper() if k.strip() in VARS else (v or "")
             for k, v in r.items() if k}
        if not r.get("unsure_YN"):
            r["unsure_YN"] = "N"
        rows[r["item_id"].strip()] = r
    missing = [i for i in ids if i not in rows or any(rows[i][v] not in ("Y", "N") for v in VARS)]
    if missing:                                    # kodlama bitmeden analyze koşmaz
        sys.exit(f"{path}: {len(missing)} öğe eksik/geçersiz (ilk: {missing[:5]})")
    return rows


def _guard_paths() -> dict:
    from experiments.gfp_benchmark.intervention_paths import classify
    from experiments.gfp_benchmark.rescore_crosslingual import FILE_GLOBS, _latest
    paths = {}
    for (lang, model), pattern in FILE_GLOBS.items():
        f = _latest(pattern)
        if not f:
            continue
        for l in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(l) if l.strip() else {}
            if r.get("config") == "grounded_guard":
                paths[(f"{lang}|{model}", r["question"]["id"], str(r.get("repeat", 0)))] = classify(r)
    return paths


def analyze(c1: str, c2: str, consensus: str | None = None) -> None:
    key = {r["item_id"]: r for r in csv.DictReader((OUT / "coding_key.csv").open(encoding="utf-8-sig"))}
    ids = sorted(key)
    r1, r2 = _read_coding(c1, ids), _read_coding(c2, ids)
    rel = {v: _kappa([r1[i][v] for i in ids], [r2[i][v] for i in ids]) for v in VARS}
    if consensus:
        rc = _read_coding(consensus, ids)
        label_sets = {"consensus": {i: {v: rc[i][v] == "Y" for v in VARS} for i in ids}}
    else:                                          # A18: katı (AND) / gevşek (OR) sınırlar
        label_sets = {
            "strict_AND": {i: {v: r1[i][v] == "Y" and r2[i][v] == "Y" for v in VARS} for i in ids},
            "lenient_OR": {i: {v: r1[i][v] == "Y" or r2[i][v] == "Y" for v in VARS} for i in ids}}
    paths = _guard_paths()
    out = {"n_items": len(ids), "reliability": rel, "by_label_set": {}}
    for name, lab in label_sets.items():
        items = []
        for i in ids:
            k, h = key[i], lab[i]
            lex = set(filter(None, k["lexicon_scales"].split("|")))
            items.append({"id": i, "stratum": k["stratum"], "w": 1.0 / float(k["pi"]),
                          "condition": k["condition"], "qid": k["qid"], "repeat": k["repeat"],
                          "lex_feeder": "feeder" in lex, "lex_policy": "policy" in lex,
                          "h_multi": h["scale_multi_feeder_YN"] or h["aggregation_YN"],
                          "h_policy": h["scale_policy_YN"], "h_building": h["scale_building_YN"],
                          "h_any": h["scale_building_YN"] or h["scale_multi_feeder_YN"]
                                   or h["scale_policy_YN"],
                          "sim_match": k["sim_match"] == "1", "fragment": k["fragment_flag"] == "1",
                          "t2": [t for t in k["s2_matches"].split("|") if t]})
        S = {s: [x for x in items if x["stratum"] == s] for s in ("S1", "S2", "S3")}
        lex_nb = lambda x: x["lex_feeder"] or x["lex_policy"]
        res = {}
        # (1) precision: sözlük-bayraklı sansüs (S1 + S2'ye düşen bayraklılar), ham Wilson
        flagged = [x for x in items if x["stratum"] in ("S1", "S2") and lex_nb(x)]
        prec = {}
        for scale, lx, hx in (("feeder", "lex_feeder", "h_multi"), ("policy", "lex_policy", "h_policy")):
            pool = [x for x in flagged if x[lx]]
            tp = sum(x[hx] for x in pool)
            w_den = sum(x["w"] for x in pool)
            prec[scale] = {"tp": tp, "n": len(pool), "wilson": _wilson(tp, len(pool)),
                           "n_from_S2": sum(x["stratum"] == "S2" for x in pool),
                           "ht_point": round(sum(x["w"] for x in pool if x[hx]) / w_den, 4)
                           if w_den else None}
        res["precision"] = prec
        # (2) FN-oranı S3 (sözlük none/building ∧ insan multi/feeder), ham Wilson
        fn = sum(x["h_multi"] for x in S["S3"])
        res["fn_rate_S3"] = {"fn": fn, "n": len(S["S3"]), "wilson": _wilson(fn, len(S["S3"]))}
        # (3) recall = TP_S1 / (TP_S1 + p̂_FN × N₃) — S1 ∪ S3 üzerinde HT, kümeli bootstrap
        s13 = S["S1"] + S["S3"]
        res["recall_population"] = {**_ratio_boot(s13, lambda x: x["h_multi"] and lex_nb(x),
                                                  lambda x: x["h_multi"]), "label": "rough bound"}
        res["recall_population_incl_S2"] = {**_ratio_boot(items, lambda x: x["h_multi"] and lex_nb(x),
                                                          lambda x: x["h_multi"]),
                                            "label": "rough bound, secondary"}
        # (4) prevalans (HT, tüm tabakalar)
        res["prevalence_population"] = _ratio_boot(items, lambda x: x["h_multi"], lambda x: True)
        # (5) restatement sayısı (S2 sansüs) + T2 ayrıştırması (iddia-düzeyi, dışlayıcı)
        rest = [x for x in S["S2"] if x["h_multi"] and not x["h_building"]]
        cells = sorted({(x["condition"], x["qid"], x["repeat"]) for x in rest})
        t2 = lambda xs: {c: sum(t == c for x in xs for t in x["t2"])
                         for c in ("small_int", "ratio", "other")}
        res["restatement_S2"] = {
            "n_sentences": len(rest), "n_responses": len(cells),
            "n_questions": len({x["qid"] for x in rest}),
            "by_condition": {c: sum(x["condition"] == c for x in rest)
                             for c in sorted({x["condition"] for x in items})},
            "S2_size": len(S["S2"]),
            "T2_all_S2_matches": t2(S["S2"]), "T2_restatement_matches": t2(rest),
            # (7) aynı (koşul, soru, tekrar) hücrelerinin guard-kolu A22-1 yolu, betimsel
            "guard_arm_paths": {p: sum(paths.get(c) == p for c in cells)
                                for p in ("P0", "P1a", "P1b", "P2", "P3", None)},
        }
        # (6) parametrik agregasyon: simülatör-eşleşmesiz ∧ insan multi/aggregation
        par = [x for x in items if not x["sim_match"] and x["h_multi"]]
        res["parametric_aggregation"] = {"n_coded": len(par),
                                         "ht_weighted_total": round(sum(x["w"] for x in par), 2),
                                         "label": "descriptive; not a provenance restatement"}
        fr = [x for x in items if x["fragment"]]
        res["fragments"] = {"n": len(fr), "any_scale_Y": sum(x["h_any"] for x in fr)}
        res["unsure_Y"] = sum(lab[i]["unsure_YN"] for i in ids)
        out["by_label_set"][name] = res
    out["jev"] = _jev_block(key, label_sets)
    (OUT / "a26_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1,
                                                     default=str), encoding="utf-8")
    md = ["| label set | precision feeder | precision policy | FN-rate S3 | recall (rough bound) "
          "| prevalence | restatements (sent./resp.) |", "|---|---|---|---|---|---|---|"]
    for name, r in out["by_label_set"].items():
        pf, pp, f3 = r["precision"]["feeder"], r["precision"]["policy"], r["fn_rate_S3"]
        rc, pv, rs = r["recall_population"], r["prevalence_population"], r["restatement_S2"]
        md.append(f"| {name} | {pf['tp']}/{pf['n']} {pf['wilson']} | {pp['tp']}/{pp['n']} "
                  f"{pp['wilson']} | {f3['fn']}/{f3['n']} {f3['wilson']} | {rc['point']} "
                  f"{rc['ci95']} | {pv['point']} {pv['ci95']} | {rs['n_sentences']}/"
                  f"{rs['n_responses']} |")
    (OUT / "a26_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def _jev_block(key: dict, label_sets: dict) -> dict:
    """Jev κ (kodlanan altküme) + kapı geçtiyse ölçeklendirilmiş oranlar AYRI blokta."""
    out = {}
    coded = OUT / "a26_jev_coded.jsonl"
    if not coded.exists():
        return {"status": "not run"}
    pred, meta = _jev_read(coded)
    out["coded"] = {**meta, "n_items": len(pred)}
    multi = lambda p: p["scale_multi_feeder_YN"] or p["aggregation_YN"]
    for name, lab in label_sets.items():
        ks = sorted(set(pred) & set(lab))
        out["coded"][name] = {v: _kappa(["Y" if pred[i][v] else "N" for i in ks],
                                        ["Y" if lab[i][v] else "N" for i in ks])
                              for v in VARS if v != "unsure_YN"}
        out["coded"][name]["multi"] = _kappa(["Y" if multi(pred[i]) else "N" for i in ks],
                                             ["Y" if multi(lab[i]) else "N" for i in ks])
    # dondurulmuş kapı: multi κ, konsensüs varsa ona yoksa strict_AND'e karşı
    ref = "consensus" if "consensus" in label_sets else "strict_AND"
    out["coded"]["gate"] = {"variable": "multi", "against": ref,
                            "kappa": out["coded"][ref]["multi"]["kappa"],
                            "status": meta["status"], "threshold": 0.6}
    scale = OUT / "a26_jev_scaleout.jsonl"
    if scale.exists():
        pred_s, meta_s = _jev_read(scale)
        pop = {}
        for name, tag in (("population.jsonl", "trap_remaining"),
                          ("population_nontrap.jsonl", "nontrap")):
            for d in map(json.loads, (OUT / name).read_text(encoding="utf-8").splitlines()):
                pop[f"u{d['uid']}"] = (tag, d)
        kap = (meta_s.get("kappa_gate") or {}).get("kappa")
        blk = {**meta_s, "label": f"Jev-estimated, human-validated on n={len(key)} trap "
                                  f"sentences (kappa={kap})"}
        for tag in ("trap_remaining", "nontrap"):
            rows = [(pred_s[u], d) for u, (t, d) in pop.items() if t == tag and u in pred_s]
            flagged = [(p, d) for p, d in rows if d["s1_eligible"]]
            s2 = [(p, d) for p, d in rows if d["s2_eligible"]]
            blk[tag] = {                           # yalnız kapılı değişken (multi) ölçeklenir
                "n": len(rows), "jev_multi_or_aggregation": sum(multi(p) for p, _ in rows),
                "lexicon_flagged": len(flagged),
                "lexicon_flagged_jev_agrees_multi": sum(multi(p) for p, _ in flagged),
                "S2_eligible": len(s2),
                "jev_restatement_candidates": sum(multi(p) and not p["scale_building_YN"]
                                                  for p, _ in s2),
            }
        out["scaleout"] = blk
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "jev":
        jev(scale_out=sys.argv[2:3] == ["--scale-out"])
    elif cmd == "analyze":
        analyze(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        sys.exit(f"bilinmeyen komut: {cmd}")
