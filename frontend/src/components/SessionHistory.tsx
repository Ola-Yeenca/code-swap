import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { listChatSessions } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { ChatMode, ChatSession } from "../types/api";

const MODE_LABELS: Record<ChatMode, string> = {
  single: "Single",
  compare: "Compare",
  crew: "Crew",
};

const MODE_COLORS: Record<ChatMode, string> = {
  single: "bg-slate-100 text-slate-700",
  compare: "bg-amber-50 text-amber-800",
  crew: "bg-emerald-50 text-emerald-800",
};

function formatRelativeDate(dateString?: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "\u2026";
}

interface SessionHistoryProps {
  workspaceId?: string;
}

export function SessionHistory({ workspaceId }: SessionHistoryProps) {
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);

  const { sessionId, setSessionId, setChatMode } = useAppStore();

  const { data: sessions, isLoading, isError, error } = useQuery({
    queryKey: ["chatSessions", workspaceId],
    queryFn: () => listChatSessions(workspaceId),
    refetchOnWindowFocus: false,
  });

  const recentSessions: ChatSession[] = (sessions ?? [])
    .slice()
    .sort((a, b) => {
      const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return dateB - dateA;
    })
    .slice(0, 10);

  const handleResume = (session: ChatSession) => {
    setChatMode(session.chatMode);
    setSessionId(session.id);
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["chatSessions", workspaceId] });
  };

  return (
    <section className="panel">
      <button
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setCollapsed((prev) => !prev)}
        type="button"
      >
        <h2 className="font-display text-lg font-semibold">Session History</h2>
        <svg
          className={`h-4 w-4 text-slate-500 transition-transform duration-200 ${
            collapsed ? "-rotate-90" : "rotate-0"
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              {recentSessions.length > 0
                ? `${recentSessions.length} recent session${recentSessions.length !== 1 ? "s" : ""}`
                : ""}
            </p>
            <button
              className="flex items-center gap-1 text-xs font-medium transition-colors hover:opacity-80"
              style={{ color: "var(--pine)" }}
              onClick={(e) => {
                e.stopPropagation();
                handleRefresh();
              }}
              type="button"
            >
              <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Refresh
            </button>
          </div>

          {isLoading && <p className="text-sm text-slate-400">Loading sessions...</p>}

          {isError && (
            <p className="text-sm text-red-600">
              {error instanceof Error ? error.message : "Failed to load sessions"}
            </p>
          )}

          {!isLoading && !isError && recentSessions.length === 0 && (
            <p className="py-2 text-center text-sm text-slate-400">No past sessions</p>
          )}

          {recentSessions.length > 0 && (
            <ul className="space-y-1.5">
              {recentSessions.map((session) => {
                const isActive = session.id === sessionId;
                return (
                  <li key={session.id}>
                    <button
                      className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                        isActive
                          ? "border border-[var(--brass)] bg-amber-50/60"
                          : "border border-transparent hover:bg-white/60"
                      }`}
                      onClick={() => handleResume(session)}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span
                          className={`text-sm font-medium leading-snug ${
                            isActive ? "text-[var(--brass)]" : "text-[var(--ink)]"
                          }`}
                        >
                          {truncate(session.title, 32)}
                        </span>
                        <span
                          className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            MODE_COLORS[session.chatMode]
                          }`}
                        >
                          {MODE_LABELS[session.chatMode]}
                        </span>
                      </div>
                      {session.created_at && (
                        <p className="mt-0.5 text-xs text-slate-400">
                          {formatRelativeDate(session.created_at)}
                        </p>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
