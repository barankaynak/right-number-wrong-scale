import pandapower as pp
import simbench as sb
import pandas as pd
import numpy as np
from typing import Optional

def create_distribution_network(region_id: str = "1-LV-rural1--1-sw") -> pp.pandapowerNet:
    """
    Creates a distribution network from SimBench benchmark grids.
    Default: rural low-voltage network similar to Turkish distribution grids.

    A23 (2026-10-14): the static SimBench base case is used. A former call to
    `sb.apply_const_controllers(net, 0)` raised in the installed simbench for every grid
    and was swallowed, so it never had any effect; it is removed rather than silenced.
    A SimBench loading failure now raises instead of silently substituting a synthetic
    radial network (no silent fallback on the benchmark tool path).
    """
    return sb.get_simbench_net(region_id)


def create_synthetic_radial_network() -> pp.pandapowerNet:
    """Small explicit radial LV network (NAYY 4x50 SE equivalent lines) for unit tests and
    demos. It is never substituted for SimBench automatically (A23: no silent fallback)."""
    net = pp.create_empty_network(f_hz=50.0, sn_mva=0.4)
    b0 = pp.create_bus(net, vn_kv=0.4, name="Slack")
    b1 = pp.create_bus(net, vn_kv=0.4, name="Bus 1")
    b2 = pp.create_bus(net, vn_kv=0.4, name="Bus 2")
    b3 = pp.create_bus(net, vn_kv=0.4, name="Bus 3")
    pp.create_ext_grid(net, bus=b0, vm_pu=1.0, name="Grid")
    # NAYY 4x50 SE equivalent: r=0.641 Ω/km, x=0.083 Ω/km, c=210 nF/km, imax=141 A
    lp = dict(r_ohm_per_km=0.641, x_ohm_per_km=0.083,
              c_nf_per_km=210, max_i_ka=0.141)
    pp.create_line_from_parameters(net, b0, b1, length_km=0.2, **lp)
    pp.create_line_from_parameters(net, b1, b2, length_km=0.2, **lp)
    pp.create_line_from_parameters(net, b2, b3, length_km=0.2, **lp)
    pp.create_load(net, bus=b1, p_mw=0.010, q_mvar=0.002)
    pp.create_load(net, bus=b2, p_mw=0.010, q_mvar=0.002)
    pp.create_load(net, bus=b3, p_mw=0.010, q_mvar=0.002)
    return net


def simulate_grid_impact(
    region_id: str = "1-LV-rural1--1-sw",
    pv_penetration_pct: float = 30.0,
    bess_penetration_pct: float = 0.0,
    load_growth_pct: float = 0.0
) -> dict:
    """
    Newton-Raphson load flow analysis for grid impact assessment.

    Returns grid impact metrics including voltage violations, line loading,
    transformer loading, losses, and reverse power flow indicators.
    """
    net = create_distribution_network(region_id)

    # Scale loads by load growth
    if load_growth_pct > 0:
        net.load['p_mw'] *= (1 + load_growth_pct / 100)
        net.load['q_mvar'] *= (1 + load_growth_pct / 100)

    # Get total load to scale PV and BESS
    total_load_mw = net.load['p_mw'].sum() if len(net.load) > 0 else 0.01

    # Add PV generators (distributed across load buses)
    pv_total_mw = total_load_mw * (pv_penetration_pct / 100)
    load_buses = net.load['bus'].unique() if len(net.load) > 0 else [net.bus.index[1]]

    pv_per_bus = pv_total_mw / len(load_buses)
    for bus in load_buses:
        pp.create_sgen(
            net, bus=bus,
            p_mw=pv_per_bus,
            q_mvar=0.0,
            name=f"PV_{bus}"
        )

    # Add BESS (modeled as negative load / storage)
    if bess_penetration_pct > 0:
        bess_total_mw = total_load_mw * (bess_penetration_pct / 100)
        bess_per_bus = bess_total_mw / len(load_buses)
        for bus in load_buses:
            # During peak PV: BESS absorbs excess (acts as load, positive = charging)
            pp.create_storage(
                net, bus=bus,
                p_mw=bess_per_bus,   # positive = charging (consuming power from grid/PV)
                max_e_mwh=bess_per_bus * 2,
                name=f"BESS_{bus}"
            )

    # Run load flow
    try:
        try:
            pp.runpp(net, algorithm='nr', numba=True, tolerance_mva=1e-6)
        except Exception:
            pp.runpp(net, algorithm='nr', numba=False, tolerance_mva=1e-6)
        converged = net['converged']
    except Exception:
        converged = False

    if not converged:
        return {
            "converged": False,
            "error": "Load flow did not converge",
            "pv_penetration_pct": pv_penetration_pct,
            "bess_penetration_pct": bess_penetration_pct,
        }

    # Extract results
    bus_voltages = net.res_bus['vm_pu']
    max_voltage = float(bus_voltages.max())
    min_voltage = float(bus_voltages.min())
    voltage_violation = bool(max_voltage > 1.05 or min_voltage < 0.95)

    line_loading = net.res_line['loading_percent'] if len(net.res_line) > 0 else pd.Series([0])
    max_line_loading = float(line_loading.max()) if len(line_loading) > 0 else 0.0
    line_overload = bool(max_line_loading > 100)

    trafo_loading = net.res_trafo['loading_percent'] if len(net.res_trafo) > 0 else pd.Series([0])
    trafo_loading_pct = float(trafo_loading.max()) if len(trafo_loading) > 0 else 0.0
    trafo_overload = bool(trafo_loading_pct > 100)

    total_losses_mw = float(net.res_line['pl_mw'].sum()) if len(net.res_line) > 0 else 0.0

    # Reverse power flow: ext_grid absorbing power (negative p_mw means grid exporting)
    ext_grid_p = net.res_ext_grid['p_mw'].sum() if len(net.res_ext_grid) > 0 else 0.0
    reverse_power_flow = bool(ext_grid_p < 0)

    return {
        "converged": True,
        "pv_penetration_pct": pv_penetration_pct,
        "bess_penetration_pct": bess_penetration_pct,
        "max_voltage_pu": round(max_voltage, 4),
        "min_voltage_pu": round(min_voltage, 4),
        "voltage_violation": voltage_violation,
        "max_line_loading_pct": round(max_line_loading, 2),
        "line_overload": line_overload,
        "trafo_loading_pct": round(trafo_loading_pct, 2),
        "trafo_overload": trafo_overload,
        "total_losses_mw": round(total_losses_mw, 6),
        "reverse_power_flow": reverse_power_flow,
    }


def run_penetration_analysis(
    region_id: str = "1-LV-rural1--1-sw",
    levels: list = None
) -> pd.DataFrame:
    """
    Hosting capacity analysis: runs load flow for PV penetration levels 0-100%.
    Returns DataFrame with grid metrics at each penetration level.
    Hosting capacity = first penetration level where voltage limit (1.05 pu) is exceeded.
    """
    if levels is None:
        levels = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    results = []
    for pct in levels:
        impact = simulate_grid_impact(region_id, pv_penetration_pct=float(pct))
        results.append({
            "pv_penetration_pct": pct,
            "converged": impact.get("converged", False),
            "max_voltage_pu": impact.get("max_voltage_pu", None),
            "min_voltage_pu": impact.get("min_voltage_pu", None),
            "voltage_violation": impact.get("voltage_violation", None),
            "max_line_loading_pct": impact.get("max_line_loading_pct", None),
            "total_losses_mw": impact.get("total_losses_mw", None),
            "reverse_power_flow": impact.get("reverse_power_flow", None),
        })

    df = pd.DataFrame(results)

    # Hosting capacity: first level with voltage violation
    violation_levels = df[df["voltage_violation"] == True]["pv_penetration_pct"]
    hosting_capacity_pct = float(violation_levels.min()) if len(violation_levels) > 0 else 100.0

    df.attrs["hosting_capacity_pct"] = hosting_capacity_pct
    return df


def simulate_transformer_deferral(
    region_id: str = "1-LV-rural1--1-sw",
    pv_penetration_pct: float = 30.0,
    bess_penetration_pct: float = 20.0,
    years: int = 10,
    annual_load_growth_pct: float = 3.0
) -> dict:
    """
    Calculates how many years DER investment can defer transformer upgrade.

    Without DER: transformer overloads when load growth exceeds capacity.
    With DER: peak shaving from BESS reduces effective peak load, delaying overload.

    Returns: deferral years, annual savings from deferred investment.
    """
    # Find when transformer overloads WITHOUT DER
    years_without_der = None
    for year in range(1, years + 1):
        impact = simulate_grid_impact(
            region_id,
            pv_penetration_pct=0,
            bess_penetration_pct=0,
            load_growth_pct=annual_load_growth_pct * year
        )
        if impact.get("trafo_overload") or impact.get("voltage_violation"):
            years_without_der = year
            break

    # Find when transformer overloads WITH DER
    years_with_der = None
    for year in range(1, years + 1):
        impact = simulate_grid_impact(
            region_id,
            pv_penetration_pct=pv_penetration_pct,
            bess_penetration_pct=bess_penetration_pct,
            load_growth_pct=annual_load_growth_pct * year
        )
        if impact.get("trafo_overload") or impact.get("voltage_violation"):
            years_with_der = year
            break

    # Assume transformer upgrade cost ~500,000 TL (400 kVA typical LV trafo)
    trafo_upgrade_cost_tl = 500_000
    discount_rate = 0.12

    deferral_years = 0
    npv_deferral_benefit_tl = 0.0

    if years_without_der is not None:
        years_with = years_with_der if years_with_der is not None else years
        deferral_years = max(0, years_with - years_without_der)
        # NPV benefit: delayed cost
        if deferral_years > 0:
            npv_deferral_benefit_tl = trafo_upgrade_cost_tl * (
                1 / (1 + discount_rate) ** years_without_der -
                1 / (1 + discount_rate) ** years_with
            )

    return {
        "years_without_der": years_without_der,
        "years_with_der": years_with_der,
        "deferral_years": deferral_years,
        "trafo_upgrade_cost_tl": trafo_upgrade_cost_tl,
        "npv_deferral_benefit_tl": round(npv_deferral_benefit_tl, 2),
        "annual_load_growth_pct": annual_load_growth_pct,
        "pv_penetration_pct": pv_penetration_pct,
        "bess_penetration_pct": bess_penetration_pct,
    }
