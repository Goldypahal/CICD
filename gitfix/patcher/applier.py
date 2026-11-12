from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .unified_diff import PatchError, apply_unified_diff, looks_like_unified_diff

# A backup of None means the file did not exist before the patch.
Backup = Tuple[Path, Optional[str]]


class CodePatcher:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir or Path.cwd()).resolve()

    def apply_fix_payload(self, files_payload: List[Dict[str, str]]) -> Tuple[bool, List[str], List[Backup]]:
        """Apply full-file contents or single-file unified diffs. All-or-nothing."""
        backups: List[Backup] = []
        modified: List[str] = []

        try:
            for item in files_payload:
                rel_path = item.get("path")
                content = item.get("content", "")
                if not rel_path:
                    continue

                full_path = (self.root_dir / rel_path).resolve()
                if not full_path.is_relative_to(self.root_dir):
                    raise PatchError(f"Path outside workspace: {rel_path}")

                orig_content = full_path.read_text(encoding="utf-8") if full_path.exists() else None
                new_content = (
                    apply_unified_diff(orig_content or "", content)
                    if looks_like_unified_diff(content)
                    else content
                )

                backups.append((full_path, orig_content))
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(new_content, encoding="utf-8")
                modified.append(rel_path)

            return True, modified, backups
        except Exception as e:
            print(f"[Patcher] Error applying fix payload: {e}")
            self.rollback(backups)
            return False, [], backups

    def rollback(self, backups: List[Backup]):
        for path, orig_content in reversed(backups):
            try:
                if orig_content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(orig_content, encoding="utf-8")
            except Exception as e:
                print(f"[Patcher] Rollback warning for {path}: {e}")
