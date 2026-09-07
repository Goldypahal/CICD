from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..analyzer.code_retriever import CodeRetriever
from ..analyzer.context_builder import ContextBuilder
from ..analyzer.stack_trace import ParsedError, StackTraceParser
from ..detector import ProjectInfo
from ..git.repo_manager import GitRepoManager


@dataclass
class DiagnosisReport:
    parsed_error: ParsedError
    affected_files: List[str]
    context_prompt: str


class DiagnosisAgent:
    """Diagnoses test failures by extracting stack traces, code diffs, and context."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir).resolve()
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.parser = StackTraceParser()
        self.retriever = CodeRetriever(self.repo_manager)
        self.context_builder = ContextBuilder(self.retriever)

    def diagnose(
        self,
        test_output: str,
        project_info: ProjectInfo,
        commit_hash: str,
        similar_fixes: Optional[List[Dict]] = None,
    ) -> DiagnosisReport:
        print("[DiagnosisAgent] 🧠 Parsing stack traces and retrieving code context...")
        parsed_error = self.parser.parse(test_output)
        
        diff = self.repo_manager.get_commit_diff()
        changed_files = self.repo_manager.get_changed_files()

        context_packet = self.context_builder.build_context(
            project_info=project_info,
            commit_hash=commit_hash,
            diff=diff,
            changed_files=changed_files,
            parsed_error=parsed_error,
            historical_fixes=similar_fixes or [],
        )

        prompt = self.context_builder.format_prompt(context_packet)

        frame_files = [f.filename for f in parsed_error.frames if f.filename]
        affected = list(set(changed_files + frame_files))

        return DiagnosisReport(
            parsed_error=parsed_error,
            affected_files=affected,
            context_prompt=prompt,
        )
