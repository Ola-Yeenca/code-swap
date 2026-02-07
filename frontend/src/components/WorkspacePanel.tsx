import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createWorkspace,
  inviteWorkspaceMember,
  listWorkspaceInvites,
  listWorkspaces,
} from "../api/client";

interface Props {
  selectedWorkspaceId?: string;
  onWorkspaceSelect: (workspaceId?: string) => void;
}

export function WorkspacePanel({ selectedWorkspaceId, onWorkspaceSelect }: Props) {
  const queryClient = useQueryClient();
  const [workspaceName, setWorkspaceName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
  });

  const selectedWorkspace = useMemo(
    () => (workspaces || []).find((item) => item.workspace.id === selectedWorkspaceId),
    [workspaces, selectedWorkspaceId]
  );
  const canManageWorkspace = Boolean(
    selectedWorkspace && (selectedWorkspace.role === "owner" || selectedWorkspace.role === "admin")
  );

  const { data: invites } = useQuery({
    queryKey: ["workspace-invites", selectedWorkspaceId],
    queryFn: () => listWorkspaceInvites(selectedWorkspaceId as string),
    enabled: Boolean(selectedWorkspaceId && canManageWorkspace),
  });

  const createWorkspaceMutation = useMutation({
    mutationFn: createWorkspace,
    onSuccess: (workspace) => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      onWorkspaceSelect(workspace.id);
      setWorkspaceName("");
    },
  });

  const inviteMutation = useMutation({
    mutationFn: inviteWorkspaceMember,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-invites", selectedWorkspaceId] });
      setInviteEmail("");
    },
  });

  function createWorkspaceSubmit(event: FormEvent) {
    event.preventDefault();
    if (!workspaceName.trim()) {
      return;
    }
    createWorkspaceMutation.mutate({ name: workspaceName.trim(), dataRegion: "us" });
  }

  function inviteSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selectedWorkspaceId || !inviteEmail.trim()) {
      return;
    }
    inviteMutation.mutate({
      workspaceId: selectedWorkspaceId,
      email: inviteEmail.trim(),
      role: "member",
    });
  }

  return (
    <section className="panel p-4">
      <h2 className="font-display text-lg font-semibold">Workspace</h2>
      <p className="mt-1 text-sm text-slate-600">Create shared workspaces and send member invites.</p>

      <form className="mt-3 space-y-2" onSubmit={createWorkspaceSubmit}>
        <input
          className="w-full rounded border border-slate-300 bg-white p-2"
          placeholder="Workspace name"
          value={workspaceName}
          onChange={(e) => setWorkspaceName(e.target.value)}
        />
        <button
          className="w-full rounded bg-ink px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          type="submit"
          disabled={createWorkspaceMutation.isPending}
        >
          {createWorkspaceMutation.isPending ? "Creating..." : "Create Workspace"}
        </button>
      </form>

      <div className="mt-3 space-y-2">
        <button
          className={`w-full rounded border px-3 py-2 text-left text-sm ${
            selectedWorkspaceId ? "border-slate-300" : "border-ink bg-ink text-white"
          }`}
          type="button"
          onClick={() => onWorkspaceSelect(undefined)}
        >
          Personal Mode
        </button>
        {(workspaces || []).map((item) => (
          <button
            key={item.workspace.id}
            className={`w-full rounded border px-3 py-2 text-left text-sm ${
              selectedWorkspaceId === item.workspace.id
                ? "border-ink bg-ink text-white"
                : "border-slate-300 bg-white"
            }`}
            type="button"
            onClick={() => onWorkspaceSelect(item.workspace.id)}
          >
            {item.workspace.name}
            <span className="ml-2 text-xs opacity-80">({item.role})</span>
          </button>
        ))}
      </div>

      {canManageWorkspace ? (
        <>
          <form className="mt-4 space-y-2" onSubmit={inviteSubmit}>
            <input
              className="w-full rounded border border-slate-300 bg-white p-2 text-sm"
              placeholder="Invite email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
            <button
              className="w-full rounded bg-pine px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              type="submit"
              disabled={inviteMutation.isPending}
            >
              {inviteMutation.isPending ? "Inviting..." : "Send Invite"}
            </button>
          </form>

          <div className="mt-3 space-y-2 text-xs">
            {(invites || []).slice(0, 4).map((invite) => (
              <div className="rounded border border-slate-200 bg-white p-2" key={invite.id}>
                <div>{invite.email}</div>
                <div className="text-slate-600">{invite.deliveryStatus || "pending"}</div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
