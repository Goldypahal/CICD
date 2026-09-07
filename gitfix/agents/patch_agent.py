from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..llm.agentic_loop import AgenticRepairLoop, AgentLoopResult
from ..llm.provider import BaseLLMProvider
from ..llm.tools import AgentTools


@dataclass
class PatchAgentResult:
    success: bool
    explanation: str
    modified_files: List[str]
    steps_taken: int


class PatchAgent:
    """Executes tool-calling LLM repair loops to generate and apply code patches."""

    def __init__(self, repo_dir: Path, llm: BaseLLMProvider, test_command: str):
        self.repo_dir = Path(repo_dir).resolve()
        self.llm = llm
        self.tools = AgentTools(self.repo_dir, test_command=test_command)
        self.loop = AgenticRepairLoop(self.llm, self.tools, max_steps=10)

    def generate_and_apply_fix(self, context_prompt: str) -> PatchAgentResult:
        print("[PatchAgent] 🛠️ Executing interactive tool-calling fix generation...")
        loop_res: AgentLoopResult = self.loop.run(context_prompt)
        
        return PatchAgentResult(
            success=loop_res.success,
            explanation=loop_res.summary,
            modified_files=loop_res.modified_files,
            steps_taken=loop_res.steps_taken,
        )
