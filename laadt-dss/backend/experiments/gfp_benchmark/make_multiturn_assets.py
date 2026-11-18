"""A28 — G1-MT (çok turlu ek deney) donmuş girdileri [PRE-RUN; hiçbir Ekim sonucu görülmeden].

Üretir (deterministik, ağ/LLM yok):
  multiturn_turn2.json — 21 eksik-girdili soru için ikinci-tur kullanıcı mesajı (TR + EN).
                         Mesaj YALNIZ soru metninde geçmeyen referans argüman değerlerini sayar
                         (`suggested_args[_per_step]`; stakeholder_type, $prev ve bayraklar hariç).
                         Araç, ölçek ya da çarpma hakkında ipucu YOK.
  answer_keys.json     — `numeric_focus` etiketi → kayıt-anahtarı regex'i (indeksler "[]" yapılır).
                         Kullanılabilir-cevap vekili (TU) bu eşlemeyi kullanır; eşlenemeyen etiket
                         (trafo erteleme: araç yolu üretmez) boş listedir.
Kullanım: python -m experiments.gfp_benchmark.make_multiturn_assets
Kaynak: QUESTION_INPUTS.md (kapsam), PREREGISTRATION.md A28.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Soru metninde geçmeyen referans değerleri (QUESTION_INPUTS.md; elle doğrulandı).
# Sıra = mesajdaki sıra. Değerler suggested_args[_per_step] ile birebir aynıdır (assert'li).
TURN2_VALUES: dict[str, list[tuple[str, object]]] = {
    "res-04": [("panel_kw", 4)],
    "res-11": [("city", "istanbul"), ("pv_penetration_pct", 40)],
    "res-12": [("city", "izmir"), ("pv_penetration_pct", 40)],
    "com-10": [("pv_penetration_pct", 40)],
    "com-11": [("pv_penetration_pct", 80)],
    "com-12": [("city", "ankara")],
    "dis-03": [("pv_penetration_pct", 30)],
    "dis-05": [("pv_penetration_pct", 50)],
    "dis-09": [("pv_penetration_pct", 45)],
    "dis-10": [("pv_penetration_pct", 80)],
    "dis-13": [("pv_penetration_pct", 10)],
    "sta-01": [("city", "ankara"), ("bess_kwh", 10), ("monthly_bill_tl", 2500), ("lifetime_years", 25)],
    "sta-02": [("base_investment_tl", 400000), ("annual_savings_tl", 55000), ("lifetime_years", 25),
               ("discount_rate", 0.15)],
    "sta-03": [("base_investment_tl", 350000), ("annual_savings_tl", 48000), ("lifetime_years", 20),
               ("discount_rate", 0.14)],
    "sta-05": [("city", "istanbul"), ("monthly_bill_tl", 18000), ("lifetime_years", 25)],
    "sta-06": [("base_investment_tl", 300000), ("annual_savings_tl", 42000), ("lifetime_years", 20)],
    "sta-07": [("city", "bursa"), ("panel_kw", 30), ("bess_kwh", 15), ("annual_consumption_kwh", 60000),
               ("lifetime_years", 25), ("pv_penetration_pct", 40)],
    "sta-08": [("base_investment_tl", 900000), ("annual_savings_tl", 110000)],
    "sta-09": [("base_investment_tl", 250000), ("annual_savings_tl", 35000), ("lifetime_years", 20),
               ("discount_rate", 0.15)],
    "sta-10": [("city", "konya"), ("bess_kwh", 5), ("monthly_bill_tl", 1800), ("pv_penetration_pct", 40),
               ("lifetime_years", 25)],
    "sta-11": [("annual_savings_tl", 28000), ("lifetime_years", 15), ("discount_rate", 0.15)],
}
CLEAR_17 = ["res-04", "res-11", "res-12", "com-12", "dis-03", "dis-09", "dis-10", "sta-01", "sta-02",
            "sta-03", "sta-05", "sta-06", "sta-07", "sta-08", "sta-09", "sta-10", "sta-11"]
STRICT_4 = ["com-10", "com-11", "dis-05", "dis-13"]

CITY = {"istanbul": ("İstanbul", "Istanbul"), "izmir": ("İzmir", "Izmir"), "ankara": ("Ankara", "Ankara"),
        "bursa": ("Bursa", "Bursa"), "konya": ("Konya", "Konya")}


def _tr_int(v: float) -> str:
    return f"{int(v):,}".replace(",", ".")


def _en_int(v: float) -> str:
    return f"{int(v):,}"


def _pct(v: float) -> str:
    return f"{round(v * 100) if v < 1 else v:g}"


LABELS = {  # key -> (TR, EN) biçimleyicileri
    "city": (lambda v: f"şehir {CITY[v][0]}", lambda v: f"city {CITY[v][1]}"),
    "panel_kw": (lambda v: f"PV sistem gücü {v} kW", lambda v: f"PV system size {v} kW"),
    "bess_kwh": (lambda v: f"batarya kapasitesi {v} kWh", lambda v: f"battery capacity {v} kWh"),
    "annual_consumption_kwh": (lambda v: f"yıllık tüketim {_tr_int(v)} kWh",
                               lambda v: f"annual consumption {_en_int(v)} kWh"),
    "monthly_bill_tl": (lambda v: f"aylık fatura {_tr_int(v)} TL", lambda v: f"monthly bill {_en_int(v)} TL"),
    "pv_penetration_pct": (lambda v: f"PV penetrasyonu %{v}", lambda v: f"PV penetration {v}%"),
    "base_investment_tl": (lambda v: f"yatırım tutarı {_tr_int(v)} TL",
                           lambda v: f"investment cost {_en_int(v)} TL"),
    "annual_savings_tl": (lambda v: f"yıllık tasarruf {_tr_int(v)} TL",
                          lambda v: f"annual savings {_en_int(v)} TL"),
    "lifetime_years": (lambda v: f"sistem ömrü {v} yıl", lambda v: f"system lifetime {v} years"),
    "discount_rate": (lambda v: f"iskonto oranı %{_pct(v)}", lambda v: f"discount rate {_pct(v)}%"),
}

# numeric_focus etiketi -> normalize kayıt-anahtarı regex'leri (re.fullmatch)
_SWEEP = r"hosting_capacity_analysis\.sweep_results\[\]"
ANSWER_KEYS: dict[str, list[str]] = {
    "simple_payback_years": [r"simple_payback_years"],
    "npv_tl": [r"npv_tl"],
    "annual_savings_tl": [r"annual_savings_tl"],
    "irr_percent": [r"irr_percent"],
    "annual_production_kwh": [r"annual_production_kwh"],
    "self_consumption_ratio": [r"self_consumption_ratio"],
    "lcoe_tl_per_kwh": [r"lcoe_tl_per_kwh"],
    "system_cost_tl": [r"system_cost_tl"],
    "payback distribution percentiles": [r"payback_statistics\.(p5|p50|p95|mean)_years"],
    "npv percentiles": [r"npv_statistics\.(p5|p25|p50|p75|p95|mean)_tl"],
    "policy comparison npv/payback": [r"policy_results\[\]\.npv_tl",
                                      r"policy_results\[\]\.(simple|discounted)_payback_years"],
    "policy_npv_tl": [r"policy_results\[\]\.npv_tl"],
    "policy npv": [r"policy_results\[\]\.npv_tl"],
    "policy_payback_years": [r"policy_results\[\]\.(simple|discounted)_payback_years"],
    "policy payback": [r"policy_results\[\]\.(simple|discounted)_payback_years"],
    "government_cost_tl": [r"policy_results\[\]\.state_cost(_per_mw)?_tl"],
    "state_cost_tl": [r"policy_results\[\]\.state_cost(_per_mw)?_tl"],
    "leverage": [r"policy_results\[\]\.incentive_effectiveness_score"],
    "hosting_capacity_pct": [r"hosting_capacity_analysis\.hosting_capacity_pct"],
    "max_voltage_pu": [r"grid_impact\.max_voltage_pu", _SWEEP + r"\.max_voltage_pu"],
    "min_voltage_pu": [r"grid_impact\.min_voltage_pu", _SWEEP + r"\.min_voltage_pu"],
    "voltage pu": [r"grid_impact\.(max|min)_voltage_pu", _SWEEP + r"\.(max|min)_voltage_pu"],
    "line_loading_pct": [r"grid_impact\.max_line_loading_pct", _SWEEP + r"\.max_line_loading_pct"],
    "max_line_loading_pct": [r"grid_impact\.max_line_loading_pct", _SWEEP + r"\.max_line_loading_pct"],
    "transformer deferral": [],          # araç yolu run_deferral_analysis göndermez → kayıt yok
    "transformer_deferral_years": [],
}


def main() -> None:
    qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]}
    assert sorted(TURN2_VALUES) == sorted(CLEAR_17 + STRICT_4)
    labels = {f for q in qs.values() for f in q["numeric_focus"]}
    assert labels == set(ANSWER_KEYS), labels ^ set(ANSWER_KEYS)

    turn2 = {}
    for qid, pairs in TURN2_VALUES.items():
        q = qs[qid]
        steps = q.get("suggested_args_per_step") or [q["suggested_args"]]
        for k, v in pairs:                       # her değer referansta birebir var
            assert any(s.get(k) == v for s in steps), (qid, k, v)
        tr = "Ek bilgi: " + "; ".join(LABELS[k][0](v) for k, v in pairs) + "."
        en = "Additional information: " + "; ".join(LABELS[k][1](v) for k, v in pairs) + "."
        answerable = any(ANSWER_KEYS[f] for f in q["numeric_focus"])
        turn2[qid] = {"tr": tr, "en": en, "values": dict(pairs),
                      "subset": "clear" if qid in CLEAR_17 else "strict", "answerable": answerable}

    (HERE / "multiturn_turn2.json").write_text(
        json.dumps({"amendment": "A28", "questions": turn2}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    (HERE / "answer_keys.json").write_text(
        json.dumps({"amendment": "A28", "normalize": "indices [n] -> []; re.fullmatch",
                    "labels": ANSWER_KEYS}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(len(turn2), "turn-2 messages;", sum(not t["answerable"] for t in turn2.values()), "unanswerable")


if __name__ == "__main__":
    main()
