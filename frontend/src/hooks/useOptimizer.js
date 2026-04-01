import { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = 'http://localhost:8000';

/**
 * Custom hook for managing optimizer state and API calls.
 * Supports client-side Pareto front re-selection when weights change.
 * Emits detailed, level-tagged logs for the Optimizer Console.
 */
export function useOptimizer() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [selectedPathId, setSelectedPathId] = useState(null);
  const [logs, setLogs] = useState([]);
  const abortRef = useRef(null);
  const lastSelectedIdxRef = useRef(null);

  const addLog = useCallback((msg, level = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    const entry = { timestamp, msg, level };
    setLogs(prev => [...prev.slice(-200), entry]); // keep last 200 logs
    console.log(`[GreenPath ${level.toUpperCase()}] ${msg}`);
  }, []);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const optimize = useCallback(async (params) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    clearLogs();
    lastSelectedIdxRef.current = null;

    // ── Phase 1: Initialization ──
    addLog(`━━━ Starting Optimization ━━━`, 'info');
    addLog(`Route: ${params.origin} → ${params.destination}`, 'info');
    addLog(`Aircraft: ${params.aircraft}`, 'info');
    addLog(`NOAA GFS: ${params.useNoaa ? 'Enabled' : 'Disabled (synthetic mode)'}`, params.useNoaa ? 'info' : 'warn');
    addLog(`Route Cache: ${params.useCache ? 'Enabled' : 'Disabled (force fresh)'}`, 'info');
    addLog(`Weights: CO₂=${params.weights.co2}% | Contrail=${params.weights.contrail}% | Time=${params.weights.time}%`, 'info');

    // ── Phase 2: Validating inputs ──
    addLog(`Validating route parameters...`, 'info');
    if (!params.origin || !params.destination) {
      addLog(`Missing origin or destination`, 'error');
      setError('Origin and destination are required');
      setLoading(false);
      return;
    }
    if (params.origin === params.destination) {
      addLog(`Origin and destination are the same`, 'error');
      setError('Origin and destination must be different');
      setLoading(false);
      return;
    }
    addLog(`Input validation passed`, 'success');

    // ── Phase 3: API Request ──
    addLog(`Sending optimization request to backend...`, 'info');
    addLog(`POST ${API_BASE}/optimize`, 'info');

    const startTime = Date.now();

    try {
      addLog(`Awaiting server response (timeout: 180s)...`, 'info');
      
      const response = await axios.post(`${API_BASE}/optimize`, {
        origin: params.origin,
        destination: params.destination,
        aircraft: params.aircraft,
        departure_iso: params.departureIso,
        weights: {
          co2: params.weights.co2 / 100,
          contrail: params.weights.contrail / 100,
          time: params.weights.time / 100,
        },
        use_noaa: params.useNoaa,
        use_cache: params.useCache !== false,
      }, {
        signal: controller.signal,
        timeout: 180000, // 3 min timeout
      });

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

      // ── Phase 4: Process Response ──
      addLog(`Server responded in ${elapsed}s (HTTP ${response.status})`, 'success');

      const data = response.data;
      const gfsSource = data.gfs_source;

      // ── Cache detection ──
      if (data._cached) {
        addLog(`Route cache HIT — returning previously computed result`, 'success');
        addLog(`To force fresh optimization, disable the Route Cache toggle`, 'info');
      }

      // ── Phase 5: Atmospheric Data Source ──
      if (gfsSource === 'noaa_live') {
        addLog(`Atmospheric data: NOAA GFS Live`, 'success');
        addLog(`GFS Timestamp: ${data.gfs_timestamp}`, 'info');
      } else {
        addLog(`Atmospheric data: Synthetic Fallback`, 'warn');
        addLog(`NOAA GFS fetch failed — the backend was unable to retrieve live atmospheric data from NOAA servers. This could be due to:`, 'warn');
        addLog(`• NOAA servers temporarily unavailable or rate-limited`, 'warn');
        addLog(`• Network connectivity issues to NOAA endpoints`, 'warn');
        addLog(`• GFS data not yet available for the requested time`, 'warn');
        addLog(`Using synthetic atmosphere model as fallback. Results are approximate.`, 'warn');
      }

      // ── Phase 6: Pareto Front ──
      addLog(`Pareto front: ${data.pareto_front.length} non-dominated solutions`, 'info');

      // ── Phase 7: Stats Summary ──
      const stats = data.stats;
      addLog(`Baseline: CO₂=${stats.baseline_co2_kg}kg | EF=${stats.baseline_ef} | Time=${stats.baseline_time_min}min`, 'info');
      addLog(`Optimized: CO₂=${stats.selected_co2_kg}kg | EF=${stats.selected_ef} | Time=${stats.selected_time_min}min`, 'info');

      if (stats.co2_saving_pct > 0) {
        addLog(`CO₂ savings: ${stats.co2_saving_pct}% reduction`, 'success');
      } else {
        addLog(`CO₂ savings: ${stats.co2_saving_pct}% (no improvement)`, 'warn');
      }

      if (stats.ef_reduction_pct > 0) {
        addLog(`Contrail EF reduction: ${stats.ef_reduction_pct}%`, 'success');
      } else {
        addLog(`Contrail EF reduction: ${stats.ef_reduction_pct}% (no improvement)`, 'warn');
      }

      addLog(`Extra distance: ${stats.extra_km > 0 ? '+' : ''}${stats.extra_km}km | Extra time: ${stats.extra_min > 0 ? '+' : ''}${stats.extra_min}min`, 'info');
      addLog(`━━━ Optimization Complete ━━━`, 'success');

      setResults(data);
      setSelectedPathId(null);
    } catch (err) {
      if (axios.isCancel(err)) {
        addLog(`Request cancelled by user`, 'warn');
        return;
      }

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        addLog(`Request timed out after ${elapsed}s`, 'error');
        addLog(`The optimization took too long. Try a shorter route or reduce parameters.`, 'error');
      } else if (err.response) {
        addLog(`Server error (HTTP ${err.response.status}) after ${elapsed}s`, 'error');
        const detail = err.response.data?.detail;
        if (detail) {
          addLog(`Detail: ${detail}`, 'error');
        }
      } else if (err.request) {
        addLog(`No response from server after ${elapsed}s`, 'error');
        addLog(`Backend may not be running. Check that the server is started on port 8000.`, 'error');
      } else {
        addLog(`Unexpected error: ${err.message}`, 'error');
      }

      const msg = err.response?.data?.detail || err.message || 'Optimization failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [addLog, clearLogs]);

  // Client-side Pareto front re-selection by weights
  const reselectByWeights = useCallback((weights) => {
    if (!results?.pareto_front || results.pareto_front.length === 0) return;

    const front = results.pareto_front;
    const co2Vals = front.map(p => p.co2_kg);
    const efVals = front.map(p => p.contrail_ef);
    const timeVals = front.map(p => p.time_min);

    const co2Min = Math.min(...co2Vals), co2Max = Math.max(...co2Vals);
    const efMin = Math.min(...efVals), efMax = Math.max(...efVals);
    const timeMin = Math.min(...timeVals), timeMax = Math.max(...timeVals);

    const co2Range = co2Max - co2Min || 1;
    const efRange = efMax - efMin || 1;
    const timeRange = timeMax - timeMin || 1;

    const wTotal = weights.co2 + weights.contrail + weights.time || 1;
    const wCo2 = weights.co2 / wTotal;
    const wContrail = weights.contrail / wTotal;
    const wTime = weights.time / wTotal;

    let bestScore = Infinity;
    let bestIdx = 0;

    front.forEach((p, i) => {
      const score = wCo2 * (p.co2_kg - co2Min) / co2Range
                  + wContrail * (p.contrail_ef - efMin) / efRange
                  + wTime * (p.time_min - timeMin) / timeRange;
      if (score < bestScore) {
        bestScore = score;
        bestIdx = i;
      }
    });

    // Guard: skip if the same point is already selected
    if (lastSelectedIdxRef.current === bestIdx) return;
    lastSelectedIdxRef.current = bestIdx;

    const selected = front[bestIdx];
    addLog(`Re-selected Pareto point #${selected.path_id}: CO₂=${selected.co2_kg}kg EF=${selected.contrail_ef} Time=${selected.time_min}min`);

    // Update the displayed path to the selected Pareto solution's path
    if (selected.path) {
      setResults(prev => ({
        ...prev,
        selected_path: selected.path,
        stats: {
          ...prev.stats,
          selected_co2_kg: selected.co2_kg,
          selected_ef: selected.contrail_ef,
          selected_time_min: selected.time_min,
          co2_saving_pct: prev.stats.baseline_co2_kg > 0
            ? Math.round((prev.stats.baseline_co2_kg - selected.co2_kg) / prev.stats.baseline_co2_kg * 1000) / 10
            : 0,
          ef_reduction_pct: prev.stats.baseline_ef > 0
            ? Math.round((prev.stats.baseline_ef - selected.contrail_ef) / prev.stats.baseline_ef * 1000) / 10
            : 0,
          extra_min: Math.round((selected.time_min - prev.stats.baseline_time_min) * 10) / 10,
        }
      }));
    }

    setSelectedPathId(selected.path_id);
  }, [results, addLog]);

  const geocode = useCallback(async (query) => {
    if (!query || query.length < 2) return [];
    try {
      const response = await axios.get(`${API_BASE}/airports`, {
        params: { q: query },
        timeout: 5000,
      });
      return response.data;
    } catch {
      return [];
    }
  }, []);

  const selectParetoPoint = useCallback((pathId) => {
    if (!results?.pareto_front) return;
    const point = results.pareto_front.find(p => p.path_id === pathId);
    if (point?.path) {
      addLog(`Selected Pareto point #${pathId}: CO₂=${point.co2_kg}kg EF=${point.contrail_ef}`);
      lastSelectedIdxRef.current = results.pareto_front.indexOf(point);
      setResults(prev => ({
        ...prev,
        selected_path: point.path,
        stats: {
          ...prev.stats,
          selected_co2_kg: point.co2_kg,
          selected_ef: point.contrail_ef,
          selected_time_min: point.time_min,
          co2_saving_pct: prev.stats.baseline_co2_kg > 0
            ? Math.round((prev.stats.baseline_co2_kg - point.co2_kg) / prev.stats.baseline_co2_kg * 1000) / 10
            : 0,
          ef_reduction_pct: prev.stats.baseline_ef > 0
            ? Math.round((prev.stats.baseline_ef - point.contrail_ef) / prev.stats.baseline_ef * 1000) / 10
            : 0,
          extra_min: Math.round((point.time_min - prev.stats.baseline_time_min) * 10) / 10,
        }
      }));
    }
    setSelectedPathId(pathId);
  }, [results, addLog]);

  return {
    loading,
    results,
    error,
    selectedPathId,
    logs,
    optimize,
    geocode,
    selectParetoPoint,
    reselectByWeights,
    addLog,
    clearLogs,
  };
}
