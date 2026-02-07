import type { Provider } from "../types/api";

interface Props {
  title: string;
  provider: Provider;
  modelId: string;
  keyMode: "vault" | "local";
  localApiKey?: string;
  modelOptions: Array<{ provider: Provider; modelId: string }>;
  onChange: (next: {
    provider?: Provider;
    modelId?: string;
    keyMode?: "vault" | "local";
    localApiKey?: string;
  }) => void;
}

export function ModelSelect({
  title,
  provider,
  modelId,
  keyMode,
  localApiKey,
  modelOptions,
  onChange,
}: Props) {
  const providerModels = modelOptions.filter((model) => model.provider === provider);

  const handleProviderChange = (nextProvider: Provider) => {
    const nextModels = modelOptions.filter((model) => model.provider === nextProvider);
    onChange({
      provider: nextProvider,
      modelId: nextModels[0]?.modelId ?? "",
    });
  };

  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <h3 className="font-display text-sm font-semibold">{title}</h3>
      <div className="mt-2 space-y-2">
        <select
          className="w-full rounded border border-slate-300 p-2 text-sm"
          value={provider}
          onChange={(e) => handleProviderChange(e.target.value as Provider)}
        >
          <option value="openai">OpenAI (direct)</option>
          <option value="anthropic">Anthropic (direct)</option>
          <option value="openrouter">OpenRouter (router)</option>
        </select>

        {provider === "openrouter" ? (
          <p className="text-xs text-slate-600">
            OpenRouter models can span vendors, for example <code>openai/gpt-5</code> or{" "}
            <code>anthropic/claude-sonnet-4.5</code>.
          </p>
        ) : null}

        <select
          className="w-full rounded border border-slate-300 p-2 text-sm"
          value={modelId}
          onChange={(e) => onChange({ modelId: e.target.value })}
        >
          {providerModels.map((model) => (
            <option key={`${model.provider}:${model.modelId}`} value={model.modelId}>
              {model.modelId}
            </option>
          ))}
          {providerModels.length === 0 ? (
            <option value="" disabled>
              No models synced for this provider
            </option>
          ) : null}
        </select>

        {provider === "openrouter" ? (
          <input
            className="w-full rounded border border-slate-300 p-2 text-sm"
            placeholder="Or type any OpenRouter model id (e.g. openai/gpt-5)"
            value={modelId}
            onChange={(e) => onChange({ modelId: e.target.value })}
          />
        ) : null}

        <select
          className="w-full rounded border border-slate-300 p-2 text-sm"
          value={keyMode}
          onChange={(e) => onChange({ keyMode: e.target.value as "vault" | "local" })}
        >
          <option value="vault">Vault key</option>
          <option value="local">Local key per request</option>
        </select>

        {keyMode === "local" ? (
          <input
            className="w-full rounded border border-slate-300 p-2 text-sm"
            placeholder="Local API key"
            type="password"
            value={localApiKey || ""}
            onChange={(e) => onChange({ localApiKey: e.target.value })}
          />
        ) : null}
      </div>
    </div>
  );
}
