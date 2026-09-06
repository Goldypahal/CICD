from dataclasses import dataclass, field
from typing import Dict, List, Optional
from ..detector.base import ProjectInfo
from .stack_trace import ParsedError
from .code_retriever import CodeRetriever

@dataclass
class ContextPacket:
    project_info: ProjectInfo
    commit_hash: str
    diff: str
    changed_files: List[str]
    parsed_error: ParsedError
    file_snippets: Dict[str, str] = field(default_factory=dict)
    test_snippets: Dict[str, str] = field(default_factory=dict)
    historical_fixes: List[Dict] = field(default_factory=list)

class ContextBuilder:
    def __init__(self, code_retriever: CodeRetriever):
        self.retriever = code_retriever

    def build_context(
        self,
        project_info: ProjectInfo,
        commit_hash: str,
        diff: str,
        changed_files: List[str],
        parsed_error: ParsedError,
        historical_fixes: Optional[List[Dict]] = None,
    ) -> ContextPacket:
        file_snippets = {}
        
        # 1. Fetch file snippets for changed files
        for f in changed_files:
            # Check if stack trace referenced line in this file
            center_line = None
            for frame in parsed_error.frames:
                if frame.filename and f in frame.filename:
                    center_line = frame.line_number
                    break
            snippet = self.retriever.get_file_snippet(f, center_line=center_line)
            if snippet:
                file_snippets[f] = snippet

        # 2. Fetch related test files snippets
        test_snippets = {}
        related_tests = self.retriever.find_related_test_files(changed_files)
        for t in related_tests:
            snippet = self.retriever.get_file_snippet(t)
            if snippet:
                test_snippets[t] = snippet

        return ContextPacket(
            project_info=project_info,
            commit_hash=commit_hash,
            diff=diff,
            changed_files=changed_files,
            parsed_error=parsed_error,
            file_snippets=file_snippets,
            test_snippets=test_snippets,
            historical_fixes=historical_fixes or [],
        )

    def format_prompt(self, context: ContextPacket) -> str:
        prompt_parts = [
            "ROLE: You are an autonomous software debugging agent (GitFix-Agent).",
            f"PROJECT: {context.project_info.language} ({context.project_info.framework or 'General'})",
            f"COMMIT: {self.context_hash_display(context.commit_hash)}",
            "",
            "=== ERROR DETAILS ===",
            f"Error Type: {context.parsed_error.error_type}",
            f"Message: {context.parsed_error.error_message}",
            "",
            "=== RAW TEST OUTPUT ===",
            context.parsed_error.raw_output[-1500:],
            "",
            "=== GIT DIFF (HEAD~1..HEAD) ===",
            context.diff or "[No diff detected]",
            "",
            "=== CHANGED FILES & CODE SNIPPETS ===",
        ]

        for filepath, snippet in context.file_snippets.items():
            prompt_parts.append(f"--- File: {filepath} ---")
            prompt_parts.append(snippet)
            prompt_parts.append("")

        if context.test_snippets:
            prompt_parts.append("=== RELATED TEST SUITE ===")
            for tpath, tsnippet in context.test_snippets.items():
                prompt_parts.append(f"--- Test File: {tpath} ---")
                prompt_parts.append(tsnippet)
                prompt_parts.append("")

        if context.historical_fixes:
            prompt_parts.append("=== RELEVANT HISTORICAL FIXES (RAG MEMORY) ===")
            for fix in context.historical_fixes:
                prompt_parts.append(f"Past Error: {fix.get('error_type')}: {fix.get('error_message')}")
                prompt_parts.append(f"Solution: {fix.get('summary')}")
                prompt_parts.append("")

        prompt_parts.extend([
            "=== INSTRUCTIONS ===",
            "1. Analyze the root cause of the error introduced by the commit diff or existing logic.",
            "2. Provide a unified diff patch OR full updated file content to fix the issue cleanly.",
            "3. Do not modify test assertions unless the test itself is genuinely invalid.",
            "4. Return your output in the following JSON format:",
            "```json",
            "{",
            '  "explanation": "Clear explanation of root cause and fix",',
            '  "files": [',
            "    {",
            '      "path": "path/to/file.ext",',
            '      "content": "Full complete code for the file OR patch diff"',
            "    }",
            "  ]",
            "}",
            "```"
        ])

        return "\n".join(prompt_parts)

    @staticmethod
    def context_hash_display(h: str) -> str:
        return h[:7] if h else "HEAD"
