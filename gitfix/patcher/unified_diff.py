import re
from typing import List

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    pass


def looks_like_unified_diff(text: str) -> bool:
    head = text.lstrip()[:400]
    return (head.startswith("--- ") or head.startswith("diff --git")) and "\n@@ " in text


def _same(a: str, b: str) -> bool:
    return a.rstrip("\r\n") == b.rstrip("\r\n")


def apply_unified_diff(original: str, diff_text: str) -> str:
    """Apply a single-file unified diff to `original`.

    Context and removed lines are checked against the original; any mismatch raises
    PatchError rather than writing a corrupted file.
    """
    orig: List[str] = original.splitlines(keepends=True)
    orig_missing_final_nl = bool(orig) and not orig[-1].endswith("\n")
    if orig_missing_final_nl:
        orig[-1] += "\n"

    out: List[str] = []
    pos = 0
    lines = diff_text.splitlines(keepends=True)
    i = 0
    saw_hunk = False
    last_tag = ""

    while i < len(lines):
        m = HUNK_RE.match(lines[i])
        if not m:
            if saw_hunk and lines[i].startswith("diff --git"):
                raise PatchError("Multi-file diffs are not supported; send one diff per file.")
            i += 1
            continue
        saw_hunk = True
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) is not None else 1
        start_idx = old_start - 1 if old_count > 0 else old_start
        if start_idx < pos or start_idx > len(orig):
            raise PatchError(f"Hunk at line {old_start} is out of order or beyond end of file.")
        out.extend(orig[pos:start_idx])
        pos = start_idx
        i += 1

        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line.startswith("diff --git") or (line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ ")):
                raise PatchError("Multi-file diffs are not supported; send one diff per file.")
            if line.startswith("\\"):
                # "\ No newline at end of file" applies to the previous line
                if last_tag in ("+", " ") and out:
                    out[-1] = out[-1].rstrip("\r\n")
                i += 1
                continue
            tag, body = (line[:1], line[1:]) if line.strip("\r\n") else (" ", "\n")
            if tag in (" ", "-"):
                if pos >= len(orig) or not _same(orig[pos], body):
                    found = orig[pos].rstrip() if pos < len(orig) else "<EOF>"
                    raise PatchError(f"Patch does not match file at line {pos + 1}: expected {body.rstrip()!r}, found {found!r}")
                if tag == " ":
                    out.append(orig[pos])
                pos += 1
            elif tag == "+":
                out.append(body if body.endswith("\n") else body + "\n")
            else:
                raise PatchError(f"Unexpected line in hunk: {line.rstrip()!r}")
            last_tag = tag
            i += 1

    if not saw_hunk:
        raise PatchError("No hunks found in diff.")

    tail = orig[pos:]
    out.extend(tail)
    result = "".join(out)
    if tail and orig_missing_final_nl:
        # Untouched last line keeps its original "no newline at EOF" state.
        result = result[:-1]
    return result
