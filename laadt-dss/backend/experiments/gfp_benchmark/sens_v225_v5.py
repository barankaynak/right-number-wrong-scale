"""ProvenanceGuard v5: platform-side fixes on top of the GFP-frozen guard (platform paper, 2026-11-14).

`provenance_guard.py` is frozen for the GFP paper (sha256 a050b46a…f7c2) and stays byte-identical. This module
subclasses its `ProvenanceGraph` and changes two things, found in the frozen scenario run `scn_freeze_v1`
(paper-platform/plans/2026-11-14-platform-scenarios-v2.md):

1. **Sign.** The frozen number regex captures no sign, so "-588,032 TL" was read as +588032 and every negative
   value was UNGROUNDED, including in the guard's own fallback. Here a claim takes its sign from `claim_sign`, and a
   signed claim matches only a record of the same sign.
   - Fail-closed: an unsigned claim never matches a negative record. "NPV 588,032 TL" against −588,031 is a
     decision-critical sign error. A negative written in words ("a loss of 588,032 TL") therefore stays unmatched.
   - `check_response` is a verbatim copy of the frozen method plus the lines marked "v5". On text without a minus
     sign it returns exactly what the frozen guard returns (tested).
2. **Fallback summary.** The frozen `safe_summary` read only top-level keys, so grid, Monte Carlo and policy results
   (nested) gave "no summarizable numeric field found". Here it also reads `grid_impact.*`,
   `hosting_capacity_analysis.*`, `npv_statistics.*`, `payback_statistics.*` and `policy_results[*]`. Labels carry no
   digits, so the summary passes its own check.

`claim_sign` is a pure function so that the GFP session can import the same rule (one shared source).
"""
from __future__ import annotations

import re

from app.llm.provenance_guard import (  # noqa: F401  (names used by the verbatim check_response copy)
    _COUNT_CONTEXT_RE, _IGNORABLE_INTS, _NUM_RE, _PAYBACK_CUES, _YEAR_RANGE, ClaimCheck, ProvenanceGraph,
    ProvenanceRecord, ProvenanceReport, _candidate_values, _infer_claim_unit, _matches, _sentence_scales,
    _split_sentences, _units_compatible,
)

_MINUS = "-−–"              # hyphen-minus, minus sign (U+2212), en dash
_FILLERS = ("**", "*", "₺", "$", "TL")  # may stand between the minus and the digits


def claim_sign(sentence: str, start: int) -> int:
    """Sign of the number whose digits start at `start` in `sentence`: -1 or +1.

    - A minus (`-`, `−`, `–`) counts only directly before the number. A currency sign (₺, $, TL) or `*`/`**` may
      stand in between: "-588,032", "−₺588,032", "**-588,032**", "(-4,676 TL)".
    - A dash after a letter, digit, `%` or `.` is a hyphen or a range, so the number stays positive: "year-1",
      "LFP-10", "5-10".
    - A dash whose previous non-space character is a digit or `%` is a spaced range: "%8 - %12", "12:00 - 16:00".
    - A dash followed by a space (a list dash, "- 25 yıllık") is not directly before the number, so it is positive.
    """
    i = start
    while True:
        for f in _FILLERS:
            if i >= len(f) and sentence[i - len(f):i] == f:
                i -= len(f)
                break
        else:
            break
    if i == 0 or sentence[i - 1] not in _MINUS:
        return 1
    j = i - 1
    if j > 0 and (sentence[j - 1].isalnum() or sentence[j - 1] in "%."):
        return 1
    k = j - 1
    while k >= 0 and sentence[k] == " ":
        k -= 1
    if k >= 0 and (sentence[k].isdigit() or sentence[k] == "%"):
        return 1
    return -1


# (container, key, TR label, EN label, format) — labels carry no digits (they are checked like any other text).
# Voltages use three decimals: the frozen number regex reads "1.1015" as "1.101" plus a stray "5".
_NESTED_KEYS = [
    ("grid_impact", "pv_penetration_pct", "PV penetrasyonu", "PV penetration", "%{:.1f}"),
    ("grid_impact", "max_voltage_pu", "Maks. gerilim", "Max voltage", "{:.3f} pu"),
    ("grid_impact", "min_voltage_pu", "Min. gerilim", "Min voltage", "{:.3f} pu"),
    ("grid_impact", "max_line_loading_pct", "Maks. hat yüklenmesi", "Max line loading", "%{:.1f}"),
    ("grid_impact", "trafo_loading_pct", "Trafo yüklenmesi", "Transformer loading", "%{:.1f}"),
    ("hosting_capacity_analysis", "hosting_capacity_pct", "Hosting kapasitesi", "Hosting capacity", "%{:.1f}"),
    ("npv_statistics", "p5_tl", "NPV, belirsizlik bandının alt ucu", "NPV, low end of the uncertainty band",
     "{:,.0f} TL"),
    ("npv_statistics", "p50_tl", "NPV, medyan", "NPV, median", "{:,.0f} TL"),
    ("npv_statistics", "p95_tl", "NPV, belirsizlik bandının üst ucu", "NPV, high end of the uncertainty band",
     "{:,.0f} TL"),
    ("npv_statistics", "prob_positive_npv", "NPV'nin pozitif olduğu çekiliş payı",
     "Share of draws with a positive NPV", "%{:.1f}"),
    ("payback_statistics", "p50_years", "Geri ödeme, medyan", "Payback, median", "{:.1f} yıl"),
]
_MC_INPUT_KEYS = [
    ("base_investment_tl", "Kullanılan yatırım", "Investment used", "{:,.0f} TL"),
    ("base_annual_savings_tl", "Kullanılan ilk yıl tasarrufu", "First-year savings used", "{:,.0f} TL"),
]
_FLAGS = [
    ("voltage_violation", "Gerilim sınırı aşıldı", "Voltage limit exceeded"),
    ("line_overload", "Hat aşırı yüklendi", "Line overload"),
    ("trafo_overload", "Trafo aşırı yüklendi", "Transformer overload"),
]


def _policy_label(name: str) -> str:
    """The policy name without numbers (they would be checked as claims): "%30 Sermaye Hibesi" -> "Sermaye Hibesi"."""
    s = re.sub(r"\([^)]*\d[^)]*\)", "", name or "")
    s = re.sub(r"%?\s*\d+(?:[.,]\d+)?\s*%?", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    return s or "Policy"


def _fmt(val: float, fmt: str, en: bool, ratio_as_pct: bool = False) -> str:
    v = float(val)
    if ratio_as_pct and v <= 1.0:
        v *= 100.0
    s = fmt.format(v)
    if en:
        s = s.replace(" yıl", " years")
        if s.startswith("%"):
            s = s[1:] + "%"
    return s


class ProvenanceGraphV5(ProvenanceGraph):
    """The frozen ProvenanceGraph with the sign rule and the nested fallback summary (see the module docstring)."""

    def safe_summary(self, tool_result: dict | None, lang: str = "tr") -> str:
        en = lang == "en"
        if not self.records:
            return self._EMPTY_GRAPH_SUMMARY["en" if en else "tr"]
        lines = ["Simulation results (verified values):" if en else "Simülasyon sonuçları (doğrulanmış değerler):"]
        src = tool_result or {}
        for key, tr_label, en_label, fmt in self._SUMMARY_KEYS:          # frozen top-level keys, frozen format
            if src.get(key) is not None:
                lines.append(f"• {en_label if en else tr_label}: "
                             f"{_fmt(src[key], fmt, en, key == 'self_consumption_ratio')}")
        for box, key, tr_label, en_label, fmt in _NESTED_KEYS:
            val = (src.get(box) or {}).get(key) if isinstance(src.get(box), dict) else None
            if val is not None and not isinstance(val, bool):
                lines.append(f"• {en_label if en else tr_label}: "
                             f"{_fmt(val, fmt, en, key == 'prob_positive_npv')}")
        grid = src.get("grid_impact") if isinstance(src.get("grid_impact"), dict) else {}
        for key, tr_label, en_label in _FLAGS:
            if isinstance(grid.get(key), bool):
                yes = ("yes" if en else "evet") if grid[key] else ("no" if en else "hayır")
                lines.append(f"• {en_label if en else tr_label}: {yes}")
        if isinstance(src.get("npv_statistics"), dict):
            for key, tr_label, en_label, fmt in _MC_INPUT_KEYS:
                if src.get(key) is not None:
                    lines.append(f"• {en_label if en else tr_label}: {_fmt(src[key], fmt, en)}")
        for p in src.get("policy_results") or []:
            if not isinstance(p, dict):
                continue
            parts = []
            if p.get("npv_tl") is not None:
                parts.append(f"NPV {_fmt(p['npv_tl'], '{:,.0f} TL', en)}")
            if p.get("state_cost_tl") is not None:
                parts.append(f"{'state cost' if en else 'devlet maliyeti'} {_fmt(p['state_cost_tl'], '{:,.0f} TL', en)}")
            if p.get("irr_pct") is not None:
                parts.append(f"{'IRR' if en else 'İVO'} {_fmt(p['irr_pct'], '%{:.1f}', en)}")
            if parts:
                lines.append(f"• {_policy_label(p.get('policy_name', ''))}: {', '.join(parts)}")
        for key, tr_label, en_label in (("best_policy_by_npv", "NPV'ye göre en iyi", "Best by NPV"),
                                        ("best_policy_by_effectiveness", "Etkinliğe göre en iyi",
                                         "Best by effectiveness")):
            if isinstance(src.get(key), str):
                lines.append(f"• {en_label if en else tr_label}: {_policy_label(src[key])}")
        if len(lines) == 1:
            lines.append("• (no summarizable numeric field found)" if en
                         else "• (özetlenebilir sayısal alan bulunamadı)")
        lines.append("")
        lines.append(
            "Note: the response was replaced with a deterministic summary because the "
            "numeric verification (provenance guard) could not match the LLM text's "
            "values to the simulation source." if en else
            "Not: Yanıt, sayısal doğrulama (provenance guard) LLM metnindeki "
            "değerleri simülasyon kaynağıyla eşleyemediği için deterministik "
            "özetle değiştirilmiştir.")
        return "\n".join(lines)

    def check_response(self, text: str) -> ProvenanceReport:
        # Verbatim copy of the frozen ProvenanceGraph.check_response; the only change is marked "v5".
        report = ProvenanceReport()
        # v4.2 (A21): boş graf da denetlenir — kayıt yoksa her sayı UNGROUNDED/IGNORED
        if not text:
            return report

        for sentence in _split_sentences(text):
            claimed = _sentence_scales(sentence)
            for m in _NUM_RE.finditer(sentence):
                token = m.group("num")
                is_pct = bool(m.group("pct") or m.group("pct2"))
                cands = _candidate_values(token, m.group("mag"))
                # v5: the claim's sign (claim_sign); a signed claim matches only same-sign records
                sign = claim_sign(sentence, m.start("num"))
                if sign < 0:
                    cands = [-c for c in cands]
                if is_pct:
                    # yüzde iddiası, kayıtta 0-1 ORAN olarak durabilir (%53,8 ↔ 0.538)
                    cands = cands + [c / 100.0 for c in cands]
                claim_unit = "%" if is_pct else _infer_claim_unit(
                    sentence, m.start(), m.end())

                # A1-r2: iki geçişli eşleştirme — önce BİRİM-UYUMLU kayıtlar;
                # yalnız birim-ÇELİŞEN kayıt eşleşiyorsa → UNIT_MISMATCH
                # ("doğru sayı / yanlış kaynak": üretim-kWh'si tasarruf-TL diye sunulmuş)
                matched: ProvenanceRecord | None = None
                matched_val = None
                unit_conflict: ProvenanceRecord | None = None
                n_compatible = 0
                for v in cands:
                    for r in self.records:
                        if not _matches(v, r.value):
                            continue
                        if _units_compatible(claim_unit, r.unit):
                            n_compatible += 1
                            if matched is None:
                                matched = r
                                matched_val = v
                        elif unit_conflict is None:
                            unit_conflict = r
                            matched_val = matched_val if matched else v
                    if matched:
                        break
                if n_compatible > 1:
                    report.ambiguous_matches += 1   # telemetri: çakışan eşleşme

                if matched is None and unit_conflict is not None:
                    report.claims.append(ClaimCheck(
                        text=m.group(0).strip(), value=matched_val,
                        verdict="UNIT_MISMATCH", sentence=sentence,
                        matched_key=unit_conflict.key,
                        record_scale=unit_conflict.scale,
                        claimed_scales=claimed,
                    ))
                    continue

                if matched is None:
                    v0 = cands[0]
                    year_like = (v0 == int(v0) and _YEAR_RANGE[0] <= v0 <= _YEAR_RANGE[1]
                                 and not is_pct and "." not in token and "," not in token)
                    # Karar-kritik payback iddiası: küçük-tamsayı muafiyeti GEÇERSİZ.
                    # Pencere ±25 karakter (cümle-düzeyi, bileşik cümlede "25 yıllık
                    # ömür"ü yanlış bloklardı); yıl-sayıları (2026) ve ≥100 hariç.
                    window = sentence[max(0, m.start() - 25):m.end() + 25].lower()
                    payback_claim = (claim_unit == "yıl" and v0 < 100 and not year_like
                                     and any(cue in window for cue in _PAYBACK_CUES))
                    count_context = bool(_COUNT_CONTEXT_RE.match(sentence[m.end():]))
                    ignorable = not payback_claim and (
                        count_context or
                        (v0 == int(v0) and int(v0) in _IGNORABLE_INTS) or
                        year_like
                    )
                    report.claims.append(ClaimCheck(
                        text=m.group(0).strip(), value=v0,
                        verdict="IGNORED" if ignorable else "UNGROUNDED",
                        sentence=sentence, claimed_scales=claimed,
                    ))
                    continue

                # Ölçek denetimi: kayıt building iken cümle feeder/policy iddia ediyorsa vb.
                verdict = "GROUNDED"
                if claimed and matched.scale not in claimed:
                    verdict = "SCALE_VIOLATION"
                report.claims.append(ClaimCheck(
                    text=m.group(0).strip(), value=matched_val,
                    verdict=verdict, sentence=sentence,
                    matched_key=matched.key, record_scale=matched.scale,
                    claimed_scales=claimed,
                ))

        for c in report.claims:
            if c.verdict == "UNGROUNDED":
                report.violations.append(
                    f"UNGROUNDED: '{c.text}' — hiçbir araç çıktısında/girdisinde yok "
                    f"(cümle: {c.sentence[:80]}…)")
            elif c.verdict == "SCALE_VIOLATION":
                report.violations.append(
                    f"SCALE_VIOLATION: '{c.text}' ({c.matched_key}, ölçek={c.record_scale}) "
                    f"cümlede {c.claimed_scales} ölçeği iddia ediliyor — sayı bu ölçekte "
                    f"doğrulanmamıştır (cümle: {c.sentence[:80]}…)")
            elif c.verdict == "UNIT_MISMATCH":
                report.violations.append(
                    f"UNIT_MISMATCH: '{c.text}' değeri kaynakta '{c.matched_key}' olarak "
                    f"üretilmiş — metin farklı bir birim/nicelik olarak sunuyor "
                    f"(cümle: {c.sentence[:80]}…)")
        report.passed = not report.violations
        return report
