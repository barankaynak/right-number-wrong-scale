"""Temmuz korpusunu (G4/B4) yeniden-oynatmak için süreç-içi clear-sky simülatör modu (A23-3).

`enable()` çağrıldıktan sonra orchestrator'ın simülatör HTTP çağrıları süreç-içi FastAPI
uygulamasına yönlenir, ışınım kaynağı `clearsky` olur ve Redis sonuç-önbelleği atlanır.
Çalışan backend'e ve Redis'e hiçbir şey yazılmaz. Eşdeğerliği `regression_clearsky_replay`
kanıtlar (56 referans grafı, 5 032 kayıt, 0 fark).
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

_ENABLED = False


def enable() -> None:
    global _ENABLED
    if _ENABLED:
        return
    os.environ["IRRADIANCE_SOURCE"] = "clearsky"
    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm import ollama_orchestrator as oo
    import app.api.routes.simulation as sim_routes

    sim_routes.get_cached = lambda *a, **k: None
    sim_routes.set_cached = lambda *a, **k: None
    client = TestClient(app)

    def _post(url, json=None, timeout=None, **kw):
        return client.post(urlparse(url).path, json=json)

    oo.httpx.post = _post
    _ENABLED = True
