import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

class ErrorDatabase:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or Path(".gitfix/history.json")).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_fix(
        self,
        error_type: str,
        error_message: str,
        commit_hash: str,
        summary: str,
        modified_files: List[str],
        patch_diff: str,
    ):
        record = {
            "timestamp": time.time(),
            "commit_hash": commit_hash,
            "error_type": error_type,
            "error_message": error_message,
            "summary": summary,
            "modified_files": modified_files,
            "patch_diff": patch_diff,
        }
        self.records.append(record)
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=2)
        except Exception as e:
            print(f"[Warning] Failed to save history to {self.db_path}: {e}")

    def query_similar_errors(self, error_type: str, error_message: str, limit: int = 3) -> List[Dict[str, Any]]:
        matches = []
        err_type_lower = error_type.lower()
        msg_lower = error_message.lower()

        for rec in self.records:
            score = 0
            if rec.get("error_type", "").lower() == err_type_lower:
                score += 5
            # Simple keyword similarity matching
            rec_msg = rec.get("error_message", "").lower()
            tokens = set(msg_lower.split())
            for t in tokens:
                if len(t) > 3 and t in rec_msg:
                    score += 1
            
            if score > 0:
                matches.append((score, rec))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches[:limit]]

    def get_all_records(self) -> List[Dict[str, Any]]:
        return self.records
