import { useAppStore } from "../store/appStore";

function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`;
  }
  return count.toLocaleString();
}

function formatCost(cost: number): string {
  if (cost < 0.01) {
    return `$${cost.toFixed(4)}`;
  }
  return `$${cost.toFixed(2)}`;
}

export function CostBadge() {
  const { sessionTokensIn, sessionTokensOut, sessionCost, resetUsage } = useAppStore();

  if (sessionTokensIn === 0 && sessionTokensOut === 0 && sessionCost === 0) {
    return null;
  }

  return (
    <div className="panel px-3 py-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Session Cost</p>
        <button
          className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
          onClick={resetUsage}
          title="Reset session counters"
          type="button"
        >
          Reset
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-sm font-mono">
        <span className="text-slate-500" title="Input tokens">
          <span className="text-[10px] opacity-60">IN</span>{" "}
          {formatTokens(sessionTokensIn)}
        </span>
        <span className="text-slate-500" title="Output tokens">
          <span className="text-[10px] opacity-60">OUT</span>{" "}
          {formatTokens(sessionTokensOut)}
        </span>
        <span className="ml-auto font-semibold" style={{ color: "var(--pine)" }} title="Estimated cost">
          {formatCost(sessionCost)}
        </span>
      </div>
    </div>
  );
}
