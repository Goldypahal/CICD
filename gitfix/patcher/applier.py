from pathlib import Path
from typing import Dict, List, Optional, Tuple

class CodePatcher:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir or Path.cwd()).resolve()

    def apply_fix_payload(self, files_payload: List[Dict[str, str]]) -> Tuple[bool, List[str], List[Tuple[Path, str]]]:
        """
        Applies a list of file modifications.
        Returns: (success: bool, modified_files: List[str], backups: List[(Path, original_content)])
        """
        backups = []
        modified = []

        try:
            for item in files_payload:
                rel_path = item.get("path")
                content = item.get("content", "")
                if not rel_path:
                    continue

                full_path = self.root_dir / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Store original for rollback
                orig_content = ""
                if full_path.exists():
                    orig_content = full_path.read_text(encoding="utf-8")

                backups.append((full_path, orig_content))

                # Check if content is unified diff patch
                if content.startswith("--- ") or content.startswith("diff --git"):
                    applied = self._apply_unified_diff(full_path, orig_content, content)
                    if not applied:
                        full_path.write_text(content, encoding="utf-8")
                else:
                    full_path.write_text(content, encoding="utf-8")

                modified.append(rel_path)

            return True, modified, backups
        except Exception as e:
            print(f"[Patcher] Error applying fix payload: {e}")
            self.rollback(backups)
            return False, [], backups

    def _apply_unified_diff(self, file_path: Path, orig_content: str, diff_text: str) -> bool:
        """Simple pure-Python unified diff hunk applier."""
        try:
            lines = orig_content.splitlines(keepends=True)
            diff_lines = diff_text.splitlines()

            # Extract added/removed lines from hunk
            new_lines = []
            hunk_started = False

            for dline in diff_lines:
                if dline.startswith("@@"):
                    hunk_started = True
                    continue
                if not hunk_started:
                    continue

                if dline.startswith("+") and not dline.startswith("+++"):
                    new_lines.append(dline[1:] + "\n")
                elif dline.startswith("-") and not dline.startswith("---"):
                    continue
                elif dline.startswith(" "):
                    new_lines.append(dline[1:] + "\n")

            if new_lines:
                file_path.write_text("".join(new_lines), encoding="utf-8")
                return True
        except Exception:
            pass
        return False

    def rollback(self, backups: List[Tuple[Path, str]]):
        for path, orig_content in backups:
            try:
                if orig_content == "":
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(orig_content, encoding="utf-8")
            except Exception as e:
                print(f"[Patcher] Rollback warning for {path}: {e}")
