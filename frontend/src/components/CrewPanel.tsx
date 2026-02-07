import { useState } from "react";
import { streamCrewChat } from "../api/client";
import { useAppStore } from "../store/appStore";
import { CrewDashboard } from "./CrewDashboard";

interface CrewPanelProps {
  sessionId: string;
}

const CREW_OPTIONS = [
  { value: "default", label: "Default \u2014 Claude codes, GPT reviews", desc: "Right model per task. Clear cost per agent." },
  { value: "full-stack", label: "Full Stack \u2014 GPT + Claude + Gemini + DeepSeek", desc: "Best model per role. See cost per agent." },
  { value: "code-review", label: "Code Review \u2014 Multi-perspective analysis", desc: "Claude analyzes, GPT checks security, Gemini reviews style." },
  { value: "research", label: "Research \u2014 Deep reasoning + synthesis", desc: "DeepSeek thinks, Claude compiles. Every dollar visible." },
];

export function CrewPanel({ sessionId }: CrewPanelProps) {
  const { crewName, setCrewName, crewBudget, updateAgentOutput, setSynthesisText, setCrewTotalCost, resetCrewState } = useAppStore();
  const [task, setTask] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedCrew = CREW_OPTIONS.find((o) => o.value === crewName);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!task.trim() || isRunning) return;

    setIsRunning(true);
    setError(null);
    resetCrewState();

    try {
      const stream = await streamCrewChat({
        sessionId,
        task: task.trim(),
        crewName,
      });

      for await (const event of stream) {
        switch (event.type) {
          case "crew_start":
            event.agents?.forEach((a: string) => updateAgentOutput(a, { status: "pending", text: "", model: "" }));
            break;
          case "agent_start":
            if (event.agent) updateAgentOutput(event.agent, { status: "running", model: event.model || "" });
            break;
          case "agent_delta":
            if (event.agent && event.text) {
              updateAgentOutput(event.agent, {
                text: (useAppStore.getState().agentOutputs[event.agent]?.text || "") + event.text,
              });
            }
            break;
          case "agent_done":
            if (event.agent) {
              updateAgentOutput(event.agent, {
                status: "done",
                ...(typeof event.cost === "number" ? { cost: event.cost } : {}),
                ...(typeof event.tokens === "number" ? { tokens: event.tokens } : {}),
              });
            }
            break;
          case "crew_done":
            if (typeof event.totalCost === "number") setCrewTotalCost(event.totalCost);
            break;
          case "synthesis_delta":
            if (event.text) setSynthesisText(event.text);
            break;
          case "error":
            setError(event.message || "Unknown error");
            break;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stream failed");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="font-semibold text-lg mb-3">Crew Mode</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Crew</label>
            <div className="space-y-1.5">
              {CREW_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                    crewName === opt.value
                      ? "border-brass bg-[#b26a2b0a]"
                      : "border-slate-200 hover:border-slate-300"
                  } ${isRunning ? "pointer-events-none opacity-60" : ""}`}
                >
                  <input
                    type="radio"
                    name="crew"
                    value={opt.value}
                    checked={crewName === opt.value}
                    onChange={() => setCrewName(opt.value)}
                    disabled={isRunning}
                    className="mt-0.5 accent-[#b26a2b]"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium" style={{ color: "#111013" }}>{opt.label}</span>
                    <p className="text-xs mt-0.5" style={{ color: "#6b7280" }}>{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Task</label>
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              rows={3}
              placeholder="Describe the task for the crew..."
              disabled={isRunning}
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={isRunning || !task.trim()}
              className="flex-1 rounded bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {isRunning ? "Running..." : "Run Crew"}
            </button>
            <span
              className="text-xs font-mono px-2.5 py-1.5 rounded-full border whitespace-nowrap"
              style={{ borderColor: "#b26a2b60", color: "#b26a2b" }}
            >
              ${crewBudget.toFixed(2)} budget
            </span>
          </div>
        </form>
        {selectedCrew && crewName !== CREW_OPTIONS[0].value && (
          <p className="mt-2 text-xs" style={{ color: "#1f4d3d" }}>
            {selectedCrew.desc}
          </p>
        )}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>
      <CrewDashboard />
    </div>
  );
}
