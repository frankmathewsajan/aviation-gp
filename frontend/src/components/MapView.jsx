import { useEffect, useRef, useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getISSRColor, getRiskInfo } from '../utils/colors';

function FitBounds({ bounds }) {
  const map = useMap();
  const lastBoundsRef = useRef(null);

  useEffect(() => {
    if (!bounds) return;
    const boundsKey = JSON.stringify(bounds);
    if (boundsKey !== lastBoundsRef.current) {
      lastBoundsRef.current = boundsKey;
      map.fitBounds(bounds, { padding: [60, 60], maxZoom: 6, animate: true });
    }
  }, [bounds, map]);

  return null;
}

function NOAAOverlay({ points, visible }) {
  const map = useMap();
  const canvasLayerRef = useRef(null);

  useEffect(() => {
    if (canvasLayerRef.current) {
      map.removeLayer(canvasLayerRef.current);
      canvasLayerRef.current = null;
    }
    if (!visible || !points || points.length === 0) return;

    const CanvasOverlay = L.GridLayer.extend({
      _data: points,
      _gridSize: 1.0,
      createTile(coords) {
        const tile = document.createElement('canvas');
        const size = this.getTileSize();
        tile.width = size.x;
        tile.height = size.y;
        const ctx = tile.getContext('2d');

        const nwPoint = coords.scaleBy(size);
        const nw = map.unproject(nwPoint, coords.z);
        const se = map.unproject(nwPoint.add(size), coords.z);
        const tileBounds = { minLat: Math.min(nw.lat, se.lat), maxLat: Math.max(nw.lat, se.lat), minLon: Math.min(nw.lng, se.lng), maxLon: Math.max(nw.lng, se.lng) };
        const latRange = tileBounds.maxLat - tileBounds.minLat;
        const lonRange = tileBounds.maxLon - tileBounds.minLon;

        for (const p of this._data) {
          if (p.issr_intensity < 0.3) continue;
          const cs = this._gridSize;
          const pMinLat = p.lat - cs / 2, pMaxLat = p.lat + cs / 2;
          const pMinLon = p.lon - cs / 2, pMaxLon = p.lon + cs / 2;
          if (pMaxLat < tileBounds.minLat || pMinLat > tileBounds.maxLat) continue;
          if (pMaxLon < tileBounds.minLon || pMinLon > tileBounds.maxLon) continue;

          const x1 = ((pMinLon - tileBounds.minLon) / lonRange) * size.x;
          const y1 = ((tileBounds.maxLat - pMaxLat) / latRange) * size.y;
          const x2 = ((pMaxLon - tileBounds.minLon) / lonRange) * size.x;
          const y2 = ((tileBounds.maxLat - pMinLat) / latRange) * size.y;
          const intensity = Math.min(p.issr_intensity / 20, 1);
          const alpha = 0.08 + intensity * 0.35;

          if (intensity < 0.25) ctx.fillStyle = `rgba(16, 185, 129, ${alpha})`;
          else if (intensity < 0.5) ctx.fillStyle = `rgba(245, 158, 11, ${alpha})`;
          else if (intensity < 0.75) ctx.fillStyle = `rgba(239, 68, 68, ${alpha})`;
          else ctx.fillStyle = `rgba(190, 24, 93, ${alpha})`;

          ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
        }
        return tile;
      },
    });

    canvasLayerRef.current = new CanvasOverlay({ opacity: 0.7, zIndex: 200 });
    canvasLayerRef.current.addTo(map);

    return () => {
      if (canvasLayerRef.current) { map.removeLayer(canvasLayerRef.current); canvasLayerRef.current = null; }
    };
  }, [points, visible, map]);

  return null;
}

function AircraftAnimation({ path }) {
  const map = useMap();
  const markerRef = useRef(null);
  const animRef = useRef(null);

  useEffect(() => {
    if (!path || path.length < 2) return;
    if (markerRef.current) map.removeLayer(markerRef.current);
    const icon = L.divIcon({ className: 'aircraft-marker', html: '<div class="aircraft-marker-icon">✈</div>', iconSize: [24, 24], iconAnchor: [12, 12] });
    markerRef.current = L.marker([path[0].lat, path[0].lon], { icon, zIndexOffset: 1000 }).addTo(map);
    let idx = 0;
    const animate = () => {
      if (idx >= path.length) idx = 0;
      const p = path[idx];
      markerRef.current.setLatLng([p.lat, p.lon]);
      if (idx < path.length - 1) {
        const next = path[idx + 1];
        const angle = Math.atan2(next.lon - p.lon, next.lat - p.lat) * (180 / Math.PI);
        const el = markerRef.current.getElement();
        if (el) el.style.transform = el.style.transform.replace(/rotate\([^)]*\)/, '') + ` rotate(${90 - angle}deg)`;
      }
      idx++;
      animRef.current = setTimeout(animate, 150);
    };
    animate();
    return () => { if (animRef.current) clearTimeout(animRef.current); if (markerRef.current) map.removeLayer(markerRef.current); };
  }, [path, map]);

  return null;
}

export default function MapView({ results, showNoaaOverlay }) {
  const bounds = useMemo(() => {
    if (!results) return null;
    const allPoints = [...(results.selected_path || []), ...(results.baseline_path || [])];
    if (allPoints.length === 0) return null;
    let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
    for (const p of allPoints) { minLat = Math.min(minLat, p.lat); maxLat = Math.max(maxLat, p.lat); minLon = Math.min(minLon, p.lon); maxLon = Math.max(maxLon, p.lon); }
    return [[minLat - 3, minLon - 3], [maxLat + 3, maxLon + 3]];
  }, [results]);

  const pathSegments = useMemo(() => {
    if (!results?.selected_path) return [];
    const segments = [];
    const path = results.selected_path;
    for (let i = 0; i < path.length - 1; i++) {
      const p1 = path[i], p2 = path[i + 1];
      const avg = (p1.issr_intensity + p2.issr_intensity) / 2;
      segments.push({ positions: [[p1.lat, p1.lon], [p2.lat, p2.lon]], color: getISSRColor(avg), intensity: avg });
    }
    return segments;
  }, [results]);

  const baselinePath = useMemo(() => {
    if (!results?.baseline_path) return [];
    return results.baseline_path.map(p => [p.lat, p.lon]);
  }, [results]);

  const waypoints = useMemo(() => {
    if (!results?.selected_path) return [];
    const path = results.selected_path;
    const step = Math.max(1, Math.floor(path.length / 10));
    return path.filter((_, i) => i % step === 0 || i === path.length - 1);
  }, [results]);

  return (
    <div className="flex-1 h-full relative">
      <MapContainer center={[35, -20]} zoom={3} zoomControl={true} style={{ height: '100%', width: '100%' }}>
        {/* Light map tiles — CartoDB Positron */}
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
          maxZoom={18}
        />
        {bounds && <FitBounds bounds={bounds} />}
        {results?.atmosphere_sample && <NOAAOverlay points={results.atmosphere_sample} visible={showNoaaOverlay} />}

        {/* Baseline */}
        {baselinePath.length > 0 && (
          <Polyline positions={baselinePath} pathOptions={{ color: '#d1d5db', weight: 1.5, dashArray: '6, 8', opacity: 0.7 }} />
        )}

        {/* Optimized path segments */}
        {pathSegments.map((seg, i) => (
          <Polyline key={i} positions={seg.positions} pathOptions={{ color: seg.color, weight: 3.5, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }} />
        ))}

        {/* Waypoints */}
        {waypoints.map((wp, i) => {
          const ri = getRiskInfo(wp.contrail_risk);
          return (
            <CircleMarker key={i} center={[wp.lat, wp.lon]} radius={4} pathOptions={{ color: ri.color, fillColor: ri.color, fillOpacity: 0.85, weight: 1 }}>
              <Popup>
                <div className="font-mono font-bold text-stone-800 mb-1">Waypoint {i + 1}</div>
                <div className="flex justify-between text-xs text-stone-500 gap-3"><span>Alt</span><span className="font-mono font-semibold text-stone-800">{wp.alt_ft?.toLocaleString()} ft</span></div>
                <div className="flex justify-between text-xs text-stone-500 gap-3"><span>ISSR</span><span className="font-mono font-semibold text-stone-800">{wp.issr_intensity?.toFixed(1)}%</span></div>
                <div className="flex justify-between text-xs text-stone-500 gap-3"><span>Risk</span><span className="font-semibold" style={{ color: ri.color }}>{ri.label}</span></div>
              </Popup>
            </CircleMarker>
          );
        })}

        {results?.selected_path && <AircraftAnimation path={results.selected_path} />}

        {results?.origin && (
          <CircleMarker center={[results.origin.lat, results.origin.lon]} radius={7} pathOptions={{ color: '#0ea5e9', fillColor: '#0ea5e9', fillOpacity: 1, weight: 2 }}>
            <Popup><div className="font-mono font-bold text-stone-800">{results.origin.code}</div><div className="text-xs text-stone-400">{results.origin.name}</div></Popup>
          </CircleMarker>
        )}
        {results?.destination && (
          <CircleMarker center={[results.destination.lat, results.destination.lon]} radius={7} pathOptions={{ color: '#f97316', fillColor: '#f97316', fillOpacity: 1, weight: 2 }}>
            <Popup><div className="font-mono font-bold text-stone-800">{results.destination.code}</div><div className="text-xs text-stone-400">{results.destination.name}</div></Popup>
          </CircleMarker>
        )}
      </MapContainer>

      {/* NOAA legend */}
      {showNoaaOverlay && results && (
        <div className="absolute bottom-20 right-[340px] z-[998] bg-white/90 backdrop-blur-lg rounded-xl shadow-md border border-stone-200/50 px-3 py-2.5">
          <div className="text-[9px] font-bold text-stone-400 uppercase tracking-wider mb-1.5">🛰️ ISSR Intensity</div>
          {[['bg-emerald-400/50', 'Low'], ['bg-amber-400/50', 'Moderate'], ['bg-red-400/50', 'High'], ['bg-pink-700/50', 'Severe']].map(([bg, label]) => (
            <div key={label} className="flex items-center gap-2 text-[10px] text-stone-500 mb-0.5">
              <div className={`w-3 h-2 rounded-sm ${bg}`} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
