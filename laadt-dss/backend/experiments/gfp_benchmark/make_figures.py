"""Makale figürleri — repo sonuç JSON'larından yeniden-üretilebilir.

Gereksinim: matplotlib (app runtime değil; figür-build): pip install "matplotlib<3.9".
Çıktı: experiments/gfp_benchmark/figures/*.pdf (+.png). Sonra host'ta paper/figures'a kopyalanır.

Figürler: G4 recall (fig_g4_recall), G4 ROC (fig_g4_roc), G1 Ekim Δ + sınırlar (fig_g1_decomp),
G1 Ekim McNemar + araçsız pay (fig_g1_mcnemar), G3 f* (fig_g3_fstar),
G3 ΔV-vs-f eğrileri (fig_g3_curves).

Kullanım: python -m experiments.gfp_benchmark.make_figures
"""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)

# ── stil (ColorBrewer, renk-körü-güvenli; serif; 300 DPI) ──
plt.rcParams.update({
    "font.family": "serif", "font.size": 9, "axes.titlesize": 10,
    "axes.labelsize": 9, "legend.fontsize": 8, "figure.dpi": 300,
    "savefig.dpi": 300, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
})
C_GFP = "#2166ac"      # mavi — GFP
C_LEG = "#b2182b"      # kırmızı — legacy/point-check
C_N1 = "#4393c3"       # açık mavi
C_N2 = "#f4a582"       # açık turuncu
C_GRAY = "#7f7f7f"
FEEDER_C = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02"]


def _load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def _save(fig, stem):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{stem}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {stem}.pdf/.png")


# ── Fig 3 — G4 kategori-başı recall (GFP vs nokta-guard) ──
def fig_g4_recall():
    d = _load("g4_summary.json")["per_category"]
    order = ["scale_swap", "unit_swap", "value_fabrication", "small_int_fabrication"]
    labels = ["scale-swap", "unit-swap", "value-fabr.", "small-int.$^{\\dagger}$"]
    gfp = [d[c]["gfp_ref_recall"] for c in order]
    leg = [d[c]["legacy_primary_recall"] for c in order]
    ps = [d[c]["mcnemar_gfp_vs_legacy"]["p"] for c in order]
    x = np.arange(len(order)); w = 0.38
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    ax.bar(x - w/2, gfp, w, label="GFP (provenance)", color=C_GFP)
    ax.bar(x + w/2, leg, w, label="deployed point-check", color=C_LEG)
    for i, (g, p) in enumerate(zip(gfp, ps)):
        star = "***" if p < 1e-3 else "**" if p < 1e-2 else "*" if p < 0.05 else "n.s."
        ax.text(i, g + 0.03, f"$p$={p:.2g}\n{star}", ha="center", va="bottom", fontsize=6.5)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("detection recall"); ax.set_ylim(0, 1.0)
    ax.set_title("G4: injected-error detection, per category (exact McNemar)")
    ax.legend(loc="upper right", frameon=False)
    ax.text(0.0, -0.30, "$^{\\dagger}$pre-registered power-limited ($n{=}10$)",
            transform=ax.transAxes, fontsize=6.5, color=C_GRAY)
    _save(fig, "fig_g4_recall")


# ── Fig 4 — G4 işletim-noktası (recall vs kontrol-FP) ──
def fig_g4_roc():
    d = _load("g4_summary.json")
    tot = d["tiers"]["overall"]
    gfp_rec = tot["gfp_ref_recall"]
    cf = d["control_fp"]
    # legacy okumaları: (recall, fp) — recall v2.11.5'ten sabit (JSON'da yok)
    pts = [
        ("GFP (provenance)", gfp_rec, cf["gfp_ref"]["rate"], C_GFP, "o"),
        ("point-check: violations", 0.0, cf["legacy_primary_violations"]["rate"], C_LEG, "s"),
        ("point-check: +warnings", 0.486, cf["legacy_s1_warnings"]["rate"], "#ef8a62", "^"),
        ("point-check: generosity ceiling", 0.752, cf["legacy_s2_ceiling"]["rate"], "#fddbc7", "v"),
    ]
    fig, ax = plt.subplots(figsize=(4.4, 3.4))
    ax.plot([0, 1], [0, 1], ls=":", color=C_GRAY, lw=0.8)
    for name, rec, fp, c, m in pts:
        ax.scatter(fp, rec, s=70, color=c, marker=m, edgecolor="k", lw=0.4, zorder=3, label=name)
    ax.axvspan(0.30, 1.0, color="red", alpha=0.05)
    ax.text(0.55, 0.05, "unusable\noperating region\n(high false alarm)", fontsize=6.5,
            color=C_LEG, ha="center")
    ax.set_xlabel("false-positive rate (unmutated controls)")
    ax.set_ylabel("detection recall (109 injections)")
    ax.set_xlim(-0.03, 0.75); ax.set_ylim(-0.03, 0.85)
    ax.set_title("G4: no legacy reading yields a usable operating point")
    ax.legend(loc="upper left", fontsize=6.5, frameon=False)
    _save(fig, "fig_g4_roc")


# ── Ekim G1 (oct_v42) — koşul-başına; yalnız donmuş analiz çıktılarını okur ──
OCT = RES / "oct_v42"
G1_CONDS = [("tr", "gemma4:e4b", "A tr"), ("en", "gemma4:e4b", "A en"),
            ("tr", "qwen3.8:27b", "B tr"), ("en", "qwen3.8:27b", "B en"),
            ("tr", "mistral-small3.2:24b", "C tr"), ("tr", "muse-glimmer:30b", "E tr")]


def _oct_gfs():
    out = {}
    for f in sorted((OCT / "analysis").glob("gfs_*_2026*.out")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[("en" if "_en_" in f.name else "tr", d["model"])] = d
    return out


# ── Fig 5 — G1: H_G1b Δ, birincil kural + iki ön-kayıtlı sınır (işaret muhasebeye bağlı) ──
def fig_g1_decomp():
    g = _oct_gfs()
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    y = np.arange(len(G1_CONDS))[::-1]
    rows = [("primary (withheld excluded)", lambda d: d["G1_reference_gfs"]["H_G1b"], C_GFP, "o"),
            ("bound: withheld = 0", lambda d: d["G1_reference_gfs_sensitivity"]["withheld_as_0"]["H_G1b"], C_LEG, "v"),
            ("bound: withheld = 1", lambda d: d["G1_reference_gfs_sensitivity"]["withheld_as_1"]["H_G1b"], C_N1, "^")]
    for k, (lab, get, c, m) in enumerate(rows):
        for i, (lang, model, name) in enumerate(G1_CONDS):
            b = get(g[(lang, model)])["bootstrap"]
            yy = y[i] + (0.22 - 0.22 * k)
            ax.errorbar(b["mean_diff"], yy, xerr=[[b["mean_diff"] - b["ci95"][0]], [b["ci95"][1] - b["mean_diff"]]],
                        fmt=m, color=c, ms=4.5, lw=0.9, capsize=1.5, label=lab if i == 0 else None)
    for i, (lang, model, name) in enumerate(G1_CONDS):
        n = g[(lang, model)]["G1_reference_gfs"]["H_G1b"]["achieved_n"]
        ax.text(1.01, y[i] + 0.22, f"n={n}", fontsize=6.5, va="center", color=C_GFP,
                transform=ax.get_yaxis_transform())
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y); ax.set_yticklabels([c[2] for c in G1_CONDS])
    ax.set_xlabel("delivered reference-GFS, guard $-$ no-guard (bootstrap mean, 95% CI)")
    ax.set_title("G1: the sign of the guard's effect depends on how withheld answers count", fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, fontsize=6.5, frameon=False)
    _save(fig, "fig_g1_decomp")


# ── Fig 6 — G1: tek-yönlü McNemar + aşırı-alıkoyma; araçsız pay ──
def fig_g1_mcnemar():
    g = _oct_gfs()
    names = [c[2] for c in G1_CONDS]
    a_only, b_only, over, toolless = [], [], [], []
    for lang, model, _ in G1_CONDS:
        d = g[(lang, model)]
        m = d["G1_reference_gfs"]["H_G1b"]["mcnemar_clean"]
        a_only.append(m["a_only"]); b_only.append(m["b_only"])
        over.append(d["withheld"]["clean_in_noguard_withheld_in_guard"]["any_repeat"]["n_questions"])
        toolless.append(100 * d["guard_side_metrics"]["toolless_rate"])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 3.0))
    x = np.arange(len(names)); w = 0.27
    ax1.bar(x - w, a_only, w, color=C_GFP, label="guard-only clean")
    ax1.bar(x, b_only, w, color=C_LEG, label="no-guard-only clean")
    ax1.bar(x + w, over, w, color=C_N2, label="over-blocking (clean withheld)")
    for i, b in enumerate(b_only):     # sıfır çubuk görünmez → değeri yaz
        ax1.text(x[i], b + 0.2, str(b), ha="center", fontsize=6.5, color=C_LEG)
    ax1.set_xticks(x); ax1.set_xticklabels(names, fontsize=7)
    ax1.set_ylabel("questions (of 56)"); ax1.set_title("(a) Clean-response McNemar", fontsize=9)
    ax1.legend(loc="upper right", fontsize=6, frameon=False); ax1.set_ylim(0, 16)
    ax2.bar(names, toolless, color=C_N1, width=0.55)
    for i, t in enumerate(toolless):
        ax2.text(i, t + 1.5, f"{t:.0f}%", ha="center", fontsize=6.5)
    ax2.set_ylabel("guarded responses without a tool call (%)"); ax2.set_ylim(0, 100)
    ax2.set_title("(b) No simulator call", fontsize=9)
    ax2.tick_params(axis="x", labelsize=7)
    fig.tight_layout(w_pad=2.0)
    _save(fig, "fig_g1_mcnemar")


# ── Fig 9 — G3 kritik ölçekleme faktörü f* (fider-başı) ──
def fig_g3_fstar():
    d = _load("g3_all.json")
    feeders = list(d.keys())
    short = [f.replace("1-LV-", "").replace("--1-sw", "") for f in feeders]
    fstar = [d[f]["critical_scaling_factor_fstar"]["voltage_rise_dV3pct"] for f in feeders]
    order = np.argsort(fstar)
    short = [short[i] for i in order]; fstar = [fstar[i] for i in order]
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    bars = ax.bar(short, fstar, color=[C_LEG if f <= 1.0 else C_GFP for f in fstar], width=0.6)
    ax.axhspan(1.2, 1.4, color=C_GRAY, alpha=0.25, label="real-world oversizing (1.2–1.4$\\times$)")
    ax.axhline(1.0, color="k", ls="--", lw=1.0, label="net-zero sizing")
    ax.axhline(1.56, color=C_GFP, ls=":", lw=1.0)
    ax.text(2.4, 1.63, "all feeders violate $\\leq 1.56\\times$", ha="center",
            fontsize=7, color=C_GFP)
    for b, f in zip(bars, fstar):
        ax.text(b.get_x()+b.get_width()/2, f+0.02, f"{f:.2f}", ha="center", fontsize=6.5)
    ax.set_ylabel("critical scaling factor $f^{*}_{\\Delta V}$ (net-zero=1)")
    ax.set_title("G3: no building-scale safety factor is simultaneously safe and non-forfeiting")
    ax.legend(loc="upper left", fontsize=6.5, frameon=False); ax.set_ylim(0, 1.9)
    _save(fig, "fig_g3_fstar")


# ── Fig 8 — G3 ΔV-vs-f eğrileri (fider-fider, %3 limit) ──
def fig_g3_curves():
    from experiments.gfp_benchmark.g3_cross_scale import (
        _fresh_net, _building_optimal, _base_vbus, _solve, LOAD_FACTOR, SLACK_DELIVERED, LV_CODES)
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    fs = np.linspace(0, 2.0, 21)
    for c, col in zip(LV_CODES, FEEDER_C):
        net = _fresh_net(c); bk, _ = _building_optimal(net)
        base = _base_vbus(c, LOAD_FACTOR, SLACK_DELIVERED)
        dvs = []
        for f in fs:
            r = _solve(c, {b: k*f for b, k in bk.items()}, LOAD_FACTOR, SLACK_DELIVERED, base)
            dvs.append(r.get("max_dv_pct") if r.get("converged") else np.nan)
        ax.plot(fs, dvs, color=col, lw=1.3, label=c.replace("1-LV-", "").replace("--1-sw", ""))
    ax.axhline(3.0, color="k", ls="--", lw=1.0)
    ax.text(0.05, 3.15, "$\\Delta V$ limit 3% (VDE-AR-N 4105)", fontsize=6.5)
    ax.axvline(1.0, color=C_GRAY, ls=":", lw=0.8)
    ax.text(1.02, 0.2, "net-zero", fontsize=6.5, color=C_GRAY)
    ax.set_xlabel("aggregate PV scaling factor $f$ (net-zero building-optimal $=1$)")
    ax.set_ylabel("max voltage rise $\\Delta V$ (%)")
    ax.set_title("G3: aggregate building-optimal PV vs slack-independent voltage rise")
    ax.legend(loc="upper left", fontsize=6.5, frameon=False, ncol=2)
    _save(fig, "fig_g3_curves")


# ── şematik yardımcıları ──
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def _box(ax, x, y, w, h, text, fc="#eef2f7", ec="#33475b", fs=7.5, bold=False, tc="k"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.0, edgecolor=ec, facecolor=fc, zorder=2))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs, zorder=3,
            fontweight="bold" if bold else "normal", color=tc)


def _arrow(ax, x1, y1, x2, y2, text="", c="#33475b", fs=6.5, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=10,
                                 lw=1.1, color=c, zorder=1))
    if text:
        ax.text((x1+x2)/2, (y1+y2)/2, text, ha="center", va="center", fontsize=fs,
                color=c, backgroundcolor="white", zorder=4)


# ── Fig 1 — sistem mimarisi + çok-paydaş/çok-ölçek DSS ──
def fig_architecture():
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.set_xlim(0, 12); ax.set_ylim(0, 10); ax.axis("off")
    W = 11.2; X0 = 0.4
    # katmanlar (tam-genişlik bantlar; aralarında oklar için boşluk)
    personas = [("Household", "building"), ("Commercial", "building"),
                ("Distribution", "feeder"), ("State", "policy")]
    for i, (p, s) in enumerate(personas):
        _box(ax, X0 + i*2.85, 8.7, 2.6, 0.95, f"{p}\n(scale: {s})", fc="#dbe7f3", fs=7.5)
    ax.text(6, 9.78, "Four stakeholder personas — same system, four scales",
            ha="center", fontsize=8, style="italic")
    _box(ax, X0, 6.55, W, 1.0, "LLM Orchestrator  —  agentic tool-calling",
         fc="#e8eef7", fs=9, bold=True)
    _box(ax, X0, 4.65, W, 1.0,
         "GROUNDING FIDELITY PROTOCOL — provenance + fail-closed guard",
         fc="#cfe3f0", ec=C_GFP, fs=8.5, bold=True, tc=C_GFP)
    tools = ["PV\n(PVGIS/pvlib)", "BESS\ndispatch", "Grid & hosting\n(SimBench/\npandapower)",
             "Economics\n(EPDK tariffs)"]
    for i, t in enumerate(tools):
        _box(ax, X0 + i*2.85, 2.35, 2.6, 1.3, t, fc="#eaf3ea", ec="#4a7a4a", fs=7)
    ax.text(6, 1.85, "Physics-based simulators (ground truth)", ha="center", fontsize=7.5,
            style="italic")
    # oklar: aşağı (query) SOLDA, yukarı (response) SAĞDA — etiketler boşlukta, kutu üstünde değil
    _arrow(ax, 4.2, 8.7, 4.2, 7.6)                       # personas -> LLM
    _arrow(ax, 4.2, 6.55, 4.2, 3.7)                      # LLM -> tools (query/tool-calls)
    ax.text(3.7, 8.15, "query", ha="right", fontsize=7, color="#33475b")
    ax.text(3.7, 4.15, "tool calls", ha="right", fontsize=7, color="#33475b")   # GFP-tools boşluğu
    _arrow(ax, 7.8, 3.7, 7.8, 6.5, c="#4a7a4a")          # tools -> LLM (results)
    ax.text(8.3, 4.15, "results", ha="left", fontsize=7, color="#4a7a4a")       # GFP-tools boşluğu
    _arrow(ax, 7.8, 6.55, 7.8, 8.65, c=C_GFP)            # LLM/GFP -> personas (grounded response)
    ax.text(8.3, 7.7, "grounded\nresponse", ha="left", fontsize=7, color=C_GFP)
    ax.text(6, 0.75, "The interactive interface (3D map studio, network editor) is a separate "
            "software contribution.", ha="center", fontsize=6.8, color="#666", style="italic")
    _save(fig, "fig_architecture")


# ── Fig 2 — GFP provenance şeması + fail-closed akış + worked example ──
def fig_gfp_schema():
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.set_xlim(0, 14); ax.set_ylim(0, 9.2); ax.axis("off")
    # sol: iddia + 5-alan provenance kaydı
    _box(ax, 0.4, 7.7, 6.0, 0.95, 'claim:  "NPV = 219,000 TL"', fc="#e8eef7", fs=9, bold=True)
    _box(ax, 0.4, 3.9, 6.0, 3.3, "", fc="#f7f4ea", ec="#a08a4a")
    ax.text(3.4, 6.85, "5-field provenance record", ha="center", fontsize=8, fontweight="bold")
    fields = ["function      = simulate_pv_bess", "parameters  = {city, panel_kw, ...}",
              "stakeholder = residential", "scale-validity = building", "timestamp    = 2026-04-04"]
    ax.text(0.75, 5.9, "\n".join(fields), ha="left", va="center", fontsize=7.5, family="monospace")
    _arrow(ax, 3.4, 7.7, 3.4, 7.25)
    # sağ: fail-closed akış
    _box(ax, 7.2, 7.7, 6.4, 0.95, "check claim vs. provenance graph", fc="#eef2f7", fs=8.5)
    _arrow(ax, 10.4, 7.7, 10.4, 6.85)
    ax.add_patch(FancyBboxPatch((9.4, 5.7), 2.0, 1.05, boxstyle="round,pad=0.02",
                 linewidth=1.0, edgecolor="#33475b", facecolor="#fff", zorder=2))
    ax.text(10.4, 6.22, "verifiable\nat this scale?", ha="center", va="center", fontsize=7.5, zorder=3)
    _box(ax, 6.8, 4.1, 2.9, 1.1, "GROUNDED\n(pass)", fc="#dff0d8", ec="#4a7a4a", fs=8.5, bold=True)
    _box(ax, 10.3, 4.1, 3.3, 1.1, "VIOLATION\nblock; deliver\nprovenance summary",
         fc="#f2dede", ec=C_LEG, fs=7.5, bold=True)
    _arrow(ax, 9.7, 5.7, 8.5, 5.25, "yes", c="#4a7a4a")
    _arrow(ax, 11.1, 5.7, 11.9, 5.25, "no", c=C_LEG)
    # alt: worked example (right number, wrong scale) — kısaltılmış, sığan
    _box(ax, 0.4, 0.5, 13.2, 2.9, "", fc="#f5f0fb", ec="#7570b3")
    ax.text(7.0, 2.95, 'Worked example — "right number, wrong scale"', ha="center",
            fontsize=8.5, fontweight="bold", color="#5b53a0")
    wex = ("The same value 219,000 TL is GROUNDED in a building-scale sentence,\n"
           "but a SCALE_VIOLATION in a feeder-scale sentence ('the neighbourhood total is 219,000 TL')\n"
           "— a failure a point-wise check, which only confirms the value matches the simulator, cannot see.")
    ax.text(7.0, 1.5, wex, ha="center", va="center", fontsize=7.8)
    _save(fig, "fig_gfp_schema")


def main():
    # NOT: şematikler (fig_architecture, fig_gfp_schema) artık TikZ (paper/figures/*.tex);
    # matplotlib sürümleri KULLANILMIYOR (main()'den çıkarıldı ki TikZ PDF'lerini ezmesin).
    # fig_taxonomy kaldırıldı: Ekim canlı taksonomisi (41 bayrak) makalede metin + tolerans tablosunda
    figs = [fig_g4_recall, fig_g4_roc, fig_g1_decomp, fig_g1_mcnemar,
            fig_g3_fstar, fig_g3_curves]
    for f in figs:
        try:
            f()
        except Exception as e:
            print(f"  ✗ {f.__name__}: {e!r}")
    print(f"figürler → {OUT}")


if __name__ == "__main__":
    main()
