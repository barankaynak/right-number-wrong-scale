import numpy as np
import pytest
from app.simulation.bess.battery_model import BatteryModel
from app.simulation.pv.solar_model import simulate_pv_production
from app.simulation.pv.load_profile import generate_load_profile

def test_battery_model_soc_bounds():
    # 10 kWh battery, 10 kW PV, 5MWh Load
    battery = BatteryModel(capacity_kwh=10.0, min_soc=0.1, max_soc=1.0)
    pv_profile = simulate_pv_production(39.93, 32.86, 10.0, 30.0, 180.0)  # önbellekli Ankara (A23)
    load_profile = generate_load_profile('residential', 5000.0)
    
    res = battery.dispatch_self_consumption(pv_profile, load_profile)
    
    soc_series = res['soc']
    
    # Check if SoC stayed within 0 to 100% bounds
    assert soc_series.min() >= 0.099  # float precision tolerance
    assert soc_series.max() <= 1.001

def test_round_trip_efficiency():
    # Test charging efficiency: charge 10 kW for 1 hour -> energy in battery = 10 * sqrt(0.9)
    battery = BatteryModel(capacity_kwh=20.0, min_soc=0.0, max_soc=1.0, round_trip_efficiency=0.90)
    battery.current_soc = 0.0  # Start empty
    
    # PV = 10 kW for 1 hour, Load = 0 -> charge
    pv = np.array([10.0])
    load = np.array([0.0])
    res1 = battery.dispatch_self_consumption(pv, load)
    
    # Energy stored = 10 * eta_charge = 10 * sqrt(0.9) ≈ 9.487 kWh
    eta_charge = np.sqrt(0.9)
    stored_kwh = res1['soc'][0] * 20.0
    assert abs(stored_kwh - 10.0 * eta_charge) < 0.05, f"Stored energy mismatch: {stored_kwh}"
    
    # Now discharge: battery has stored_kwh, load > pv, battery provides stored_kwh * eta_discharge
    pv2 = np.array([0.0])
    load2 = np.array([stored_kwh * 2])  # Ask for more than available
    res2 = battery.dispatch_self_consumption(pv2, load2)
    
    eta_discharge = np.sqrt(0.9)
    energy_delivered = stored_kwh * eta_discharge  # ≈ 9.0 kWh
    expected_grid_import = load2[0] - energy_delivered
    assert abs(res2['grid_import_kwh'][0] - expected_grid_import) < 0.05

def test_self_consumption_improvement():
    # PV = Load = randomish
    pv_profile = np.array([5.0, 0.0, 5.0, 0.0])
    load_profile = np.array([0.0, 5.0, 0.0, 5.0])
    
    # Without BESS (Using fake 0 capacity battery to calculate)
    battery_none = BatteryModel(capacity_kwh=0.0)
    res_none = battery_none.dispatch_self_consumption(pv_profile, load_profile)
    sc_ratio_none = res_none['self_consumption_ratio']
    
    # With BESS
    battery_10kwh = BatteryModel(capacity_kwh=10.0)
    res_10kwh = battery_10kwh.dispatch_self_consumption(pv_profile, load_profile)
    sc_ratio_bess = res_10kwh['self_consumption_ratio']
    
    assert sc_ratio_bess > sc_ratio_none
