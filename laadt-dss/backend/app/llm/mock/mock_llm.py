import re
import httpx

class MockLLMOrchestrator:
    """
    Gerçek LLM'i taklit eden deterministik stub.
    Pattern-matching ile intent tespiti yaparak ilgili simülasyon API'si çağırılır.
    """
    SIMULATION_BASE_URL = "http://localhost:8000/api/v1/simulate"

    INTENTS = {
        "pv_feasibility": {
            "patterns": [r"güneş\s*panel", r"\bges\b", r"\bpv\b", r"kaç\s*kwh", r"üretim", r"solar"],
            "missing_params": ["panel_kw", "location"],
        },
        "bess_feasibility": {
            "patterns": [r"batarya", r"\bbess\b", r"pil", r"depolama", r"amorti", r"geri\s*dönüş"],
            "missing_params": ["bess_kwh", "annual_consumption_kwh"],
        },
        "savings_query": {
            "patterns": [r"tasarruf", r"fatura", r"kar"],
            "missing_params": [],
        },
        "commercial_feasibility": {
            "patterns": [r"ticari", r"ofis", r"fabrika", r"mağaza", r"otel", r"restoran", r"commercial"],
            "missing_params": ["panel_kw", "annual_consumption_kwh"],
        },
        "municipal_policy": {
            "patterns": [r"belediye", r"sokak\s*aydınlatma", r"su\s*pompas", r"kamu\s*bina", r"municipal"],
            "missing_params": ["annual_consumption_kwh"],
        },
        "utility_grid": {
            "patterns": [r"şebeke", r"dağıtım", r"trafo", r"gerilim", r"yük\s*akış", r"hosting", r"grid", r"penetrasyon"],
            "missing_params": ["pv_penetration_pct"],
        },
        "policy_comparison": {
            "patterns": [r"teşvik", r"sübvansiyon", r"vergi\s*indirimi", r"kredi", r"net\s*sayaç", r"feed.in", r"politika", r"senaryo"],
            "missing_params": ["base_investment_tl"],
        },
        "general_info": {
            "patterns": [],
            "missing_params": [],
        },
    }

    def _classify_intent(self, message: str) -> str:
        msg_lower = message.lower()
        for intent, config in self.INTENTS.items():
            if intent == "general_info":
                continue
            for pattern in config["patterns"]:
                if re.search(pattern, msg_lower):
                    return intent
        return "general_info"

    def _extract_params(self, message: str) -> dict:
        params = {}
        # Panel gücü: "10 kW", "5kw", "10kWp"
        panel_match = re.search(r"(\d+(?:\.\d+)?)\s*kw(?:p)?", message.lower())
        if panel_match:
            params["panel_kw"] = float(panel_match.group(1))

        # Batarya kapasitesi: "14.4 kWh", "10kwh"
        bess_match = re.search(r"(\d+(?:\.\d+)?)\s*kwh", message.lower())
        if bess_match:
            params["bess_kwh"] = float(bess_match.group(1))

        # Yatırım tutarı: "500000 TL", "500k TL"
        investment_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k\s*)?tl", message.lower())
        if investment_match:
            val = float(investment_match.group(1))
            if "k tl" in message.lower() or "k\ttl" in message.lower():
                val *= 1000
            params["base_investment_tl"] = val

        # PV penetrasyon yüzdesi
        pv_pct_match = re.search(r"(%?)\s*(\d+(?:\.\d+)?)\s*%?\s*(?:pv|penetrasyon)", message.lower())
        if pv_pct_match:
            params["pv_penetration_pct"] = float(pv_pct_match.group(2))

        # Lokasyon: şehir ismi (Hızlı lookup)
        city_map = {
            "ankara": (39.93, 32.86),
            "istanbul": (41.01, 28.95),
            "izmir": (38.42, 27.14),
            "antalya": (36.90, 30.70),
            "konya": (37.87, 32.49),
        }
        for city, (lat, lon) in city_map.items():
            if city in message.lower():
                params["latitude"] = lat
                params["longitude"] = lon
                params["city"] = city
                break

        # Stakeholder type detection
        stakeholder_map = {
            "ofis": "commercial",
            "ticari": "commercial",
            "fabrika": "commercial",
            "mağaza": "commercial",
            "belediye": "municipal",
            "kamu": "municipal",
            "dağıtım": "utility",
            "şebeke": "utility",
        }
        for keyword, stype in stakeholder_map.items():
            if keyword in message.lower():
                params["stakeholder_type"] = stype
                break

        return params

    def _call_simulation(self, intent: str, params: dict) -> dict | None:
        if intent in ("pv_feasibility", "bess_feasibility", "savings_query",
                      "commercial_feasibility", "municipal_policy"):
            # Build a best-effort pv-bess request
            payload = {
                "panel_kw": params.get("panel_kw", 10.0),
                "bess_kwh": params.get("bess_kwh", 0.0),
                "latitude": params.get("latitude", 39.93),
                "longitude": params.get("longitude", 32.86),
                "annual_consumption_kwh": params.get("annual_consumption_kwh", 5000.0),
                "stakeholder_type": params.get("stakeholder_type", "residential"),
            }
            try:
                resp = httpx.post(
                    f"{self.SIMULATION_BASE_URL}/pv-bess",
                    json=payload,
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        elif intent == "utility_grid":
            payload = {
                "pv_penetration_pct": params.get("pv_penetration_pct", 30.0),
                "bess_penetration_pct": params.get("bess_penetration_pct", 0.0),
                "run_penetration_sweep": True,
            }
            try:
                resp = httpx.post(
                    f"{self.SIMULATION_BASE_URL}/grid-impact",
                    json=payload,
                    timeout=60
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        elif intent == "policy_comparison":
            base_inv = params.get("base_investment_tl", 250000.0)
            # Default: compare capital subsidy vs low-interest loan vs no incentive
            payload = {
                "base_investment_tl": base_inv,
                "annual_savings_tl": base_inv * 0.12,  # ~12% annual yield
                "lifetime_years": 25,
                "discount_rate": 0.12,
                "policies": [
                    {
                        "name": "Teşviksiz Baz Senaryo",
                        "incentives": []
                    },
                    {
                        "name": "%30 Sermaye Hibesi",
                        "incentives": [{"type": "capital_subsidy", "subsidy_pct": 30}]
                    },
                    {
                        "name": "Düşük Faizli Kredi (%10, 10 yıl)",
                        "incentives": [{"type": "low_interest_loan", "loan_pct": 70, "loan_rate_pct": 10, "loan_term_yr": 10}]
                    },
                    {
                        "name": "KDV Muafiyeti + Karbon Kredisi",
                        "incentives": [
                            {"type": "vat_exemption", "vat_rate": 0.20},
                            {"type": "carbon_credit", "carbon_credit_tl_per_ton": 500}
                        ]
                    },
                ],
            }
            try:
                resp = httpx.post(
                    f"{self.SIMULATION_BASE_URL}/policy-scenario",
                    json=payload,
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        return None

    def _format_response(self, sim_result: dict | None, intent: str, params: dict) -> dict:
        if sim_result is None:
            return {
                "reply": (
                    "Simülasyon çalıştırılamadı. Lütfen panel gücü (kW), "
                    "batarya kapasitesi (kWh) ve konum bilgisini paylaşın."
                ),
                "simulation_result": None,
                "missing_params": ["panel_kw", "location"],
                "follow_up_questions": [
                    "Kaç kW'lık panel düşünüyorsunuz?",
                    "Hangi şehirde kurulacak?",
                ],
            }

        if intent == "utility_grid":
            grid = sim_result.get("grid_impact", {})
            hca = sim_result.get("hosting_capacity_analysis", {})
            hosting = hca.get("hosting_capacity_pct", "N/A")
            voltage_ok = not grid.get("voltage_violation", True)
            max_v = grid.get("max_voltage_pu", "?")

            reply = (
                f"Şebeke etki analizi sonuçları:\n"
                f"• Maksimum gerilim: **{max_v} pu** ({'Kabul edilebilir' if voltage_ok else 'İHLAL'})\n"
                f"• Hat yüklenme: **%{grid.get('max_line_loading_pct', '?')}**\n"
                f"• Ters güç akışı: {'Evet' if grid.get('reverse_power_flow') else 'Hayır'}\n"
                f"• Hosting kapasitesi: **%{hosting}** PV penetrasyonuna kadar güvenli\n\n"
                f"NAYY 4x50 SE kablo standardına göre analiz yapılmıştır."
            )
            return {
                "reply": reply,
                "simulation_result": sim_result,
                "missing_params": [],
                "follow_up_questions": [
                    "BESS ekleyerek hosting kapasitesini artıralım mı?",
                    "Trafo yükseltme ertelemesi analizi yapalım mı?",
                ],
            }

        if intent == "policy_comparison":
            best = sim_result.get("best_policy_by_npv", "?")
            results = sim_result.get("policy_results", [])
            summary_lines = []
            for r in results[:4]:
                pbp = r.get('simple_payback_years')
                pbp_txt = f"{pbp:.1f} yıl" if isinstance(pbp, (int, float)) else "ömür içinde geri ödemiyor"
                summary_lines.append(
                    f"• {r['policy_name']}: NPV={r['npv_tl']:,.0f} TL, "
                    f"Geri dönüş={pbp_txt}"
                )
            reply = (
                f"Teşvik politikası karşılaştırması:\n"
                + "\n".join(summary_lines) +
                f"\n\n**En iyi senaryo (NPV): {best}**\n"
                f"Sonuçlar 2026 Türkiye piyasa koşullarına göre hesaplanmıştır."
            )
            return {
                "reply": reply,
                "simulation_result": sim_result,
                "missing_params": [],
                "follow_up_questions": [
                    "Monte Carlo belirsizlik analizi yapalım mı?",
                    "Farklı teşvik kombinasyonlarını deneyelim mi?",
                ],
            }

        npv = sim_result.get("npv_tl", 0)
        payback = sim_result.get("simple_payback_years", "?")
        savings = sim_result.get("annual_savings_tl", 0)
        irr = sim_result.get("irr_percent", "?")

        reply = (
            f"Simülasyon sonuçlarına göre:\n"
            f"• Yıllık tahmini tasarruf: **{savings:,.0f} TL**\n"
            f"• Geri dönüş süresi: **{payback:.1f} yıl** (basit)\n"
            f"• 25 yıllık NPV: **{npv:,.0f} TL**\n"
            f"• IRR: **%{irr}**\n\n"
            f"Bu sonuçlar 2026 Türkiye EPDK tarifesine ve standart meteoroloji "
            f"verilerine (PVGIS) dayanmaktadır."
        ) if isinstance(payback, float) else (
            "Şu an tam hesaplama yapılamıyor. Lütfen eksik parametreleri sağlayın."
        )

        follow_ups = [
            "Batarya eklemek ister misiniz?",
            "Farklı bir senaryo deneyelim mi?",
        ]
        if intent in ("commercial_feasibility",):
            follow_ups = [
                "Hangi ticari yapı tipi (ofis/fabrika/mağaza)?",
                "Teşvik senaryolarını karşılaştıralım mı?",
            ]
        elif intent == "municipal_policy":
            follow_ups = [
                "Belediye tipi nedir (sokak aydınlatma/su pompası/kamu binası)?",
                "Şebeke etki analizini de yapalım mı?",
            ]

        return {
            "reply": reply,
            "simulation_result": sim_result,
            "missing_params": [],
            "follow_up_questions": follow_ups,
        }

    def process_message(self, message: str, session_id: str, stakeholder_type: str = "residential") -> dict:
        intent = self._classify_intent(message)
        params = self._extract_params(message)
        sim_result = self._call_simulation(intent, params)
        return self._format_response(sim_result, intent, params)
