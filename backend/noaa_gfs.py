"""
NOAA GFS atmospheric data integration for GreenPath.
Fetches real GFS data via NOMADS GRIB Filter, OPeNDAP, or AWS S3.
Falls back to synthetic atmosphere when all sources fail.

Data sources (in priority order):
  1. NOMADS GRIB Filter — most reliable, subsets via HTTP
  2. NOMADS OPeNDAP — direct xarray access
  3. AWS S3 (noaa-gfs-bdp-pds) — cloud-hosted GRIB2 files
  4. Synthetic fallback — US Standard Atmosphere with ISSR patches
"""
import numpy as np
from datetime import datetime, timedelta
import hashlib
import os
import logging
import time as _time
import struct
import io

logger = logging.getLogger(__name__)

PRESSURE_LEVELS = [200, 250, 300, 350, 400, 450, 500]  # hPa

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".gfs_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(date_str: str, hour: int, bbox: tuple) -> str:
    """Generate cache key for GFS data."""
    raw = f"{date_str}_{hour}_{bbox}"
    return hashlib.md5(raw.encode()).hexdigest()


def _check_cache(key: str) -> dict:
    """Check if cached data exists."""
    path = os.path.join(CACHE_DIR, f"{key}.npz")
    if os.path.exists(path):
        try:
            data = np.load(path, allow_pickle=True)
            logger.info(f"[GFS] Cache HIT: {key[:8]}...")
            return {k: data[k] for k in data.files}
        except Exception:
            return None
    return None


def _save_cache(key: str, data: dict):
    """Save data to cache."""
    path = os.path.join(CACHE_DIR, f"{key}.npz")
    try:
        np.savez_compressed(path, **data)
        logger.info(f"[GFS] Cached data: {key[:8]}...")
    except Exception as e:
        logger.warning(f"[GFS] Failed to save cache: {e}")


def fetch_gfs_data(
    origin_lat: float, origin_lon: float,
    dest_lat: float, dest_lon: float,
    departure_time: datetime,
    use_noaa: bool = True
) -> dict:
    """
    Fetch atmospheric data for the flight corridor.
    Tries multiple NOAA sources, falls back to synthetic.
    """
    logger.info(f"[GFS] Fetching atmosphere for ({origin_lat:.1f},{origin_lon:.1f}) → ({dest_lat:.1f},{dest_lon:.1f})")
    logger.info(f"[GFS] Departure: {departure_time.isoformat()}, NOAA enabled: {use_noaa}")

    # Compute bounding box
    min_lat = min(origin_lat, dest_lat) - 15.0
    max_lat = max(origin_lat, dest_lat) + 15.0
    min_lon = min(origin_lon, dest_lon) - 15.0
    max_lon = max(origin_lon, dest_lon) + 15.0

    min_lat = max(min_lat, -90)
    max_lat = min(max_lat, 90)
    min_lon = max(min_lon, -180)
    max_lon = min(max_lon, 180)

    bbox = (min_lat, max_lat, min_lon, max_lon)
    date_str = departure_time.strftime("%Y%m%d")
    hour = (departure_time.hour // 6) * 6

    # Check cache
    key = _cache_key(date_str, hour, bbox)
    cached = _check_cache(key)
    if cached:
        source = str(cached.get("source", ["cached"])[0])
        logger.info(f"[GFS] Using cached data (source: {source})")
        return {k: v for k, v in cached.items()}

    # Try NOAA GFS if enabled
    if use_noaa:
        # Method 1: NOMADS GRIB Filter (most reliable)
        logger.info("[GFS] Attempting NOAA NOMADS GRIB Filter fetch...")
        start_t = _time.time()
        try:
            data = _fetch_nomads_filter(date_str, hour, bbox)
            if data is not None:
                elapsed = _time.time() - start_t
                logger.info(f"[GFS] ✓ NOMADS GRIB Filter data fetched in {elapsed:.1f}s")
                _save_cache(key, data)
                return data
        except Exception as e:
            elapsed = _time.time() - start_t
            logger.warning(f"[GFS] ✗ NOMADS GRIB Filter failed in {elapsed:.1f}s: {e}")

        # Method 2: OPeNDAP
        logger.info("[GFS] Attempting NOAA GFS OPeNDAP fetch...")
        start_t = _time.time()
        try:
            data = _fetch_noaa_gfs(date_str, hour, bbox)
            if data is not None:
                elapsed = _time.time() - start_t
                logger.info(f"[GFS] ✓ NOAA GFS OPeNDAP data fetched in {elapsed:.1f}s")
                _save_cache(key, data)
                return data
        except Exception as e:
            elapsed = _time.time() - start_t
            logger.warning(f"[GFS] ✗ NOAA GFS OPeNDAP failed in {elapsed:.1f}s: {e}")

        # Method 3: AWS S3 cloud access
        logger.info("[GFS] Attempting AWS S3 cloud fetch...")
        start_t = _time.time()
        try:
            data = _fetch_aws_s3(date_str, hour, bbox)
            if data is not None:
                elapsed = _time.time() - start_t
                logger.info(f"[GFS] ✓ AWS S3 data fetched in {elapsed:.1f}s")
                _save_cache(key, data)
                return data
        except Exception as e:
            elapsed = _time.time() - start_t
            logger.warning(f"[GFS] ✗ AWS S3 fetch failed in {elapsed:.1f}s: {e}")
    else:
        logger.info("[GFS] NOAA disabled by user, using synthetic data")

    # Fall back to synthetic
    logger.info("[GFS] All NOAA sources failed. Generating synthetic atmospheric data...")
    data = generate_synthetic_atmosphere(
        origin_lat, origin_lon, dest_lat, dest_lon, departure_time
    )
    logger.info("[GFS] ✓ Synthetic data generated")
    return data


def _fetch_nomads_filter(date_str: str, hour: int, bbox: tuple) -> dict:
    """
    Fetch GFS data via NOMADS GRIB Filter service.
    This is NOAA's recommended approach (replacing deprecated OPeNDAP).
    Downloads a small subset of variables/levels/region as GRIB2.
    """
    try:
        import requests
    except ImportError:
        logger.warning("[GFS] requests not installed")
        return None

    min_lat, max_lat, min_lon, max_lon = bbox

    # Variables we need for contrail detection
    variables = ["TMP", "RH", "UGRD", "VGRD"]
    # Pressure levels for upper atmosphere (flight levels)
    levels = ["200_mb", "250_mb", "300_mb", "350_mb", "400_mb", "450_mb", "500_mb"]

    for day_offset in [0, -1, -2]:
        try:
            from datetime import datetime as dt
            base_date = dt.strptime(date_str, "%Y%m%d") + timedelta(days=day_offset)
            attempt_date = base_date.strftime("%Y%m%d")

            file_name = f"gfs.t{hour:02d}z.pgrb2.0p25.f000"
            dir_path = f"%2Fgfs.{attempt_date}%2F{hour:02d}%2Fatmos"

            # Build URL with parameters
            url = f"https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?"
            url += f"file={file_name}"
            for lev in levels:
                url += f"&lev_{lev}=on"
            for var in variables:
                url += f"&var_{var}=on"
            url += f"&subregion="
            url += f"&leftlon={min_lon}"
            url += f"&rightlon={max_lon}"
            url += f"&toplat={max_lat}"
            url += f"&bottomlat={min_lat}"
            url += f"&dir={dir_path}"

            logger.info(f"[GFS] NOMADS Filter: attempting {attempt_date}/{hour:02d}z")

            resp = requests.get(url, timeout=45)
            if resp.status_code != 200:
                logger.info(f"[GFS] NOMADS Filter: HTTP {resp.status_code} for {attempt_date}")
                continue

            if len(resp.content) < 500:
                logger.info(f"[GFS] NOMADS Filter: response too small ({len(resp.content)} bytes)")
                continue

            # Try to parse with cfgrib via xarray
            data = _parse_grib_response(resp.content, bbox, attempt_date, hour)
            if data is not None:
                return data

        except Exception as e:
            logger.info(f"[GFS] NOMADS Filter attempt for offset {day_offset} failed: {e}")
            continue

    return None


def _parse_grib_response(content: bytes, bbox: tuple, date_str: str, hour: int) -> dict:
    """Parse GRIB2 response using cfgrib/xarray or manual extraction."""
    min_lat, max_lat, min_lon, max_lon = bbox

    # Try cfgrib first
    try:
        import xarray as xr
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.grib2', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Open all datasets from GRIB (different variables may be in different messages)
            datasets = xr.open_datasets(tmp_path, engine='cfgrib',
                                        backend_kwargs={'indexpath': ''})
            
            if not datasets:
                datasets = [xr.open_dataset(tmp_path, engine='cfgrib',
                                            backend_kwargs={'indexpath': ''})]

            # Merge all datasets
            ds = xr.merge(datasets, compat='override')

            lats = ds.latitude.values
            lons = ds.longitude.values
            # Convert 0-360 to -180..180
            lons = np.where(lons > 180, lons - 360, lons)

            temp_data = []
            rh_data = []
            u_data = []
            v_data = []

            # Detect variable names (GFS uses various naming)
            temp_var = None
            for name in ['t', 'TMP', 'tmp', 'temperature']:
                if name in ds:
                    temp_var = name
                    break

            rh_var = None
            for name in ['r', 'RH', 'rh', 'relative_humidity']:
                if name in ds:
                    rh_var = name
                    break

            u_var = None
            for name in ['u', 'UGRD', 'ugrd', 'u-component_of_wind']:
                if name in ds:
                    u_var = name
                    break

            v_var = None
            for name in ['v', 'VGRD', 'vgrd', 'v-component_of_wind']:
                if name in ds:
                    v_var = name
                    break

            if not all([temp_var, rh_var, u_var, v_var]):
                logger.warning(f"[GFS] Missing variables in GRIB: available={list(ds.data_vars)}")
                return None

            # Check for pressure level dimension
            level_dim = None
            for dim in ['isobaricInhPa', 'level', 'lev', 'pressure']:
                if dim in ds.dims or dim in ds.coords:
                    level_dim = dim
                    break

            for p_level in PRESSURE_LEVELS:
                if level_dim:
                    level_data = ds.sel({level_dim: p_level}, method='nearest')
                else:
                    level_data = ds

                temp_data.append(level_data[temp_var].values)
                rh_data.append(level_data[rh_var].values)
                u_data.append(level_data[u_var].values)
                v_data.append(level_data[v_var].values)

            ds.close()

            from sac_engine import saturation_pressure_water, saturation_pressure_ice

            temp_arr = np.array(temp_data)
            rh_arr = np.array(rh_data)

            e_w = saturation_pressure_water(temp_arr)
            e_i = saturation_pressure_ice(temp_arr)
            safe_e_i = np.where(e_i > 0, e_i, 1.0)
            rhi = rh_arr * (e_w / safe_e_i)
            issr_intensity = np.maximum(0.0, rhi - 100.0)

            logger.info(f"[GFS] GRIB parsed: temp={temp_arr.shape}, ISSR max={issr_intensity.max():.1f}")

            return {
                "lats": lats,
                "lons": lons,
                "pressure_levels": np.array(PRESSURE_LEVELS),
                "temperature": temp_arr,
                "rh": rh_arr,
                "u_wind": np.array(u_data),
                "v_wind": np.array(v_data),
                "issr_intensity": issr_intensity,
                "source": np.array(["noaa_live"]),
                "timestamp": np.array([f"{date_str}T{hour:02d}:00:00Z"]),
            }
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except ImportError:
        logger.info("[GFS] cfgrib not available, skipping GRIB parse")
    except Exception as e:
        logger.warning(f"[GFS] GRIB parse failed: {e}")

    return None


def _fetch_noaa_gfs(date_str: str, hour: int, bbox: tuple) -> dict:
    """
    Attempt to fetch real GFS data from NOAA OPeNDAP server.
    """
    try:
        import xarray as xr
    except ImportError:
        logger.warning("[GFS] xarray not installed — cannot use OPeNDAP")
        return None

    # Try today and yesterday (GFS may take hours to publish)
    for day_offset in [0, -1, -2]:
        try:
            from datetime import datetime as dt
            base_date = dt.strptime(date_str, "%Y%m%d") + timedelta(days=day_offset)
            attempt_date = base_date.strftime("%Y%m%d")

            url = f"https://nomads.ncep.noaa.gov/dods/gfs_0p25/gfs{attempt_date}/gfs_0p25_{hour:02d}z"
            logger.info(f"[GFS] Trying OPeNDAP: {url}")

            min_lat, max_lat, min_lon, max_lon = bbox

            # OPeNDAP uses 0-360 longitude
            olon_min = min_lon + 360 if min_lon < 0 else min_lon
            olon_max = max_lon + 360 if max_lon < 0 else max_lon

            ds = xr.open_dataset(url, engine='pydap', timeout=30)

            ds_sub = ds.sel(
                lat=slice(min_lat, max_lat),
                lon=slice(olon_min, olon_max),
                time=ds.time[0]
            )

            lats = ds_sub.lat.values
            lons = ds_sub.lon.values
            lons = np.where(lons > 180, lons - 360, lons)

            temp_data = []
            rh_data = []
            u_data = []
            v_data = []

            # Detect variable names
            temp_var = 'tmpprs' if 'tmpprs' in ds_sub else 'tmp'
            rh_var = 'rhprs' if 'rhprs' in ds_sub else 'rh'
            u_var = 'ugrdprs' if 'ugrdprs' in ds_sub else 'ugrd'
            v_var = 'vgrdprs' if 'vgrdprs' in ds_sub else 'vgrd'

            for p_level in PRESSURE_LEVELS:
                level_sel = ds_sub.sel(lev=p_level, method='nearest')
                temp_data.append(level_sel[temp_var].values)
                rh_data.append(level_sel[rh_var].values)
                u_data.append(level_sel[u_var].values)
                v_data.append(level_sel[v_var].values)

            ds.close()

            from sac_engine import saturation_pressure_water, saturation_pressure_ice

            temp_arr = np.array(temp_data)
            rh_arr = np.array(rh_data)

            e_w = saturation_pressure_water(temp_arr)
            e_i = saturation_pressure_ice(temp_arr)
            safe_e_i = np.where(e_i > 0, e_i, 1.0)
            rhi = rh_arr * (e_w / safe_e_i)
            issr_intensity = np.maximum(0.0, rhi - 100.0)

            logger.info(f"[GFS] NOAA data shape: temp={temp_arr.shape}, ISSR max={issr_intensity.max():.1f}")

            return {
                "lats": lats,
                "lons": lons,
                "pressure_levels": np.array(PRESSURE_LEVELS),
                "temperature": temp_arr,
                "rh": rh_arr,
                "u_wind": np.array(u_data),
                "v_wind": np.array(v_data),
                "issr_intensity": issr_intensity,
                "source": np.array(["noaa_live"]),
                "timestamp": np.array([f"{attempt_date}T{hour:02d}:00:00Z"]),
            }
        except Exception as e:
            logger.info(f"[GFS] OPeNDAP attempt for offset {day_offset} failed: {e}")
            continue

    return None


def _fetch_aws_s3(date_str: str, hour: int, bbox: tuple) -> dict:
    """
    Fetch GFS data from AWS S3 public bucket (noaa-gfs-bdp-pds).
    No AWS credentials required — bucket is publicly accessible.
    """
    try:
        import requests
    except ImportError:
        return None

    min_lat, max_lat, min_lon, max_lon = bbox

    for day_offset in [0, -1, -2]:
        try:
            from datetime import datetime as dt
            base_date = dt.strptime(date_str, "%Y%m%d") + timedelta(days=day_offset)
            attempt_date = base_date.strftime("%Y%m%d")

            # AWS S3 public URL pattern
            s3_url = (
                f"https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
                f"gfs.{attempt_date}/{hour:02d}/atmos/"
                f"gfs.t{hour:02d}z.pgrb2.0p25.f000"
            )

            logger.info(f"[GFS] AWS S3: checking {attempt_date}/{hour:02d}z")

            # Do a HEAD request first to check if file exists
            head_resp = requests.head(s3_url, timeout=10)
            if head_resp.status_code != 200:
                logger.info(f"[GFS] AWS S3: file not found for {attempt_date}/{hour:02d}z (HTTP {head_resp.status_code})")
                continue

            file_size = int(head_resp.headers.get('content-length', 0))
            logger.info(f"[GFS] AWS S3: file exists ({file_size / 1024 / 1024:.1f} MB)")

            # The full file is large (300+ MB). We can't download it all.
            # Use range requests if supported, otherwise skip to cfgrib with Herbie
            # For now, try using the Herbie library if available
            try:
                from herbie import Herbie
                h = Herbie(
                    f"{attempt_date[:4]}-{attempt_date[4:6]}-{attempt_date[6:8]} {hour:02d}:00",
                    model="gfs",
                    product="pgrb2.0p25",
                    fxx=0,
                    verbose=False,
                )

                import xarray as xr

                # Download temperature and RH for our levels
                ds_t = h.xarray(":TMP:", remove_grib=False)
                ds_rh = h.xarray(":RH:", remove_grib=False)
                ds_u = h.xarray(":UGRD:", remove_grib=False)
                ds_v = h.xarray(":VGRD:", remove_grib=False)

                # Subset to bbox
                lat_mask = (ds_t.latitude >= min_lat) & (ds_t.latitude <= max_lat)
                lon_mask = (ds_t.longitude >= min_lon) & (ds_t.longitude <= max_lon)

                ds_t_sub = ds_t.where(lat_mask & lon_mask, drop=True)

                lats = ds_t_sub.latitude.values
                lons = ds_t_sub.longitude.values
                lons = np.where(lons > 180, lons - 360, lons)

                temp_data = []
                rh_data = []
                u_data = []
                v_data = []

                for p_level in PRESSURE_LEVELS:
                    temp_data.append(ds_t_sub.sel(isobaricInhPa=p_level, method='nearest')['t'].values)
                    rh_data.append(ds_rh.where(lat_mask & lon_mask, drop=True).sel(isobaricInhPa=p_level, method='nearest')['r'].values)
                    u_data.append(ds_u.where(lat_mask & lon_mask, drop=True).sel(isobaricInhPa=p_level, method='nearest')['u'].values)
                    v_data.append(ds_v.where(lat_mask & lon_mask, drop=True).sel(isobaricInhPa=p_level, method='nearest')['v'].values)

                from sac_engine import saturation_pressure_water, saturation_pressure_ice

                temp_arr = np.array(temp_data)
                rh_arr = np.array(rh_data)

                e_w = saturation_pressure_water(temp_arr)
                e_i = saturation_pressure_ice(temp_arr)
                safe_e_i = np.where(e_i > 0, e_i, 1.0)
                rhi = rh_arr * (e_w / safe_e_i)
                issr_intensity = np.maximum(0.0, rhi - 100.0)

                return {
                    "lats": lats,
                    "lons": lons,
                    "pressure_levels": np.array(PRESSURE_LEVELS),
                    "temperature": temp_arr,
                    "rh": rh_arr,
                    "u_wind": np.array(u_data),
                    "v_wind": np.array(v_data),
                    "issr_intensity": issr_intensity,
                    "source": np.array(["noaa_live"]),
                    "timestamp": np.array([f"{attempt_date}T{hour:02d}:00:00Z"]),
                }

            except ImportError:
                logger.info("[GFS] Herbie not installed — cannot use AWS S3 GRIB download")
            except Exception as e:
                logger.info(f"[GFS] Herbie S3 access failed: {e}")

        except Exception as e:
            logger.info(f"[GFS] AWS S3 attempt for offset {day_offset} failed: {e}")
            continue

    return None


def generate_synthetic_atmosphere(
    origin_lat: float, origin_lon: float,
    dest_lat: float, dest_lon: float,
    departure_time: datetime,
    grid_resolution: float = 1.0
) -> dict:
    """
    Generate synthetic atmospheric data using US Standard Atmosphere
    with added ISSR patches. Uses route-based seed for variety.
    """
    # Route-based seed so different routes get different atmospheres
    # but same route gives consistent (reproducible) results
    seed = int(abs(origin_lat * 100 + origin_lon * 10 + dest_lat * 7 + dest_lon * 3
                    + departure_time.hour * 13 + departure_time.day * 37)) % 100000
    rng = np.random.RandomState(seed)
    logger.info(f"[SYNTH] Generating atmosphere with seed={seed}")

    min_lat = min(origin_lat, dest_lat) - 15.0
    max_lat = max(origin_lat, dest_lat) + 15.0
    min_lon = min(origin_lon, dest_lon) - 15.0
    max_lon = max(origin_lon, dest_lon) + 15.0

    min_lat = max(min_lat, -90)
    max_lat = min(max_lat, 90)
    min_lon = max(min_lon, -180)
    max_lon = min(max_lon, 180)

    lats = np.arange(min_lat, max_lat + 0.1, grid_resolution)
    lons = np.arange(min_lon, max_lon + 0.1, grid_resolution)

    n_levels = len(PRESSURE_LEVELS)
    n_lat = len(lats)
    n_lon = len(lons)

    temp_grid = np.zeros((n_levels, n_lat, n_lon))
    rh_grid = np.zeros((n_levels, n_lat, n_lon))
    u_wind_grid = np.zeros((n_levels, n_lat, n_lon))
    v_wind_grid = np.zeros((n_levels, n_lat, n_lon))

    for k, p_hPa in enumerate(PRESSURE_LEVELS):
        h_km = 44.330 * (1.0 - (p_hPa / 1013.25) ** 0.1903)
        if h_km < 11.0:
            T_base = 288.15 - 6.5 * h_km
        else:
            T_base = 216.65

        lat_factor = np.cos(np.radians(lats)) * 5.0
        T_lat = T_base + lat_factor[:, np.newaxis] * np.ones((1, n_lon))
        T_lat += rng.randn(n_lat, n_lon) * 2.0
        temp_grid[k] = T_lat

        rh_base = max(20, 70 - h_km * 5)
        rh = np.full((n_lat, n_lon), rh_base, dtype=float)
        rh += rng.randn(n_lat, n_lon) * 10
        rh_grid[k] = np.clip(rh, 5, 100)

        jet_strength = max(0, 30 - abs(p_hPa - 250) * 0.1)
        for i, lat in enumerate(lats):
            lat_contrib = np.exp(-((abs(lat) - 45) ** 2) / (2 * 15 ** 2))
            u_wind_grid[k, i, :] = jet_strength * lat_contrib + rng.randn(n_lon) * 4
            v_wind_grid[k, i, :] = rng.randn(n_lon) * 3

    # Add 4-7 random elliptical ISSR patches along the route
    n_patches = rng.randint(4, 8)
    logger.info(f"[SYNTH] Adding {n_patches} ISSR patches along route")

    for p_idx in range(n_patches):
        t = rng.uniform(0.05, 0.95)
        center_lat = origin_lat + t * (dest_lat - origin_lat) + rng.uniform(-10, 10)
        center_lon = origin_lon + t * (dest_lon - origin_lon) + rng.uniform(-10, 10)

        sigma_lat = rng.uniform(2, 7)
        sigma_lon = rng.uniform(3, 9)
        peak_rhi_boost = rng.uniform(20, 50)
        target_level = rng.randint(0, 3)

        logger.info(f"[SYNTH]   ISSR patch {p_idx+1}: center=({center_lat:.1f},{center_lon:.1f}) "
                    f"σ=({sigma_lat:.1f},{sigma_lon:.1f}) boost={peak_rhi_boost:.1f} level={target_level}")

        for k in range(max(0, target_level - 1), min(n_levels, target_level + 2)):
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    dist_sq = ((lat - center_lat) / sigma_lat) ** 2 + \
                              ((lon - center_lon) / sigma_lon) ** 2
                    if dist_sq < 4.0:
                        boost = peak_rhi_boost * np.exp(-dist_sq / 2)
                        rh_grid[k, i, j] += boost

    rh_grid = np.clip(rh_grid, 0, 100)

    from sac_engine import saturation_pressure_water, saturation_pressure_ice

    e_w = saturation_pressure_water(temp_grid)
    e_i = saturation_pressure_ice(temp_grid)
    safe_e_i = np.where(e_i > 0, e_i, 1.0)
    rhi_grid = rh_grid * (e_w / safe_e_i)
    issr_intensity = np.maximum(0.0, rhi_grid - 100.0)

    issr_max = issr_intensity.max()
    issr_coverage = (issr_intensity > 1.0).mean() * 100
    logger.info(f"[SYNTH] Atmosphere stats: grid=({n_levels}×{n_lat}×{n_lon}), "
                f"ISSR max={issr_max:.1f}, coverage={issr_coverage:.1f}%")

    return {
        "lats": lats,
        "lons": lons,
        "pressure_levels": np.array(PRESSURE_LEVELS),
        "temperature": temp_grid,
        "rh": rh_grid,
        "u_wind": u_wind_grid,
        "v_wind": v_wind_grid,
        "issr_intensity": issr_intensity,
        "source": np.array(["synthetic_fallback"]),
        "timestamp": np.array([departure_time.strftime("%Y-%m-%dT%H:%M:%SZ")]),
    }
