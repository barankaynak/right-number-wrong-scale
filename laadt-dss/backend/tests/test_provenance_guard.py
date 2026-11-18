"""ProvenanceGuard (GFP/A1) testleri.

Kapsam: provenance graf inşası (5 alan + confidence), sayı çıkarımı (TR/EN
format), GROUNDED/UNGROUNDED/SCALE_VIOLATION/IGNORED kararları, güvenli özet,
ve orchestrator bloklama entegrasyonu (mock Ollama ile).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.provenance_guard import (
    ProvenanceGraph, SCALE_BUILDING, SCALE_FEEDER, SCALE_POLICY,
    _candidate_values,
)

# Temsili pv-bess sonucu (A0 sonrası gerçekçi büyüklükler)
PV_BESS_RESULT = {
    "annual_savings_tl": 21676.0,
    "simple_payback_years": 7.0,
    "npv_tl": 219000.0,
    "irr_percent": 19.0,
    "annual_production_kwh": 7300.0,
    "self_consumption_ratio": 0.538,
}
PV_BESS_ARGS = {"city": "antalya", "panel_kw": 3.3, "bess_kwh": 4.8}


def _graph() -> ProvenanceGraph:
    g = ProvenanceGraph()
    g.add_tool_result("simulate_pv_bess", PV_BESS_ARGS, "residential", PV_BESS_RESULT)
    return g


# ── Graf inşası ──────────────────────────────────────────────────────────────

def test_graph_records_have_five_fields_plus_confidence():
    g = _graph()
    assert g.has_records
    npv = next(r for r in g.records if r.key == "npv_tl")
    # 5 alan: fonksiyon, parametre, paydaş, ölçek, zaman/vintage — + confidence
    assert npv.source_function == "simulate_pv_bess"
    assert npv.parameters.get("panel_kw") == 3.3
    assert npv.stakeholder == "residential"
    assert npv.scale == SCALE_BUILDING
    assert npv.timestamp and npv.vintage
    # A0 bonus: finansal değer tarife vintage'ı + confidence bayrağı taşır
    assert npv.vintage == "2026-04-04"
    assert npv.confidence == "tariff:two_independent"


def test_graph_records_tool_inputs():
    g = _graph()
    keys = {r.key for r in g.records}
    assert "input:panel_kw" in keys and "input:bess_kwh" in keys


def test_tool_scale_mapping():
    g = ProvenanceGraph()
    g.add_tool_result("simulate_grid_impact", {"pv_penetration_pct": 40},
                      "utility", {"max_line_loading_pct": 72.5})
    g.add_tool_result("run_policy_scenario", {"base_investment_tl": 150000},
                      "utility", {"best_policy_by_npv": "FiT", "npv_tl": 5.0e6})
    scales = {r.key: r.scale for r in g.records}
    assert scales["max_line_loading_pct"] == SCALE_FEEDER
    assert scales["npv_tl"] == SCALE_POLICY


def test_failed_tool_result_not_recorded():
    g = ProvenanceGraph()
    g.add_tool_result("simulate_pv_bess", {}, "residential",
                      {"error": "boom", "status": "simulation_failed"})
    assert not any(r.source_function == "simulate_pv_bess" for r in g.records)


# ── Sayı çıkarımı (format varyantları) ───────────────────────────────────────

@pytest.mark.parametrize("token,mag,expected", [
    ("219.000", None, 219000.0),   # TR binlik
    ("1.234,56", None, 1234.56),   # TR tam
    ("1,234.56", None, 1234.56),   # EN tam
    ("8.5", None, 8.5),            # ondalık
    ("21", "bin", 21000.0),        # "21 bin"
    ("1,2", "milyon", 1.2e6),      # "1,2 milyon"
])
def test_candidate_values(token, mag, expected):
    assert any(abs(v - expected) < 1e-6 for v in _candidate_values(token, mag))


# ── Kararlar ────────────────────────────────────────────────────────────────

def test_grounded_response_passes():
    g = _graph()
    text = ("Binanız için 3.3 kWp sistem öneriyorum. Net bugünkü değer 219.000 TL, "
            "geri ödeme 7 yıl, iç verim oranı %19. Yıllık üretim 7.300 kWh olacaktır.")
    rep = g.check_response(text)
    assert rep.passed, rep.violations
    assert rep.counts["GROUNDED"] >= 4
    assert rep.counts["UNGROUNDED"] == 0


def test_fabricated_number_is_ungrounded():
    g = _graph()
    text = "Bu sistemle yılda tam 55.000 TL tasarruf edersiniz."   # gerçek: 21.676
    rep = g.check_response(text)
    assert not rep.passed
    assert rep.counts["UNGROUNDED"] == 1
    assert "55.000" in rep.violations[0]


def test_rounding_within_tolerance_is_grounded():
    g = _graph()
    # %2 tolerans: 219.000 → "yaklaşık 220 bin TL" kabul edilir
    rep = g.check_response("Net bugünkü değer yaklaşık 220 bin TL.")
    assert rep.passed, rep.violations


def test_scale_violation_building_number_at_feeder_scale():
    """GFP çekirdek iddiası: 'doğru sayı, yanlış ölçek' — bina-NPV'si mahalle/şebeke
    ölçeğinde sunulursa nokta-bazlı guard geçirir, provenance guard YAKALAR."""
    g = _graph()
    # Bina-ölçeği NPV, şebeke/mahalle TOPLAMI gibi sunuluyor (building kelimesi YOK)
    text = "Bu mahalledeki şebeke için toplam yıllık kazanç 219.000 TL olacaktır."
    rep = g.check_response(text)
    assert not rep.passed
    assert rep.counts["SCALE_VIOLATION"] == 1
    claim = next(c for c in rep.claims if c.verdict == "SCALE_VIOLATION")
    assert claim.record_scale == SCALE_BUILDING
    assert SCALE_FEEDER in claim.claimed_scales


def test_same_number_at_building_scale_is_fine():
    g = _graph()
    rep = g.check_response("Binanız için net bugünkü değer 219.000 TL.")
    assert rep.passed, rep.violations


def test_g4_scale_swap_count_number_ignored_detection_from_real_number():
    """G4 blocker #3 (danışman v2.10): scale_swap enjeksiyonu 'mahalledeki tüm 40
    ev' gibi bir SAYMA sayısı ('40') ekler. Bu '40' IGNORED olmalı; tespit YALNIZ
    gerçek bina-sayısının SCALE_VIOLATION'ından gelmeli (yanlış-neden tespiti değil)."""
    g = _graph()
    text = "Mahalledeki tüm 40 ev için net bugünkü değer 219.000 TL olarak hesaplandı."
    rep = g.check_response(text)
    assert not rep.passed
    # '40' sayma-bağlamı → IGNORED (eşleşmeyen, kaynaksız değil)
    forty = next(c for c in rep.claims if c.text == "40")
    assert forty.verdict == "IGNORED"
    # gerçek NPV → SCALE_VIOLATION (tespitin GERÇEK nedeni)
    assert rep.counts["SCALE_VIOLATION"] == 1
    assert rep.counts["UNGROUNDED"] == 0
    npv = next(c for c in rep.claims if c.verdict == "SCALE_VIOLATION")
    assert npv.matched_key == "npv_tl"


def test_feeder_number_at_feeder_scale_ok():
    g = ProvenanceGraph()
    g.add_tool_result("simulate_grid_impact", {"pv_penetration_pct": 40},
                      "utility", {"max_line_loading_pct": 72.5, "hosting_capacity_pct": 55.0})
    rep = g.check_response("Şebekede maksimum hat yüklenmesi %72,5; hosting kapasitesi %55.")
    assert rep.passed, rep.violations


def test_contextual_ints_ignored_not_blocked():
    g = _graph()
    # 25 (ömür) ve 2026 (yıl) araç çıktısında yok ama bloklamamalı
    rep = g.check_response("25 yıllık ömür boyunca, 2026 itibarıyla, geri ödeme 7 yıl.")
    assert rep.passed, rep.violations
    assert rep.counts["IGNORED"] >= 2


def test_safe_summary_contains_only_grounded_numbers():
    g = _graph()
    summary = g.safe_summary(PV_BESS_RESULT)
    rep = g.check_response(summary)
    assert rep.counts["UNGROUNDED"] == 0
    assert rep.passed, rep.violations
    assert "doğrulanmış" in summary.lower() or "doğrulama" in summary.lower()


# ── Orchestrator bloklama entegrasyonu (mock Ollama) ─────────────────────────

def _mk_text(content):
    return {"role": "assistant", "content": content, "tool_calls": None}


def _mk_tool_call(name, args):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def _run_orchestrated(narrations: list[str], monkeypatch) -> dict:
    """Tool-call → sim sonucu → anlatım(lar). narrations[0] ilk final,
    narrations[1] (varsa) düzeltme denemesinin çıktısı."""
    from app.llm.ollama_orchestrator import OllamaOrchestrator
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "GUARD_MODE", "block")
    orch = OllamaOrchestrator()
    orch._memory.delete_session("sess-prov")
    orch._memory._local.clear()

    chat_calls = {"n": 0}

    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if "/api/chat" in url:
            chat_calls["n"] += 1
            if chat_calls["n"] == 1:
                resp.json.return_value = {"message": _mk_tool_call(
                    "simulate_pv_bess", {"city": "antalya", "panel_kw": 3.3})}
            else:
                idx = min(chat_calls["n"] - 2, len(narrations) - 1)
                resp.json.return_value = {"message": _mk_text(narrations[idx])}
        else:
            resp.json.return_value = PV_BESS_RESULT
        return resp

    with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
        return orch.process_message("Antalya fizibilite", "sess-prov")


def test_orchestrator_grounded_reply_passes_through(monkeypatch):
    reply = "Net bugünkü değer 219.000 TL, geri ödeme 7 yıl."
    out = _run_orchestrated([reply], monkeypatch)
    assert out["reply"] == reply
    assert out["provenance"]["passed"] is True
    assert out["provenance"]["blocked"] is False


def test_orchestrator_corrective_retry_fixes_reply(monkeypatch):
    bad = "Yılda 99.000 TL tasarruf edersiniz."               # temelsiz
    fixed = "Yıllık tasarruf 21.676 TL, geri ödeme 7 yıl."    # temellendirilmiş
    out = _run_orchestrated([bad, fixed], monkeypatch)
    assert out["reply"] == fixed
    assert out["provenance"]["retried"] is True
    assert out["provenance"]["blocked"] is False
    assert out["provenance"]["passed"] is True


# ── A1-r2: unit-farkındalıklı eşleştirme ─────────────────────────────────────

def test_unit_mismatch_detected_kwh_presented_as_tl():
    """G4 kategori-(i): 'doğru sayı / yanlış kaynak' — üretim-kWh değeri
    tasarruf-TL olarak sunulursa yakalanmalı (değer-çakışması bunu geçirirdi)."""
    g = _graph()
    rep = g.check_response("Bu sistemle yılda 7.300 TL tasarruf edersiniz.")
    assert not rep.passed
    assert rep.counts["UNIT_MISMATCH"] == 1
    claim = next(c for c in rep.claims if c.verdict == "UNIT_MISMATCH")
    assert claim.matched_key == "annual_production_kwh"


def test_unit_correct_kwh_still_grounded():
    g = _graph()
    rep = g.check_response("Sistem yılda 7.300 kWh üretiyor.")
    assert rep.passed, rep.violations
    assert rep.counts["GROUNDED"] == 1


def test_unknown_claim_unit_matches_by_value():
    g = _graph()
    rep = g.check_response("Sonuç: 219.000 çıktı.")   # birim yok → değerle eşleş
    assert rep.passed, rep.violations


# ── A1-r3: kalibre ölçek sözlüğü — meşru bina-cümleleri FP üretmemeli ────────

def test_calibration_dev_corpus_zero_false_positives():
    """Over-blocking denetimi: dev-korpustaki TÜM yanıtlar temellendirilmiştir →
    guard hiçbirinde ihlal üretmemeli (FP oranı = 0). Korpus G1 setinden AYRI."""
    import json
    from pathlib import Path
    corpus_path = (Path(__file__).resolve().parent.parent
                   / "experiments" / "gfp_benchmark" / "dev_corpus.json")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    fixtures = corpus["fixtures"]
    fp = []
    for entry in corpus["replies"]:
        fx = fixtures[entry["fixture"]]
        g = ProvenanceGraph()
        g.add_tool_result(fx["tool_name"], fx["args"], fx["stakeholder"], fx["result"])
        rep = g.check_response(entry["text"])
        if not rep.passed:
            fp.append((entry["id"], rep.violations))
    assert not fp, f"Over-blocking FP'leri: {fp}"


def test_calibration_fn_probes_all_detected():
    """İki-yönlü korpus (ORTA-9c): KASITLI ölçek-ihlali cümlelerinin HEPSİ
    yakalanmalı (FN denetimi) — 'daire'/'fabrika' v3 kelimeleri dahil."""
    import json
    from pathlib import Path
    corpus_path = (Path(__file__).resolve().parent.parent
                   / "experiments" / "gfp_benchmark" / "dev_corpus.json")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    fixtures = corpus["fixtures"]
    missed = []
    for entry in corpus["fn_probes"]:
        fx = fixtures[entry["fixture"]]
        g = ProvenanceGraph()
        g.add_tool_result(fx["tool_name"], fx["args"], fx["stakeholder"], fx["result"])
        rep = g.check_response(entry["text"])
        if rep.counts["SCALE_VIOLATION"] == 0:
            missed.append((entry["id"], rep.counts))
    assert not missed, f"Yakalanamayan FN probe'ları: {missed}"


def test_payback_small_int_fabrication_caught():
    """ORTA-9d: 'kendini 3 yılda öder' uydurması (gerçek 7) artık GEÇMEZ.
    Not: '3', panel_kw=3.3 girdisine küçük-değer toleransıyla değer-çarpışması
    yapar; r2 unit-eşleştirmesi OLMASAYDI bu GROUNDED sayılacaktı — burada
    UNIT_MISMATCH olarak yakalanır (kategori fark etmeksizin ihlaldir)."""
    g = _graph()
    rep = g.check_response("Sistem kendini 3 yılda öder.")
    assert not rep.passed
    caught = rep.counts["UNGROUNDED"] + rep.counts["UNIT_MISMATCH"]
    assert caught == 1


def test_lifetime_years_still_ignored_next_to_payback():
    """Bileşik cümlede '25 yıllık ömür' (payback-cue'dan uzak) hâlâ bloklanmaz."""
    g = _graph()
    rep = g.check_response(
        "25 yıllık ömür boyunca sistem kârlıdır; geri ödeme süresi 7 yıl olarak hesaplandı.")
    assert rep.passed, rep.violations


def test_aggregation_pattern_still_catches_multiplication_trap():
    """Kalibrasyon FP'leri temizlerken GERÇEK agregasyon tuzağı kaçmamalı."""
    g = _graph()
    rep = g.check_response(
        "Tüm 40 haneye kurarsak kazanç hane başı 219.000 TL üzerinden hesaplanabilir.")
    assert rep.counts["SCALE_VIOLATION"] == 1


# ── A1-r1: oturum-kalıcı graf (çok-turlu sahte-UNGROUNDED artefaktı) ─────────

def test_session_persistent_graph_across_turns(monkeypatch):
    """Tur-1'de araç çağrılır; tur-2 ARAÇSIZ ama tur-1'in doğru sayısını anar →
    UNGROUNDED olmamalı (A1-r1 öncesi bug: graf tur-başına sıfırlanıyordu)."""
    from app.llm.ollama_orchestrator import OllamaOrchestrator
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "GUARD_MODE", "block")
    orch = OllamaOrchestrator()
    orch._memory.delete_session("sess-persist")
    orch._memory._local.clear()

    chat_calls = {"n": 0}
    turn2_reply = "Evet, az önce hesapladığımız gibi net bugünkü değer 219.000 TL idi."

    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if "/api/chat" in url:
            chat_calls["n"] += 1
            if chat_calls["n"] == 1:
                resp.json.return_value = {"message": _mk_tool_call(
                    "simulate_pv_bess", {"city": "antalya", "panel_kw": 3.3})}
            elif chat_calls["n"] == 2:
                resp.json.return_value = {"message": _mk_text(
                    "Net bugünkü değer 219.000 TL, geri ödeme 7 yıl.")}
            else:
                resp.json.return_value = {"message": _mk_text(turn2_reply)}
        else:
            resp.json.return_value = PV_BESS_RESULT
        return resp

    with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
        out1 = orch.process_message("Antalya fizibilite", "sess-persist")
        out2 = orch.process_message("NPV kaçtı demiştin?", "sess-persist")

    assert out1["provenance"]["passed"] is True
    # Tur-2: araç çağrılmadı ama önceki turun sayısı TANINIYOR (bloklanmadı)
    assert out2["reply"] == turn2_reply
    assert out2["provenance"] is not None, "araçsız tur da denetlenmeli"
    assert out2["provenance"]["passed"] is True
    assert out2["provenance"]["blocked"] is False


def test_multi_round_tool_loop(monkeypatch):
    """A1-r1: model art arda İKİ araç çağırabilmeli (zincir tek kullanıcı-turunda);
    her iki aracın sayıları da provenance'ta olmalı."""
    from app.llm.ollama_orchestrator import OllamaOrchestrator
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "GUARD_MODE", "block")
    orch = OllamaOrchestrator()
    orch._memory.delete_session("sess-chain")
    orch._memory._local.clear()

    grid_result = {"hosting_capacity_pct": 55.0, "max_line_loading_pct": 72.5}
    final = "Bina NPV'si 219.000 TL; fiderde hosting kapasitesi %55."
    chat_calls = {"n": 0}

    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if "/api/chat" in url:
            chat_calls["n"] += 1
            if chat_calls["n"] == 1:
                resp.json.return_value = {"message": _mk_tool_call(
                    "simulate_pv_bess", {"city": "antalya", "panel_kw": 3.3})}
            elif chat_calls["n"] == 2:
                resp.json.return_value = {"message": _mk_tool_call(
                    "simulate_grid_impact", {"pv_penetration_pct": 40})}
            else:
                resp.json.return_value = {"message": _mk_text(final)}
        elif "/grid-impact" in url:
            resp.json.return_value = grid_result
        else:
            resp.json.return_value = PV_BESS_RESULT
        return resp

    with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
        out = orch.process_message("Fizibilite + şebeke etkisi", "sess-chain")

    assert out["reply"] == final
    assert out["provenance"]["passed"] is True, out["provenance"]["violations"]
    assert out["provenance"]["n_records"] >= 10  # iki aracın kayıtları birlikte (7 pv + 3 grid)


def test_orchestrator_blocks_with_safe_summary_when_retry_fails(monkeypatch):
    bad = "Yılda 99.000 TL tasarruf edersiniz."
    still_bad = "Emin olun, tasarruf 88.500 TL olacak."
    out = _run_orchestrated([bad, still_bad], monkeypatch)
    assert out["provenance"]["blocked"] is True
    assert out["provenance"]["retried"] is True
    # Yedek özet: temelsiz sayı içermez, doğrulanmış değerleri içerir
    assert "doğrula" in out["reply"].lower()
    assert "99.000" not in out["reply"] and "88.500" not in out["reply"]
    assert out["provenance"]["passed"] is True   # yedek özet kendi denetiminden geçer


# ── v4.2 (A21): boş-graf (araçsız tek-tur) yanıtlar da değerlendirilir ────────
# A20: v4.1'de guard yalnız `has_records` iken çalışıyordu → araç çağrılmayan
# tek-tur yanıt DEĞERLENDİRİLMEDEN teslim ediliyordu. v4.2: boş grafta her sayı
# UNGROUNDED ya da IGNORED; aynı düzelt→blokla hattı, boş-graf metin varyantlarıyla.

def test_empty_graph_numbers_are_ungrounded():
    rep = ProvenanceGraph().check_response("Yılda 21.676 TL tasarruf edersiniz.")
    assert not rep.passed
    assert rep.counts["UNGROUNDED"] == 1


def test_empty_graph_ignorable_only_passes():
    rep = ProvenanceGraph().check_response(
        "2026 tarifesiyle hesaplamak için sizden 2 bilgiye ihtiyacım var.")
    assert rep.passed, rep.violations
    assert rep.counts["IGNORED"] >= 2


def test_empty_graph_corrective_instruction_variant():
    g = ProvenanceGraph()
    rep = g.check_response("Yılda 21.676 TL tasarruf edersiniz.")
    tr = g.corrective_instruction(rep, "tr")
    en = g.corrective_instruction(rep, "en")
    # araç çıktısı YOK → "yalnız araç çıktısındaki sayıları kullan" denemez
    assert "simülasyon çalıştırılmadı" in tr.lower()
    assert "araç çağırma" in tr.lower()
    assert "no simulation has been run" in en.lower()
    assert "do not call a tool" in en.lower()


def test_empty_graph_safe_summary_variant():
    g = ProvenanceGraph()
    for lang in ("tr", "en"):
        msg = g.safe_summary(None, lang)
        assert not any(ch.isdigit() for ch in msg), msg      # hiç sayı yok
        assert "doğrulanmış değerler" not in msg.lower()      # simülasyon yapılmış gibi değil
        assert "verified values" not in msg.lower()
        assert g.check_response(msg).passed


def _run_toolless(narrations: list[str], monkeypatch, mode: str = "block",
                  sid: str = "sess-toolless") -> dict:
    """Model HİÇ araç çağırmaz; narrations[0] ilk yanıt, [1] düzeltme denemesi."""
    from app.llm.ollama_orchestrator import OllamaOrchestrator
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "GUARD_MODE", mode)
    orch = OllamaOrchestrator()
    orch._memory.delete_session(sid)
    orch._memory._local.clear()
    chat_calls = {"n": 0}

    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        chat_calls["n"] += 1
        idx = min(chat_calls["n"] - 1, len(narrations) - 1)
        resp.json.return_value = {"message": _mk_text(narrations[idx])}
        return resp

    with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
        return orch.process_message("Antalya'da 5 kW GES kaç yılda öder?", sid)


def test_toolless_turn_is_evaluated_and_blocked(monkeypatch):
    bad = "Yılda yaklaşık 21.000 TL tasarruf eder, 6,5 yılda öder."
    still_bad = "Tasarruf 19.500 TL civarında olur."
    out = _run_toolless([bad, still_bad], monkeypatch)
    prov = out["provenance"]
    assert prov is not None, "araçsız tek-tur yanıt da değerlendirilmeli"
    assert prov["retried"] is True and prov["blocked"] is True
    assert prov["n_records"] == 0
    assert prov["pre_intervention"]["reply"] == bad
    assert not any(ch.isdigit() for ch in out["reply"])        # boş-graf mesajı
    assert prov["passed"] is True


def test_toolless_turn_retry_without_numbers_is_delivered(monkeypatch):
    bad = "Yılda yaklaşık 21.000 TL tasarruf eder."
    fixed = ("Bunu doğru hesaplamak için simülasyon çalıştırmam gerekiyor; "
             "aylık faturanızı paylaşır mısınız?")
    out = _run_toolless([bad, fixed], monkeypatch, sid="sess-toolless-fix")
    assert out["reply"] == fixed
    assert out["provenance"]["retried"] is True
    assert out["provenance"]["blocked"] is False


def test_toolless_turn_log_mode_records_but_never_intervenes(monkeypatch):
    """noguard / ungrounded kolları log modunda: araçsız yanıt kaydedilir, DEĞİŞMEZ."""
    bad = "Yılda yaklaşık 21.000 TL tasarruf eder."
    out = _run_toolless([bad], monkeypatch, mode="log", sid="sess-toolless-log")
    assert out["reply"] == bad
    assert out["provenance"] is not None
    assert out["provenance"]["retried"] is False and out["provenance"]["blocked"] is False
    assert out["provenance"]["pre_intervention"]["counts"]["UNGROUNDED"] == 1


def test_toolless_turn_with_ignorable_only_passes_untouched(monkeypatch):
    reply = "2026 tarifesiyle hesaplayabilmem için 2 bilgiye ihtiyacım var: şehir ve fatura."
    out = _run_toolless([reply], monkeypatch, sid="sess-toolless-ign")
    assert out["reply"] == reply
    assert out["provenance"]["retried"] is False
    assert out["provenance"]["blocked"] is False


def test_retry_telemetry_tool_call_only_retry_is_blocked(monkeypatch):
    """A21-E3: retry yalnız araç çağrısı döndürürse içerik boş → blok; telemetri
    alanları bunu kaydeder (retry araç YÜRÜTMEZ — v4.1 davranışı, E9)."""
    from app.llm.ollama_orchestrator import OllamaOrchestrator
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "GUARD_MODE", "block")
    orch = OllamaOrchestrator()
    orch._memory.delete_session("sess-retry-tel")
    orch._memory._local.clear()
    calls = {"n": 0}

    def _fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        calls["n"] += 1
        if calls["n"] == 1:
            resp.json.return_value = {"message": _mk_text("Yılda 21.000 TL tasarruf eder.")}
        else:
            resp.json.return_value = {"message": _mk_tool_call(
                "simulate_pv_bess", {"city": "antalya", "panel_kw": 5})}
        return resp

    with patch("app.llm.ollama_orchestrator.httpx.post", side_effect=_fake_post):
        out = orch.process_message("Antalya'da 5 kW GES?", "sess-retry-tel")
    prov = out["provenance"]
    assert prov["blocked"] is True
    assert prov["retry_tool_calls_requested"] is True
    assert prov["retry_content_empty"] is True
    assert prov["retry_error"] is False
