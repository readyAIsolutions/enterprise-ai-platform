#!/usr/bin/env python3
"""
Model Adapter - Per-model prompt optimization for consistent quality
Makes Hermes work better than Claude Code regardless of model
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import yaml


class ModelFamily(Enum):
    CLAUDE = "claude"
    GPT = "gpt"
    NEMOTRON = "nemotron"
    DEEPSEEK = "deepseek"
    SOLAR = "solar"
    GLM = "glm"
    LLAMA = "llama"
    MISTRAL = "mistral"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass
class ModelProfile:
    """Optimized configuration for a specific model family."""
    family: ModelFamily
    name_patterns: List[str] = field(default_factory=list)
    
    # System prompt style
    system_style: str = "structured"  # structured, concise, explicit, direct
    use_xml_tags: bool = True
    use_markdown: bool = True
    
    # Tool calling format
    tool_format: str = "function_calling"  # function_calling, json_schema, structured_output
    parallel_tools: bool = True
    require_tool_descriptions: bool = True
    
    # Reasoning
    reasoning_style: str = "chain_of_thought"  # chain_of_thought, extended_thinking, step_by_step, few_shot
    show_reasoning: bool = True
    reasoning_budget: int = 4000
    
    # Context handling
    context_window: int = 128000
    compression_strategy: str = "smart"  # smart, truncate, summarize
    preserve_tool_results: bool = True
    
    # Output preferences
    prefer_markdown: bool = True
    prefer_code_blocks: bool = True
    verbose_explanations: bool = True
    
    # Special handling
    supports_system_prompt: bool = True
    supports_temperature: bool = True
    supports_top_p: bool = True
    max_output_tokens: int = 8192
    
    # Prompt templates
    system_prefix: str = ""
    system_suffix: str = ""
    tool_prefix: str = ""
    tool_suffix: str = ""
    
    # Few-shot examples
    few_shot_examples: List[Dict] = field(default_factory=list)


# =============================================================================
# MODEL PROFILES
# =============================================================================

MODEL_PROFILES = {
    ModelFamily.CLAUDE: ModelProfile(
        family=ModelFamily.CLAUDE,
        name_patterns=["claude", "anthropic"],
        system_style="structured",
        use_xml_tags=True,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="extended_thinking",
        show_reasoning=True,
        reasoning_budget=8000,
        context_window=200000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=8192,
        system_prefix="",
        system_suffix="",
        few_shot_examples=[]
    ),
    
    ModelFamily.GPT: ModelProfile(
        family=ModelFamily.GPT,
        name_patterns=["gpt", "openai"],
        system_style="concise",
        use_xml_tags=False,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="chain_of_thought",
        show_reasoning=False,
        reasoning_budget=4000,
        context_window=128000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=False,
        supports_system_prompt=True,
        max_output_tokens=4096,
        system_prefix="",
        system_suffix="",
        few_shot_examples=[]
    ),
    
    ModelFamily.NEMOTRON: ModelProfile(
        family=ModelFamily.NEMOTRON,
        name_patterns=["nemotron", "nvidia"],
        system_style="direct",
        use_xml_tags=False,
        use_markdown=True,
        tool_format="json_schema",
        parallel_tools=False,
        reasoning_style="step_by_step",
        show_reasoning=True,
        reasoning_budget=4000,
        context_window=128000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=8192,
        system_prefix="<|system|>\n",
        system_suffix="\n<|user|>",
        few_shot_examples=[]
    ),
    
    ModelFamily.DEEPSEEK: ModelProfile(
        family=ModelFamily.DEEPSEEK,
        name_patterns=["deepseek"],
        system_style="explicit",
        use_xml_tags=True,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="chain_of_thought",
        show_reasoning=True,
        reasoning_budget=8000,
        context_window=128000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=8192,
        few_shot_examples=[]
    ),
    
    ModelFamily.SOLAR: ModelProfile(
        family=ModelFamily.SOLAR,
        name_patterns=["solar", "upstage"],
        system_style="structured",
        use_xml_tags=True,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="chain_of_thought",
        show_reasoning=False,
        reasoning_budget=4000,
        context_window=32000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=4096,
        few_shot_examples=[]
    ),
    
    ModelFamily.GLM: ModelProfile(
        family=ModelFamily.GLM,
        name_patterns=["glm", "zhipu"],
        system_style="structured",
        use_xml_tags=True,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="chain_of_thought",
        show_reasoning=False,
        reasoning_budget=4000,
        context_window=128000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=8192,
        few_shot_examples=[]
    ),
    
    ModelFamily.LLAMA: ModelProfile(
        family=ModelFamily.LLAMA,
        name_patterns=["llama", "meta-llama"],
        system_style="explicit",
        use_xml_tags=False,
        use_markdown=True,
        tool_format="json_schema",
        parallel_tools=False,
        reasoning_style="few_shot",
        show_reasoning=True,
        reasoning_budget=4000,
        context_window=128000,
        compression_strategy="truncate",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=4096,
        system_prefix="<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n",
        system_suffix="\n<|eot_id|><|start_header_id|>user<|end_header_id|>\n",
        few_shot_examples=[]
    ),
    
    ModelFamily.MISTRAL: ModelProfile(
        family=ModelFamily.MISTRAL,
        name_patterns=["mistral", "mixtral"],
        system_style="concise",
        use_xml_tags=False,
        use_markdown=True,
        tool_format="function_calling",
        parallel_tools=True,
        reasoning_style="chain_of_thought",
        show_reasoning=False,
        reasoning_budget=4000,
        context_window=32000,
        compression_strategy="smart",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=False,
        supports_system_prompt=True,
        max_output_tokens=4096,
        few_shot_examples=[]
    ),
    
    ModelFamily.LOCAL: ModelProfile(
        family=ModelFamily.LOCAL,
        name_patterns=["local", "ollama", "vllm"],
        system_style="explicit",
        use_xml_tags=False,
        use_markdown=True,
        tool_format="json_schema",
        parallel_tools=False,
        reasoning_style="few_shot",
        show_reasoning=True,
        reasoning_budget=4000,
        context_window=32000,
        compression_strategy="truncate",
        prefer_markdown=True,
        prefer_code_blocks=True,
        verbose_explanations=True,
        supports_system_prompt=True,
        max_output_tokens=4096,
        system_prefix="<|system|>\n",
        system_suffix="\n<|user|>",
        few_shot_examples=[]
    )
}


# =============================================================================
# MODEL ADAPTER
# =============================================================================

class ModelAdapter:
    """
    Adapts prompts and parameters for optimal performance per model.
    """
    
    def __init__(self):
        self.profiles = MODEL_PROFILES
        self.custom_profiles: Dict[str, ModelProfile] = {}
    
    def detect_family(self, model_name: str) -> ModelFamily:
        """Detect model family from name."""
        model_lower = model_name.lower()
        
        for family, profile in self.profiles.items():
            for pattern in profile.name_patterns:
                if pattern in model_lower:
                    return family
        
        # Check custom profiles
        for name, profile in self.custom_profiles.items():
            for pattern in profile.name_patterns:
                if pattern in model_lower:
                    return profile.family
        
        return ModelFamily.UNKNOWN
    
    def get_profile(self, model_name: str) -> ModelProfile:
        """Get profile for a model."""
        family = self.detect_family(model_name)
        
        if family == ModelFamily.UNKNOWN:
            # Try custom profiles
            for name, profile in self.custom_profiles.items():
                if name.lower() in model_name.lower():
                    return profile
            # Default to local profile
            return self.profiles[ModelFamily.LOCAL]
        
        return self.profiles[family]
    
    def register_custom_profile(self, name: str, profile: ModelProfile):
        """Register a custom model profile."""
        self.custom_profiles[name] = profile
    
    def load_profiles_from_yaml(self, path: str):
        """Load profiles from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        for name, config in data.get("profiles", {}).items():
            profile = ModelProfile(
                family=ModelFamily(config.get("family", "unknown")),
                name_patterns=config.get("name_patterns", [name]),
                **{k: v for k, v in config.items() if k not in ["family", "name_patterns"]}
            )
            self.custom_profiles[name] = profile
    
    def adapt_system_prompt(self, base_prompt: str, model_name: str) -> str:
        """Adapt system prompt for model."""
        profile = self.get_profile(model_name)
        
        # Apply prefix/suffix
        prompt = profile.system_prefix + base_prompt + profile.system_suffix
        
        # Add style instructions
        style_instructions = self._get_style_instructions(profile)
        if style_instructions:
            prompt = style_instructions + "\n\n" + prompt
        
        # Add tool format instructions
        tool_instructions = self._get_tool_instructions(profile)
        if tool_instructions:
            prompt = prompt + "\n\n" + tool_instructions
        
        return prompt
    
    def _get_style_instructions(self, profile: ModelProfile) -> str:
        """Generate style instructions based on profile."""
        instructions = []
        
        if profile.system_style == "structured":
            instructions.append("Use clear sections with headers. Be thorough and organized.")
        elif profile.system_style == "concise":
            instructions.append("Be concise and direct. Avoid unnecessary verbosity.")
        elif profile.system_style == "direct":
            instructions.append("Be direct and imperative. Give clear instructions.")
        elif profile.system_style == "explicit":
            instructions.append("Be explicit and detailed. Provide step-by-step guidance.")
        
        if profile.use_xml_tags:
            instructions.append("Use XML tags for structured output (e.g., <thinking>, <answer>).")
        
        if profile.use_markdown:
            instructions.append("Use Markdown formatting for readability.")
        
        if profile.verbose_explanations:
            instructions.append("Provide thorough explanations with reasoning.")
        else:
            instructions.append("Be concise. Focus on actionable information.")
        
        return "\n".join(instructions) if instructions else ""
    
    def _get_tool_instructions(self, profile: ModelProfile) -> str:
        """Generate tool usage instructions."""
        instructions = []
        
        if profile.tool_format == "function_calling":
            instructions.append("Use the function calling format for tool invocations.")
        elif profile.tool_format == "json_schema":
            instructions.append("Output tool calls as JSON matching the provided schema.")
        elif profile.tool_format == "structured_output":
            instructions.append("Use structured output format for tools.")
        
        if profile.parallel_tools:
            instructions.append("You can invoke multiple tools in parallel when appropriate.")
        
        if profile.require_tool_descriptions:
            instructions.append("Always explain what each tool call does before invoking.")
        
        if profile.preserve_tool_results:
            instructions.append("Carefully analyze tool results before proceeding.")
        
        return "\n".join(instructions) if instructions else ""
    
    def adapt_tools(self, tools: List[Dict], model_name: str) -> List[Dict]:
        """Adapt tool definitions for model."""
        profile = self.get_profile(model_name)
        
        if profile.tool_format == "json_schema":
            # Convert to JSON Schema format
            return [self._to_json_schema(tool) for tool in tools]
        elif profile.tool_format == "structured_output":
            return [self._to_structured_output(tool) for tool in tools]
        
        return tools
    
    def _to_json_schema(self, tool: Dict) -> Dict:
        """Convert tool to JSON Schema format."""
        return {
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}})
            }
        }
    
    def _to_structured_output(self, tool: Dict) -> Dict:
        """Convert to structured output format."""
        return {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "schema": tool.get("parameters", {"type": "object", "properties": {}})
        }
    
    def get_sampling_params(self, model_name: str) -> Dict:
        """Get optimal sampling parameters for model."""
        profile = self.get_profile(model_name)
        
        return {
            "temperature": 0.7 if profile.supports_temperature else None,
            "top_p": 0.95 if profile.supports_top_p else None,
            "max_tokens": profile.max_output_tokens,
            "stop_sequences": []
        }
    
    def format_tool_call(self, tool_name: str, args: Dict, model_name: str) -> str:
        """Format tool call for model."""
        profile = self.get_profile(model_name)
        
        if profile.tool_format == "json_schema":
            return json.dumps({
                "name": tool_name,
                "arguments": args
            })
        elif profile.tool_format == "function_calling":
            # Return as structured object (handled by API)
            return {"name": tool_name, "arguments": args}
        
        return str({"name": tool_name, "arguments": args})


# =============================================================================
# PROMPT TEMPLATES PER MODEL
# =============================================================================

PROMPT_TEMPLATES = {
    "code_review": {
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
    },
    
    "debugging": {
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
}


def get_prompt_template(template_name: str, model_name: str) -> str:
    """Get optimized prompt template for model."""
    adapter = ModelAdapter()
    family = adapter.detect_family(model_name)
    
    templates = PROMPT_TEMPLATES.get(template_name, {})
    return templates.get(family, templates.get(ModelFamily.LOCAL, ""))


# =============================================================================
# USAGE
# =============================================================================

def demo():
    """Demo the model adapter."""
    adapter = ModelAdapter()
    
    test_models = [
        "anthropic/claude-3-opus",
        "openai/gpt-4o",
        "nvidia/nemotron-3-ultra",
        "deepseek/deepseek-v3",
        "upstage/solar-pro",
        "zhipu/glm-4",
        "meta-llama/llama-3.1-70b",
        "mistralai/mistral-large",
        "local/llama-3.1-8b"
    ]
    
    base_prompt = "You are a helpful assistant that writes clean, efficient code."
    
    for model in test_models:
        profile = adapter.get_profile(model)
        adapted = adapter.adapt_system_prompt(base_prompt, model)
        params = adapter.get_sampling_params(model)
        
        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"Family: {profile.family.value}")
        print(f"Style: {profile.system_style}")
        print(f"Tool format: {profile.tool_format}")
        print(f"Reasoning: {profile.reasoning_style}")
        print(f"Context window: {profile.context_window:,}")
        print(f"Max output: {profile.max_output_tokens}")
        print(f"Adapted prompt length: {len(adapted)} chars")
        print(f"Sampling: {params}")


if __name__ == "__main__":
    demo()