"""
Ice-Supersaturated Region (ISSR) Detector for GreenPath.
Uses Alduchov & Eskridge 1996 saturation vapor pressure formulas.
"""
import numpy as np
from sac_engine import saturation_pressure_water, saturation_pressure_ice


def rh_liquid_to_ice(rh_liquid_pct: float, temp_K: float) -> float:
    """
    Convert relative humidity over liquid water to relative humidity over ice.
    RHi = RH_liquid * (e_w / e_i)
    """
    e_w = saturation_pressure_water(temp_K)
    e_i = saturation_pressure_ice(temp_K)
    if e_i <= 0:
        return 0.0
    return rh_liquid_pct * (e_w / e_i)


def rh_liquid_to_ice_grid(rh_grid: np.ndarray, temp_grid: np.ndarray) -> np.ndarray:
    """
    Convert a grid of RH_liquid values to RH_ice.
    Both arrays should have the same shape.
    """
    e_w = saturation_pressure_water(temp_grid)
    e_i = saturation_pressure_ice(temp_grid)
    safe_e_i = np.where(e_i > 0, e_i, 1.0)
    return rh_grid * (e_w / safe_e_i)


def detect_issr(rh_ice_grid: np.ndarray) -> np.ndarray:
    """
    Detect ice-supersaturated regions.
    Returns a boolean 3D grid where True = ISSR (RHi > 100%).
    """
    return rh_ice_grid > 100.0


def compute_issr_intensity(rh_ice_grid: np.ndarray) -> np.ndarray:
    """
    Compute ISSR intensity as max(0, RHi - 100).
    Higher values = more intense super-saturation = more persistent contrails.
    """
    return np.maximum(0.0, rh_ice_grid - 100.0)


def get_issr_at_point(
    lat: float, lon: float, alt_band: int,
    atmo_data: dict
) -> float:
    """
    Get ISSR intensity at a specific (lat, lon, altitude_band) point.
    Uses nearest-neighbor interpolation on the atmospheric grid.
    
    Parameters:
        lat, lon: geographic coordinates
        alt_band: altitude band index [0-3]
        atmo_data: atmospheric data dict with keys:
            - lats: 1D array of latitudes
            - lons: 1D array of longitudes
            - issr_intensity: 3D array [level, lat, lon]
    
    Returns ISSR intensity value (0 if outside grid).
    """
    lats = atmo_data.get("lats")
    lons = atmo_data.get("lons")
    issr = atmo_data.get("issr_intensity")
    
    if lats is None or lons is None or issr is None:
        return 0.0
    
    lat_idx = np.argmin(np.abs(lats - lat))
    lon_idx = np.argmin(np.abs(lons - lon))
    
    level_idx = min(max(alt_band, 0), issr.shape[0] - 1)
    
    return float(issr[level_idx, lat_idx, lon_idx])


def get_wind_at_point(
    lat: float, lon: float, alt_band: int,
    atmo_data: dict
) -> tuple:
    """
    Get wind components (u, v) at a specific point.
    Uses nearest-neighbor interpolation.
    
    Returns (u_wind_ms, v_wind_ms) tuple.
    """
    lats = atmo_data.get("lats")
    lons = atmo_data.get("lons")
    u_grid = atmo_data.get("u_wind")
    v_grid = atmo_data.get("v_wind")
    
    if lats is None or lons is None or u_grid is None or v_grid is None:
        return (0.0, 0.0)
    
    lat_idx = np.argmin(np.abs(lats - lat))
    lon_idx = np.argmin(np.abs(lons - lon))
    level_idx = min(max(alt_band, 0), u_grid.shape[0] - 1)
    
    return (float(u_grid[level_idx, lat_idx, lon_idx]),
            float(v_grid[level_idx, lat_idx, lon_idx]))


def generate_atmosphere_sample(atmo_data: dict, n_points: int = 200) -> list:
    """
    Generate a sparse sample of atmosphere data for frontend heatmap visualization.
    Returns list of {lat, lon, issr_intensity} dicts.
    """
    lats = atmo_data.get("lats")
    lons = atmo_data.get("lons")
    issr = atmo_data.get("issr_intensity")
    
    if lats is None or lons is None or issr is None:
        return []
    
    # Use the level with highest ISSR (typically 200-300 hPa)
    max_issr = np.max(issr, axis=0)  # collapse pressure levels
    
    samples = []
    n_lat, n_lon = max_issr.shape
    
    # Sample at regular intervals
    lat_step = max(1, n_lat // int(np.sqrt(n_points)))
    lon_step = max(1, n_lon // int(np.sqrt(n_points)))
    
    for i in range(0, n_lat, lat_step):
        for j in range(0, n_lon, lon_step):
            intensity = float(max_issr[i, j])
            if intensity > 0.5:  # only include significant ISSR
                samples.append({
                    "lat": float(lats[i]),
                    "lon": float(lons[j]),
                    "issr_intensity": intensity,
                })
    
    return samples[:n_points]
