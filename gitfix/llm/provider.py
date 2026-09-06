from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class BaseLLMProvider(ABC):
    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.2):
        self.model = model
        self.temperature = temperature

    @abstractmethod
    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        """
        Sends prompt to LLM and returns structured dict with:
        - "explanation": str
        - "files": List[Dict[str, str]] with "path" and "content"
        """
        pass
