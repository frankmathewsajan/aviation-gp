import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import ParetoChart from './ParetoChart';

export default function ResultsOverlay({
  results,
  showNoaaOverlay,
  onToggleNoaa,
  showAltitude,
  onToggleAltitude,
  onSelectParetoPoint,
  selectedPathId,
  onCollapse,
}) {
  if (!results) return null;

  const { stats, pareto_front } = results;

  return (
    <>
      {/* Floating Stats Card — bottom center of map (matching demo) */}
      <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-[998]">
        <Card className="bg-white/90 backdrop-blur-xl shadow-lg border-stone-200/50">
          <CardContent className="flex items-end gap-8 px-6 py-4">
            <div>
              <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Est. Time</div>
              <div className="text-2xl font-bold text-stone-900 leading-tight">
                {Math.floor(stats.selected_time_min / 60)}h
                <span className="text-lg ml-0.5">{Math.round(stats.selected_time_min % 60)}m</span>
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Fuel Burn</div>
              <div className="text-2xl font-bold text-stone-900 leading-tight">
                {(stats.selected_co2_kg / 3.16 / 1000).toFixed(1)}k
                <span className="text-lg ml-0.5 text-stone-500">kg</span>
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">CO₂ Saved</div>
              <div className={`text-2xl font-bold leading-tight ${stats.co2_saving_pct > 0 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {stats.co2_saving_pct > 0 ? '-' : '+'}{Math.abs(stats.co2_saving_pct)}%
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Contrail EF</div>
              <div className={`text-2xl font-bold leading-tight ${stats.ef_reduction_pct > 0 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {stats.ef_reduction_pct > 0 ? '-' : '+'}{Math.abs(stats.ef_reduction_pct)}%
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Right panel — analysis tools */}
      <div className="fixed right-3 top-3 bottom-3 w-[320px] z-[999] bg-white/90 backdrop-blur-xl rounded-2xl border border-stone-200/60 shadow-xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">Analysis</h2>
          <button onClick={onCollapse} className="w-7 h-7 rounded-full border border-stone-200 flex items-center justify-center hover:bg-stone-50 transition-colors cursor-pointer">
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" className="text-stone-400">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-5 pb-5">
          {/* Quick stats */}
          <div className="grid grid-cols-2 gap-2 mb-4">
            <div className="bg-stone-50 rounded-xl p-3">
              <div className="text-[9px] font-semibold text-stone-400 uppercase tracking-wider">Baseline CO₂</div>
              <div className="text-lg font-bold font-mono text-stone-800">{stats.baseline_co2_kg?.toLocaleString()}<span className="text-xs font-normal text-stone-400 ml-1">kg</span></div>
            </div>
            <div className="bg-stone-50 rounded-xl p-3">
              <div className="text-[9px] font-semibold text-stone-400 uppercase tracking-wider">Optimized CO₂</div>
              <div className="text-lg font-bold font-mono text-stone-800">{stats.selected_co2_kg?.toLocaleString()}<span className="text-xs font-normal text-stone-400 ml-1">kg</span></div>
            </div>
            <div className="bg-stone-50 rounded-xl p-3">
              <div className="text-[9px] font-semibold text-stone-400 uppercase tracking-wider">Extra Distance</div>
              <div className="text-lg font-bold font-mono text-stone-800">{stats.extra_km > 0 ? '+' : ''}{stats.extra_km}<span className="text-xs font-normal text-stone-400 ml-1">km</span></div>
            </div>
            <div className="bg-stone-50 rounded-xl p-3">
              <div className="text-[9px] font-semibold text-stone-400 uppercase tracking-wider">Extra Time</div>
              <div className="text-lg font-bold font-mono text-stone-800">{stats.extra_min > 0 ? '+' : ''}{stats.extra_min?.toFixed(0)}<span className="text-xs font-normal text-stone-400 ml-1">min</span></div>
            </div>
          </div>

          <Separator className="my-3" />

          {/* Pareto front */}
          <div className="mb-4">
            <h3 className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-2">Pareto Front</h3>
            <div className="bg-stone-50 rounded-xl p-2">
              <ParetoChart data={pareto_front} selectedId={selectedPathId} onSelect={onSelectParetoPoint} />
            </div>
          </div>

          <Separator className="my-3" />

          {/* Toggles */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-stone-600 font-medium flex items-center gap-2">
                <span>🛰️</span>NOAA Data Overlay
              </Label>
              <Switch checked={showNoaaOverlay} onCheckedChange={onToggleNoaa} />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-xs text-stone-600 font-medium flex items-center gap-2">
                <span>📊</span>Altitude Profile
              </Label>
              <Switch checked={showAltitude} onCheckedChange={onToggleAltitude} />
            </div>
          </div>

          {/* Altitude profile */}
          {showAltitude && results.selected_path && (
            <div className="mt-4 bg-stone-50 rounded-xl p-3">
              <h4 className="text-[9px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Altitude Along Path</h4>
              <svg width="100%" height="80" viewBox="0 0 260 80">
                {results.selected_path.map((wp, i) => {
                  if (i >= results.selected_path.length - 1) return null;
                  const x1 = (i / results.selected_path.length) * 260;
                  const x2 = ((i + 1) / results.selected_path.length) * 260;
                  const altMap = { 30000: 65, 33000: 50, 37000: 30, 41000: 10 };
                  const y1 = altMap[wp.alt_ft] || 40;
                  const y2 = altMap[results.selected_path[i + 1].alt_ft] || 40;
                  return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#0ea5e9" strokeWidth="2" opacity="0.8" />;
                })}
                <text x="2" y="13" fill="#94a3b8" fontSize="7" fontFamily="monospace">FL410</text>
                <text x="2" y="33" fill="#94a3b8" fontSize="7" fontFamily="monospace">FL370</text>
                <text x="2" y="53" fill="#94a3b8" fontSize="7" fontFamily="monospace">FL330</text>
                <text x="2" y="73" fill="#94a3b8" fontSize="7" fontFamily="monospace">FL300</text>
              </svg>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
