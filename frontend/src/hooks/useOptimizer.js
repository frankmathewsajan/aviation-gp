import { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = 'http://localhost:8000';

/**
 * Custom hook for managing optimizer state and API calls.
 * Supports client-side Pareto front re-selection when weights change.
 */
export function useOptimizer() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [selectedPathId, setSelectedPathId] = useState(null);
  const [logs, setLogs] = useState([]);
  const abortRef = useRef(null);

  const addLog = useCallback((msg, level = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    const entry = { timestamp, msg, level };
    setLogs(prev => [...prev.slice(-100), entry]); // keep last 100 logs
    console.log(`[GreenPath ${level.toUpperCase()}] ${msg}`);
  }, []);

  const optimize = useCallback(async (params) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    addLog(`Starting optimization: ${params.origin} → ${params.destination}`);
    addLog(`Aircraft: ${params.aircraft}, NOAA: ${params.useNoaa}`);
    addLog(`Weights: CO₂=${params.weights.co2}% Contrail=${params.weights.contrail}% Time=${params.weights.time}%`);

    const startTime = Date.now();

    try {
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
      }, {
        signal: controller.signal,
        timeout: 180000, // 3 min timeout
      });

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      addLog(`✓ Optimization complete in ${elapsed}s`);
      addLog(`Source: ${response.data.gfs_source}`);
      addLog(`Pareto front: ${response.data.pareto_front.length} solutions`);
      addLog(`Stats: CO₂ saved ${response.data.stats.co2_saving_pct}%, Contrail EF -${response.data.stats.ef_reduction_pct}%`);

      setResults(response.data);
      setSelectedPathId(null);
    } catch (err) {
      if (axios.isCancel(err)) return;
      const msg = err.response?.data?.detail || err.message || 'Optimization failed';
      addLog(`✗ Error: ${msg}`, 'error');
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [addLog]);

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
  };
}
