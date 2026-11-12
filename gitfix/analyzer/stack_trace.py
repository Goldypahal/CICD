import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


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
    """Parses raw test-runner output into an error type, message and stack frames."""

    PYTHON_FRAME_REGEX = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?')
    PYTEST_LOCATION_REGEX = re.compile(r"^(?P<file>[\w./\\-]+\.py):(?P<line>\d+): (?P<type>\w+)$")
    NODE_FRAME_REGEX = re.compile(r"at (?:(?P<func>[^\s(]+) )?\(?(?P<file>[^\s():]+\.[cm]?[jt]sx?):(?P<line>\d+):(?P<col>\d+)\)?")
    JAVA_FRAME_REGEX = re.compile(r"at (?P<class>[\w.$]+)\.(?P<method>[\w$<>]+)\((?P<file>[\w$]+\.java):(?P<line>\d+)\)")
    GO_FRAME_REGEX = re.compile(r"^\s*(?P<file>[\w./-]+\.go):(?P<line>\d+):")

    # pytest "E   ValueError: msg" lines are the most precise source for Python
    PYTEST_E_LINE = re.compile(r"^E\s+(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))(?::\s*(?P<msg>.*))?$")
    # pytest short summary: "FAILED tests/x.py::test_y - AssertionError: msg"
    PYTEST_SUMMARY = re.compile(r"^(?:FAILED|ERROR) (?P<test>\S+)(?: - (?P<type>[A-Za-z_][\w.]*)(?::\s*(?P<msg>.*))?)?$")
    GENERIC_ERROR = re.compile(r"(?P<type>\b[A-Z][\w.]*(?:Error|Exception))\b:?\s*(?P<msg>.*)")
    GO_FAIL = re.compile(r"^--- FAIL: (?P<test>\S+)")
    JEST_FAIL = re.compile(r"^\s*● (?P<test>.+)$")

    def parse(self, raw_output: str) -> ParsedError:
        frames: List[StackFrame] = []
        best: Optional[Tuple[int, str, str]] = None  # (priority, type, message); lower priority wins

        def offer(priority: int, etype: str, msg: str) -> None:
            nonlocal best
            if best is None or priority < best[0]:
                best = (priority, etype.strip(), (msg or "").strip())

        lines = raw_output.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()

            m = self.PYTHON_FRAME_REGEX.search(line)
            if m:
                code = lines[i + 1].strip() if i + 1 < len(lines) else None
                frames.append(StackFrame(m.group("file"), int(m.group("line")), m.group("func"), code))
            m = self.PYTEST_LOCATION_REGEX.match(stripped)
            if m:
                frames.append(StackFrame(m.group("file"), int(m.group("line"))))
            m = self.NODE_FRAME_REGEX.search(line)
            if m and "node_modules" not in m.group("file") and not m.group("file").startswith("node:"):
                frames.append(StackFrame(m.group("file"), int(m.group("line")), m.group("func")))
            m = self.JAVA_FRAME_REGEX.search(line)
            if m:
                frames.append(StackFrame(m.group("file"), int(m.group("line")), f"{m.group('class')}.{m.group('method')}"))
            m = self.GO_FRAME_REGEX.match(line)
            if m:
                frames.append(StackFrame(m.group("file"), int(m.group("line"))))

            m = self.PYTEST_E_LINE.match(stripped)
            if m:
                offer(0, m.group("type"), m.group("msg") or "")
                continue
            m = self.PYTEST_SUMMARY.match(stripped)
            if m and m.group("type"):
                offer(1, m.group("type"), m.group("msg") or m.group("test"))
                continue
            m = self.GO_FAIL.match(stripped) or self.JEST_FAIL.match(line)
            if m:
                offer(2, "TestFailure", m.group("test"))
                continue
            m = self.GENERIC_ERROR.search(stripped)
            if m:
                offer(3, m.group("type"), m.group("msg"))

        error_type, error_message = ("UnknownError", "Test or build failure detected.") if best is None else (best[1], best[2])
        return ParsedError(
            error_type=error_type,
            error_message=error_message or "Test or build failure detected.",
            frames=frames,
            raw_output=raw_output,
        )
