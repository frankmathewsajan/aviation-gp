import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Separator } from '@/components/ui/separator';
import { Label } from '@/components/ui/label';

const AIRCRAFT_OPTIONS = [
  { id: 'A320', fullName: 'Airbus A320-200', speed: '230 m/s', range: '3,300 nm' },
  { id: 'B738', fullName: 'Boeing 737-800', speed: '225 m/s', range: '3,115 nm' },
  { id: 'B77W', fullName: 'Boeing 777-300ER', speed: '255 m/s', range: '7,370 nm' },
  { id: 'A35K', fullName: 'Airbus A350-1000', speed: '252 m/s', range: '8,700 nm' },
];

function AirportInput({ label, icon, value, onChange, onSelect, geocode, placeholder }) {
  const [suggestions, setSuggestions] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const debounceRef = useRef(null);
  const wrapperRef = useRef(null);

  const handleChange = (e) => {
    const val = e.target.value;
    onChange(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (val.length >= 2) {
        const results = await geocode(val);
        setSuggestions(results);
        setShowDropdown(results.length > 0);
      } else {
        setSuggestions([]);
        setShowDropdown(false);
      }
    }, 300);
  };

  const handleSelect = (airport) => {
    onSelect(airport.code);
    onChange(airport.code);
    setShowDropdown(false);
  };

  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div className="relative" ref={wrapperRef}>
      <button className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-stone-50 transition-colors rounded-lg group">
        <div className="flex items-center gap-3">
          <span className="text-stone-400 text-base w-5 text-center">{icon}</span>
          <span className="text-sm font-medium text-stone-600">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={value}
            onChange={handleChange}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
            placeholder={placeholder}
            className="w-20 text-right text-sm font-semibold text-stone-900 bg-transparent border-none outline-none focus:ring-0 placeholder:text-stone-300"
            autoComplete="off"
          />
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" className="text-stone-300">
            <path d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </button>
      {showDropdown && (
        <div className="absolute top-full left-4 right-4 z-50 mt-1 bg-white rounded-xl shadow-lg border border-stone-100 max-h-48 overflow-y-auto">
          {suggestions.map((s, i) => (
            <div key={i} onClick={() => handleSelect(s)}
              className="px-4 py-2.5 flex items-center gap-2 hover:bg-stone-50 cursor-pointer text-sm border-b border-stone-50 last:border-0 transition-colors">
              <span className="font-mono font-bold text-stone-800 text-xs">{s.code}</span>
              <span className="text-stone-400 text-xs truncate">{s.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ControlPanel({ onOptimize, onWeightsChange, loading, geocode, gfsSource, onCollapse, useCache, onToggleCache }) {
  const [origin, setOrigin] = useState('JFK');
  const [destination, setDestination] = useState('LHR');
  const [aircraft, setAircraft] = useState('A320');
  const [departure, setDeparture] = useState('2025-01-15T10:00');
  const [weights, setWeights] = useState({ co2: 40, contrail: 40, time: 20 });
  const [useNoaa, setUseNoaa] = useState(true);
  const [showAircraftMenu, setShowAircraftMenu] = useState(false);
  const weightsDebounceRef = useRef(null);

  const selectedAircraft = AIRCRAFT_OPTIONS.find(a => a.id === aircraft);

  const handleWeightChange = useCallback((key, newVal) => {
    setWeights(prev => {
      const val = newVal[0] ?? newVal;
      const others = Object.keys(prev).filter(k => k !== key);
      const remaining = 100 - val;
      const currentOthersSum = others.reduce((s, k) => s + prev[k], 0);
      const newWeights = { ...prev, [key]: val };
      if (currentOthersSum > 0) {
        for (const k of others) {
          newWeights[k] = Math.round((prev[k] / currentOthersSum) * remaining);
        }
      } else {
        const share = Math.round(remaining / others.length);
        others.forEach(k => { newWeights[k] = share; });
      }
      const diff = 100 - Object.values(newWeights).reduce((s, v) => s + v, 0);
      if (diff !== 0) newWeights[others[0]] += diff;
      return newWeights;
    });
  }, []);

  useEffect(() => {
    if (weightsDebounceRef.current) clearTimeout(weightsDebounceRef.current);
    weightsDebounceRef.current = setTimeout(() => {
      if (onWeightsChange) onWeightsChange(weights);
    }, 200);
  }, [weights, onWeightsChange]);

  const handleSubmit = () => {
    const depIso = new Date(departure).toISOString();
    onOptimize({ origin, destination, aircraft, departureIso: depIso, weights, useNoaa });
  };

  return (
    <div className="w-[340px] h-full bg-white/90 backdrop-blur-xl border-r border-stone-200/60 flex flex-col shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-2">
        <button onClick={onCollapse} className="w-8 h-8 rounded-full border border-stone-200 flex items-center justify-center hover:bg-stone-50 transition-colors cursor-pointer">
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" className="text-stone-400">
            <path d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold tracking-wider text-stone-800 bg-stone-100 px-2.5 py-1 rounded-full">PRO</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-1">
        {/* Airport inputs */}
        <AirportInput label="Origin" icon={<i className="fa-solid fa-plane-departure" />} value={origin} onChange={setOrigin} onSelect={setOrigin} geocode={geocode} placeholder="JFK" />
        <AirportInput label="Destination" icon={<i className="fa-solid fa-location-dot" />} value={destination} onChange={setDestination} onSelect={setDestination} geocode={geocode} placeholder="LHR" />

        <div className="px-4"><Separator className="my-1" /></div>

        {/* Aircraft selector */}
        <div className="relative">
          <button onClick={() => setShowAircraftMenu(v => !v)}
            className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-stone-50 transition-colors rounded-lg">
            <div className="flex items-center gap-3">
              <span className="text-stone-400 text-base w-5 text-center"><i className="fa-solid fa-plane" /></span>
              <span className="text-sm font-medium text-stone-600">Aircraft Type</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-stone-900">{aircraft}</span>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" className="text-stone-300">
                <path d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>
          {showAircraftMenu && (
            <div className="absolute left-4 right-4 top-full z-50 bg-white rounded-xl shadow-lg border border-stone-100 overflow-hidden">
              {AIRCRAFT_OPTIONS.map(ac => (
                <button key={ac.id} onClick={() => { setAircraft(ac.id); setShowAircraftMenu(false); }}
                  className={`w-full px-4 py-3 flex items-center justify-between text-left hover:bg-stone-50 transition-colors border-b border-stone-50 last:border-0 cursor-pointer ${aircraft === ac.id ? 'bg-stone-50' : ''}`}>
                  <div>
                    <div className="text-sm font-bold text-stone-800">{ac.id}</div>
                    <div className="text-xs text-stone-400">{ac.fullName}</div>
                  </div>
                  <span className="text-xs font-mono text-stone-400">{ac.speed}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Departure */}
        <button className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-stone-50 transition-colors rounded-lg">
          <div className="flex items-center gap-3">
            <span className="text-stone-400 text-base w-5 text-center"><i className="fa-regular fa-clock" /></span>
            <span className="text-sm font-medium text-stone-600">Departure</span>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="datetime-local"
              value={departure}
              onChange={e => setDeparture(e.target.value)}
              className="text-sm font-semibold text-stone-900 bg-transparent border-none outline-none w-40 text-right"
            />
          </div>
        </button>

        {/* NOAA toggle */}
        <div className="flex items-center justify-between px-4 py-3.5">
          <div className="flex items-center gap-3">
            <span className="text-stone-400 text-base w-5 text-center"><i className="fa-solid fa-satellite" /></span>
            <div>
              <span className="text-sm font-medium text-stone-600">NOAA GFS Data</span>
              <p className="text-[10px] text-stone-400 mt-0.5">
                {useNoaa ? 'Live atmospheric data' : 'Synthetic fallback'}
              </p>
            </div>
          </div>
          <Switch checked={useNoaa} onCheckedChange={setUseNoaa} />
        </div>

        {/* Cache toggle */}
        <div className="flex items-center justify-between px-4 py-3.5">
          <div className="flex items-center gap-3">
            <span className="text-stone-400 text-base w-5 text-center"><i className="fa-solid fa-database" /></span>
            <div>
              <span className="text-sm font-medium text-stone-600">Route Cache</span>
              <p className="text-[10px] text-stone-400 mt-0.5">
                {useCache ? 'Use cached results if available' : 'Force fresh optimization'}
              </p>
            </div>
          </div>
          <Switch checked={useCache} onCheckedChange={onToggleCache} />
        </div>

        <div className="px-4"><Separator className="my-1" /></div>

        {/* Optimization weights */}
        <div className="px-4 py-3">
          <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-3">Optimization Weights</div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <Label className="text-xs text-stone-600 font-medium"><i className="fa-solid fa-leaf text-emerald-500 mr-1.5" /> Minimize CO₂</Label>
                <span className="text-xs font-mono font-bold text-stone-800">{weights.co2}%</span>
              </div>
              <Slider value={[weights.co2]} max={100} step={1} onValueChange={(v) => handleWeightChange('co2', v)} />
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <Label className="text-xs text-stone-600 font-medium"><i className="fa-solid fa-cloud text-sky-400 mr-1.5" /> Minimize Contrails</Label>
                <span className="text-xs font-mono font-bold text-stone-800">{weights.contrail}%</span>
              </div>
              <Slider value={[weights.contrail]} max={100} step={1} onValueChange={(v) => handleWeightChange('contrail', v)} />
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <Label className="text-xs text-stone-600 font-medium"><i className="fa-solid fa-stopwatch text-amber-500 mr-1.5" /> Minimize Time</Label>
                <span className="text-xs font-mono font-bold text-stone-800">{weights.time}%</span>
              </div>
              <Slider value={[weights.time]} max={100} step={1} onValueChange={(v) => handleWeightChange('time', v)} />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom action */}
      <div className="px-5 py-4 border-t border-stone-100">
        <Button
          onClick={handleSubmit}
          disabled={loading || !origin || !destination}
          className="w-full h-12 rounded-2xl text-sm font-bold tracking-wide"
          size="lg"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Optimizing…
            </span>
          ) : (
            'Generate Flight Path'
          )}
        </Button>

        {gfsSource && (
          <div className="text-center mt-2">
            <span className={`text-[10px] font-mono ${gfsSource === 'noaa_live' ? 'text-emerald-500' : 'text-amber-500'}`}>
              ● {gfsSource === 'noaa_live' ? 'NOAA GFS Live' : 'Synthetic Fallback'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
