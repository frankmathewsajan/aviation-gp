import { useState, useCallback, useEffect } from 'react';
import MapView from './components/MapView';
import ControlPanel from './components/ControlPanel';
import ResultsOverlay from './components/ResultsPanel';
import PathLegend from './components/PathLegend';
import { useOptimizer } from './hooks/useOptimizer';
import './index.css';

function App() {
  const {
    loading, results, error, selectedPathId, logs,
    optimize, geocode, selectParetoPoint, reselectByWeights, addLog
  } = useOptimizer();
  const [showNoaaOverlay, setShowNoaaOverlay] = useState(false);
  const [showAltitude, setShowAltitude] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [useCache, setUseCache] = useState(true);

  // Auto-open right panel when results arrive
  useEffect(() => {
    if (results) {
      setRightCollapsed(false);
    }
  }, [results]);

  const handleOptimize = useCallback((params) => {
    // Auto-open right panel to show logs
    setRightCollapsed(false);
    optimize({ ...params, useCache });
  }, [optimize, useCache]);

  const handleWeightsChange = useCallback((weights) => {
    if (results) {
      reselectByWeights(weights);
    }
  }, [results, reselectByWeights]);

  return (
    <div className="relative w-full h-full flex bg-stone-50">
      {/* Map — fills entire background */}
      <MapView results={results} showNoaaOverlay={showNoaaOverlay} leftCollapsed={leftCollapsed} />

      {/* Left sidebar — collapsible */}
      <div className={`fixed top-0 left-0 bottom-0 z-[999] flex items-stretch transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] ${leftCollapsed ? 'w-10' : ''}`}>
        {!leftCollapsed && (
          <ControlPanel
            onOptimize={handleOptimize}
            onWeightsChange={handleWeightsChange}
            loading={loading}
            geocode={geocode}
            gfsSource={results?.gfs_source}
            onCollapse={() => setLeftCollapsed(true)}
            useCache={useCache}
            onToggleCache={setUseCache}
          />
        )}
        {leftCollapsed && (
          <button
            onClick={() => setLeftCollapsed(false)}
            className="w-10 h-full bg-white/80 backdrop-blur-lg border-r border-stone-200/60 flex items-center justify-center hover:bg-white transition-colors cursor-pointer"
          >
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      {/* Results overlay — floating on map */}
      {(results || loading) && !rightCollapsed && (
        <ResultsOverlay
          results={results}
          showNoaaOverlay={showNoaaOverlay}
          onToggleNoaa={() => setShowNoaaOverlay(v => !v)}
          showAltitude={showAltitude}
          onToggleAltitude={() => setShowAltitude(v => !v)}
          onSelectParetoPoint={selectParetoPoint}
          selectedPathId={selectedPathId}
          onCollapse={() => setRightCollapsed(true)}
          logs={logs}
          loading={loading}
        />
      )}

      {/* Expand right panel button */}
      {results && rightCollapsed && (
        <button
          onClick={() => setRightCollapsed(false)}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-[999] w-10 h-24 bg-white/80 backdrop-blur-lg border border-r-0 border-stone-200/60 rounded-l-xl flex items-center justify-center hover:bg-white transition-colors cursor-pointer"
        >
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Legend */}
      <PathLegend visible={!!results} />

      {/* Loading */}
      {loading && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-3 px-6 py-3 bg-white rounded-full shadow-lg border border-stone-200/60">
          <div className="w-4 h-4 border-2 border-stone-200 border-t-stone-800 rounded-full animate-spin" />
          <span className="text-sm font-medium text-stone-600">
            Running <span className="font-mono font-bold text-stone-900">NSGA-II</span> optimizer…
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-2 px-5 py-3 bg-red-50 rounded-full border border-red-200 text-red-600 text-sm font-medium">
          <i className="fa-solid fa-triangle-exclamation" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

export default App;
