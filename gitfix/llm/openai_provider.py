import json
import os
import re
import urllib.request
from typing import Any, Dict
from .provider import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.2):
        super().__init__(model=model, temperature=temperature)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            return {
                "explanation": "OPENAI_API_KEY is missing from environment.",
                "files": []
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or 'ollama'}",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are GitFix-Agent, an expert autonomous code patcher."},
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            return {
                "explanation": f"OpenAI/Ollama provider error: {e}",
                "files": [],
            }
