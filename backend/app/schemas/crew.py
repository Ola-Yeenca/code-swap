from __future__ import annotations
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    name: str
    model: str
    role: str  # "orchestrator" | "specialist"
    system_prompt: str
    max_tokens: int = 4096


class CrewRunRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    task: str
    crew_name: str = Field(alias="crewName", default="default")
    agents: list[AgentConfig] | None = None  # override defaults
    budget_limit_usd: float = Field(alias="budgetLimitUsd", default=5.0)

    model_config = {"populate_by_name": True}


class SubtaskResult(BaseModel):
    id: str
    description: str
    assigned_to: str = Field(alias="assignedTo")
    status: str
    agent_model: str = Field(alias="agentModel")
    tokens_in: int = Field(alias="tokensIn", default=0)
    tokens_out: int = Field(alias="tokensOut", default=0)
    cost_usd: float = Field(alias="costUsd", default=0.0)

    model_config = {"populate_by_name": True}


class CrewRunSummary(BaseModel):
    run_id: str = Field(alias="runId")
    status: str
    subtasks: list[SubtaskResult]
    total_cost_usd: float = Field(alias="totalCostUsd")
    final_result: str = Field(alias="finalResult", default="")

    model_config = {"populate_by_name": True}
