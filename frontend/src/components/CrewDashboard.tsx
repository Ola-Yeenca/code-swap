import { AgentCard } from "./AgentCard";
import { useAppStore } from "../store/appStore";

export function CrewDashboard() {
  const { agentOutputs, synthesisText, crewTotalCost, crewBudget } = useAppStore();
  const agents = Object.entries(agentOutputs);

  const hasAnyDone = agents.some(([, data]) => data.status === "done");

  const totalTokens = agents.reduce((sum, [, data]) => sum + (data.tokens ?? 0), 0);
  const totalCost = crewTotalCost > 0
    ? crewTotalCost
    : agents.reduce((sum, [, data]) => sum + (data.cost ?? 0), 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {agents.map(([name, data]) => (
          <AgentCard
            key={name}
            name={name}
            model={data.model}
            status={data.status as "pending" | "running" | "done" | "failed"}
            output={data.text}
            cost={data.cost}
            tokens={data.tokens}
          />
        ))}
      </div>

      {hasAnyDone && (totalTokens > 0 || totalCost > 0) && (
        <div
          className="panel rounded-lg border px-4 py-2.5 flex items-center justify-between text-sm"
          style={{ borderColor: "#b26a2b40" }}
        >
          <span className="font-medium" style={{ color: "#111013" }}>
            Total
          </span>
          <span className="font-mono text-xs" style={{ color: "#1f4d3d" }}>
            {totalTokens > 0 && <>{totalTokens.toLocaleString("en-US")} tokens &middot; </>}
            ${totalCost.toFixed(4)} / ${crewBudget.toFixed(2)} budget
          </span>
        </div>
      )}

      {synthesisText && (
        <section className="panel rounded-lg border p-4">
          <h3 className="font-semibold text-sm mb-2">Synthesis</h3>
          <div className="prose prose-sm max-w-none whitespace-pre-wrap">{synthesisText}</div>
        </section>
      )}
    </div>
  );
}
