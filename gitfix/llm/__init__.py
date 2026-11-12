import os
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
    elif p_lower == "openai":
        return OpenAIProvider(model=model or "gpt-4o-mini", temperature=temperature)
    elif p_lower == "ollama":
        # Ollama exposes an OpenAI-compatible API locally; no API key needed.
        base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "http://localhost:11434/v1"
        return OpenAIProvider(model=model or "llama3.1", temperature=temperature, base_url=base_url)
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
