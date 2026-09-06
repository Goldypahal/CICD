import re
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class StackFrame:
    filename: str
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    code_line: Optional[str] = None

@dataclass
class ParsedError:
    error_type: str
    error_message: str
    frames: List[StackFrame] = field(default_factory=list)
    raw_output: str = ""

class StackTraceParser:
    """Parses raw stdout/stderr output from test runs into structured error details."""

    PYTHON_FRAME_REGEX = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?')
    NODE_FRAME_REGEX = re.compile(r'at (?P<func>\S+ \([^)]+\)|\S+) \((?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)\)')
    JAVA_FRAME_REGEX = re.compile(r'at (?P<class>[a-zA-Z0-9_\.]+)\.(?P<method>[a-zA-Z0-9_]+)\((?P<file>[a-zA-Z0-9_\.]+\.java):(?P<line>\d+)\)')

    def parse(self, raw_output: str) -> ParsedError:
        error_type = "UnknownError"
        error_message = "Test or build failure detected."
        frames = []

        lines = raw_output.splitlines()
        for i, line in enumerate(lines):
            # Python Traceback detection
            py_match = self.PYTHON_FRAME_REGEX.search(line)
            if py_match:
                filename = py_match.group("file")
                line_no = int(py_match.group("line"))
                func = py_match.group("func")
                code_snippet = lines[i+1].strip() if i + 1 < len(lines) else None
                frames.append(StackFrame(filename=filename, line_number=line_no, function_name=func, code_line=code_snippet))

            # Node/JS Stack Trace
            node_match = self.NODE_FRAME_REGEX.search(line)
            if node_match:
                filename = node_match.group("file")
                line_no = int(node_match.group("line"))
                func = node_match.group("func")
                frames.append(StackFrame(filename=filename, line_number=line_no, function_name=func))

            # Exception line (e.g. TypeError: ..., AssertionError: ...)
            if ":" in line and any(err_kw in line for err_kw in ["Error", "Exception", "FAIL", "FAILED"]):
                parts = line.split(":", 1)
                if len(parts) == 2 and len(parts[0].strip()) < 50:
                    error_type = parts[0].strip()
                    error_message = parts[1].strip()

        return ParsedError(
            error_type=error_type,
            error_message=error_message,
            frames=frames,
            raw_output=raw_output,
        )
