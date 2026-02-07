import { FormEvent, useRef, useState } from "react";

import { streamCompareChat } from "../api/client";
import { useAppStore } from "../store/appStore";
import { calculateCost, estimateTokens, formatCost, formatTokens } from "../utils/pricing";
import type { Provider } from "../types/api";
import { ModelSelect } from "./ModelSelect";

interface Choice {
  provider: Provider;
  modelId: string;
  keyMode: "vault" | "local";
  localApiKey?: string;
}

interface Props {
  sessionId: string;
  modelOptions: Array<{ provider: Provider; modelId: string }>;
  left: Choice;
  right: Choice;
  onLeftChange: (next: Partial<Choice>) => void;
  onRightChange: (next: Partial<Choice>) => void;
  fileId?: string;
}

interface SideUsage {
  tokensIn: number;
  tokensOut: number;
  cost: number;
  estimated: boolean;
}

function UsageFooter({ usage, label }: { usage: SideUsage | null; label: string }) {
  if (!usage) {
    return null;
  }
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[11px] font-mono text-slate-400">
      <span title={`${label} input tokens`}>IN {formatTokens(usage.tokensIn)}</span>
      <span title={`${label} output tokens`}>OUT {formatTokens(usage.tokensOut)}</span>
      <span className="ml-auto font-semibold" style={{ color: "var(--pine)" }} title={`${label} cost`}>
        {formatCost(usage.cost)}
      </span>
      {usage.estimated ? (
        <span className="text-[9px] text-slate-300">est.</span>
      ) : null}
    </div>
  );
}

export function ComparePanel({
  sessionId,
  modelOptions,
  left,
  right,
  onLeftChange,
  onRightChange,
  fileId,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [leftOutput, setLeftOutput] = useState("");
  const [rightOutput, setRightOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [leftUsage, setLeftUsage] = useState<SideUsage | null>(null);
  const [rightUsage, setRightUsage] = useState<SideUsage | null>(null);
  const addUsage = useAppStore((s) => s.addUsage);

  const promptRef = useRef("");
  const leftAccRef = useRef("");
  const rightAccRef = useRef("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || busy) {
      return;
    }

    setBusy(true);
    setLeftOutput("");
    setRightOutput("");
    setLeftUsage(null);
    setRightUsage(null);
    promptRef.current = prompt;
    leftAccRef.current = "";
    rightAccRef.current = "";

    let gotLeftUsage = false;
    let gotRightUsage = false;

    try {
      const stream = await streamCompareChat({
        sessionId,
        prompt,
        fileId,
        left,
        right,
      });
      for await (const eventData of stream) {
        if (eventData.type === "delta" && eventData.text && eventData.side === "left") {
          leftAccRef.current += eventData.text;
          setLeftOutput((prev) => prev + eventData.text);
        } else if (eventData.type === "delta" && eventData.text && eventData.side === "right") {
          rightAccRef.current += eventData.text;
          setRightOutput((prev) => prev + eventData.text);
        } else if (eventData.type === "error") {
          const message = eventData.message || "Stream failed";
          if (eventData.side === "left") {
            setLeftOutput((prev) => prev || `Error: ${message}`);
          } else if (eventData.side === "right") {
            setRightOutput((prev) => prev || `Error: ${message}`);
          } else {
            setLeftOutput((prev) => prev || `Error: ${message}`);
            setRightOutput((prev) => prev || `Error: ${message}`);
          }
        }

        if (
          (eventData.type === "done" || eventData.type === "complete") &&
          eventData.usage
        ) {
          const tokensIn = eventData.usage.prompt_tokens ?? 0;
          const tokensOut = eventData.usage.completion_tokens ?? 0;
          if (eventData.side === "left") {
            const cost = calculateCost(tokensIn, tokensOut, left.modelId);
            setLeftUsage({ tokensIn, tokensOut, cost, estimated: false });
            addUsage(tokensIn, tokensOut, cost);
            gotLeftUsage = true;
          } else if (eventData.side === "right") {
            const cost = calculateCost(tokensIn, tokensOut, right.modelId);
            setRightUsage({ tokensIn, tokensOut, cost, estimated: false });
            addUsage(tokensIn, tokensOut, cost);
            gotRightUsage = true;
          }
        }
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : "Compare stream failed";
      setLeftOutput(text);
      setRightOutput(text);
    } finally {
      if (!gotLeftUsage && leftAccRef.current.length > 0) {
        const tokensIn = estimateTokens(promptRef.current);
        const tokensOut = estimateTokens(leftAccRef.current);
        const cost = calculateCost(tokensIn, tokensOut, left.modelId);
        setLeftUsage({ tokensIn, tokensOut, cost, estimated: true });
        addUsage(tokensIn, tokensOut, cost);
      }
      if (!gotRightUsage && rightAccRef.current.length > 0) {
        const tokensIn = estimateTokens(promptRef.current);
        const tokensOut = estimateTokens(rightAccRef.current);
        const cost = calculateCost(tokensIn, tokensOut, right.modelId);
        setRightUsage({ tokensIn, tokensOut, cost, estimated: true });
        addUsage(tokensIn, tokensOut, cost);
      }
      setBusy(false);
    }
  }

  const combinedCost =
    (leftUsage?.cost ?? 0) + (rightUsage?.cost ?? 0);
  const hasCost = leftUsage !== null || rightUsage !== null;

  return (
    <section className="panel p-4">
      <div className="grid gap-3 md:grid-cols-2">
        <ModelSelect
          title="Left"
          provider={left.provider}
          modelId={left.modelId}
          keyMode={left.keyMode}
          localApiKey={left.localApiKey}
          modelOptions={modelOptions}
          onChange={onLeftChange}
        />
        <ModelSelect
          title="Right"
          provider={right.provider}
          modelId={right.modelId}
          keyMode={right.keyMode}
          localApiKey={right.localApiKey}
          modelOptions={modelOptions}
          onChange={onRightChange}
        />
      </div>

      <form className="mt-3 space-y-2" onSubmit={submit}>
        <textarea
          className="h-28 w-full rounded border border-slate-300 p-3"
          placeholder="Prompt to compare"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        {fileId ? (
          <p className="text-xs text-slate-600">Using attached file context: {fileId}</p>
        ) : null}
        <button
          className="rounded bg-brass px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={busy || !prompt.trim()}
          type="submit"
        >
          {busy ? "Comparing..." : "Compare"}
        </button>
      </form>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <article className="min-h-40 rounded border border-slate-200 bg-white p-3 text-sm whitespace-pre-wrap">
            {leftOutput || "Left output"}
          </article>
          <UsageFooter usage={leftUsage} label="Left" />
        </div>
        <div>
          <article className="min-h-40 rounded border border-slate-200 bg-white p-3 text-sm whitespace-pre-wrap">
            {rightOutput || "Right output"}
          </article>
          <UsageFooter usage={rightUsage} label="Right" />
        </div>
      </div>

      {hasCost ? (
        <div className="mt-3 flex items-center justify-end gap-2 border-t border-slate-100 pt-2 text-xs font-mono">
          <span className="text-slate-400">Combined</span>
          <span className="font-semibold" style={{ color: "var(--pine)" }}>
            {formatCost(combinedCost)}
          </span>
        </div>
      ) : null}
    </section>
  );
}
