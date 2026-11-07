import copy
import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

DEFAULT_CONFIG = {
    "project": {
        "language": "auto",
        "framework": "auto",
    },
    "validation": {
        "test_command": "auto",
        "build_command": "auto",
        "lint_command": "auto",
        "timeout_seconds": 120,
    },
    "agent": {
        "provider": os.getenv("LLM_PROVIDER", "nemotron"),
        "model": os.getenv("LLM_MODEL", "nvidia/nemotron-4-340b-instruct"),
        "max_retries": 5,
        "temperature": 0.2,
        # Test files define "passing". Keep false so the agent can't fix a bug by weakening a test.
        "allow_test_edits": False,
    },
    "git": {
        "branch_strategy": "ai-branch",  # "ai-branch" or "direct"
        "auto_commit": False,
        "auto_push": False,
        "branch_prefix": "ai/fix-",
    },
    "sandbox": {
        "image": "auto",          # "auto" = picked from the detected language
        "setup_command": "auto",  # "auto" = detected install command; "" to skip
        "cpu_limit": "2.0",
        "memory_limit": "2g",
    },
    "memory": {
        "enabled": True,
        "db_path": ".gitfix/history.json",
    }
}

class Config:
    def __init__(self, repo_dir: Optional[str] = None):
        self.repo_dir = Path(repo_dir or os.getcwd()).resolve()
        self.config_path = self.repo_dir / ".gitfix" / "config.yaml"
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        data = copy.deepcopy(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_cfg = yaml.safe_load(f) or {}
                    self._deep_update(data, file_cfg)
            except Exception as e:
                print(f"[Warning] Failed to load config at {self.config_path}: {e}")
        return data

    def _deep_update(self, target: dict, source: dict):
        for k, v in source.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                self._deep_update(target[k], v)
            else:
                target[k] = v

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False)

    @property
    def provider(self) -> str:
        return os.getenv("LLM_PROVIDER", self._data["agent"]["provider"])

    @property
    def model(self) -> str:
        return os.getenv("LLM_MODEL", self._data["agent"]["model"])

    @property
    def max_retries(self) -> int:
        return int(self._data["agent"]["max_retries"])

    @property
    def branch_strategy(self) -> str:
        return self._data["git"]["branch_strategy"]

    @property
    def auto_commit(self) -> bool:
        return bool(self._data["git"]["auto_commit"])

    @property
    def timeout_seconds(self) -> int:
        return int(self._data["validation"]["timeout_seconds"])

    @property
    def test_command_override(self) -> Optional[str]:
        cmd = self._data["validation"].get("test_command")
        return None if not cmd or cmd == "auto" else str(cmd)

    @property
    def branch_prefix(self) -> str:
        return str(self._data["git"].get("branch_prefix") or "ai/fix-")

    @property
    def auto_push(self) -> bool:
        return bool(self._data["git"].get("auto_push"))

    @property
    def allow_test_edits(self) -> bool:
        return bool(self._data["agent"].get("allow_test_edits"))

    @property
    def temperature(self) -> float:
        return float(self._data["agent"].get("temperature", 0.2))

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        curr = self._data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr
