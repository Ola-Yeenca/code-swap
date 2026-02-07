"""Crew configuration data model and YAML I/O.

A "crew" is a named collection of agents (LLM personas) that collaborate on
a task.  Exactly one agent has the ``orchestrator`` role and is responsible
for breaking work into subtasks and dispatching them to ``specialist`` agents.

Crew definitions live as YAML files under ``~/.code_swap/crews/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CREWS_DIR: Path = Path.home() / ".code_swap" / "crews"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentDef:
    """Definition of a single agent in a crew."""

    name: str
    model: str
    role: str  # "orchestrator" | "specialist"
    system_prompt: str
    max_tokens: int = 4096


@dataclass(slots=True)
class CrewConfig:
    """Complete crew configuration."""

    name: str
    description: str
    orchestrator: str  # name of the orchestrator agent
    agents: dict[str, AgentDef] = field(default_factory=dict)
    budget_limit_usd: float = 5.0


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def load_crew(name: str) -> CrewConfig:
    """Load a crew config from ``~/.code_swap/crews/{name}.yaml``.

    Raises ``SystemExit`` with a user-friendly message when the file is
    missing or malformed.
    """
    path = CREWS_DIR / f"{name}.yaml"
    if not path.exists():
        available = list_crews()
        hint = f"Available crews: {', '.join(available)}" if available else "No crews found. Run ensure_default_crews() first."
        raise SystemExit(f"Crew config not found: {path}\n{hint}")

    try:
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        raise SystemExit(f"Failed to parse {path}: {exc}") from exc

    # -- Validate required top-level keys --
    for key in ("name", "description", "orchestrator", "agents"):
        if key not in raw:
            raise SystemExit(f"Crew config {path} is missing required key: '{key}'")

    # -- Build AgentDef objects --
    agents: dict[str, AgentDef] = {}
    raw_agents = raw["agents"]
    if not isinstance(raw_agents, dict) or not raw_agents:
        raise SystemExit(f"Crew config {path}: 'agents' must be a non-empty mapping")

    for agent_name, agent_data in raw_agents.items():
        if not isinstance(agent_data, dict):
            raise SystemExit(f"Crew config {path}: agent '{agent_name}' must be a mapping")
        try:
            agents[agent_name] = AgentDef(
                name=agent_name,
                model=agent_data["model"],
                role=agent_data["role"],
                system_prompt=agent_data.get("system_prompt", ""),
                max_tokens=int(agent_data.get("max_tokens", 4096)),
            )
        except KeyError as exc:
            raise SystemExit(
                f"Crew config {path}: agent '{agent_name}' is missing required field {exc}"
            ) from exc

    orchestrator = raw["orchestrator"]
    if orchestrator not in agents:
        raise SystemExit(
            f"Crew config {path}: orchestrator '{orchestrator}' is not listed in agents "
            f"(available: {', '.join(agents)})"
        )

    return CrewConfig(
        name=raw["name"],
        description=raw["description"],
        orchestrator=orchestrator,
        agents=agents,
        budget_limit_usd=float(raw.get("budget_limit_usd", 5.0)),
    )


def save_crew(config: CrewConfig) -> Path:
    """Persist *config* to ``~/.code_swap/crews/{config.name}.yaml``.

    Returns the path written.
    """
    CREWS_DIR.mkdir(parents=True, exist_ok=True)

    agents_dict: dict[str, dict[str, Any]] = {}
    for name, agent in config.agents.items():
        agents_dict[name] = {
            "model": agent.model,
            "role": agent.role,
            "system_prompt": agent.system_prompt,
            "max_tokens": agent.max_tokens,
        }

    data: dict[str, Any] = {
        "name": config.name,
        "description": config.description,
        "budget_limit_usd": config.budget_limit_usd,
        "orchestrator": config.orchestrator,
        "agents": agents_dict,
    }

    path = CREWS_DIR / f"{config.name}.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return path


def list_crews() -> list[str]:
    """Return names of all available crew configs (sorted)."""
    if not CREWS_DIR.exists():
        return []
    return sorted(p.stem for p in CREWS_DIR.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Template crews
# ---------------------------------------------------------------------------

_TEMPLATE_DEFAULT = """\
name: default
description: "General-purpose coding crew"
budget_limit_usd: 2.00
orchestrator: planner
agents:
  planner:
    model: anthropic/claude-sonnet-4-5
    role: orchestrator
    system_prompt: |
      You are a task planner. Break the user's request into subtasks.
      Output JSON: {"subtasks": [{"id": "1", "description": "...", "assign_to": "agent_name"}]}
      Available agents: coder, reviewer
    max_tokens: 4096
  coder:
    model: anthropic/claude-sonnet-4-5
    role: specialist
    system_prompt: |
      You are a coding specialist. Implement the task you are given.
      Write clean, well-structured code with appropriate error handling.
      Include brief inline comments only where the logic is non-obvious.
    max_tokens: 8192
  reviewer:
    model: openai/gpt-4.1
    role: specialist
    system_prompt: |
      You are a code reviewer. Examine the code for bugs, security issues,
      performance problems, and readability. Provide actionable suggestions
      with specific line references.
    max_tokens: 4096
"""

_TEMPLATE_FULL_STACK = """\
name: full-stack
description: "Full-stack development crew with research capabilities"
budget_limit_usd: 5.00
orchestrator: planner
agents:
  planner:
    model: openai/gpt-4.1
    role: orchestrator
    system_prompt: |
      You are a full-stack project planner. Decompose the user's request into
      concrete subtasks covering frontend, backend, and research as needed.
      Output JSON: {"subtasks": [{"id": "1", "description": "...", "assign_to": "agent_name"}]}
      Available agents: coder, reviewer, researcher
      Assign research tasks first when the request involves unfamiliar APIs or libraries.
    max_tokens: 4096
  coder:
    model: anthropic/claude-sonnet-4-5
    role: specialist
    system_prompt: |
      You are an expert full-stack developer. You handle frontend (React, Vue,
      HTML/CSS) and backend (Python, Node.js, SQL) equally well. Implement the
      task with production-quality code. Follow the project's existing patterns
      and conventions.
    max_tokens: 8192
  reviewer:
    model: google/gemini-2.5-pro
    role: specialist
    system_prompt: |
      You are a thorough code reviewer specializing in full-stack applications.
      Check for correctness, security vulnerabilities (OWASP top 10), proper
      error handling, and consistency between frontend and backend contracts.
      Flag any mismatched API interfaces or missing validations.
    max_tokens: 4096
  researcher:
    model: deepseek/deepseek-r1
    role: specialist
    system_prompt: |
      You are a technical researcher. When given a topic, API, or library,
      provide a concise summary of the relevant documentation, best practices,
      and common pitfalls. Include code snippets for the most relevant patterns.
      Cite sources where possible.
    max_tokens: 8192
"""

_TEMPLATE_CODE_REVIEW = """\
name: code-review
description: "Comprehensive code review crew"
budget_limit_usd: 3.00
orchestrator: analyzer
agents:
  analyzer:
    model: anthropic/claude-sonnet-4-5
    role: orchestrator
    system_prompt: |
      You are a code review coordinator. When given code to review, dispatch
      it to specialist reviewers and synthesize their feedback into a single
      cohesive report.
      Output JSON: {"subtasks": [{"id": "1", "description": "...", "assign_to": "agent_name"}]}
      Available agents: security, style
      Always dispatch to both agents, then compile results.
    max_tokens: 4096
  security:
    model: openai/gpt-4.1
    role: specialist
    system_prompt: |
      You are a security-focused code reviewer. Analyze the code for
      vulnerabilities including injection flaws, authentication weaknesses,
      data exposure, CSRF, XSS, insecure deserialization, and dependency
      risks. Rate each finding by severity (critical / high / medium / low)
      and provide remediation steps.
    max_tokens: 4096
  style:
    model: google/gemini-2.5-pro
    role: specialist
    system_prompt: |
      You are a code style and quality reviewer. Evaluate the code for
      readability, maintainability, naming conventions, DRY violations,
      complexity, and adherence to language-specific idioms. Suggest concrete
      refactoring improvements with before/after examples.
    max_tokens: 4096
"""

_TEMPLATE_RESEARCH = """\
name: research
description: "Deep research and synthesis crew"
budget_limit_usd: 4.00
orchestrator: coordinator
agents:
  coordinator:
    model: openai/gpt-4.1
    role: orchestrator
    system_prompt: |
      You are a research coordinator. Break the user's question into focused
      research subtasks that can be investigated independently, then have
      the synthesizer compile the results.
      Output JSON: {"subtasks": [{"id": "1", "description": "...", "assign_to": "agent_name"}]}
      Available agents: deep-thinker, synthesizer
      Send complex reasoning or analysis tasks to deep-thinker.
      Send compilation and summary tasks to synthesizer.
    max_tokens: 4096
  deep-thinker:
    model: deepseek/deepseek-r1
    role: specialist
    system_prompt: |
      You are a deep reasoning specialist. Think through problems step by
      step, consider edge cases, and explore multiple angles. Provide
      thorough analysis with explicit reasoning chains. When uncertain,
      state your confidence level and list assumptions.
    max_tokens: 8192
  synthesizer:
    model: anthropic/claude-sonnet-4-5
    role: specialist
    system_prompt: |
      You are a research synthesizer. Take findings from multiple sources
      or analyses and compile them into a clear, well-organized summary.
      Highlight areas of agreement, contradiction, and open questions.
      Use structured formatting with headers and bullet points for clarity.
    max_tokens: 8192
"""

_TEMPLATES: dict[str, str] = {
    "default": _TEMPLATE_DEFAULT,
    "full-stack": _TEMPLATE_FULL_STACK,
    "code-review": _TEMPLATE_CODE_REVIEW,
    "research": _TEMPLATE_RESEARCH,
}


def ensure_default_crews() -> None:
    """Create template crew YAML files if the crews directory is empty.

    Idempotent: does nothing if any ``.yaml`` files already exist.
    """
    CREWS_DIR.mkdir(parents=True, exist_ok=True)

    existing = list(CREWS_DIR.glob("*.yaml"))
    if existing:
        return

    for name, content in _TEMPLATES.items():
        (CREWS_DIR / f"{name}.yaml").write_text(content)
