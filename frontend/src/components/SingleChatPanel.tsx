import { FormEvent, useMemo, useRef, useState } from "react";

import { streamSingleChat } from "../api/client";
import { useAppStore } from "../store/appStore";
import { calculateCost, estimateTokens, formatCost, formatTokens } from "../utils/pricing";
import { ModelSelect } from "./ModelSelect";
import type { Provider } from "../types/api";

interface Choice {
  provider: Provider;
  modelId: string;
  keyMode: "vault" | "local";
  localApiKey?: string;
}

interface Props {
  sessionId: string;
  modelOptions: Array<{ provider: Provider; modelId: string }>;
  choice: Choice;
  onChoiceChange: (next: Partial<Choice>) => void;
  fileId?: string;
}

interface UsageInfo {
  tokensIn: number;
  tokensOut: number;
  cost: number;
  estimated: boolean;
}

export function SingleChatPanel({ sessionId, modelOptions, choice, onChoiceChange, fileId }: Props) {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState(false);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const addUsage = useAppStore((s) => s.addUsage);
  const promptRef = useRef("");

  const canSend = useMemo(() => prompt.trim().length > 0 && !busy, [prompt, busy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSend) {
      return;
    }

    setBusy(true);
    setResponse("");
    setUsage(null);
    promptRef.current = prompt;

    let gotServerUsage = false;
    let accumulated = "";

    try {
      const stream = await streamSingleChat({
        sessionId,
        provider: choice.provider,
        modelId: choice.modelId,
        keyMode: choice.keyMode,
        localApiKey: choice.localApiKey,
        prompt,
        fileId,
        imageUrl: imageUrl || undefined,
      });

      for await (const eventData of stream) {
        if (eventData.type === "delta" && eventData.text) {
          accumulated += eventData.text;
          setResponse((prev) => prev + eventData.text);
        }

        if (
          (eventData.type === "done" || eventData.type === "complete") &&
          eventData.usage
        ) {
          const tokensIn = eventData.usage.prompt_tokens ?? 0;
          const tokensOut = eventData.usage.completion_tokens ?? 0;
          const cost = calculateCost(tokensIn, tokensOut, choice.modelId);
          setUsage({ tokensIn, tokensOut, cost, estimated: false });
          addUsage(tokensIn, tokensOut, cost);
          gotServerUsage = true;
        }
      }
    } catch (error) {
      setResponse(error instanceof Error ? error.message : "Stream failed");
    } finally {
      if (!gotServerUsage && accumulated.length > 0) {
        const tokensIn = estimateTokens(promptRef.current);
        const tokensOut = estimateTokens(accumulated);
        const cost = calculateCost(tokensIn, tokensOut, choice.modelId);
        setUsage({ tokensIn, tokensOut, cost, estimated: true });
        addUsage(tokensIn, tokensOut, cost);
      }
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <ModelSelect
        title="Single Chat"
        provider={choice.provider}
        modelId={choice.modelId}
        keyMode={choice.keyMode}
        localApiKey={choice.localApiKey}
        modelOptions={modelOptions}
        onChange={onChoiceChange}
      />

      <form className="mt-3 space-y-2" onSubmit={submit}>
        <textarea
          className="h-28 w-full rounded border border-slate-300 p-3"
          placeholder="Prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <input
          className="w-full rounded border border-slate-300 p-2 text-sm"
          placeholder="Optional image URL"
          value={imageUrl}
          onChange={(e) => setImageUrl(e.target.value)}
        />
        <button
          className="rounded bg-brass px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={!canSend}
          type="submit"
        >
          {busy ? "Streaming..." : "Send"}
        </button>
      </form>

      <article className="mt-4 min-h-40 rounded border border-slate-200 bg-white p-3 text-sm whitespace-pre-wrap">
        {response || "Response will stream here."}
      </article>

      {usage ? (
        <div className="mt-2 flex items-center gap-3 rounded border border-slate-100 bg-slate-50 px-3 py-1.5 text-xs font-mono">
          <span className="text-slate-400" title="Input tokens">
            IN {formatTokens(usage.tokensIn)}
          </span>
          <span className="text-slate-400" title="Output tokens">
            OUT {formatTokens(usage.tokensOut)}
          </span>
          <span className="ml-auto font-semibold" style={{ color: "var(--pine)" }} title="Cost">
            {formatCost(usage.cost)}
          </span>
          {usage.estimated ? (
            <span className="text-[10px] text-slate-300" title="Cost estimated from character count">
              est.
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
