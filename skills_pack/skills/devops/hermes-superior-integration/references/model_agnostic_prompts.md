# Model-Agnostic Prompt Engineering

This document details how Hermes adapts prompts and parameters for optimal performance across different model families, making it work better than Claude Code regardless of the underlying model.

## Core Insight

Claude Code is optimized for Anthropic models only. Hermes uses **model-agnostic prompt engineering** - dynamically adapting prompts, tool formats, and reasoning styles per model family.

## Model Family Profiles

| Family | Models | System Style | Tool Format | Reasoning | Context | Key Features |
|--------|--------|--------------|-------------|-----------|---------|--------------|
| **Claude** | claude-3-opus/sonnet/haiku | Structured, XML tags | Function calling | Extended thinking | 200K | XML tags, verbose, structured |
| **GPT** | gpt-4o, gpt-4-turbo | Concise, markdown | Function calling | Chain of thought | 128K | Concise, parallel tools |
| **Nemotron** | nvidia/nemotron-3-ultra | Direct, imperative | JSON schema | Step by step | 128K | Direct, system prefixes |
| **DeepSeek** | deepseek-v3, deepseek-r1 | Explicit, XML tags | Function calling | Chain of thought | 128K | XML tags, verbose |
| **SOLAR** | upstage/solar-pro | Structured | Function calling | Chain of thought | 32K | Structured, markdown |
| **GLM** | zhipu/glm-4/5.2 | Structured | Function calling | Chain of thought | 128K | Structured, XML tags |
| **Llama** | llama-3.1-8b/70b | Explicit, few-shot | JSON schema | Few-shot | 128K | Explicit, headers |
| **Mistral** | mistral-large, mixtral | Concise | Function calling | Chain of thought | 32K | Concise, parallel |
| **Local** | ollama, vllm | Explicit, few-shot | JSON schema | Few-shot | 32K | Explicit, headers |

## Per-Model Prompt Adaptation

### System Prompt Adaptation

```python
def adapt_system_prompt(base_prompt: str, model_name: str) -> str:
    profile = get_profile(model_name)
    
    # Apply model-specific prefix/suffix
    prompt = profile.system_prefix + base_prompt + profile.system_suffix
    
    # Add style instructions
    if profile.system_style == "structured":
        prompt += "\n\nUse clear sections with headers. Be thorough and organized."
    elif profile.system_style == "concise":
        prompt += "\n\nBe concise and direct. Avoid unnecessary verbosity."
    elif profile.system_style == "direct":
        prompt += "\n\nBe direct and imperative. Give clear instructions."
    elif profile.system_style == "explicit":
        prompt += "\n\nBe explicit and detailed. Provide step-by-step guidance."
    
    # Tool format instructions
    if profile.tool_format == "function_calling":
        prompt += "\n\nUse function calling format for tool invocations."
        if profile.parallel_tools:
            prompt += " You can invoke multiple tools in parallel."
    elif profile.tool_format == "json_schema":
        prompt += "\n\nOutput tool calls as JSON matching the provided schema."
    
    return prompt
```

### Tool Format Adaptation

```python
def adapt_tools(tools: List[Dict], model_name: str) -> List[Dict]:
    profile = get_profile(model_name)
    
    if profile.tool_format == "json_schema":
        # Convert to JSON Schema format
        return [{
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters", {"type": "object", "properties": {}})
            }
        } for t in tools]
    
    return tools
```

### Sampling Parameters

```python
def get_sampling_params(model_name: str) -> Dict:
    profile = get_profile(model_name)
    
    return {
        "temperature": 0.7 if profile.supports_temperature else None,
        "top_p": 0.95 if profile.supports_top_p else None,
        "max_tokens": profile.max_output_tokens,
        "stop_sequences": profile.stop_sequences or []
    }
```

## Task-Specific Prompt Templates

### Code Review Template

```python
CODE_REVIEW_TEMPLATES = {
    ModelFamily.CLAUDE: """<task>
You are an expert code reviewer. Analyze the provided code for:
1. Correctness and edge cases
2. Security vulnerabilities
3. Performance implications
4. Code style and maintainability
5. Test coverage

Provide specific, actionable feedback with line references.
</task>""",
    
    ModelFamily.GPT: """You are an expert code reviewer. Analyze for:
1. Correctness & edge cases
2. Security vulnerabilities
3. Performance implications
4. Code style & maintainability
5. Test coverage

Be specific with line references.""",
    
    ModelFamily.NEMOTRON: """<|system|>
You are an expert code reviewer. Check for:
1. Correctness & edge cases
2. Security vulnerabilities
3. Performance issues
4. Code style & maintainability
5. Test coverage

Give specific feedback with line numbers.
<|user|>""",
    
    ModelFamily.LOCAL: """<|system|>
You are an expert code reviewer. Analyze the code for:
1. Correctness & edge cases
2. Security vulnerabilities
3. Performance issues
4. Code style & maintainability
5. Test coverage

Provide specific feedback with line references.
<|user|>"""
}
```

### Debugging Template

```python
DEBUGGING_TEMPLATES = {
    ModelFamily.CLAUDE: """<task>
You are an expert debugger. Given an error or failing test:
1. Analyze the error message and stack trace
2. Identify the root cause
3. Propose a minimal fix
4. Explain why the fix works
5. Suggest tests to prevent regression
</task>""",
    
    ModelFamily.GPT: """You are an expert debugger. For the given error:
1. Analyze error & stack trace
2. Find root cause
3. Propose minimal fix
4. Explain why it works
5. Suggest prevention tests""",
    
    ModelFamily.NEMOTRON: """<|system|>
You are an expert debugger. For the error:
1. Analyze error & stack trace
2. Find root cause
3. Propose minimal fix
4. Explain why it works
5. Suggest regression tests
<|user|>""",
    
    ModelFamily.LOCAL: """<|system|>
You are an expert debugger. Given an error:
1. Analyze error & stack trace
2. Identify root cause
3. Propose minimal fix
4. Explain why it works
5. Suggest tests to prevent regression
<|user|>"""
}
```

## Configuration File

```yaml
# ~/.hermes/model_profiles.yaml
profiles:
  custom-model:
    family: "claude"
    name_patterns: ["my-custom-model"]
    system_style: "structured"
    use_xml_tags: true
    tool_format: "function_calling"
    parallel_tools: true
    reasoning_style: "extended_thinking"
    context_window: 100000
    compression_strategy: "smart"
    max_output_tokens: 8192
    system_prefix: ""
    system_suffix: ""
```

## Usage

```python
from hermes_superior.scripts.model_adapter import ModelAdapter, get_prompt_template

adapter = ModelAdapter()

# Auto-adapt for any model
model = "nvidia/nemotron-3-ultra"
adapted_prompt = adapter.adapt_system_prompt(base_prompt, model)
tools = adapter.adapt_tools(tools, model)
params = adapter.get_sampling_params(model)

# Get task-specific template
code_review_prompt = get_prompt_template("code_review", model)
debug_prompt = get_prompt_template("debugging", model)
```

## Why This Makes Hermes Superior

| Aspect | Claude Code | Hermes |
|--------|-------------|--------|
| Model support | Anthropic only | **ALL models** |
| Prompt optimization | Fixed for Claude | **Per-model optimized** |
| Tool format | Fixed | **Adapted per model** |
| Reasoning style | Fixed | **Per-model optimized** |
| Context handling | Fixed | **Per-model optimized** |
| Fallback | None | **Auto-fallback chain** |
| Local models | No | **Full support** |
| Cost optimization | No | **Free tier models** |

**Result: Hermes works better than Claude Code with ANY model because the architecture adapts to the model, not the other way around.**