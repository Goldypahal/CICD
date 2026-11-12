from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from ..llm.agentic_loop import AgenticRepairLoop, AgentLoopResult
from ..llm.provider import BaseLLMProvider
from ..llm.tools import AgentTools, CommandRunner


@dataclass
class PatchAgentResult:
    success: bool
    explanation: str
    modified_files: List[str]
    steps_taken: int
    provider_error: Optional[str] = None


class PatchAgent:
    """Runs the tool-calling LLM loop that writes the candidate fix."""

    def __init__(
        self,
        repo_dir: Path,
        llm: BaseLLMProvider,
        test_command: str,
        security_agent: Optional[Any] = None,
        runner: Optional[CommandRunner] = None,
        max_steps: int = 10,
    ):
        self.repo_dir = Path(repo_dir).resolve()
        self.llm = llm
        self.security_agent = security_agent
        self.tools = AgentTools(self.repo_dir, test_command=test_command, security_agent=security_agent, runner=runner)
        self.loop = AgenticRepairLoop(self.llm, self.tools, max_steps=max_steps)

    def generate_and_apply_fix(self, context_prompt: str) -> PatchAgentResult:
        print("[PatchAgent] 🛠️ Executing interactive tool-calling fix generation...")
        loop_res: AgentLoopResult = self.loop.run(context_prompt)
        return PatchAgentResult(
            success=loop_res.success,
            explanation=loop_res.summary,
            modified_files=loop_res.modified_files,
            steps_taken=loop_res.steps_taken,
            provider_error=loop_res.provider_error,
        )

    def rollback(self) -> None:
        """Undo every file this agent wrote. Touches nothing else in the working tree."""
        self.tools.rollback()

    def accept(self) -> None:
        """Keep the current edits (they've been committed)."""
        self.tools.commit_backups()
