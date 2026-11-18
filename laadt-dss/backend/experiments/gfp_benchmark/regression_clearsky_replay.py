"""A23-3 — Temmuz clear-sky yolunun yeniden-oynatma kanıtı.

PV simülatörü v4.2 dönemine kadar (Temmuz G1 + G4 korpusu + ilk Ekim denemesi) pvlib
0.15'te `get_pvgis_tmy` imza uyuşmazlığı yüzünden HER çağrıda sessizce clear-sky'a
düşüyordu. A23 düzeltmesi PVGIS TMY önbelleğini varsayılan yapar ve eski yolu yalnız
`IRRADIANCE_SOURCE=clearsky` ile, bayt-özdeş olarak korur. Bu script iki adımda kanıtlar:

  snapshot : DÜZELTMEDEN ÖNCE, çalışan backend üzerinden 56 referans grafının kayıtlarını
             JSON'a döker (Temmuz analizlerinin kullandığı clear-sky referanslar).
  replay   : düzeltmeden SONRA, simülatörü süreç-içi (FastAPI TestClient) ve
             `IRRADIANCE_SOURCE=clearsky` ile çalıştırıp aynı grafları yeniden kurar ve
             snapshot'la kayıt-kayıt karşılaştırır (Redis sonuç-önbelleği atlanır).
             Beklenen fark = 0 → v41/v42 regresyonu, G4 ve B4 Temmuz korpusunda geçerli kalır.

Kullanım:
    python -m experiments.gfp_benchmark.regression_clearsky_replay snapshot
    python -m experiments.gfp_benchmark.regression_clearsky_replay replay
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from urllib.parse import urlparse

from experiments.gfp_benchmark.run_benchmark import HERE

OUT = HERE / "results"
SNAP = OUT / "clearsky_ref_snapshot.json"
FIELDS = ("key", "value", "source_function", "scale", "unit", "stakeholder", "confidence")


def _graphs() -> dict:
    from app.llm import ollama_orchestrator as oo
    from experiments.gfp_benchmark.run_g4_final import _ref_graph_and_results
    orch = oo.OllamaOrchestrator()
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    out = {}
    for q in qs:
        g = _ref_graph_and_results(q, orch)[0]
        out[q["id"]] = (None if g is None else
                        [{f: d.get(f) for f in FIELDS} for d in g.records_as_dicts()])
    return out


def snapshot() -> None:
    data = _graphs()
    js = json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True)
    SNAP.write_text(js, encoding="utf-8")
    n = sum(len(v or []) for v in data.values())
    print(f"snapshot: {len(data)} soru, {n} kayıt, "
          f"{sum(v is None for v in data.values())} kurulamayan -> {SNAP.name} "
          f"sha256 {hashlib.sha256(js.encode()).hexdigest()}")


def replay() -> None:
    os.environ["IRRADIANCE_SOURCE"] = "clearsky"
    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm import ollama_orchestrator as oo
    import app.api.routes.simulation as sim_routes

    sim_routes.get_cached = lambda *a, **k: None       # Redis sonuç-önbelleğini atla
    sim_routes.set_cached = lambda *a, **k: None
    client = TestClient(app)

    def _post(url, json=None, timeout=None, **kw):     # HTTP → süreç-içi uygulama
        return client.post(urlparse(url).path, json=json)

    oo.httpx.post = _post
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    new = _graphs()
    diffs = []
    for qid, recs in snap.items():
        if recs != new.get(qid):
            diffs.append(qid)
    out = {"snapshot_sha256": hashlib.sha256(SNAP.read_bytes()).hexdigest(),
           "questions": len(snap),
           "records": sum(len(v or []) for v in snap.values()),
           "irradiance_source": "clearsky",
           "n_diff_questions": len(diffs), "diff_questions": diffs}
    (OUT / "regression_clearsky_replay.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    {"snapshot": snapshot, "replay": replay}[sys.argv[1]]()
