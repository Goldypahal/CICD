import json
import os
import urllib.request
from typing import Any, Dict, Optional

from .provider import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Chat Completions, or any OpenAI-compatible server (Ollama, vLLM, LM Studio)."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.2, base_url: Optional[str] = None):
        super().__init__(model=model, temperature=temperature)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    def _is_local(self) -> bool:
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def is_configured(self) -> bool:
        return bool(self.api_key) or self._is_local()

    def configuration_error(self) -> str:
        return "" if self.is_configured() else "OPENAI_API_KEY is not set."

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        if not self.is_configured():
            msg = self.configuration_error()
            return {"error": msg, "explanation": msg, "files": []}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or 'ollama'}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are GitFix-Agent, an expert autonomous code patcher. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
        except Exception as e:
            msg = f"OpenAI/Ollama provider error: {e}"
            return {"error": msg, "explanation": msg, "files": []}

        try:
            return json.loads(content)
        except Exception:
            return {"explanation": content, "files": []}
