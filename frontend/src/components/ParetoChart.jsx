import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

export default function ParetoChart({ data, selectedId, onSelect }) {
  const svgRef = useRef(null);
  const tooltipRef = useRef(null);

  useEffect(() => {
    if (!data || data.length === 0 || !svgRef.current) return;

    const container = svgRef.current.parentElement;
    const width = container.clientWidth - 16;
    const height = 180;
    const margin = { top: 12, right: 12, bottom: 32, left: 44 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    const xScale = d3.scaleLinear().domain(d3.extent(data, d => d.co2_kg)).nice().range([0, innerW]);
    const yScale = d3.scaleLinear().domain(d3.extent(data, d => d.contrail_ef)).nice().range([innerH, 0]);
    const sizeScale = d3.scaleLinear().domain(d3.extent(data, d => d.time_min)).range([3, 10]);

    // Grid
    g.selectAll('line.gx').data(xScale.ticks(4)).enter().append('line')
      .attr('x1', d => xScale(d)).attr('x2', d => xScale(d)).attr('y1', 0).attr('y2', innerH)
      .attr('stroke', '#e5e7eb').attr('stroke-dasharray', '2,3');
    g.selectAll('line.gy').data(yScale.ticks(4)).enter().append('line')
      .attr('x1', 0).attr('x2', innerW).attr('y1', d => yScale(d)).attr('y2', d => yScale(d))
      .attr('stroke', '#e5e7eb').attr('stroke-dasharray', '2,3');

    // Axes
    g.append('g').attr('transform', `translate(0,${innerH})`).call(d3.axisBottom(xScale).ticks(4).tickFormat(d => `${(d/1000).toFixed(0)}k`))
      .selectAll('text').attr('fill', '#9ca3af').attr('font-size', '8px').attr('font-family', 'monospace');
    g.append('g').call(d3.axisLeft(yScale).ticks(4).tickFormat(d => d.toFixed(0)))
      .selectAll('text').attr('fill', '#9ca3af').attr('font-size', '8px').attr('font-family', 'monospace');

    g.append('text').attr('x', innerW / 2).attr('y', innerH + 26).attr('text-anchor', 'middle').attr('fill', '#9ca3af').attr('font-size', '9px').text('CO₂ (kg)');
    g.append('text').attr('transform', 'rotate(-90)').attr('x', -innerH / 2).attr('y', -34).attr('text-anchor', 'middle').attr('fill', '#9ca3af').attr('font-size', '9px').text('Contrail EF');

    g.selectAll('.domain').attr('stroke', '#e5e7eb');
    g.selectAll('.tick line').attr('stroke', '#e5e7eb');

    const tooltip = d3.select(tooltipRef.current);

    // Points
    g.selectAll('circle.dp').data(data).enter().append('circle')
      .attr('cx', d => xScale(d.co2_kg))
      .attr('cy', d => yScale(d.contrail_ef))
      .attr('r', d => sizeScale(d.time_min))
      .attr('fill', d => d.path_id === selectedId ? '#f97316' : '#38bdf8')
      .attr('fill-opacity', d => d.path_id === selectedId ? 0.9 : 0.5)
      .attr('stroke', d => d.path_id === selectedId ? '#f97316' : '#38bdf8')
      .attr('stroke-width', d => d.path_id === selectedId ? 2 : 1)
      .attr('stroke-opacity', d => d.path_id === selectedId ? 1 : 0.3)
      .attr('cursor', 'pointer')
      .on('mouseover', function (event, d) {
        d3.select(this).transition().duration(150).attr('r', sizeScale(d.time_min) + 3).attr('fill-opacity', 1);
        tooltip.style('left', `${event.offsetX + 12}px`).style('top', `${event.offsetY - 12}px`).style('opacity', 1)
          .html(`<div class="text-[10px] space-y-0.5"><div class="flex justify-between gap-3"><span class="text-stone-400">CO₂</span><span class="font-mono font-bold text-stone-800">${d.co2_kg.toLocaleString()} kg</span></div><div class="flex justify-between gap-3"><span class="text-stone-400">EF</span><span class="font-mono font-bold text-stone-800">${d.contrail_ef.toFixed(1)}</span></div><div class="flex justify-between gap-3"><span class="text-stone-400">Time</span><span class="font-mono font-bold text-stone-800">${d.time_min.toFixed(0)} min</span></div></div>`);
      })
      .on('mouseout', function (event, d) {
        d3.select(this).transition().duration(150).attr('r', sizeScale(d.time_min)).attr('fill-opacity', d.path_id === selectedId ? 0.9 : 0.5);
        tooltip.style('opacity', 0);
      })
      .on('click', function (event, d) { if (onSelect) onSelect(d.path_id); });

    // Selected glow
    if (selectedId !== null) {
      const sp = data.find(d => d.path_id === selectedId);
      if (sp) {
        g.append('circle').attr('cx', xScale(sp.co2_kg)).attr('cy', yScale(sp.contrail_ef))
          .attr('r', sizeScale(sp.time_min) + 6).attr('fill', 'none').attr('stroke', '#f97316')
          .attr('stroke-width', 1).attr('stroke-opacity', 0.3);
      }
    }
  }, [data, selectedId, onSelect]);

  return (
    <div className="relative">
      <svg ref={svgRef} />
      <div ref={tooltipRef} className="absolute pointer-events-none bg-white rounded-lg shadow-lg border border-stone-100 px-3 py-2 opacity-0 transition-opacity z-50" />
    </div>
  );
}
