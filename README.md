# GitFix-Agent 🤖🛠️

An autonomous, repository-agnostic AI software maintenance agent that detects regressions introduced by Git commits, diagnoses root causes using repository and historical context, generates and applies verified patches, and safely commits the validated fixes.

## Core Features

- 🔍 **Universal Project Auto-Detection**: Detects Python, Node.js/TypeScript, Java, Go, and Rust project frameworks, test suites, and build commands.
- ⚡ **Git Commit Regression Tracking**: Monitors git history (`HEAD~1` vs `HEAD`) to pinpoint exact file and function diffs.
- 🧠 **Context-Aware Error Diagnosis**: Parses stack traces, extracts relevant code, imports, and test files without exceeding token budgets.
- 🔄 **Self-Verifying Repair Loop**: Generates patches, applies diffs, executes test runners in isolated sandboxes, and automatically retries if tests fail.
- 🛡️ **Safety Branch Workflows**: Creates `ai/fix-<commit_hash>` branches or PRs before modifying code, with optional `--auto-commit`.
- 💾 **RAG Error Intelligence**: Stores historical error signatures and verified fixes in a local vector/similarity memory.
- 🔌 **Pluggable LLM Providers**: Supports Google Gemini, OpenAI, Anthropic, Ollama, and offline mock modes.

## Quick Start

```bash
# Install package
pip install -e .

# Initialize GitFix in any repository
gitfix init

# Analyze project configuration & health
gitfix analyze

# Run repair on latest commit regression
gitfix fix

# Monitor git commits continuously
gitfix watch
```
