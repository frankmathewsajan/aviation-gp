"""
Aircraft-specific fuel burn model for GreenPath.
Uses ICAO type designators (type ratings) for aircraft identification.
"""
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ICAO type designators (type ratings)
AIRCRAFT = {
    "A320": {"name": "Airbus A320-200", "cruise_speed_ms": 230, "fuel_flow_kgps": 0.85, "eta": 0.35, "ceiling_ft": 39000, "range_nm": 3300, "mtow_kg": 78000},
    "B738": {"name": "Boeing 737-800", "cruise_speed_ms": 225, "fuel_flow_kgps": 0.80, "eta": 0.34, "ceiling_ft": 41000, "range_nm": 3115, "mtow_kg": 79016},
    "B77W": {"name": "Boeing 777-300ER", "cruise_speed_ms": 255, "fuel_flow_kgps": 1.80, "eta": 0.37, "ceiling_ft": 43000, "range_nm": 7370, "mtow_kg": 351534},
    "A35K": {"name": "Airbus A350-1000", "cruise_speed_ms": 252, "fuel_flow_kgps": 1.50, "eta": 0.38, "ceiling_ft": 43000, "range_nm": 8700, "mtow_kg": 316000},
}

ALTITUDE_BANDS = [30000, 33000, 37000, 41000]  # feet

CO2_PER_KG_FUEL = 3.16  # kg CO₂ per kg jet fuel


def altitude_band_to_ft(band_index: int) -> int:
    """Convert altitude band index [0-3] to feet."""
    return ALTITUDE_BANDS[min(max(band_index, 0), len(ALTITUDE_BANDS) - 1)]


def altitude_band_to_pressure(band_index: int) -> float:
    """Convert altitude band index to approximate pressure in hPa."""
    alt_ft = altitude_band_to_ft(band_index)
    pressure_map = {30000: 300, 33000: 270, 37000: 220, 41000: 180}
    return pressure_map.get(alt_ft, 250)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute initial bearing from point 1 to point 2 in radians."""
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)
    dlon = lon2_r - lon1_r
    x = np.sin(dlon) * np.cos(lat2_r)
    y = np.cos(lat1_r) * np.sin(lat2_r) - np.sin(lat1_r) * np.cos(lat2_r) * np.cos(dlon)
    return np.arctan2(x, y)


def wind_component_along_track(
    u_wind: float, v_wind: float, bearing: float
) -> float:
    """
    Calculate wind component along the flight track direction.
    Positive = tailwind (helps), Negative = headwind (hinders).
    """
    wind_along = u_wind * np.sin(bearing) + v_wind * np.cos(bearing)
    return wind_along


def compute_segment_fuel(
    lat1: float, lon1: float, lat2: float, lon2: float,
    aircraft_type: str,
    u_wind: float = 0.0, v_wind: float = 0.0
) -> dict:
    """
    Compute fuel burn and CO₂ for a single flight segment.
    Returns dict with fuel_kg, co2_kg, time_s, distance_km, groundspeed_ms.
    """
    ac = AIRCRAFT[aircraft_type]
    distance_km = haversine_distance_km(lat1, lon1, lat2, lon2)
    distance_m = distance_km * 1000.0

    bearing = compute_bearing(lat1, lon1, lat2, lon2)
    wind_along = wind_component_along_track(u_wind, v_wind, bearing)

    groundspeed = ac["cruise_speed_ms"] + wind_along
    groundspeed = max(groundspeed, 50.0)  # safety floor

    time_s = distance_m / groundspeed
    fuel_kg = ac["fuel_flow_kgps"] * time_s
    co2_kg = fuel_kg * CO2_PER_KG_FUEL

    return {
        "fuel_kg": fuel_kg,
        "co2_kg": co2_kg,
        "time_s": time_s,
        "distance_km": distance_km,
        "groundspeed_ms": groundspeed,
    }


def compute_path_fuel(
    waypoints: list, aircraft_type: str,
    wind_grid: dict = None
) -> dict:
    """
    Compute total fuel burn and CO₂ for an entire path.
    """
    total_fuel = 0.0
    total_co2 = 0.0
    total_time = 0.0
    total_dist = 0.0
    segments = []

    for i in range(len(waypoints) - 1):
        lat1, lon1, alt1 = waypoints[i]
        lat2, lon2, alt2 = waypoints[i + 1]

        u_wind, v_wind = 0.0, 0.0
        if wind_grid is not None:
            mid_lat = (lat1 + lat2) / 2
            mid_lon = (lon1 + lon2) / 2
            mid_alt = (alt1 + alt2) / 2
            u_wind, v_wind = wind_grid.get(
                (round(mid_lat, 1), round(mid_lon, 1), int(mid_alt)),
                (0.0, 0.0)
            )

        seg = compute_segment_fuel(lat1, lon1, lat2, lon2, aircraft_type, u_wind, v_wind)
        segments.append(seg)
        total_fuel += seg["fuel_kg"]
        total_co2 += seg["co2_kg"]
        total_time += seg["time_s"]
        total_dist += seg["distance_km"]

    return {
        "total_fuel_kg": total_fuel,
        "total_co2_kg": total_co2,
        "total_time_s": total_time,
        "total_time_min": total_time / 60.0,
        "total_distance_km": total_dist,
        "segments": segments,
    }
