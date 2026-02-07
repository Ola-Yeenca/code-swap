import type {
  BillingStatus,
  ChatSession,
  CrewStreamEvent,
  Entitlement,
  KeyRecord,
  ModelsResponse,
  Provider,
  StreamEvent,
  WorkspaceInvite,
  WorkspaceListItem,
} from "../types/api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/v1";
const DEV_EMAIL = "owner@example.com";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "x-dev-user-email": DEV_EMAIL,
      ...(init?.headers || {}),
    },
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function refreshModels(): Promise<void> {
  await apiFetch("/models/refresh", { method: "POST" });
}

export async function refreshModelsForProvider(provider: Provider): Promise<void> {
  await apiFetch(`/models/refresh?provider=${encodeURIComponent(provider)}`, { method: "POST" });
}

export async function getModels(): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>("/models");
}

export async function listKeys(): Promise<KeyRecord[]> {
  return apiFetch<KeyRecord[]>("/keys");
}

export async function createKey(input: {
  provider: Provider;
  keyMode: "vault" | "local";
  apiKey: string;
  label?: string;
}): Promise<KeyRecord> {
  return apiFetch<KeyRecord>("/keys", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteKey(keyId: string): Promise<void> {
  await apiFetch(`/keys/${keyId}`, { method: "DELETE" });
}

export async function listChatSessions(workspaceId?: string): Promise<ChatSession[]> {
  const params = workspaceId ? `?workspaceId=${encodeURIComponent(workspaceId)}` : "";
  return apiFetch<ChatSession[]>(`/chat/sessions${params}`);
}

export async function createChatSession(
  title: string,
  chatMode: "single" | "compare",
  workspaceId?: string
): Promise<ChatSession> {
  return apiFetch<ChatSession>("/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title, chatMode, workspaceId }),
  });
}

async function* streamFromResponse(response: Response): AsyncGenerator<StreamEvent, void, void> {
  if (!response.body) {
    throw new Error("Missing stream body");
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const event of events) {
      if (!event.startsWith("data:")) {
        continue;
      }
      const json = event.slice(5).trim();
      if (!json) {
        continue;
      }
      yield JSON.parse(json) as StreamEvent;
    }
  }
}

export async function streamSingleChat(input: {
  sessionId: string;
  provider: Provider;
  modelId: string;
  keyMode: "vault" | "local";
  localApiKey?: string;
  prompt: string;
  fileId?: string;
  imageUrl?: string;
}): Promise<AsyncGenerator<StreamEvent, void, void>> {
  const parts: Array<{ type: string; text?: string; fileId?: string; imageUrl?: string }> = [];
  parts.push({ type: "text", text: input.prompt });
  if (input.fileId) {
    parts.push({ type: "file_ref", fileId: input.fileId });
  }
  if (input.imageUrl) {
    parts.push({ type: "image", imageUrl: input.imageUrl });
  }

  const response = await fetch(`${API_BASE_URL}/chat/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-dev-user-email": DEV_EMAIL,
    },
    credentials: "include",
    body: JSON.stringify({
      sessionId: input.sessionId,
      provider: input.provider,
      modelId: input.modelId,
      keyMode: input.keyMode,
      localApiKey: input.localApiKey,
      parts,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Stream request failed: ${response.status}`);
  }

  return streamFromResponse(response);
}

export async function streamCompareChat(input: {
  sessionId: string;
  prompt: string;
  fileId?: string;
  imageUrl?: string;
  left: {
    provider: Provider;
    modelId: string;
    keyMode: "vault" | "local";
    localApiKey?: string;
  };
  right: {
    provider: Provider;
    modelId: string;
    keyMode: "vault" | "local";
    localApiKey?: string;
  };
}): Promise<AsyncGenerator<StreamEvent, void, void>> {
  const parts: Array<{ type: string; text?: string; fileId?: string; imageUrl?: string }> = [];
  parts.push({ type: "text", text: input.prompt });
  if (input.fileId) {
    parts.push({ type: "file_ref", fileId: input.fileId });
  }
  if (input.imageUrl) {
    parts.push({ type: "image", imageUrl: input.imageUrl });
  }

  const response = await fetch(`${API_BASE_URL}/compare/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-dev-user-email": DEV_EMAIL,
    },
    credentials: "include",
    body: JSON.stringify({
      sessionId: input.sessionId,
      left: input.left,
      right: input.right,
      parts,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Compare stream failed: ${response.status}`);
  }

  return streamFromResponse(response);
}

export async function streamCrewChat(input: {
  sessionId: string;
  task: string;
  crewName: string;
  apiKey?: string;
}): Promise<AsyncGenerator<CrewStreamEvent, void, void>> {
  const response = await fetch(`${API_BASE_URL}/crew/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-dev-user-email": DEV_EMAIL,
      ...(input.apiKey ? { "x-openrouter-key": input.apiKey } : {}),
    },
    credentials: "include",
    body: JSON.stringify({
      sessionId: input.sessionId,
      task: input.task,
      crewName: input.crewName,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Crew stream failed: ${response.status}`);
  }

  return streamFromCrewResponse(response);
}

async function* streamFromCrewResponse(response: Response): AsyncGenerator<CrewStreamEvent, void, void> {
  if (!response.body) throw new Error("Missing stream body");
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const event of events) {
      if (!event.startsWith("data:")) continue;
      const json = event.slice(5).trim();
      if (!json) continue;
      yield JSON.parse(json) as CrewStreamEvent;
    }
  }
}

export async function presignUpload(input: {
  filename: string;
  mimeType: string;
  sizeBytes: number;
  workspaceId?: string;
}): Promise<{ fileId: string; uploadUrl: string; storageKey: string }> {
  return apiFetch("/files/presign-upload", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function ingestFile(fileId: string): Promise<{ fileId: string; chunksCreated: number }> {
  return apiFetch(`/files/${fileId}/ingest`, { method: "POST" });
}

export async function listWorkspaces(): Promise<WorkspaceListItem[]> {
  return apiFetch<WorkspaceListItem[]>("/workspaces");
}

export async function createWorkspace(input: {
  name: string;
  dataRegion: "us" | "eu";
}): Promise<{ id: string; name: string; ownerId: string; dataRegion: "us" | "eu" }> {
  return apiFetch("/workspaces", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function inviteWorkspaceMember(input: {
  workspaceId: string;
  email: string;
  role: "owner" | "admin" | "member";
}): Promise<WorkspaceInvite> {
  return apiFetch(`/workspaces/${input.workspaceId}/invites`, {
    method: "POST",
    body: JSON.stringify({ email: input.email, role: input.role }),
  });
}

export async function listWorkspaceInvites(workspaceId: string): Promise<WorkspaceInvite[]> {
  return apiFetch(`/workspaces/${workspaceId}/invites`);
}

export async function billingCheckout(workspaceId: string): Promise<{ url: string }> {
  return apiFetch("/billing/checkout-session", {
    method: "POST",
    body: JSON.stringify({ workspaceId }),
  });
}

export async function billingStatus(workspaceId: string): Promise<BillingStatus> {
  return apiFetch(`/billing/status?workspaceId=${encodeURIComponent(workspaceId)}`);
}

export async function billingEntitlements(workspaceId: string): Promise<Entitlement[]> {
  return apiFetch(`/billing/entitlements?workspaceId=${encodeURIComponent(workspaceId)}`);
}
