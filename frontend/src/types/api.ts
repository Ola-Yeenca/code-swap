export type Provider = "openai" | "anthropic" | "openrouter";
export type KeyMode = "vault" | "local";
export type ChatMode = "single" | "compare" | "crew";

export interface ModelItem {
  id: string;
  provider: Provider;
  model_id: string;
  capabilities: Record<string, boolean>;
  is_active: boolean;
}

export interface ModelsResponse {
  items: ModelItem[];
  stale: boolean;
  stale_reason?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  chatMode: ChatMode;
  workspaceId?: string;
  userId: string;
  created_at?: string;
}

export interface KeyRecord {
  id: string;
  provider: Provider;
  keyMode: KeyMode;
  label?: string;
  maskedHint: string;
}

interface StreamUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

interface StreamStartEvent {
  type: "start";
}

interface StreamDeltaEvent {
  type: "delta";
  text?: string;
  side?: "left" | "right";
}

interface StreamDoneEvent {
  type: "done";
  side?: "left" | "right";
  usage?: StreamUsage;
}

interface StreamCompleteEvent {
  type: "complete";
  side?: "left" | "right";
  usage?: StreamUsage;
}

interface StreamErrorEvent {
  type: "error";
  message?: string;
  side?: "left" | "right";
}

export type StreamEvent =
  | StreamStartEvent
  | StreamDeltaEvent
  | StreamDoneEvent
  | StreamCompleteEvent
  | StreamErrorEvent;

export type WorkspaceRole = "owner" | "admin" | "member";

export interface Workspace {
  id: string;
  name: string;
  ownerId: string;
  dataRegion: "us" | "eu";
}

export interface WorkspaceListItem {
  workspace: Workspace;
  role: WorkspaceRole;
}

export interface WorkspaceInvite {
  id: string;
  email: string;
  role: WorkspaceRole;
  token: string;
  workspaceId: string;
  expiresAt: string;
  acceptedAt?: string | null;
  deliveryStatus?: string | null;
  inviteUrl?: string | null;
}

export interface BillingStatus {
  workspaceId: string;
  hasCustomer: boolean;
  customerId?: string | null;
  subscriptionStatus: string;
  currentPeriodEnd?: string | null;
}

export interface Entitlement {
  featureKey: string;
  isEnabled: boolean;
  quota?: number | null;
}

export interface AgentConfig {
  name: string;
  model: string;
  role: "orchestrator" | "specialist";
  systemPrompt: string;
  maxTokens: number;
}

export interface CrewConfig {
  name: string;
  description: string;
  orchestrator: string;
  agents: AgentConfig[];
  budgetLimitUsd: number;
}

interface CrewStartEvent {
  type: "crew_start";
  sessionId?: string;
  agents?: string[];
}

interface CrewPlanEvent {
  type: "plan";
  subtasks?: Array<{ id: string; description: string; assignTo: string }>;
}

interface CrewAgentStartEvent {
  type: "agent_start";
  agent?: string;
  subtaskId?: string;
  model?: string;
}

interface CrewAgentDeltaEvent {
  type: "agent_delta";
  agent?: string;
  subtaskId?: string;
  text?: string;
}

interface CrewAgentDoneEvent {
  type: "agent_done";
  agent?: string;
  subtaskId?: string;
  cost?: number;
  tokens?: number;
}

interface CrewSynthesisDeltaEvent {
  type: "synthesis_delta";
  text?: string;
}

interface CrewDoneEvent {
  type: "crew_done";
  totalCost?: number;
}

interface CrewErrorEvent {
  type: "error";
  message?: string;
}

export type CrewStreamEvent =
  | CrewStartEvent
  | CrewPlanEvent
  | CrewAgentStartEvent
  | CrewAgentDeltaEvent
  | CrewAgentDoneEvent
  | CrewSynthesisDeltaEvent
  | CrewDoneEvent
  | CrewErrorEvent;
