# GreenPath — Contrail-Aware Flight Path Optimization

> **Implementation 2** of a research project on reducing aviation's climate impact through intelligent flight routing. Uses **NSGA-II multi-objective genetic algorithm** with **physics-based contrail modeling** (Schmidt-Appleman Criterion + ISSR detection).

## Overview

GreenPath optimizes flight paths across three competing objectives:
1. **CO₂ Emissions** — Minimize fuel burn (wind-corrected)
2. **Contrail Energy Forcing** — Avoid ice-supersaturated regions (ISSRs) where persistent contrails form
3. **Flight Time** — Minimize route duration

The system uses real NOAA GFS atmospheric data (with synthetic fallback) and presents results on an interactive dark-themed world map with Pareto front visualization.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Frontend                      │
│  React + Vite + Leaflet.js + D3 + Glassmorphism │
│  Port 3000                                       │
└───────────────────────┬─────────────────────────┘
                        │ HTTP/REST
┌───────────────────────┴─────────────────────────┐
│                    Backend                        │
│  FastAPI + NSGA-II + SAC Engine + ISSR Detector  │
│  Port 8000                                       │
└─────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+

### Install & Run

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/optimize` | Run NSGA-II optimization |
| `GET` | `/geocode?q=JFK` | Geocode airport/city |
| `GET` | `/airports?q=lon` | Search airports |
| `GET` | `/health` | Health check |

### POST /optimize — Request Body
```json
{
  "origin": "JFK",
  "destination": "LHR",
  "aircraft": "A320",
  "departure_iso": "2025-01-15T10:00:00Z",
  "weights": {"co2": 0.4, "contrail": 0.4, "time": 0.2}
}
```

## Why NSGA-II over Fuzzy ACO (Implementation 1)?

| Aspect | Fuzzy ACO (Impl 1) | NSGA-II (Impl 2) |
|--------|--------------------|--------------------|
| Graph | Static waypoint graph | Continuous waypoint space |
| Objectives | Weighted sum | True multi-objective Pareto |
| Convergence | Slow (~10+ min) | Fast (<30s with numpy) |
| Atmosphere | Discretized into zones | Continuous grid interpolation |
| Result | Single solution | Full Pareto front |
| User control | Fixed weights | Interactive weight sliders |

**Fuzzy ACO failed because:**
- Static graph couldn't adapt to continuous atmospheric variations
- Single-objective formulation forced premature trade-offs
- Pheromone convergence was too slow for dynamic data
- No way to explore the full trade-off space

## Backend Modules

| Module | Purpose |
|--------|---------|
| `fuel_model.py` | Aircraft profiles (A320/B737/B777/A350), wind-corrected fuel burn |
| `sac_engine.py` | Schmidt-Appleman Criterion contrail formation physics |
| `issr_detector.py` | Ice-supersaturated region detection (Alduchov & Eskridge 1996) |
| `noaa_gfs.py` | NOAA GFS atmospheric data + synthetic fallback |
| `nsga2_optimizer.py` | Full NSGA-II with smart mutation (100 pop × 80 gen) |
| `main.py` | FastAPI app, 500-airport database, all endpoints |

## Research Paper

See `paper/paper.md` for the IEEE-format draft covering:
1. Introduction & Motivation
2. Literature Review
3. Methodology (SAC, ISSR, NSGA-II)
4. Implementation Details
5. Results & Discussion
6. Conclusion

## License

Research project — all rights reserved.
