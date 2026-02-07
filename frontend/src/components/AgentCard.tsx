interface AgentCardProps {
  name: string;
  model: string;
  status: "pending" | "running" | "done" | "failed";
  output: string;
  cost?: number;
  tokens?: number;
}

function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

function formatCost(n: number): string {
  return `$${n.toFixed(4)}`;
}

export function AgentCard({ name, model, status, output, cost, tokens }: AgentCardProps) {
  const statusColors = {
    pending: "bg-slate-100 text-slate-500",
    running: "bg-blue-100 text-blue-700",
    done: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };

  const statusIcons = {
    pending: "\u23F3",
    running: "\u26A1",
    done: "\u2713",
    failed: "\u2717",
  };

  const showCostInfo = status === "done" && (typeof tokens === "number" || typeof cost === "number");

  return (
    <div className="panel rounded-lg border p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="font-semibold text-sm">{name}</span>
          <span className="ml-2 text-xs text-slate-500">{model.split("/").pop()}</span>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[status]}`}>
            {statusIcons[status]} {status}
          </span>
          {showCostInfo && (
            <span className="text-[11px] font-medium" style={{ color: "#1f4d3d" }}>
              {typeof tokens === "number" && <>{formatTokens(tokens)} tokens</>}
              {typeof tokens === "number" && typeof cost === "number" && " \u00b7 "}
              {typeof cost === "number" && formatCost(cost)}
            </span>
          )}
        </div>
      </div>
      {output && (
        <pre className="mt-2 max-h-48 overflow-y-auto rounded bg-slate-50 p-3 text-xs font-mono whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </div>
  );
}
