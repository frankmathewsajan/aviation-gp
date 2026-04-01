/**
 * ISSR risk → color gradient utilities for GreenPath.
 * Maps intensity values to a green → yellow → red gradient.
 */

/**
 * Get color for an ISSR intensity value.
 * @param {number} intensity - ISSR intensity (0-30+)
 * @returns {string} CSS color string
 */
export function getISSRColor(intensity) {
  if (intensity <= 0) return '#00ff88';
  if (intensity <= 3) {
    const t = intensity / 3;
    return interpolateColor('#00ff88', '#88ff00', t);
  }
  if (intensity <= 8) {
    const t = (intensity - 3) / 5;
    return interpolateColor('#88ff00', '#ffdd00', t);
  }
  if (intensity <= 15) {
    const t = (intensity - 8) / 7;
    return interpolateColor('#ffdd00', '#ff6b35', t);
  }
  const t = Math.min((intensity - 15) / 10, 1);
  return interpolateColor('#ff6b35', '#ff3355', t);
}

/**
 * Get contrail risk label and color.
 */
export function getRiskInfo(risk) {
  switch (risk) {
    case 'high':
      return { color: '#ff3355', label: 'High Risk', bg: 'rgba(255, 51, 85, 0.15)' };
    case 'medium':
      return { color: '#ffdd00', label: 'Medium Risk', bg: 'rgba(255, 221, 0, 0.15)' };
    case 'low':
    default:
      return { color: '#00ff88', label: 'Low Risk', bg: 'rgba(0, 255, 136, 0.15)' };
  }
}

/**
 * Interpolate between two hex colors.
 */
function interpolateColor(color1, color2, t) {
  const r1 = parseInt(color1.slice(1, 3), 16);
  const g1 = parseInt(color1.slice(3, 5), 16);
  const b1 = parseInt(color1.slice(5, 7), 16);
  const r2 = parseInt(color2.slice(1, 3), 16);
  const g2 = parseInt(color2.slice(3, 5), 16);
  const b2 = parseInt(color2.slice(5, 7), 16);

  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);

  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

/**
 * Generate heatmap weight from ISSR intensity.
 */
export function intensityToHeatWeight(intensity) {
  return Math.min(intensity / 20, 1.0);
}
