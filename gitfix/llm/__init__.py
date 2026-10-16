from typing import Optional
from .provider import BaseLLMProvider
from .nemotron import NemotronProvider
from .gemini import GeminiProvider
from .openai_provider import OpenAIProvider
from .mock_provider import MockLLMProvider

def get_llm_provider(
    provider_name: str = "nemotron",
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> BaseLLMProvider:
    p_lower = provider_name.lower()
    if p_lower == "nemotron":
        m = model or "nvidia/nemotron-4-340b-instruct"
        return NemotronProvider(model=m, temperature=temperature)
    elif p_lower == "gemini":
        m = model or "gemini-2.5-flash"
        return GeminiProvider(model=m, temperature=temperature)
    elif p_lower in ["openai", "ollama"]:
        m = model or "gpt-4o-mini"
        return OpenAIProvider(model=m, temperature=temperature)
    elif p_lower == "mock":
        return MockLLMProvider()
    else:
        raise ValueError(
            f"Unsupported LLM provider '{provider_name}'. Supported providers: 'nemotron', 'gemini', 'openai', 'ollama', 'mock'."
        )

__all__ = [
    "BaseLLMProvider",
    "NemotronProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "MockLLMProvider",
    "get_llm_provider",
]
