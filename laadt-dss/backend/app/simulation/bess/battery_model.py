import numpy as np
import pandas as pd

class BatteryModel:
    def __init__(
        self,
        capacity_kwh: float,
        chemistry: str = 'LFP',
        round_trip_efficiency: float = 0.90,
        min_soc: float = 0.10,
        max_soc: float = 1.00,
        max_charge_crate: float = 0.5,
        max_discharge_crate: float = 0.5
    ):
        self.capacity_kwh = capacity_kwh
        self.chemistry = chemistry
        self.round_trip_efficiency = round_trip_efficiency
        # charging and discharging efficiencies (assumed equal roots of round-trip)
        self.eta_charge = np.sqrt(round_trip_efficiency)
        self.eta_discharge = np.sqrt(round_trip_efficiency)
        
        self.min_soc = min_soc
        self.max_soc = max_soc
        self.max_charge_kw = capacity_kwh * max_charge_crate
        self.max_discharge_kw = capacity_kwh * max_discharge_crate
        
        # State variables
        self.current_soc = min_soc
        self.cycles = 0.0

    def calculate_simple_degradation(self, full_cycles: float, years: int = 1) -> float:
        """
        Phase 1 simple degradation calculation.
        """
        # Roughly estimated values for LFP
        if self.chemistry == 'LFP':
            calendar_loss = 0.02 * years
            cyclic_loss = full_cycles * 0.0001
        elif self.chemistry == 'NMC':
            calendar_loss = 0.03 * years
            cyclic_loss = full_cycles * 0.0002
        else:
            calendar_loss = 0.02 * years
            cyclic_loss = full_cycles * 0.00015
            
        total_loss = calendar_loss + cyclic_loss
        return max(0.0, 1.0 - total_loss) 

    def dispatch_self_consumption(
        self,
        pv_profile_kw: np.ndarray,
        load_profile_kw: np.ndarray
    ) -> dict:
        """
        Runs an hourly dispatch simulation for 8760 hours using self-consumption logic.
        """
        length = len(pv_profile_kw)
        
        soc_series = np.zeros(length)
        charge_series = np.zeros(length)
        discharge_series = np.zeros(length)
        grid_import = np.zeros(length)
        grid_export = np.zeros(length)
        
        energy_content_kwh = self.capacity_kwh * self.current_soc
        min_energy = self.capacity_kwh * self.min_soc
        max_energy = self.capacity_kwh * self.max_soc
        
        total_discharge_kwh = 0.0
        
        for i in range(length):
            pv = pv_profile_kw[i]
            load = load_profile_kw[i]
            
            net_load = load - pv
            
            if net_load > 0:
                # We need energy from battery or grid (Discharge)
                required_from_batt = net_load / self.eta_discharge
                available_for_discharge = min(
                    self.max_discharge_kw, # Max power
                    energy_content_kwh - min_energy # Max energy
                )
                
                discharge_kw = min(required_from_batt, available_for_discharge)
                
                charge_series[i] = 0.0
                discharge_series[i] = discharge_kw
                energy_content_kwh -= discharge_kw
                total_discharge_kwh += discharge_kw
                
                # Remaining load goes to grid
                grid_import[i] = net_load - (discharge_kw * self.eta_discharge)
                grid_export[i] = 0.0
                
            else:
                # We have excess PV energy (Charge)
                excess_pv = -net_load
                available_for_charge = min(
                    self.max_charge_kw,
                    (max_energy - energy_content_kwh) / self.eta_charge
                )
                
                charge_kw = min(excess_pv, available_for_charge)
                
                charge_series[i] = charge_kw
                discharge_series[i] = 0.0
                energy_content_kwh += charge_kw * self.eta_charge
                
                # Remaining PV goes to grid export
                grid_export[i] = excess_pv - charge_kw
                grid_import[i] = 0.0
                
            soc_series[i] = energy_content_kwh / self.capacity_kwh if self.capacity_kwh > 0 else 0.0
            
        self.cycles = total_discharge_kwh / self.capacity_kwh if self.capacity_kwh > 0 else 0.0
        self.current_soc = energy_content_kwh / self.capacity_kwh if self.capacity_kwh > 0 else 0.0

        # Metrics 
        # Self consumption ratio
        total_pv = pv_profile_kw.sum()
        pv_to_grid = grid_export.sum()
        self_consumption_ratio = (total_pv - pv_to_grid) / total_pv if total_pv > 0 else 0
        
        return {
            "soc": soc_series,
            "charge_kw": charge_series,
            "discharge_kw": discharge_series,
            "grid_import_kwh": grid_import,
            "grid_export_kwh": grid_export,
            "total_cycles": self.cycles,
            "self_consumption_ratio": self_consumption_ratio
        }
