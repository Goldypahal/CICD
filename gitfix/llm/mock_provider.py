from typing import Any, Dict, List, Optional
from .provider import BaseLLMProvider

class MockLLMProvider(BaseLLMProvider):
    def __init__(self, mock_files: Optional[List[Dict[str, str]]] = None, explanation: str = "Mock automated patch"):
        super().__init__(model="mock", temperature=0.0)
        self.mock_files = mock_files or []
        self.explanation = explanation

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        return {
            "explanation": self.explanation,
            "files": self.mock_files,
        }
