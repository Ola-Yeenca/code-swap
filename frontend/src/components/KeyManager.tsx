import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createKey, deleteKey, listKeys, refreshModelsForProvider } from "../api/client";
import type { Provider } from "../types/api";

export function KeyManager() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<Provider>("openai");
  const [keyMode, setKeyMode] = useState<"vault" | "local">("vault");
  const [apiKey, setApiKey] = useState("");
  const [label, setLabel] = useState("");

  const { data: keys, isLoading } = useQuery({
    queryKey: ["keys"],
    queryFn: listKeys,
  });

  const createMutation = useMutation({
    mutationFn: createKey,
    onSuccess: async (_created, variables) => {
      try {
        await refreshModelsForProvider(variables.provider);
      } catch {
        // Keep key save successful even if model sync fails.
      }
      queryClient.invalidateQueries({ queryKey: ["models"] });
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      setApiKey("");
      setLabel("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["keys"] }),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim()) {
      return;
    }
    createMutation.mutate({ provider, keyMode, apiKey, label: label || undefined });
  };

  return (
    <section className="panel p-4">
      <h2 className="font-display text-lg font-semibold">API Route Keys (BYOK)</h2>
      <p className="mt-1 text-sm text-slate-600">
        OpenAI/Anthropic are direct APIs. OpenRouter is a router to many upstream models.
      </p>

      <form className="mt-4 space-y-2" onSubmit={submit}>
        <select
          className="w-full rounded border border-slate-300 bg-white p-2"
          value={provider}
          onChange={(e) => setProvider(e.target.value as Provider)}
        >
          <option value="openai">OpenAI (direct)</option>
          <option value="anthropic">Anthropic (direct)</option>
          <option value="openrouter">OpenRouter (aggregated models)</option>
        </select>

        {provider === "openrouter" ? (
          <p className="text-xs text-slate-600">
            One OpenRouter key can route to many model families (OpenAI, Anthropic, Google, etc).
          </p>
        ) : null}

        <select
          className="w-full rounded border border-slate-300 bg-white p-2"
          value={keyMode}
          onChange={(e) => setKeyMode(e.target.value as "vault" | "local")}
        >
          <option value="vault">Vault</option>
          <option value="local">Local</option>
        </select>

        <input
          className="w-full rounded border border-slate-300 bg-white p-2"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Label (optional)"
        />

        <input
          className="w-full rounded border border-slate-300 bg-white p-2"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="API key"
          type="password"
        />

        <button
          className="w-full rounded bg-pine px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={createMutation.isPending}
          type="submit"
        >
          {createMutation.isPending ? "Saving..." : "Add Key"}
        </button>
      </form>

      <div className="mt-4 space-y-2">
        {isLoading ? <p className="text-sm">Loading keys...</p> : null}
        {(keys || []).map((key) => (
          <div className="rounded border border-slate-200 p-2 text-sm" key={key.id}>
            <div className="flex items-center justify-between">
              <strong>{key.provider}</strong>
              <span>{key.keyMode}</span>
            </div>
            <div className="text-xs text-slate-600">{key.maskedHint}</div>
            <button
              className="mt-1 text-xs text-red-700"
              onClick={() => deleteMutation.mutate(key.id)}
              type="button"
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
