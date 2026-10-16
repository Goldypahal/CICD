import json
import os
import re
import urllib.request
from typing import Any, Dict
from .provider import BaseLLMProvider

class NemotronProvider(BaseLLMProvider):
    def __init__(self, model: str = "nvidia/nemotron-4-340b-instruct", temperature: float = 0.2):
        super().__init__(model=model, temperature=temperature)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "explanation": "NVIDIA_API_KEY environment variable is not configured. Please set NVIDIA_API_KEY to use NemotronProvider.",
                "files": [],
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are GitFix-Agent, an expert autonomous software debugging and code patching model."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "top_p": 0.7,
            "max_tokens": 4096,
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return self._parse_json_response(content)
        except Exception as e:
            return {
                "explanation": f"NVIDIA Nemotron provider error: {e}",
                "files": [],
            }

    def _parse_json_response(self, raw_text: str) -> Dict[str, Any]:
        try:
            return json.loads(raw_text)
        except Exception:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            return {"explanation": raw_text, "files": []}
