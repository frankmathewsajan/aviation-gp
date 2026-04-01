"""
Schmidt-Appleman Criterion (SAC) Engine for GreenPath.
Implements physics-based contrail formation prediction (Schumann 1996).
"""
import numpy as np


def saturation_pressure_water(T_K: float) -> float:
    """
    Saturation vapor pressure over liquid water (Pa).
    Alduchov & Eskridge 1996 formula.
    T_K: temperature in Kelvin
    """
    T_C = T_K - 273.15
    return 610.94 * np.exp((17.625 * T_C) / (T_C + 243.04))


def saturation_pressure_ice(T_K: float) -> float:
    """
    Saturation vapor pressure over ice (Pa).
    Alduchov & Eskridge 1996 formula.
    T_K: temperature in Kelvin
    """
    T_C = T_K - 273.15
    return 611.21 * np.exp((22.587 * T_C) / (T_C + 273.86))


def compute_sac_threshold(
    pressure_hPa: float,
    aircraft_eta: float = 0.35,
    EI_H2O: float = 1.25,
    Q: float = 43e6,
    cp: float = 1004.0
) -> float:
    """
    Returns critical temperature T_crit in Kelvin below which contrails form.
    Uses: Schumann 1996 approximation.
    
    Parameters:
        pressure_hPa: ambient pressure in hPa
        aircraft_eta: overall propulsion efficiency
        EI_H2O: water vapor emission index (kg/kg fuel)
        Q: specific combustion heat of fuel (J/kg)
        cp: specific heat capacity of air at constant pressure (J/(kg·K))
    """
    epsilon = 0.6222
    G = (EI_H2O * cp * pressure_hPa * 100.0) / (epsilon * Q * (1.0 - aircraft_eta))
    
    if G <= 0.053:
        return 180.0  # contrails always form at extremely high altitude
    
    lnG = np.log(G - 0.053)
    T_crit = 226.69 + 9.43 * lnG + 0.720 * lnG ** 2
    return float(T_crit)


def check_contrail_formation(
    ambient_temp_K: float,
    rh_liquid_pct: float,
    pressure_hPa: float,
    aircraft_eta: float = 0.35
) -> dict:
    """
    Check if contrails form at a given atmospheric point.
    
    Returns dict with:
        - forms: bool — whether contrail forms
        - persistent: bool — whether contrail is persistent (ISSR zone)
        - rhi_pct: float — relative humidity over ice (%)
        - t_crit: float — critical temperature (K)
        - issr_intensity: float — ISSR intensity (max(0, RHi - 100))
    """
    T_crit = compute_sac_threshold(pressure_hPa, aircraft_eta)
    
    # Convert RH_liquid to RH_ice
    e_w = saturation_pressure_water(ambient_temp_K)
    e_i = saturation_pressure_ice(ambient_temp_K)
    
    if e_i > 0:
        rhi_pct = rh_liquid_pct * (e_w / e_i)
    else:
        rhi_pct = 0.0
    
    forms = (ambient_temp_K < T_crit) and (rhi_pct > 100.0)
    persistent = rhi_pct > 100.0  # ISSR zone
    issr_intensity = max(0.0, rhi_pct - 100.0)
    
    return {
        "forms": forms,
        "persistent": persistent,
        "rhi_pct": float(rhi_pct),
        "t_crit": float(T_crit),
        "issr_intensity": float(issr_intensity),
    }


def compute_contrail_grid(
    temp_grid: np.ndarray,
    rh_grid: np.ndarray,
    pressure_levels: list,
    aircraft_eta: float = 0.35
) -> dict:
    """
    Compute contrail formation and ISSR intensity for a 3D atmospheric grid.
    
    Parameters:
        temp_grid: 3D array [pressure_level, lat, lon] of temperature (K)
        rh_grid: 3D array [pressure_level, lat, lon] of relative humidity (%)
        pressure_levels: list of pressure levels (hPa)
        aircraft_eta: propulsion efficiency
    
    Returns dict with:
        - contrail_mask: 3D boolean array
        - issr_mask: 3D boolean array (persistent contrails)
        - issr_intensity: 3D float array
        - rhi_grid: 3D float array of RHi values
    """
    n_levels, n_lat, n_lon = temp_grid.shape
    
    contrail_mask = np.zeros_like(temp_grid, dtype=bool)
    issr_mask = np.zeros_like(temp_grid, dtype=bool)
    issr_intensity = np.zeros_like(temp_grid, dtype=float)
    rhi_grid = np.zeros_like(temp_grid, dtype=float)
    
    for k, p_hPa in enumerate(pressure_levels):
        T_crit = compute_sac_threshold(p_hPa, aircraft_eta)
        
        e_w = saturation_pressure_water(temp_grid[k])
        e_i = saturation_pressure_ice(temp_grid[k])
        
        safe_e_i = np.where(e_i > 0, e_i, 1.0)
        rhi = rh_grid[k] * (e_w / safe_e_i)
        rhi_grid[k] = rhi
        
        contrail_mask[k] = (temp_grid[k] < T_crit) & (rhi > 100.0)
        issr_mask[k] = rhi > 100.0
        issr_intensity[k] = np.maximum(0.0, rhi - 100.0)
    
    return {
        "contrail_mask": contrail_mask,
        "issr_mask": issr_mask,
        "issr_intensity": issr_intensity,
        "rhi_grid": rhi_grid,
    }
