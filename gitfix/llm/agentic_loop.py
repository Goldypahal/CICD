import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .provider import BaseLLMProvider
from .tools import AgentTools, ToolResult, get_agent_tools_schema


@dataclass
class AgentLoopResult:
    success: bool
    summary: str
    steps_taken: int
    modified_files: List[str]


class AgenticRepairLoop:
    """Executes a tool-calling reasoning loop for interactive code repair."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        tools: AgentTools,
        max_steps: int = 10,
    ):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.schema = get_agent_tools_schema()

    def run(self, initial_context: str) -> AgentLoopResult:
        modified_files: List[str] = []
        conversation_history: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an autonomous AI software repair agent. "
                    "Your goal is to inspect code, identify root causes of test failures, "
                    "propose exact file fixes, and verify using tests. "
                    "You can invoke tools: read_file, search_code, git_diff, run_test, and apply_patch."
                ),
            },
            {"role": "user", "content": initial_context},
        ]

        print("[AgenticLoop] 🤖 Starting tool-calling repair loop...")

        for step in range(1, self.max_steps + 1):
            print(f"[AgenticLoop] Step {step}/{self.max_steps}: Querying LLM...")
            
            response = self.llm.generate_fix(json.dumps(conversation_history))
            
            # Check if LLM requested tool action or provided direct payload
            tool_calls = response.get("tool_calls", [])
            files_to_fix = response.get("files", [])
            explanation = response.get("explanation", "Agent processing patch...")

            if not tool_calls and files_to_fix:
                # Direct patch payload format fallback
                for f_item in files_to_fix:
                    filepath = f_item.get("path")
                    content = f_item.get("content")
                    if filepath and content:
                        res = self.tools.apply_patch(filepath, content)
                        if res.success:
                            modified_files.append(filepath)

                # Verify via test
                test_res = self.tools.run_test()
                if test_res.success:
                    return AgentLoopResult(
                        success=True,
                        summary=explanation,
                        steps_taken=step,
                        modified_files=list(set(modified_files)),
                    )

            if not tool_calls:
                # Process single response or continue
                conversation_history.append({"role": "assistant", "content": explanation})
                test_res = self.tools.run_test()
                if test_res.success:
                    return AgentLoopResult(
                        success=True,
                        summary=explanation,
                        steps_taken=step,
                        modified_files=list(set(modified_files)),
                    )
                continue

            # Execute requested tools
            for call in tool_calls:
                tool_name = call.get("name")
                args = call.get("args", {})
                print(f"[AgenticLoop] 🛠️ Calling Tool: {tool_name}({args})")

                result: ToolResult
                if tool_name == "read_file":
                    result = self.tools.read_file(**args)
                elif tool_name == "search_code":
                    result = self.tools.search_code(**args)
                elif tool_name == "git_diff":
                    result = self.tools.git_diff(**args)
                elif tool_name == "run_test":
                    result = self.tools.run_test(**args)
                elif tool_name == "apply_patch":
                    result = self.tools.apply_patch(**args)
                    if result.success and "filepath" in args:
                        modified_files.append(args["filepath"])
                else:
                    result = ToolResult(success=False, output=f"Unknown tool name: {tool_name}")

                conversation_history.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": result.output,
                    }
                )

                if tool_name == "apply_patch" and result.success:
                    verify_test = self.tools.run_test()
                    if verify_test.success:
                        print("[AgenticLoop] 🎉 All tests passed after patch application!")
                        return AgentLoopResult(
                            success=True,
                            summary=explanation,
                            steps_taken=step,
                            modified_files=list(set(modified_files)),
                        )

        return AgentLoopResult(
            success=False,
            summary="Max agent steps reached without resolving test failure.",
            steps_taken=self.max_steps,
            modified_files=list(set(modified_files)),
        )
