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
            # Fallback warning if key not provided
            return {
                "explanation": "GEMINI_API_KEY is missing from environment. Using fallback response generator.",
                "files": []
            }

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
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
            return {
                "explanation": f"Gemini API execution error: {e}",
                "files": []
            }

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
