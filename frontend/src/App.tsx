import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createChatSession, getModels, refreshModels } from "./api/client";
import { BillingPanel } from "./components/BillingPanel";
import { ComparePanel } from "./components/ComparePanel";
import { CostBadge } from "./components/CostBadge";
import { CrewPanel } from "./components/CrewPanel";
import { FileIngestPanel } from "./components/FileIngestPanel";
import { KeyManager } from "./components/KeyManager";
import { SessionHistory } from "./components/SessionHistory";
import { SingleChatPanel } from "./components/SingleChatPanel";
import { WorkspacePanel } from "./components/WorkspacePanel";
import { useAppStore } from "./store/appStore";

export default function App() {
  const queryClient = useQueryClient();
  const [attachedFileId, setAttachedFileId] = useState<string | undefined>(undefined);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | undefined>(undefined);

  const {
    chatMode,
    sessionId,
    single,
    left,
    right,
    setChatMode,
    setSessionId,
    setSingle,
    setLeft,
    setRight,
  } = useAppStore();

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
  });

  const refreshMutation = useMutation({
    mutationFn: refreshModels,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["models"] }),
  });

  const modelOptions = useMemo(() => {
    const items = modelsQuery.data?.items || [];
    return items.map((item) => ({ provider: item.provider, modelId: item.model_id }));
  }, [modelsQuery.data]);

  useEffect(() => {
    if (sessionId) {
      return;
    }
    const title = chatMode === "single" ? "Single Chat" : chatMode === "compare" ? "Compare Chat" : "Crew Chat";
    createChatSession(title, chatMode as "single" | "compare", selectedWorkspaceId)
      .then((session) => setSessionId(session.id))
      .catch(() => undefined);
  }, [chatMode, selectedWorkspaceId, sessionId, setSessionId]);

  return (
    <div className="grid-shell">
      <aside className="space-y-4">
        <section className="panel p-4">
          <h1 className="font-display text-2xl font-bold">Claude + Codex Wrapper</h1>
          <p className="mt-1 text-sm text-slate-600">
            Unified chat with direct OpenAI/Anthropic APIs plus OpenRouter multi-model routing.
          </p>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <button
              className={`rounded px-3 py-2 text-sm font-semibold ${
                chatMode === "single" ? "bg-ink text-white" : "bg-white"
              }`}
              onClick={() => {
                setChatMode("single");
                setSessionId("");
              }}
              type="button"
            >
              Single
            </button>
            <button
              className={`rounded px-3 py-2 text-sm font-semibold ${
                chatMode === "compare" ? "bg-ink text-white" : "bg-white"
              }`}
              onClick={() => {
                setChatMode("compare");
                setSessionId("");
              }}
              type="button"
            >
              Compare
            </button>
            <button
              className={`rounded px-3 py-2 text-sm font-semibold ${
                chatMode === "crew" ? "bg-ink text-white" : "bg-white"
              }`}
              onClick={() => {
                setChatMode("crew");
                setSessionId("");
              }}
              type="button"
            >
              Crew
            </button>
          </div>

          <button
            className="mt-3 w-full rounded bg-pine px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
            disabled={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
            type="button"
          >
            {refreshMutation.isPending ? "Syncing..." : "Sync Latest Models"}
          </button>
        </section>

        <SessionHistory workspaceId={selectedWorkspaceId} />
        <KeyManager />
        <WorkspacePanel
          selectedWorkspaceId={selectedWorkspaceId}
          onWorkspaceSelect={(workspaceId) => {
            setSelectedWorkspaceId(workspaceId);
            setSessionId("");
            setAttachedFileId(undefined);
          }}
        />
        <FileIngestPanel onReady={setAttachedFileId} workspaceId={selectedWorkspaceId} />
        <BillingPanel workspaceId={selectedWorkspaceId} />
        <CostBadge />
      </aside>

      <main className="space-y-4">
        {modelsQuery.isLoading ? (
          <section className="panel p-4 text-sm">Loading model catalog...</section>
        ) : null}
        {modelsQuery.error ? (
          <section className="panel p-4 text-sm text-red-700">
            {(modelsQuery.error as Error).message}
          </section>
        ) : null}
        {modelsQuery.data?.stale ? (
          <section className="panel p-4 text-sm text-amber-800">
            {modelsQuery.data.stale_reason ||
              "Model catalog may be stale. Add vault keys and refresh to pull latest models."}
          </section>
        ) : null}

        {sessionId ? (
          chatMode === "single" ? (
            <SingleChatPanel
              sessionId={sessionId}
              modelOptions={modelOptions}
              choice={single}
              onChoiceChange={setSingle}
              fileId={attachedFileId}
            />
          ) : chatMode === "crew" ? (
            <CrewPanel sessionId={sessionId} />
          ) : (
            <ComparePanel
              sessionId={sessionId}
              modelOptions={modelOptions}
              left={left}
              right={right}
              onLeftChange={setLeft}
              onRightChange={setRight}
              fileId={attachedFileId}
            />
          )
        ) : (
          <section className="panel p-4 text-sm">Creating session...</section>
        )}
      </main>
    </div>
  );
}
