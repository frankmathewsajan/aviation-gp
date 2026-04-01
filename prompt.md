Here's your master prompt for Claude Code MAX — copy-paste this entire block:

---

```
You are building "GreenPath" — a full-stack interactive flight path optimization system for contrail prevention. This is Implementation 2 of a research project (Implementation 1 used Fuzzy ACO and failed due to static graph limitations and slow convergence on dynamic atmospheric data). Implementation 2 uses NSGA-II multi-objective genetic algorithm with physics-based contrail modeling.

## PROJECT OVERVIEW

Build a complete, production-grade web application with:
1. A Python backend (FastAPI) running the NSGA-II optimizer + NOAA GFS data pipeline
2. A React frontend with a full-screen world map (Leaflet.js) and control panels
3. Real NOAA GFS atmospheric data integration (free, no API key needed)
4. Interactive Pareto front visualization and user-tunable optimization weights

The app lets users input origin + destination cities, select aircraft type, set departure time, and tune optimization weights (CO₂ vs contrail vs time). It fetches real atmospheric data, runs the optimizer, and draws the optimized path on a world map colored by contrail risk.

---

## BACKEND — FastAPI Python

### File structure:
```
backend/
  main.py              # FastAPI app, CORS, all endpoints
  noaa_gfs.py          # NOAA GFS data fetching + parsing
  sac_engine.py        # Schmidt-Appleman Criterion contrail model
  issr_detector.py     # Ice-supersaturated region detection
  nsga2_optimizer.py   # Full NSGA-II implementation
  fuel_model.py        # Aircraft-specific fuel burn model
  requirements.txt
```

### NOAA GFS Integration (noaa_gfs.py)
- Fetch from: https://nomads.ncep.noaa.gov/dods/gfs_0p25/gfs{YYYYMMDD}/gfs_0p25_{HH}z
- Use xarray + pydap or requests to fetch these variables at pressure levels [200,250,300,350,400,450,500] hPa:
  - `tmp` (temperature K)
  - `r` (relative humidity %)
  - `ugrd`, `vgrd` (wind u/v components m/s)
  - `hgt` (geopotential height m)
- Fetch only the lat/lon bounding box of the flight corridor (origin lat ± 15°, lon ± 15°) to keep it fast
- Cache fetched data as a numpy array keyed by (date, hour, bbox)
- Always fall back to synthetic atmospheric data if NOAA is unavailable (generate realistic temp/humidity profiles using standard atmosphere + added ISSR patches)

### Schmidt-Appleman Criterion Engine (sac_engine.py)
Implement the full SAC physics:
```python
def compute_sac_threshold(pressure_hPa, aircraft_eta=0.35, EI_H2O=1.25, Q=43e6, cp=1004):
    """
    Returns critical temperature T_crit in Kelvin below which contrails form.
    Uses: T_crit = (EI_H2O * cp * p) / (epsilon * Q * (1 - eta)) - based on Schumann 1996
    """
    epsilon = 0.6222
    G = (EI_H2O * cp * pressure_hPa * 100) / (epsilon * Q * (1 - aircraft_eta))
    # G is the slope of the mixing line (Pa/K)
    # T_crit is where the mixing line is tangent to the saturation curve
    # Approximate using: T_crit = 226.69 + 9.43 * ln(G - 0.053) + 0.720 * ln(G - 0.053)^2
    import numpy as np
    lnG = np.log(G - 0.053)
    T_crit = 226.69 + 9.43 * lnG + 0.720 * lnG**2
    return T_crit
```
For each grid point, if ambient_temp < T_crit AND RHi > 100% → contrail forms. If RHi > 100% → persistent (ISSR zone).

### ISSR Detector (issr_detector.py)
- Convert RH_liquid to RH_ice: RHi = RH * (e_w / e_i) where e_w, e_i are saturation vapor pressures (use Alduchov & Eskridge 1996 formulas)
- Return a 3D boolean grid of ISSR regions
- Compute "ISSR intensity" as max(0, RHi - 100) for gradient-based penalty

### Fuel Model (fuel_model.py)
Aircraft profiles:
```python
AIRCRAFT = {
    "A320": {"cruise_speed_ms": 230, "fuel_flow_kgps": 0.85, "eta": 0.35, "ceiling_ft": 39000},
    "B737": {"cruise_speed_ms": 225, "fuel_flow_kgps": 0.80, "eta": 0.34, "ceiling_ft": 41000},
    "B777": {"cruise_speed_ms": 255, "fuel_flow_kgps": 1.80, "eta": 0.37, "ceiling_ft": 43000},
    "A350": {"cruise_speed_ms": 252, "fuel_flow_kgps": 1.50, "eta": 0.38, "ceiling_ft": 43000},
}
```
Fuel burn for a segment = fuel_flow_kgps * segment_time_s, adjusted by wind (effective groundspeed = airspeed + wind component along track). CO₂ = fuel_kg * 3.16.

### NSGA-II Optimizer (nsga2_optimizer.py)

Full implementation:

**Chromosome representation**: A list of N waypoints, each = (lat, lon, altitude_band). altitude_band ∈ [0,1,2,3] mapping to [30000, 33000, 37000, 41000] ft. Origin and destination are fixed endpoints.

**Initialization**: Generate `pop_size=150` chromosomes. For each, generate 8–14 intermediate waypoints by perturbing the great-circle path (random lat/lon offsets up to ±8°, random altitude bands). Also add the great-circle path as one individual for baseline comparison.

**Objective functions** (minimize all three):
1. `f1_co2(path)`: total CO₂ kg = Σ fuel_burn(segment) * 3.16, wind-corrected
2. `f2_contrail_ef(path)`: energy forcing = Σ ISSR_intensity(waypoint) * segment_length_km * RF_weight(local_time, latitude) where RF_weight accounts for day/night (0.7 at night, 1.3 at noon)
3. `f3_time(path)`: total flight time in minutes

**NSGA-II core**:
```python
def non_dominated_sort(population_fitness):
    # Standard fast non-dominated sort (Deb 2002)
    # Returns fronts list
    
def crowding_distance(front_fitness):
    # Standard crowding distance assignment
    
def tournament_select(population, ranks, crowding):
    # Binary tournament selection
    
def crossover(parent1, parent2, crossover_rate=0.9):
    # Single-point crossover on waypoint sequences
    # Pad/trim to same length if needed
    
def mutate(chromosome, mutation_rate=0.2, atmosphere_grid):
    # Three mutation types with equal probability:
    # 1. Perturb waypoint position (±2° lat/lon)
    # 2. Shift altitude band ±1
    # 3. Insert or delete a waypoint
    # Add "smart mutation": if waypoint is in high ISSR zone, nudge toward lower-RHi neighbor
```

**Run**: 200 generations, pop_size=150. Return the full Pareto front (front 0) as a list of {waypoints, co2_kg, contrail_ef, time_min} objects.

**User weight selection**: After optimizer returns Pareto front, pick closest solution to user weights using: score = w_co2*norm(co2) + w_contrail*norm(ef) + w_time*norm(time). Return this as the "selected" path plus the full Pareto front for visualization.

### FastAPI Endpoints (main.py)

```
POST /optimize
  Body: {
    origin: "JFK",           # IATA or city name
    destination: "LHR",
    aircraft: "A320",
    departure_iso: "2025-01-15T10:00:00Z",
    weights: {co2: 0.4, contrail: 0.4, time: 0.2}
  }
  Returns: {
    selected_path: [{lat, lon, alt_ft, issr_intensity, contrail_risk},...],
    baseline_path: [{lat, lon},...],      # great circle
    pareto_front: [{co2_kg, contrail_ef, time_min, path_id},...],
    stats: {co2_saving_pct, ef_reduction_pct, extra_km, extra_min},
    atmosphere_sample: [{lat, lon, issr_intensity},...],  # for heatmap overlay
    gfs_timestamp: "2025-01-15T12:00:00Z",
    gfs_source: "noaa_live" | "synthetic_fallback"
  }

GET /geocode?q=JFK
  Returns: {lat, lon, name}   # use geopy or a simple airport DB dict

GET /health
  Returns: {status: "ok"}
```

Add CORS for localhost:3000. Run with uvicorn on port 8000.

Include a 500-entry airport IATA→lat/lon dictionary as a Python dict (hardcoded, covering all major airports). Also support city name geocoding via geopy Nominatim as fallback.

---

## FRONTEND — React + Vite

### File structure:
```
frontend/
  src/
    App.jsx
    components/
      MapView.jsx          # Leaflet map, flight paths, heatmap
      ControlPanel.jsx     # Left sidebar: inputs + sliders
      ResultsPanel.jsx     # Right sidebar: stats + Pareto chart
      ParetoChart.jsx      # D3 scatter plot of Pareto front
      PathLegend.jsx       # Map legend
    hooks/
      useOptimizer.js      # API call + state management
    utils/
      colors.js            # ISSR risk → color gradient
      geo.js               # Great circle, path interpolation
    index.css
  index.html
  package.json
  vite.config.js
```

### Design direction — DARK AEROSPACE AESTHETIC:
- Background: #0a0e1a (near-black navy)
- Accent: #00d4ff (electric cyan) + #ff6b35 (amber-orange for warnings)
- Map: Dark tile layer (CartoDB Dark Matter or Stamen Toner)
- Font: "Space Mono" for numbers/data, "Syne" for headings, system sans for body
- Panels: Semi-transparent glass-morphism (#ffffff08 background, 1px #ffffff15 border, backdrop-blur)
- Contrail risk gradient: green (#00ff88) → yellow (#ffdd00) → red (#ff3355) along the path
- Pareto front: cyan dots on dark background, selected point highlighted in orange

### Layout:
- Full-screen Leaflet map as background
- Left panel (320px): Origin/destination inputs, aircraft selector, departure datetime, optimization sliders
- Right panel (320px): Stats cards (CO₂ saved %, EF reduction %, extra km, extra min), Pareto front scatter chart, toggle for "show atmosphere heatmap"
- Bottom center: subtle loading bar when optimizing
- Top center: "GreenPath — Contrail-Aware Flight Optimization" title bar with GFS timestamp

### MapView.jsx (Leaflet):
- Use react-leaflet
- Dark basemap: L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png')
- Draw baseline (great circle) as dashed gray polyline
- Draw optimized path as a colored polyline where each segment is colored by its ISSR intensity (use L.polyline per segment with color from risk gradient)
- Add circle markers at each waypoint with popup showing: altitude, ISSR intensity %, contrail risk
- Atmosphere heatmap overlay: use leaflet-heat plugin with the atmosphere_sample points weighted by issr_intensity
- Auto-fit bounds to show full path
- Add animated "aircraft" marker that travels along the path (CSS animation)

### ControlPanel.jsx:
- Origin + destination: text inputs with autocomplete (call /geocode as user types, show dropdown)
- Aircraft selector: styled radio buttons with plane icons (A320, B737, B777, A350)
- Departure datetime: native datetime-local input, styled to match dark theme
- Three sliders (0–100, summing to 100):
  - "Minimize CO₂" 
  - "Minimize Contrails"
  - "Minimize Time"
  - Auto-normalize so they always sum to 100 (when one moves, others scale proportionally)
- "Optimize Route" button: cyan, full-width, with loading spinner
- Below button: small text showing GFS data status (live/synthetic)

### ResultsPanel.jsx:
- Four stat cards: CO₂ saved vs baseline (%), Contrail EF reduction (%), Extra distance (km), Extra time (min) — green for good numbers, amber for trade-offs
- ParetoChart: D3 scatter plot, x-axis = CO₂ kg, y-axis = Contrail EF, dot size = flight time. Hover tooltip. Click a dot to redraw that path on map. Selected solution highlighted.
- Toggle: "Show ISSR Heatmap" (leaflet-heat overlay)
- Toggle: "Show Altitude Profile" (opens a small chart below showing altitude bands along path)

### useOptimizer.js hook:
```javascript
// Manages: loading state, calling POST /optimize, storing results
// Also handles weight normalization
// Debounce slider changes by 300ms before re-optimizing
```

### package.json dependencies:
react, react-dom, react-leaflet, leaflet, d3, axios, @turf/turf (for great circle), date-fns

---

## SETUP & RUN

Create a `start.sh`:
```bash
#!/bin/bash
# Install backend
cd backend && pip install -r requirements.txt &
# Install frontend  
cd frontend && npm install &
wait
# Start both
cd backend && uvicorn main:app --reload --port 8000 &
cd frontend && npm run dev
```

Create a `README.md` with:
- Project description (Implementation 2, NSGA-II + SAC + ISSR)
- How to run
- API docs
- Research paper outline (6 sections as described)
- Explanation of why Fuzzy ACO (Impl 1) failed vs why NSGA-II (Impl 2) works

---

## IMPLEMENTATION NOTES

1. **Speed**: The full NSGA-II with 150 pop × 200 gen is ~2–3 min in pure Python. Optimize by: vectorizing objective evaluation with numpy, using numba @jit on the inner loops, and caching the atmospheric grid. Target: <30 seconds for a typical transatlantic route.

2. **NOAA fallback**: NOAA GFS can be slow or unavailable. Always implement synthetic fallback first, verify the whole pipeline works, then add real GFS. Synthetic: use US Standard Atmosphere for temperature, add 3–5 random elliptical ISSR patches along the route with RHi values 95–115%.

3. **Great circle baseline**: Use the Haversine formula to generate 20 equally-spaced waypoints along the great circle arc between origin and destination. This is the comparison baseline.

4. **Waypoint interpolation for map**: After optimizer returns sparse waypoints (8–14 points), interpolate to 50 points along each segment for smooth path rendering and heatmap alignment.

5. **Research paper**: Create a `paper/` directory with `paper.md` — a full draft paper in markdown (IEEE format structure) covering all 6 sections described in the project brief. Include placeholder [TABLE 1], [FIGURE 1] etc. markers. ~3000 words.

---

## QUALITY BAR

- All three objective functions must be physically grounded (not toy proxies)
- NSGA-II must return a genuine Pareto front (not just one solution)
- The map must visually show path deviation from great circle with clear color coding
- Sliders must actually change the selected solution on the Pareto front
- Error states must be handled gracefully (NOAA down → synthetic fallback message)
- The app must work end-to-end for at least: JFK→LHR, LAX→NRT, DXB→SYD

Build everything. No placeholders. No "TODO" comments. Working code throughout.
```

---

**How to use this:** Open Claude Code MAX in your terminal, paste this entire prompt, and let it run. A few tips:

- Tell it to **start with the backend synthetic fallback first** so the full pipeline is testable immediately without NOAA dependency
- If it stalls on NSGA-II speed, ask it to add `numba` JIT compilation specifically on the objective evaluation inner loop
- The paper draft in `paper/paper.md` gives you the narrative skeleton — you fill in actual numbers from your experiment runs
- For the research angle: run the same JFK→LHR route with both the Fuzzy ACO (Impl 1 code if you have it) and NSGA-II, record convergence time and solution quality — that's your Section 3 vs Section 4 comparison