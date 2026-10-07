from __future__ import annotations
import os
from typing import Optional
from guardian_ai.providers.base import LLMProvider
from guardian_ai.providers.gemini_provider import GeminiProvider
from guardian_ai.providers.openai_provider import OpenAIProvider
from guardian_ai.providers.anthropic_provider import AnthropicProvider
from guardian_ai.providers.heuristic_provider import HeuristicProvider

def get_llm_provider(preferred_provider: Optional[str] = None) -> LLMProvider:
    """Detects and instantiates the appropriate LLM provider.
    Priority:
    1. Explicit preferred provider if corresponding key exists
    2. GEMINI_API_KEY -> GeminiProvider
    3. OPENAI_API_KEY -> OpenAIProvider
    4. ANTHROPIC_API_KEY -> AnthropicProvider
    5. Fallback -> HeuristicProvider (Deterministic)
    """
    pref = (preferred_provider or "").lower()
    
    if pref == "gemini" and os.getenv("GEMINI_API_KEY"):
        return GeminiProvider()
    elif pref == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    elif pref == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    elif pref == "heuristic" or pref == "local":
        return HeuristicProvider()

    # Automatic detection
    if os.getenv("GEMINI_API_KEY"):
        return GeminiProvider()
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()

    return HeuristicProvider()
