import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .provider import BaseLLMProvider
from .tools import AgentTools, ToolResult, get_agent_tools_schema


@dataclass
class AgentLoopResult:
    success: bool
    summary: str
    steps_taken: int
    modified_files: List[str]
    provider_error: Optional[str] = None


def build_system_prompt(schema: List[Dict[str, Any]]) -> str:
    return (
        "You are GitFix-Agent, an autonomous software repair agent. Find the root cause of the "
        "failing tests and fix the code under test. Test files, CI configuration and dependency "
        "manifests cannot be modified; a fix that edits them will be rejected.\n\n"
        "Each turn, reply with exactly ONE JSON object and nothing else, in one of two forms:\n"
        '1. Call tools: {"tool_calls": [{"name": "<tool>", "args": {...}}], "explanation": "<why>"}\n'
        '2. Submit the fix: {"explanation": "<root cause and fix>", "files": [{"path": "<relative path>", '
        '"content": "<COMPLETE new file content>"}]}\n\n'
        "After a fix is submitted the test suite runs automatically and you will see the result.\n\n"
        f"Available tools (JSON Schema):\n{json.dumps(schema, indent=2)}"
    )


class AgenticRepairLoop:
    """Tool-calling loop: the model can inspect the repo, run tests and write files until tests pass."""

    def __init__(self, llm: BaseLLMProvider, tools: AgentTools, max_steps: int = 10):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.schema = get_agent_tools_schema()

    def _dispatch(self, name: str, args: Dict[str, Any]) -> ToolResult:
        handlers = {
            "read_file": self.tools.read_file,
            "search_code": self.tools.search_code,
            "git_diff": self.tools.git_diff,
            "run_test": self.tools.run_test,
            "apply_patch": self.tools.apply_patch,
        }
        handler = handlers.get(name)
        if handler is None:
            return ToolResult(success=False, output=f"Unknown tool name: {name}")
        try:
            return handler(**args)
        except TypeError as e:
            return ToolResult(success=False, output=f"Invalid arguments for {name}: {e}")

    def run(self, initial_context: str) -> AgentLoopResult:
        modified_files: List[str] = []
        history: List[Dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(self.schema)},
            {"role": "user", "content": initial_context},
        ]
        explanation = ""
        provider_error: Optional[str] = None

        print("[AgenticLoop] 🤖 Starting tool-calling repair loop...")
        for step in range(1, self.max_steps + 1):
            print(f"[AgenticLoop] Step {step}/{self.max_steps}: Querying LLM...")
            response = self.llm.generate_fix(json.dumps(history))
            if not isinstance(response, dict):
                response = {"explanation": str(response)}

            tool_calls = response.get("tool_calls") or []
            files_to_fix = response.get("files") or []
            explanation = response.get("explanation") or explanation or "Automated fix"
            history.append({"role": "assistant", "content": json.dumps(response)[:8000]})

            if response.get("error"):
                # Provider-level failure (missing key, network error...). Retrying won't help.
                provider_error = str(response["error"])
                print(f"[AgenticLoop] 🛑 LLM provider error: {provider_error}")
                break

            if files_to_fix:
                patch_results = []
                for item in files_to_fix:
                    path, content = item.get("path"), item.get("content")
                    if not path or content is None:
                        patch_results.append(f"Skipped invalid file entry: {item!r}"[:200])
                        continue
                    res = self.tools.apply_patch(path, content)
                    patch_results.append(res.output)
                    if res.success:
                        modified_files.append(path)

                test_res = self.tools.run_test()
                if test_res.success and modified_files:
                    print("[AgenticLoop] 🎉 Tests pass with the proposed fix.")
                    return AgentLoopResult(True, explanation, step, sorted(set(modified_files)))
                history.append({
                    "role": "tool",
                    "tool_name": "run_test",
                    "content": "Patch results:\n" + "\n".join(patch_results) + "\n\nTest output:\n" + test_res.output,
                })
                continue

            if not tool_calls:
                history.append({
                    "role": "user",
                    "content": "Your reply contained neither tool_calls nor files. Reply with one JSON object as instructed.",
                })
                continue

            for call in tool_calls:
                name = call.get("name")
                args = call.get("args") or call.get("arguments") or {}
                print(f"[AgenticLoop] 🛠️ Calling tool: {name}({', '.join(args)})")
                result = self._dispatch(name, args)
                if name == "apply_patch" and result.success:
                    modified_files.append(args.get("filepath"))
                history.append({"role": "tool", "tool_name": name, "content": result.output[:6000]})

                if name == "apply_patch" and result.success:
                    verify = self.tools.run_test()
                    if verify.success:
                        print("[AgenticLoop] 🎉 Tests pass after patch application.")
                        return AgentLoopResult(True, explanation, step, sorted(set(modified_files)))
                    history.append({"role": "tool", "tool_name": "run_test", "content": verify.output})

        # Leave the workspace exactly as we found it
        self.tools.rollback()
        return AgentLoopResult(
            success=False,
            summary="Agent did not reach passing tests. Trial patches were reverted.",
            steps_taken=step if self.max_steps else 0,
            modified_files=[],
            provider_error=provider_error,
        )
