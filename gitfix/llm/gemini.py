import json
import os
import re
from typing import Any, Dict
from .provider import BaseLLMProvider

class GeminiProvider(BaseLLMProvider):
    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.2):
        super().__init__(model=model, temperature=temperature)
        self.api_key = os.getenv("GEMINI_API_KEY")

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            msg = self.configuration_error()
            return {"error": msg, "explanation": msg, "files": []}

        try:
            from google import genai
            from google.genai import types

            # JSON mode (response_mime_type) is only served on v1beta; newer SDKs default to v1.
            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(api_version=os.getenv("GEMINI_API_VERSION", "v1beta")),
            )
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                response_mime_type="application/json",
            )
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            
            raw_text = response.text or ""
            return self._parse_json_response(raw_text)
        except Exception as e:
            msg = f"Gemini API execution error: {e}"
            return {"error": msg, "explanation": msg, "files": []}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def configuration_error(self) -> str:
        return "" if self.api_key else "GEMINI_API_KEY is not set."

    def _parse_json_response(self, raw_text: str) -> Dict[str, Any]:
        try:
            return json.loads(raw_text)
        except Exception:
            # Match json code block if present
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            return {"explanation": raw_text, "files": []}
