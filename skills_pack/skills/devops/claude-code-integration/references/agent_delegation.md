# Agent Delegation (Subagent) System

Based on `src/tools/AgentTool/` → `hermes_cli/agent_tool.py`

## Overview

Subagent delegation allows the main agent to spawn isolated agents for parallel workstreams. Each subagent has:
- Own transcript (sidechain)
- Own skill scope
- Own permission context
- Isolated working directory (optional)
- Defined toolset access

## Agent Types

```python
from enum import Enum

class AgentType(Enum):
    MAIN_SESSION = "main-session"      # Primary conversation
    SUBAGENT = "subagent"              # Delegated task
    BACKGROUND = "background"          # Background task

class AgentDefinition(BaseModel):
    agent_type: AgentType
    name: str                           # e.g., "code-reviewer", "data-analyst"
    description: str                    # When to use this agent
    system_prompt: str                  # Custom system prompt
    toolsets: List[str] = []            # Allowed toolsets
    max_turns: int = 20
    working_dir: Optional[str] = None   # Optional isolated directory
    inherit_skills: bool = True         # Inherit parent's invoked skills
```

## Built-in Agent Definitions

```python
BUILTIN_AGENTS = {
    "code-reviewer": AgentDefinition(
        agent_type=AgentType.SUBAGENT,
        name="code-reviewer",
        description="Reviews code changes for correctness, style, and security",
        system_prompt="""You are a senior code reviewer. Focus on:
- Correctness and edge cases
- Security vulnerabilities
- Performance implications
- Code style and maintainability
- Test coverage
Provide specific, actionable feedback with line references.""",
        toolsets=["read", "search", "bash"],
        max_turns=15
    ),
    
    "data-analyst": AgentDefinition(
        agent_type=AgentType.SUBAGENT,
        name="data-analyst",
        description="Analyzes data, creates visualizations, finds insights",
        system_prompt="""You are a data analyst. Given data files or queries:
- Explore data structure and quality
- Create visualizations (matplotlib/seaborn)
- Statistical analysis
- Generate reports with findings
Always show your work and explain methodology.""",
        toolsets=["read", "write", "bash", "python"],
        max_turns=25
    ),
    
    "refactoring": AgentDefinition(
        agent_type=AgentType.SUBAGENT,
        name="refactoring",
        description="Refactors code for clarity, performance, or modern patterns",
        system_prompt="""You are a refactoring expert. Safely improve code by:
- Extracting methods/classes
- Removing duplication
- Modernizing syntax
- Improving names
- Adding types
Always run tests after changes. Make minimal, focused changes.""",
        toolsets=["read", "write", "edit", "bash", "search"],
        max_turns=30
    ),
    
    "test-writer": AgentDefinition(
        agent_type=AgentType.SUBAGENT,
        name="test-writer",
        description="Writes comprehensive tests for existing code",
        system_prompt="""You are a test engineer. Write tests that:
- Cover happy paths and edge cases
- Use appropriate test framework (pytest, jest, etc.)
- Mock external dependencies
- Are maintainable and readable
Follow existing test patterns in the codebase.""",
        toolsets=["read", "write", "search", "bash"],
        max_turns=25
    ),
    
    "documentation": AgentDefinition(
        agent_type=AgentType.SUBAGENT,
        name="documentation",
        description="Creates or updates documentation",
        system_prompt="""You are a technical writer. Create documentation that is:
- Clear and concise
- Example-driven
- Up-to-date with code
- Follows project style
Include code examples, diagrams (mermaid), and cross-references.""",
        toolsets=["read", "write", "search"],
        max_turns=20
    )
}
```

## Delegation Tool

```python
from typing import Optional, List
from pydantic import BaseModel

class DelegateInput(BaseModel):
    prompt: str                          # Task description
    agent: str                           # Agent name or type
    context: Optional[Dict] = None       # Additional context
    max_turns: Optional[int] = None      # Override agent default
    toolsets: Optional[List[str]] = None # Override toolsets
    working_dir: Optional[str] = None    # Isolated directory

class DelegateOutput(BaseModel):
    result: str                          # Agent's final response
    agent_id: str                        # Subagent identifier
    turns_used: int
    tools_used: List[str]
    success: bool
    error: Optional[str] = None

async def delegate_to_agent(
    prompt: str,
    agent_name: str,
    config: AgentConfig,
    parent_session: Session,
    context: Optional[Dict] = None
) -> DelegateOutput:
    """
    Delegate a task to a specialized subagent.
    
    Flow:
    1. Resolve agent definition
    2. Create AgentContext (isolates skills, transcript)
    3. Create sidechain transcript
    4. Run agent loop with inherited + agent-specific config
    4. Return result, merge sidechain if needed
    """
    
    # 1. Get agent definition
    agent_def = BUILTIN_AGENTS.get(agent_name)
    if not agent_def:
        # Try custom agents
        agent_def = await load_custom_agent(agent_name)
    
    if not agent_def:
        return DelegateOutput(
            result="",
            agent_id="",
            turns_used=0,
            tools_used=[],
            success=False,
            error=f"Unknown agent: {agent_name}"
        )
    
    # 2. Generate agent ID
    agent_id = generate_agent_id(agent_def.agent_type)
    
    # 3. Create sidechain transcript
    sidechain = parent_session.create_sidechain(agent_id)
    
    # 4. Write initial context to sidechain
    initial_messages = []
    if context:
        initial_messages.append({
            'uuid': str(uuid.uuid4()),
            'type': 'system',
            'message': {'role': 'system', 'content': f"Context from parent: {json.dumps(context)}"},
            'timestamp': datetime.now().isoformat(),
            'session_id': agent_id,
            'version': 1
        })
    
    initial_messages.append({
        'uuid': str(uuid.uuid4()),
        'type': 'user',
        'message': {'role': 'user', 'content': prompt},
        'timestamp': datetime.now().isoformat(),
        'session_id': agent_id,
        'version': 1
    })
    
    for msg in initial_messages:
        await sidechain.append_async(msg)
    
    # 5. Prepare config for subagent
    subagent_config = config.copy()
    subagent_config.model = agent_def.model or config.model
    subagent_config.system_prompt = agent_def.system_prompt
    subagent_config.toolsets = toolsets or agent_def.toolsets
    subagent_config.max_turns = max_turns or agent_def.max_turns
    subagent_config.working_dir = working_dir or agent_def.working_dir or config.working_dir
    
    # 6. Run with agent context isolation
    from hermes_cli.agent_context import AgentContext, run_with_agent_context
    
    agent_context = AgentContext(
        agent_id=agent_id,
        agent_type=agent_def.agent_type.value,
        subagent_name=agent_def.name,
        is_built_in=True
    )
    
    result_text = ""
    turns = 0
    tools_used = []
    success = False
    error = None
    
    try:
        async with run_with_agent_context(agent_context):
            # This isolates skill invocations to this agent_id
            async for event in agent_loop(
                messages=initial_messages,
                config=subagent_config,
                session_id=agent_id
            ):
                if event.type == 'assistant':
                    result_text = event.message.content
                    for block in event.message.content:
                        if block.type == 'tool_use':
                            tools_used.append(block.name)
                    turns += 1
                    # Write to sidechain incrementally
                    await sidechain.append_async(event.to_dict())
                    
                    if event.is_final:
                        success = True
                        break
                        
                elif event.type in ('user', 'system'):
                    await sidechain.append_async(event.to_dict())
                    
    except Exception as e:
        error = str(e)
    
    # 7. Return result
    return DelegateOutput(
        result=result_text,
        agent_id=agent_id,
        turns_used=turns,
        tools_used=list(set(tools_used)),
        success=success,
        error=error
    )
```

## AgentContext Isolation

```python
# hermes_cli/agent_context.py
import contextvars
from dataclasses import dataclass
from typing import Optional, Set

@dataclass
class AgentContext:
    agent_id: str
    agent_type: str  # 'subagent', 'main-session'
    subagent_name: str
    is_built_in: bool

# Context variable for current agent
_current_agent: contextvars.ContextVar[Optional[AgentContext]] = contextvars.ContextVar('_current_agent', default=None)

@contextlib.asynccontextmanager
async def run_with_agent_context(context: AgentContext):
    """Run code within an agent context."""
    token = _current_agent.set(context)
    try:
        yield
    finally:
        _current_agent.reset(token)

def get_current_agent() -> Optional[AgentContext]:
    return _current_agent.get()

def get_current_agent_id() -> Optional[str]:
    ctx = _current_agent.get()
    return ctx.agent_id if ctx else None

# Skill invocation scoping
class SkillManager:
    def __init__(self):
        self.invoked_skills: Dict[str, Set[str]] = {}  # agent_id -> set of skill names
    
    def invoke_skill(self, skill_name: str) -> bool:
        agent_id = get_current_agent_id() or 'global'
        if agent_id not in self.invoked_skills:
            self.invoked_skills[agent_id] = set()
        
        if skill_name in self.invoked_skills[agent_id]:
            return False  # Already invoked in this agent
        
        self.invoked_skills[agent_id].add(skill_name)
        return True
    
    def clear_invoked_skills(self, preserved_agent_ids: Set[str] = None):
        """Clear invoked skills, optionally preserving some agents."""
        if preserved_agent_ids:
            to_remove = set(self.invoked_skills.keys()) - preserved_agent_ids
            for aid in to_remove:
                del self.invoked_skills[aid]
        else:
            self.invoked_skills.clear()

# Usage in skill loading:
def load_skill_for_agent(skill_name: str, agent_id: Optional[str] = None):
    target_agent = agent_id or get_current_agent_id() or 'global'
    # Load skill only if not already invoked for this agent
```

## Parent-Child Communication

```python
# In parent agent, after delegation:
result = await delegate_to_agent(
    prompt="Review the PR at #123 for security issues",
    agent_name="code-reviewer",
    context={"pr_number": 123, "repo": "org/repo"}
)

if result.success:
    # Parent can reference subagent's work
    await parent_agent.send_message(
        f"Code review complete. Summary: {result.result[:500]}..."
    )
    
    # Optionally merge sidechain into parent transcript
    if should_merge:
        await merge_sidechain_into_parent(result.agent_id, parent_session)
else:
    await parent_agent.send_message(f"Delegation failed: {result.error}")
```

## Custom Agent Registration

```python
# ~/.hermes/agents/custom.yaml
agents:
  my-analyzer:
    type: subagent
    name: "Custom Analyzer"
    description: "Analyzes project-specific patterns"
    system_prompt: |
      You are an expert on this codebase. You know the conventions,
      architecture, and common pitfalls. Provide deep analysis.
    toolsets: [read, search, bash, write]
    max_turns: 30
    working_dir: null

# Load custom agents
async def load_custom_agents():
    config_path = Path("~/.hermes/agents/custom.yaml").expanduser()
    if not config_path.exists():
        return {}
    
    import yaml
    with open(config_path) as f:
        data = yaml.safe_load(f)
    
    agents = {}
    for key, defn in data.get('agents', {}).items():
        agents[key] = AgentDefinition(**defn)
    
    return agents
```

## Background Tasks (Main Session Tasks)

```python
# Similar to LocalMainSessionTask.ts
async def start_background_session(
    prompt: str,
    parent_session: Session,
    description: str,
    agent_def: Optional[AgentDefinition] = None
) -> str:
    """Start a background session that runs independently."""
    
    task_id = generate_main_session_task_id()
    sidechain = parent_session.create_sidechain(task_id)
    
    # Write parent context to sidechain
    await sidechain.append_async({
        'uuid': str(uuid.uuid4()),
        'type': 'system',
        'message': {'role': 'system', 'content': f'Background session: {description}'},
        'timestamp': datetime.now().isoformat(),
        'session_id': task_id,
        'version': 1
    })
    await sidechain.append_async({
        'uuid': str(uuid.uuid4()),
        'type': 'user',
        'message': {'role': 'user', 'content': prompt},
        'timestamp': datetime.now().isoformat(),
        'session_id': task_id,
        'version': 1
    })
    
    # Run in background
    asyncio.create_task(run_background_main_session(
        task_id=task_id,
        sidechain=sidechain,
        prompt=prompt,
        description=description,
        agent_def=agent_def
    ))
    
    return task_id


async def run_background_main_session(
    task_id: str,
    sidechain: SidechainTranscript,
    prompt: str,
    description: str,
    agent_def: Optional[AgentDefinition]
):
    """Run background main session (similar to startBackgroundSession)."""
    
    messages = [{
        'uuid': str(uuid.uuid4()),
        'type': 'user',
        'message': {'role': 'user', 'content': prompt},
        'timestamp': datetime.now().isoformat(),
        'session_id': task_id,
        'version': 1
    }]
    
    config = load_config()
    if agent_def:
        config.system_prompt = agent_def.system_prompt
        config.toolsets = agent_def.toolsets
        config.max_turns = agent_def.max_turns
    
    try:
        async for event in agent_loop(messages, config, session_id=task_id):
            await sidechain.append_async(event.to_dict())
            
            # Update progress in task manager
            update_task_progress(task_id, event)
            
        complete_main_session_task(task_id, True)
    except Exception as e:
        complete_main_session_task(task_id, False, str(e))
```

## Usage Examples

```bash
# Delegate to built-in agent
hermes -z "Review the authentication module for security issues" --agent code-reviewer

# Delegate with context
hermes -z "Analyze the sales data in data/sales.csv and create a report" \
  --agent data-analyst \
  --context '{"file": "data/sales.csv", "format": "csv"}'

# Start background task
hermes --background "Refactor the user service to use new patterns" \
  --agent refactoring \
  --description "User service refactoring"

# List custom agents
hermes agents list

# Create custom agent
hermes agents create my-analyzer --prompt "You are an expert on this codebase..."
```

## Security Considerations

```python
# Permission inheritance
class PermissionInheritance:
    # Subagents inherit parent's permissions by default
    # Can be restricted:
    
    SUBAGENT_PERMISSIONS = {
        # Tool-level: deny dangerous tools by default
        'bash': 'ask',           # Require approval
        'write': 'ask',          # Require approval
        'edit': 'allow',         # Allow if parent allows
        'read': 'allow',         # Always allow
        'search': 'allow',
        'web': 'deny',           # Deny by default
        'mcp': 'deny',           # Deny by default
    }
    
    # Agent-specific overrides
    AGENT_OVERRIDES = {
        'code-reviewer': {'bash': 'deny', 'write': 'deny'},
        'data-analyst': {'bash': 'allow', 'python': 'allow'},
        'refactoring': {'write': 'allow', 'edit': 'allow'},
    }
```

## Integration with Hermes Skills

```python
# When delegating, skills are managed:
async def delegate_with_skills(prompt, agent_name, parent_skills):
    # 1. Create new agent context
    agent_id = generate_agent_id()
    
    # 2. Preserve parent's skills that should persist
    preserved = {s for s in parent_skills if s.is_global}
    
    # 3. Invoke agent-specific skills
    agent_skills = get_agent_skills(agent_name)
    for skill in agent_skills:
        skill_manager.invoke_skill(skill, agent_id=agent_id)
    
    # 4. Run delegation
    result = await delegate_to_agent(prompt, agent_name)
    
    # 5. Clear agent skills, restore parent
    skill_manager.clear_invoked_skills(preserved_agent_ids={agent_id})
    for skill in preserved:
        skill_manager.invoke_skill(skill)
    
    return result
```