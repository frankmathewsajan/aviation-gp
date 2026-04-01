export default function PathLegend({ visible }) {
  if (!visible) return null;

  return (
    <div className="fixed bottom-3 left-1/2 -translate-x-1/2 z-[997] flex items-center gap-5 px-5 py-2.5 bg-white/85 backdrop-blur-lg rounded-full shadow-md border border-stone-200/50 text-[10px] text-stone-500 font-medium">
      <div className="flex items-center gap-2">
        <div className="w-5 h-0 border-t border-dashed border-stone-300" />
        <span>Baseline</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="w-6 h-0.5 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-400" />
        <span>Optimized (ISSR)</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-emerald-400" />
        <span>Low</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-amber-400" />
        <span>Med</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-red-400" />
        <span>High</span>
      </div>
    </div>
  );
}
