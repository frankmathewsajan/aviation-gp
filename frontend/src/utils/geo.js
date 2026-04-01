/**
 * Geographic utilities for GreenPath.
 * Great circle calculations and path interpolation.
 */

const R = 6371; // Earth radius in km

/**
 * Haversine distance in km.
 */
export function haversineDistance(lat1, lon1, lat2, lon2) {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Generate great circle waypoints.
 */
export function greatCirclePoints(lat1, lon1, lat2, lon2, n = 50) {
  const lat1r = toRad(lat1), lon1r = toRad(lon1);
  const lat2r = toRad(lat2), lon2r = toRad(lon2);
  const d = 2 * Math.asin(Math.sqrt(
    Math.sin((lat2r - lat1r) / 2) ** 2 +
    Math.cos(lat1r) * Math.cos(lat2r) * Math.sin((lon2r - lon1r) / 2) ** 2
  ));

  if (d < 1e-10) return Array(n).fill([lat1, lon1]);

  const points = [];
  for (let i = 0; i < n; i++) {
    const f = i / (n - 1);
    const a = Math.sin((1 - f) * d) / Math.sin(d);
    const b = Math.sin(f * d) / Math.sin(d);
    const x = a * Math.cos(lat1r) * Math.cos(lon1r) + b * Math.cos(lat2r) * Math.cos(lon2r);
    const y = a * Math.cos(lat1r) * Math.sin(lon1r) + b * Math.cos(lat2r) * Math.sin(lon2r);
    const z = a * Math.sin(lat1r) + b * Math.sin(lat2r);
    const lat = toDeg(Math.atan2(z, Math.sqrt(x ** 2 + y ** 2)));
    const lon = toDeg(Math.atan2(y, x));
    points.push([lat, lon]);
  }
  return points;
}

/**
 * Get bounds for an array of [{lat, lon}] points.
 */
export function getPathBounds(points) {
  if (!points || points.length === 0) return null;
  let minLat = Infinity, maxLat = -Infinity;
  let minLon = Infinity, maxLon = -Infinity;
  for (const p of points) {
    const lat = p.lat || p[0];
    const lon = p.lon || p[1];
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
    minLon = Math.min(minLon, lon);
    maxLon = Math.max(maxLon, lon);
  }
  return [[minLat - 2, minLon - 2], [maxLat + 2, maxLon + 2]];
}

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function toDeg(rad) {
  return (rad * 180) / Math.PI;
}
