"""Kodlayıcı-1 etiketlerini (artifact veritabanı `codes/`, ArtifactData ile indirilmiş JSON'lar)
kodlama sayfasının kendi CSV dışa aktarımıyla BİREBİR aynı biçimde yazar (`auditCsv`/`scaleCsv`,
coding_interface_v3/coder1.html). Etiket içeriği yazdırılmaz; yalnız biçim doğrulaması yapılır.

Biçim doğrulaması: üretilen dosyaların etiket-dışı sütunları, örnekleme anında yazılan boş
şablonlarla (`audit/audit_sheet_coder1.csv`, `a26/coding_package_coder1.csv`) aynı olmalıdır.
Kullanım: GFP_RUN_DIR=oct_v42 python -m experiments.gfp_benchmark.export_coder1_csv
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "results" / os.environ.get("GFP_RUN_DIR", "oct_v42")
PAGE = RUN / "audit" / "coding_interface_v3" / "coder1.html"
DB = RUN / "audit" / "coder1_db_final" / "codes"
OUT = RUN / "coded"
SCALE_VARS = [("b", "scale_building_YN"), ("m", "scale_multi_feeder_YN"), ("p", "scale_policy_YN"),
              ("g", "aggregation_YN"), ("s", "unsure_YN")]


def _cell(v) -> str:                                   # csvCell
    v = "" if v is None else (str(v) if not isinstance(v, bool) else str(v).lower())
    return '"' + v.replace('"', '""') + '"' if re.search(r'[",\r\n]', v) else v


def _csv(rows) -> str:                                 # csv(): BOM + CRLF
    return "﻿" + "\r\n".join(",".join(_cell(c) for c in r) for r in rows) + "\r\n"


def _num(n) -> str:                                    # JS String(number)
    return str(int(n)) if float(n).is_integer() else str(n)


def _labels(key: str) -> dict:
    p = DB / f"{key}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return d.get("data", d) if isinstance(d, dict) else {}


def main() -> None:
    page = PAGE.read_text(encoding="utf-8")
    pfx = '<script id="data" type="application/json">'
    line = next(ln for ln in page.split("\n") if ln.startswith(pfx))
    data = json.loads(line[len(pfx):line.rindex("</script>")])

    rows = [["item", "number", "shown_value", "traceable_YN", "input_echo", "usable_answer_YN"]]
    for it in data["audit"]:
        lab = _labels("a22-" + it["item"])
        t, e, u = lab.get("t") or {}, lab.get("e") or {}, lab.get("u") or ""
        if not it["nums"]:
            rows.append([it["item"], 0, "", "", "", u])
            continue
        for k, n in enumerate(it["nums"]):
            tv = t.get(_num(n["n"]), "")
            rows.append([it["item"], _num(n["n"]), n["v"], "N/A" if tv == "NA" else (tv or ""),
                         "Y" if tv == "Y" and e.get(_num(n["n"])) else "", u if k == 0 else ""])
    audit = _csv(rows)

    rows = [["item_id", "lang", "question_text", "sentence"] + [v for _, v in SCALE_VARS]]
    for r in data["scale"]:
        lab = _labels("a26-" + r["id"])
        rows.append([r["id"], r["lang"], r["q"], r["s"]] + [lab.get(k) or "" for k, _ in SCALE_VARS])
    scale = _csv(rows)

    # biçim doğrulaması: etiket-dışı sütunlar boş şablonla aynı
    def cols(text: str, keep: list[str]) -> list[tuple]:
        rd = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        return [tuple(r[c] for c in keep) for r in rd]
    tmpl_a = (RUN / "audit" / "audit_sheet_coder1.csv").read_text(encoding="utf-8")
    tmpl_s = (RUN / "a26" / "coding_package_coder1.csv").read_text(encoding="utf-8")
    assert cols(audit, ["item", "number", "shown_value"]) == cols(tmpl_a, ["item", "number", "shown_value"])
    assert cols(scale, ["item_id", "lang", "question_text", "sentence"]) == \
        cols(tmpl_s, ["item_id", "lang", "question_text", "sentence"])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_coded_coder1.csv").write_bytes(audit.encode("utf-8"))
    (OUT / "scale_coded_coder1.csv").write_bytes(scale.encode("utf-8"))
    print("ok: format matches templates;", len(data["audit"]), "responses,", len(data["scale"]), "sentences")


if __name__ == "__main__":
    main()
