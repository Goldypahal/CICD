# GitFix-Agent 🤖🛠️

An AI maintenance agent that detects test regressions introduced by a Git commit, diagnoses the root cause, writes a fix, verifies it in a sandbox, and commits it to a safety branch or opens a Pull Request.

## How it works

1. **Regression attribution**: runs the tests at `HEAD`, then at `HEAD~1` in a temporary `git worktree`. Your checkout is never moved.
2. **Diagnosis**: parses the test output (pytest, Jest, Go, Java stack traces) and collects the commit diff, the relevant source and test files, and similar past fixes from local memory.
3. **Repair loop**: the model gets the tool schema (`read_file`, `search_code`, `git_diff`, `run_test`, `apply_patch`) and can inspect the repo and run tests until they pass. Up to `agent.max_retries` attempts.
4. **Security audit**: blocks edits to test files, CI config, dependency manifests and paths outside the repo, plus obvious exfiltration payloads.
5. **Verification**: the full test suite has to pass in the same execution environment as every earlier test run.
6. **Commit / PR**: the fix is committed to `ai/fix-<sha>` (or to the current branch with `--auto-commit`). It's pushed and a PR is opened with `--auto-pr`. The fix is also recorded in `.gitfix/history.json` and used as context for future repairs.

## Safety guarantees

- **No lost work**: GitFix refuses to run if tracked files have uncommitted changes. It never runs `git reset --hard`. On failure it reverts only the files it wrote and switches back to the branch or commit you started on.
- **Tests can't be gamed**: test files (`test_*.py`, `*_test.go`, `*.spec.ts`, `tests/`, `conftest.py`, and so on) are read-only to the agent by default. Opt in with `agent.allow_test_edits: true`.
- **Sandboxed execution** (`--sandbox`, the default): every test run (baseline, the agent's own runs, final verification) happens in Docker. Project dependencies are installed once in a setup container that has network access. That container is snapshotted (`docker commit`), and all test runs use the snapshot with `--network none` plus CPU and memory limits. If Docker isn't available, execution fails closed. Use `--no-sandbox` to run on the host.
- The content blocklist is a guard-rail, not a security boundary. The isolation comes from the sandbox.

## Supported projects

| Language | Detected by | Test command | Sandbox image | Dependency setup |
|---|---|---|---|---|
| Python | `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile` (or bare `*.py` as a last resort) | `pytest` / `poetry run pytest` / `uv run pytest` | `python:3.11-slim` | pip / poetry / uv / pipenv |
| JavaScript / TypeScript | `package.json` | `npm\|yarn\|pnpm\|bun test` | `node:20-slim` | `npm ci`, yarn, pnpm, bun |
| Go | `go.mod` | `go test ./...` | `golang:1.22` | `go mod download` |
| Rust | `Cargo.toml` | `cargo test` | `rust:1` | `cargo fetch` |
| Java | `pom.xml`, `build.gradle(.kts)` | `mvn test` / `gradle test` | maven / gradle JDK 17 | `dependency:go-offline` / `dependencies` |

## LLM providers

| Provider | `--provider` | Credentials |
|---|---|---|
| NVIDIA Nemotron (config default) | `nemotron` | `NVIDIA_API_KEY` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` (`OPENAI_BASE_URL` for compatible servers) |
| Ollama (local) | `ollama` | none, defaults to `http://localhost:11434/v1` (`OLLAMA_BASE_URL`) |
| Offline mock | `mock` | none |

If the selected provider has no credentials, GitFix stops immediately with an error instead of looping.

## Quick start

```bash
pip install -e .

gitfix init      # writes .gitfix/config.yaml and a post-commit hook (won't overwrite an existing hook)
gitfix analyze   # shows detected language, test command, sandbox image and setup
gitfix fix       # repair the latest regression on a safety branch
gitfix fix --auto-pr --base-branch main
gitfix watch     # poll for new commits and repair automatically
gitfix history   # past fixes stored in local memory
```

`gitfix fix` exits with 0 on success (or when nothing is failing), 1 when the repair fails, and 2 when the fix was committed but the push or PR failed.

## Configuration (`.gitfix/config.yaml`)

```yaml
validation:
  test_command: auto        # or e.g. "pytest -q tests/"
  timeout_seconds: 120
agent:
  provider: nemotron
  model: nvidia/nemotron-4-340b-instruct
  max_retries: 5
  allow_test_edits: false
sandbox:
  image: auto               # or any image with your toolchain
  setup_command: auto       # or e.g. "pip install -e .[dev]"; "" to skip
  cpu_limit: "2.0"
  memory_limit: 2g
git:
  auto_commit: false
  auto_push: false          # push the safety branch (when not opening a PR)
  branch_prefix: ai/fix-
memory:
  enabled: true
  db_path: .gitfix/history.json
```

`LLM_PROVIDER` and `LLM_MODEL` environment variables override the config file. `--provider` and `--model` override both.

## GitHub Action

This repo ships `.github/workflows/ci.yml` (named **CI**) and `.github/workflows/gitfix.yml`. The second workflow runs when CI fails on a push to this repository. It checks out the failing commit, runs GitFix in the sandbox, and opens a PR against the branch that failed. It never runs for fork pull requests (workflow_run has access to secrets) or for its own `ai/fix-*` branches.

To use it in another repository:

```yaml
- uses: actions/checkout@v4
  with:
    ref: ${{ github.event.workflow_run.head_sha }}
    fetch-depth: 0
- uses: Goldypahal/CICD@main
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  with:
    provider: gemini
    base_branch: ${{ github.event.workflow_run.head_branch }}
```

The job needs `contents: write` and `pull-requests: write` permissions. Outputs: `success` and `pr_url`.
