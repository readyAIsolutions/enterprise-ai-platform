# Hermes Desktop Integration - Session Notes

## Endpoints implemented (2026-07-07)

### /free-models (public)
Returns all known free models across providers:
- 30 models total
- Providers: openrouter, groq, cerebras, sambanova, google

### /hermes/skills
Returns skills from local `skills/*.md` + Hermes `list_available_skills()`

### /hermes/tools  
Returns available toolsets from Hermes config

### /hermes/kb?q=X
Queries session_search for knowledge base access

## Free models list (for /free-models endpoint)

```python
known_free = [
    # OpenRouter
    {"model": "google/gemma-4-31b-it:free", "provider": "openrouter"},
    {"model": "google/gemma-4-26b-a4b-it:free", "provider": "openrouter"},
    {"model": "moonshotai/kimi-k2.6:free", "provider": "openrouter"},
    {"model": "openai/gpt-oss-120b:free", "provider": "openrouter"},
    {"model": "qwen/qwen3-next-80b-a3b-instruct:free", "provider": "openrouter"},
    {"model": "qwen/qwen3-coder:free", "provider": "openrouter"},
    {"model": "z-ai/glm-4.5-air:free", "provider": "openrouter"},
    {"model": "meta-llama/llama-3.3-70b-instruct:free", "provider": "openrouter"},
    {"model": "nvidia/nemotron-3-ultra-550b-a55b:free", "provider": "openrouter"},
    {"model": "nousresearch/hermes-3-llama-3.1-405b:free", "provider": "openrouter"},
    {"model": "deepseek/deepseek-chat-v3:free", "provider": "openrouter"},
    {"model": "deepseek/deepseek-r1:free", "provider": "openrouter"},
    {"model": "poolside/laguna-m.1:free", "provider": "openrouter"},
    {"model": "nvidia/nemotron-3-super-120b:free", "provider": "openrouter"},
    {"model": "cohere/north-mini-code:free", "provider": "openrouter"},
    {"model": "cognitivecomputations/dolphin-mistral-24b:free", "provider": "openrouter"},
    {"model": "microsoft/mai-ds-r1:free", "provider": "openrouter"},
    {"model": "cerebras/llama-3.3-70b:free", "provider": "openrouter"},
    {"model": "sambanova/Llama-3.3-70B:free", "provider": "openrouter"},
    {"model": "openrouter/elephant-alpha", "provider": "openrouter"},
    {"model": "openrouter/owl-alpha", "provider": "openrouter"},
    # Groq
    {"model": "llama-3.3-70b-versatile", "provider": "groq"},
    {"model": "llama-3.1-8b-instant", "provider": "groq"},
    {"model": "gemma2-9b-it", "provider": "groq"},
    # Cerebras
    {"model": "llama3-70b-8192", "provider": "cerebras"},
    {"model": "llama-3.3-70b", "provider": "cerebras"},
    # Sambanova
    {"model": "Meta-Llama-3.3-70B-Instruct", "provider": "sambanova"},
    {"model": "DeepSeek-R1-Distill-Llama-70B", "provider": "sambanova"},
    # Google (free-tier limited)
    {"model": "gemini-2.5-flash", "provider": "google"},
    {"model": "gemini-2.0-flash", "provider": "google"},
]
```

## Desktop UI features

- Status indicator: green dot when online, red when offline
- Free model count badge in header
- Clickable free models popup
- Auto-grows input textarea (max 120px height)
- Markdown support: code blocks, inline code, bold
- Thinking indicator with animated dots during API calls