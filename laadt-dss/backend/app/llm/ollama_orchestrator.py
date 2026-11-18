from __future__ import annotations

"""
OllamaOrchestrator — Faz 3.3 LLM katmanı (genişletilmiş versiyon).

Desteklenen araçlar:
  Temel simülasyon:
    simulate_pv_bess, simulate_grid_impact, run_policy_scenario, run_monte_carlo
  GES konfigürasyon:
    configure_pv_system, update_pv_parameter, run_pv_simulation
  BESS konfigürasyon:
    configure_bess_system, update_bess_parameter, run_bess_simulation
  Ağ yönetimi:
    build_custom_network, update_network_element, run_loadflow_on_network

Yenilikler (3.3 tamamlama):
  - Paydaş tipine göre sistem promptu (stakeholder_prompts.py)
  - HallucinationGuard (hallucination_guard.py)
  - 9 yeni araç + mevcut 4 araç = toplam 13 araç
"""

import json
import httpx

from app.core.config import settings
from app.llm.mock.mock_llm import MockLLMOrchestrator
from app.llm.memory.session_memory import session_memory
from app.llm.prompts.stakeholder_prompts import get_system_prompt
from app.llm.hallucination_guard import validate_response
from app.llm.provenance_guard import ProvenanceGraph
from app.simulation.advisor.sizing import bill_to_annual_consumption
from app.simulation.compat import july_2026_replay

CITY_COORDS: dict[str, tuple[float, float]] = {
    "ankara": (39.93, 32.86),
    "istanbul": (41.01, 28.95),
    "izmir": (38.42, 27.14),
    "antalya": (36.90, 30.70),
    "konya": (37.87, 32.49),
    "bursa": (40.19, 29.06),
}

# ---------------------------------------------------------------------------
# Araç tanımları
# ---------------------------------------------------------------------------

SIMULATION_TOOLS = [
    # ---- Temel simülasyon araçları ----------------------------------------
    {
        "type": "function",
        "function": {
            "name": "simulate_pv_bess",
            "description": (
                "GES (Güneş Enerji Santrali) ve opsiyonel BESS yatırımının hızlı fizibilitesini hesaplar. "
                "Çıktı: yıllık üretim (kWh), tasarruf (TL), geri dönüş süresi, NPV, IRR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "enum": list(CITY_COORDS.keys())},
                    "panel_kw": {"type": "number"},
                    "bess_kwh": {"type": "number"},
                    "bess_chemistry": {"type": "string", "enum": ["LFP", "NMC", "LTO"]},
                    "annual_consumption_kwh": {"type": "number"},
                    "monthly_bill_tl": {"type": "number"},
                    "stakeholder_type": {"type": "string",
                                        "enum": ["residential", "commercial", "municipal", "utility"]},
                },
                "required": ["city", "panel_kw"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_grid_impact",
            "description": "PV/BESS penetrasyonunun dağıtım şebekesine etkisini analiz eder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pv_penetration_pct": {"type": "number"},
                    "bess_penetration_pct": {"type": "number"},
                    "run_penetration_sweep": {"type": "boolean"},
                },
                "required": ["pv_penetration_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_policy_scenario",
            "description": "Farklı devlet teşvik politikalarını karşılaştırır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_investment_tl": {"type": "number"},
                    "annual_savings_tl": {"type": "number"},
                    # A27: _run_policy_scenario bu ikisini okuyordu ama şema göstermiyordu
                    "discount_rate": {"type": "number",
                                      "description": "Ondalık oran, ör. 0.12 = %12"},
                    "lifetime_years": {"type": "integer"},
                    "policies": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["base_investment_tl", "annual_savings_tl"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_monte_carlo",
            "description": "Monte Carlo belirsizlik analizi; P5/P50/P95 NPV değerleri.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "enum": list(CITY_COORDS.keys())},
                    "panel_kw": {"type": "number"},
                    "bess_kwh": {"type": "number"},
                    "annual_consumption_kwh": {"type": "number"},
                    "n_iterations": {"type": "integer"},
                },
                "required": ["city", "panel_kw"],
            },
        },
    },
    # ---- GES konfigürasyon araçları ----------------------------------------
    {
        "type": "function",
        "function": {
            "name": "configure_pv_system",
            "description": "Detaylı GES sistemi tanımlar: panel modeli, string dizilimi, inverter, montaj tipi, gölgeleme.",
            "parameters": {
                "type": "object",
                "properties": {
                    "system_id": {"type": "string"},
                    "location": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"}, "lon": {"type": "number"},
                            "altitude": {"type": "number"}, "tz": {"type": "string"},
                        },
                        "required": ["lat", "lon"],
                    },
                    "arrays": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "modules_per_string": {"type": "integer"},
                                "strings_per_inverter": {"type": "integer"},
                                "tilt_deg": {"type": "number"},
                                "azimuth_deg": {"type": "number"},
                                "module_model": {"type": "string"},
                                "tracking": {"type": "string", "enum": ["fixed", "single_axis", "dual_axis"]},
                                "shade_loss_pct": {"type": "number"},
                            },
                        },
                    },
                    "inverter_model": {"type": "string"},
                    "dc_ac_ratio": {"type": "number"},
                },
                "required": ["system_id", "location", "arrays"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pv_parameter",
            "description": "Kayıtlı GES sisteminin belirli parametresini günceller (örn: 'arrays[0].tilt_deg').",
            "parameters": {
                "type": "object",
                "properties": {
                    "system_id": {"type": "string"},
                    "target": {"type": "string"},
                    "value": {},
                },
                "required": ["system_id", "target", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_pv_simulation",
            "description": "Kayıtlı GES sistemini pvlib ModelChain ile simüle eder, 8760 saatlik üretim profili döner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "system_id": {"type": "string"},
                    "weather_source": {"type": "string", "enum": ["pvgis_tmy", "pvgis_year", "custom"]},
                },
                "required": ["system_id"],
            },
        },
    },
    # ---- BESS konfigürasyon araçları ----------------------------------------
    {
        "type": "function",
        "function": {
            "name": "configure_bess_system",
            "description": "Detaylı BESS sistemi tanımlar: kimya, kapasite, güç, SoC limitleri, dispatch stratejisi, degradasyon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "system_id": {"type": "string"},
                    "chemistry": {"type": "string", "enum": ["LFP", "NMC", "LTO"]},
                    "capacity_kwh": {"type": "number"},
                    "power_kw": {"type": "number"},
                    "soc_min_pct": {"type": "number"},
                    "soc_max_pct": {"type": "number"},
                    "c_rate_charge_max": {"type": "number"},
                    "c_rate_discharge_max": {"type": "number"},
                    "roundtrip_efficiency_pct": {"type": "number"},
                    "dispatch_strategy": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string",
                                    "enum": ["self_consumption", "peak_shaving", "time_of_use", "grid_services"]},
                            "peak_shaving_threshold_kw": {"type": "number"},
                            "time_of_use_schedule": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                    "degradation": {"type": "object"},
                },
                "required": ["system_id", "chemistry", "capacity_kwh", "power_kw"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_bess_parameter",
            "description": "Kayıtlı BESS sisteminin belirli parametresini günceller (örn: 'dispatch_strategy.mode').",
            "parameters": {
                "type": "object",
                "properties": {
                    "system_id": {"type": "string"},
                    "target": {"type": "string"},
                    "value": {},
                },
                "required": ["system_id", "target", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bess_simulation",
            "description": "Kayıtlı BESS sistemini 8760 saatlik dispatch simülasyonuyla çalıştırır; degradasyon analizi dahil.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bess_system_id": {"type": "string"},
                    "pv_system_id": {"type": "string"},
                    "stakeholder_type": {"type": "string"},
                    "simulate_degradation_years": {"type": "integer"},
                },
                "required": ["bess_system_id"],
            },
        },
    },
    # ---- Ağ yönetim araçları -----------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "build_custom_network",
            "description": "Kullanıcı tanımlı dağıtım ağı oluşturur ve pandapower'a kaydeder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "network_id": {"type": "string"},
                    "name": {"type": "string"},
                    "buses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "vn_kv": {"type": "number"},
                                "lat": {"type": "number"},
                                "lon": {"type": "number"},
                            },
                        },
                    },
                    "lines": {"type": "array", "items": {"type": "object"}},
                    "transformers": {"type": "array", "items": {"type": "object"}},
                    "loads": {"type": "array", "items": {"type": "object"}},
                    "generators": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["network_id", "buses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_network_element",
            "description": "Mevcut ağdaki bir elemanı günceller veya siler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "network_id": {"type": "string"},
                    "element_type": {"type": "string",
                                    "enum": ["bus", "line", "trafo", "load", "generator"]},
                    "element_id": {"type": "integer"},
                    "action": {"type": "string", "enum": ["update", "delete"]},
                    "updates": {"type": "object"},
                },
                "required": ["network_id", "element_type", "element_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_loadflow_on_network",
            "description": "Belirtilen ağ üzerinde Newton-Raphson yük akışı çalıştırır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "network_id": {"type": "string"},
                    "scenario": {"type": "string",
                                "enum": ["peak_load", "min_load", "max_pv", "custom"]},
                },
                "required": ["network_id"],
            },
        },
    },
]

_DEFAULT_POLICIES = [
    {"name": "Teşviksiz Baz Senaryo", "incentives": []},
    {"name": "%30 Sermaye Hibesi",
     "incentives": [{"type": "capital_subsidy", "subsidy_pct": 30}]},
    {"name": "Düşük Faizli Kredi (%10, 10 yıl)",
     "incentives": [{"type": "low_interest_loan", "loan_pct": 70,
                     "loan_rate_pct": 10, "loan_term_yr": 10}]},
    {"name": "KDV Muafiyeti + Karbon Kredisi",
     "incentives": [{"type": "vat_exemption", "vat_rate": 0.20},
                    {"type": "carbon_credit", "carbon_credit_tl_per_ton": 500}]},
]


class OllamaOrchestrator:
    def __init__(self) -> None:
        self.ollama_url = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.sim_base = "http://localhost:8000/api/v1/simulate"
        self._memory = session_memory
        self._fallback = MockLLMOrchestrator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_message(
        self,
        message: str,
        session_id: str,
        stakeholder_type: str = "residential",
        lang: str = "tr",
    ) -> dict:
        self._lang = lang   # cross-lingual koşul: sistem-prompt + guard-yedek dilini seçer
        self._memory.update_context(session_id, stakeholder_type=stakeholder_type)

        history = self._memory.get_chat_history(session_id)
        history.append({"role": "user", "content": message})

        try:
            assistant_msg = self._call_ollama(history, stakeholder_type)
        except Exception:
            return {**self._fallback.process_message(message, session_id),
                    "fallback": True}   # deney harness'ı Mock-yanıtları dışlar

        last_tool_result: dict | None = None
        guard_result = None
        # GFP provenance grafı — OTURUM-KALICI (A1-r1): önceki turların kayıtları
        # yüklenir; böylece çok-turlu sohbette önceki turun doğru sayıları
        # sahte-UNGROUNDED üretmez ve araçsız turlar da denetlenir.
        pgraph = ProvenanceGraph()
        pgraph.load_records(self._memory.get_provenance(session_id))
        provenance_report = None
        prov_blocked = False
        prov_retried = False
        # A21-E3: retry telemetrisi (yalnız log; karar hattını DEĞİŞTİRMEZ)
        retry_tool_calls_requested = False
        retry_content_empty = False
        retry_error = False
        tool_trace: list[dict] = []   # F2: SIRALI araç izi (args'lı) — set değil

        # A1-r1: ÇOK-TURLU araç döngüsü — model art arda araç çağırabilir
        # (zincirli sorular tek kullanıcı-turunda yürür; G2 zincirleri için gerekli)
        MAX_TOOL_ROUNDS = 4
        rounds = 0
        while rounds < MAX_TOOL_ROUNDS:
            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                break
            rounds += 1
            history.append({
                "role": "assistant",
                "content": assistant_msg.get("content", ""),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name: str = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                tool_result = self._execute_tool(tool_name, raw_args, stakeholder_type)
                last_tool_result = tool_result
                pgraph.add_tool_result(tool_name, raw_args, stakeholder_type, tool_result)
                tool_trace.append({"round": rounds, "tool": tool_name,
                                   "args": raw_args,
                                   "failed": isinstance(tool_result, dict)
                                   and tool_result.get("status") == "simulation_failed"})

                history.append({
                    "role": "tool",
                    "content": json.dumps(tool_result, ensure_ascii=False),
                    "name": tool_name,
                })

            try:
                assistant_msg = self._call_ollama(history, stakeholder_type)
            except Exception:
                return {**self._fallback.process_message(message, session_id),
                        "fallback": True}   # deney harness'ı Mock-yanıtları dışlar

        final_content: str = assistant_msg.get("content", "")

        # ── GFP ProvenanceGuard (A1): denetle → (block modunda) düzelt → blokla ──
        guard_mode = getattr(settings, "GUARD_MODE", "block")
        pre_intervention = None   # ORTA-9b: müdahale-ÖNCESİ ham LLM metninin denetimi
        # v4.2 (A21): araç çağrılmamış tek-tur (boş graf) da değerlendirilir — v4.1'de
        # `pgraph.has_records` koşulu bu yanıtları denetimsiz teslim ediyordu (A20).
        if guard_mode != "off":
            provenance_report = pgraph.check_response(final_content)
            pre_intervention = {"counts": provenance_report.counts,
                                "passed": provenance_report.passed,
                                "ambiguous_matches": provenance_report.ambiguous_matches,
                                # F5: ham müdahale-öncesi metin (insan kodlaması / analiz izi)
                                "reply": final_content}
            if not provenance_report.passed and guard_mode == "block":
                # 1) Tek düzeltme denemesi: ihlaller modele bildirilir
                prov_retried = True
                history.append({"role": "system",
                                "content": pgraph.corrective_instruction(
                                    provenance_report, getattr(self, "_lang", "tr"))})
                try:
                    retry_msg = self._call_ollama(history, stakeholder_type)
                    retry_content = retry_msg.get("content", "") or ""
                    retry_tool_calls_requested = bool(retry_msg.get("tool_calls"))
                except Exception:
                    retry_content = ""
                    retry_error = True
                retry_content_empty = not retry_content.strip()
                retry_report = pgraph.check_response(retry_content) if retry_content else None
                if retry_report is not None and retry_report.passed:
                    final_content = retry_content
                    provenance_report = retry_report
                else:
                    # 2) Hâlâ ihlal → deterministik güvenli özet (temelsiz sayı SIZMAZ)
                    prov_blocked = True
                    final_content = pgraph.safe_summary(last_tool_result, getattr(self, "_lang", "tr"))
                    provenance_report = pgraph.check_response(final_content)
            if provenance_report and provenance_report.violations:
                import logging
                logging.getLogger(__name__).warning(
                    "ProvenanceGuard (session=%s, mode=%s, blocked=%s): %s",
                    session_id, guard_mode, prov_blocked,
                    provenance_report.violations[:5],
                )

        history.append({"role": "assistant", "content": final_content})
        self._memory.save_chat_history(session_id, history)
        # A1-r1: grafı oturuma kalıcılaştır (sonraki turlar önceki sayıları tanır)
        if pgraph.has_records:
            self._memory.save_provenance(session_id, pgraph.records_as_dicts())

        if last_tool_result is not None:
            self._memory.append_simulation(session_id, last_tool_result)
            # Eski nokta-bazlı guard — G4 deneyinin BASELINE'ı olarak korunur (yalnız loglar)
            guard_result = validate_response(final_content, last_tool_result)
            if not guard_result.passed:
                import logging
                logging.getLogger(__name__).warning(
                    "HallucinationGuard ihlali (session=%s): %s",
                    session_id, guard_result.violations,
                )

        prov_dict = None
        if provenance_report is not None:
            prov_dict = provenance_report.to_dict()
            prov_dict.update({
                "mode": guard_mode, "blocked": prov_blocked,
                "retried": prov_retried,
                "retry_tool_calls_requested": retry_tool_calls_requested,
                "retry_content_empty": retry_content_empty,
                "retry_error": retry_error,
                "n_records": len(pgraph.records),
                # ORTA-9b: guard-kolu GFS'i mekanik ≈1 olur (safe_summary öz-denetimden
                # geçer) → deney analizi müdahale-ÖNCESİ bileşenleri de alır
                "pre_intervention": pre_intervention,
                # telemetri: bu turda hangi araçlar kullanıldı (kaynak fonksiyonlar)
                "tools_used": sorted({r.source_function for r in pgraph.records
                                      if r.source_function != "input"}),
                # F2: SIRALI iz — aynı aracın 2× çağrılmasını da ayırt eder (res-06)
                "tool_trace": tool_trace,
            })

        return {
            "reply": final_content,
            "simulation_result": last_tool_result,
            "missing_params": [],
            "follow_up_questions": [],
            "guard": guard_result.to_dict() if guard_result else None,
            "provenance": prov_dict,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_ollama(self, messages: list[dict], stakeholder_type: str = "residential") -> dict:
        system_prompt = get_system_prompt(stakeholder_type, getattr(self, "_lang", "tr"))
        options: dict = {"temperature": 0.3}
        # Deney tekrarlanabilirliği (A2): koşucu orch._ollama_seed atarsa sabitlenir
        seed = getattr(self, "_ollama_seed", None)
        if seed is not None:
            options["seed"] = int(seed)
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "tools": SIMULATION_TOOLS,
            "stream": False,
            "options": options,
        }
        resp = httpx.post(
            f"{self.ollama_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]

    def _execute_tool(self, tool_name: str, args: dict, stakeholder_type: str) -> dict:
        try:
            if tool_name == "simulate_pv_bess":
                return self._run_pv_bess(args, stakeholder_type)
            elif tool_name == "simulate_grid_impact":
                return self._run_grid_impact(args)
            elif tool_name == "run_policy_scenario":
                return self._run_policy_scenario(args)
            elif tool_name == "run_monte_carlo":
                return self._run_monte_carlo(args)
            elif tool_name == "configure_pv_system":
                return self._run_configure_pv_system(args)
            elif tool_name == "update_pv_parameter":
                return self._run_update_pv_parameter(args)
            elif tool_name == "run_pv_simulation":
                return self._run_pv_simulation(args)
            elif tool_name == "configure_bess_system":
                return self._run_configure_bess_system(args)
            elif tool_name == "update_bess_parameter":
                return self._run_update_bess_parameter(args)
            elif tool_name == "run_bess_simulation":
                return self._run_bess_simulation(args)
            elif tool_name == "build_custom_network":
                return self._run_build_custom_network(args)
            elif tool_name == "update_network_element":
                return self._run_update_network_element(args)
            elif tool_name == "run_loadflow_on_network":
                return self._run_loadflow_on_network(args)
            else:
                return {"error": f"Bilinmeyen araç: {tool_name}", "status": "simulation_failed"}
        except Exception as exc:
            return {"error": str(exc), "status": "simulation_failed"}

    # ---- Temel simülasyon -----------------------------------------------

    def _run_pv_bess(self, args: dict, stakeholder_type: str) -> dict:
        city = args.get("city", "ankara")
        lat, lon = CITY_COORDS.get(city, CITY_COORDS["ankara"])
        annual_kwh = args.get("annual_consumption_kwh")
        if annual_kwh is None:
            monthly_bill = args.get("monthly_bill_tl")
            if not monthly_bill:
                annual_kwh = 5000.0
            elif july_2026_replay():
                annual_kwh = monthly_bill * 12 / 0.5      # Temmuz-replay: eski sabit (A27)
            else:
                # A27: faturanın tarife-tersi (mesken kademeli, diğerleri düz fiyat)
                annual_kwh = bill_to_annual_consumption(
                    monthly_bill_tl=monthly_bill,
                    stakeholder_type=args.get("stakeholder_type", stakeholder_type))

        payload = {
            "panel_kw": args["panel_kw"],
            "bess_kwh": args.get("bess_kwh", 0.0),
            "latitude": lat, "longitude": lon,
            "annual_consumption_kwh": annual_kwh,
            "stakeholder_type": args.get("stakeholder_type", stakeholder_type),
            "bess_chemistry": args.get("bess_chemistry", "LFP"),
        }
        resp = httpx.post(f"{self.sim_base}/pv-bess", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _run_grid_impact(self, args: dict) -> dict:
        payload = {
            "pv_penetration_pct": args["pv_penetration_pct"],
            "bess_penetration_pct": args.get("bess_penetration_pct", 0.0),
            "run_penetration_sweep": args.get("run_penetration_sweep", False),
        }
        resp = httpx.post(f"{self.sim_base}/grid-impact", json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()

    def _run_policy_scenario(self, args: dict) -> dict:
        payload = {
            "base_investment_tl": args["base_investment_tl"],
            "annual_savings_tl": args["annual_savings_tl"],
            "lifetime_years": args.get("lifetime_years", 25),
            "discount_rate": args.get("discount_rate", 0.12),
            "policies": args.get("policies") or _DEFAULT_POLICIES,
        }
        resp = httpx.post(f"{self.sim_base}/policy-scenario", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _run_monte_carlo(self, args: dict) -> dict:
        # /simulate/monte-carlo yatırım+tasarruf ister (panel/şehir DEĞİL) —
        # args'ta yoksa önce fizibilite koşulur, MC onun çıktısıyla beslenir.
        # (Eski payload panel_kw gönderiyordu → araç BAŞTAN BERİ 422 veriyordu;
        # KRİTİK-7 referans-graf fail-fast'i bu üretim bug'ını açığa çıkardı.)
        inv = args.get("base_investment_tl")
        sav = args.get("base_annual_savings_tl")
        if inv is None or sav is None:
            feas = self._run_pv_bess(args, args.get("stakeholder_type", "residential"))
            inv = feas.get("system_cost_tl")
            sav = feas.get("annual_savings_tl")
            if inv is None or sav is None:
                raise ValueError("Monte Carlo için yatırım/tasarruf türetilemedi "
                                 "(fizibilite yanıtı beklenen alanları içermiyor)")
        payload = {
            "base_investment_tl": inv,
            "base_annual_savings_tl": sav,
            "lifetime_years": int(args.get("lifetime_years", 25)),
            "n_iterations": max(100, int(args.get("n_iterations", 1000))),
        }
        resp = httpx.post(f"{self.sim_base}/monte-carlo", json=payload, timeout=300)
        resp.raise_for_status()
        return {**resp.json(),
                "base_investment_tl": inv, "base_annual_savings_tl": sav}

    # ---- GES konfigürasyon ----------------------------------------------

    def _run_configure_pv_system(self, args: dict) -> dict:
        resp = httpx.post("http://localhost:8000/api/v1/pv-system/create", json=args, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _run_update_pv_parameter(self, args: dict) -> dict:
        system_id = args.pop("system_id")
        resp = httpx.patch(
            f"http://localhost:8000/api/v1/pv-system/{system_id}/parameter",
            json={"target": args["target"], "value": args["value"]},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _run_pv_simulation(self, args: dict) -> dict:
        system_id = args["system_id"]
        resp = httpx.post(
            f"http://localhost:8000/api/v1/pv-system/{system_id}/run",
            json={"weather_source": args.get("weather_source", "pvgis_tmy")},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        # LLM narasyonuna gerekli özet alanları ekle (hourly_profile çok büyük olduğu için çıkar)
        result.pop("hourly_profile_kwh", None)
        return result

    # ---- BESS konfigürasyon --------------------------------------------

    def _run_configure_bess_system(self, args: dict) -> dict:
        resp = httpx.post("http://localhost:8000/api/v1/bess-system/create", json=args, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _run_update_bess_parameter(self, args: dict) -> dict:
        system_id = args.pop("system_id")
        resp = httpx.patch(
            f"http://localhost:8000/api/v1/bess-system/{system_id}/parameter",
            json={"target": args["target"], "value": args["value"]},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _run_bess_simulation(self, args: dict) -> dict:
        bess_id = args["bess_system_id"]
        pv_hourly: list | None = None
        pv_sys_id = args.get("pv_system_id")
        if pv_sys_id:
            try:
                pv_resp = httpx.post(
                    f"http://localhost:8000/api/v1/pv-system/{pv_sys_id}/run",
                    json={"weather_source": "pvgis_tmy"},
                    timeout=120,
                )
                pv_resp.raise_for_status()
                pv_hourly = pv_resp.json().get("hourly_profile_kwh")
            except Exception:
                pv_hourly = None

        payload = {
            "pv_hourly_kwh": pv_hourly,
            "stakeholder_type": args.get("stakeholder_type", "residential"),
            "simulate_degradation_years": int(args.get("simulate_degradation_years", 1)),
        }
        resp = httpx.post(
            f"http://localhost:8000/api/v1/bess-system/{bess_id}/run",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        # Büyük profilleri çıkar
        result.pop("soc_profile", None)
        result.pop("charge_profile", None)
        result.pop("discharge_profile", None)
        return result

    # ---- Ağ yönetimi ---------------------------------------------------

    def _run_build_custom_network(self, args: dict) -> dict:
        resp = httpx.post("http://localhost:8000/api/v1/network/create", json=args, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _run_update_network_element(self, args: dict) -> dict:
        network_id = args.pop("network_id")
        resp = httpx.put(
            f"http://localhost:8000/api/v1/network/{network_id}/element",
            json=args,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _run_loadflow_on_network(self, args: dict) -> dict:
        network_id = args["network_id"]
        resp = httpx.post(
            f"http://localhost:8000/api/v1/network/{network_id}/run",
            json={"scenario": args.get("scenario", "peak_load")},
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        # Harita verisini koru ama özet oluştur
        summary = result.get("summary", {})
        return {
            "network_id": network_id,
            "converged": result.get("converged"),
            "summary": summary,
            "bus_count": len(result.get("buses", [])),
            "line_count": len(result.get("lines", [])),
            "voltage_violation": summary.get("voltage_violation"),
            "max_vm_pu": summary.get("max_vm_pu"),
            "min_vm_pu": summary.get("min_vm_pu"),
        }
