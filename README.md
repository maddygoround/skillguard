# SkillGuard  ·  AI Skills Security Evaluator

Automatically discovers every skill (SKILL.md) in your skills directory,
generates a promptfoo redteam config, runs a full security red-team suite,
and reports findings.

---

## What this does

| Stage | Tool | What it checks |
|---|---|---|
| **Static scan** | `skillguard scan` | Injection patterns, exfiltration URLs, obfuscation, absolute-compliance directives |
| **Dynamic redteam** | `skillguard run` | Prompt injection, jailbreaks, PII leakage, harmful content, excessive agency, RBAC bypass, hijacking, and more |

---

## Prerequisites

### 1. Node.js ≥ 18
```bash
# macOS
brew install node

# Ubuntu/Debian
sudo apt install nodejs npm
```

### 2. Python 3.10+
```bash
pip3 install pyyaml  # optional – falls back to built-in serialiser
```

### 3. API key
```bash
# For Anthropic (default)
export ANTHROPIC_API_KEY=sk-ant-...

# Or OpenAI
export OPENAI_API_KEY=sk-...

# Optional: separate attacker/grader model for redteam generation
export REDTEAM_PROVIDER=openai:chat:gpt-5-mini
```

---

## Installation

```bash
cd promptfoo-redteam
pip install -e .
```

After installation, the `skillguard` command is available globally.

---

## Quick start

```bash
export ANTHROPIC_API_KEY=sk-ant-...
skillguard run
```

That's it. The command:
1. Scans every `SKILL.md` recursively under `LOCATION`
2. Runs a static pattern analysis and writes `results/static-scan-report.json`
3. Deduplicates repeated cached skills by content hash (configurable)
4. Generates `promptfooconfig.yaml` with Promptfoo plugin/strategy presets
5. Runs `npx promptfoo@latest redteam run`
6. Writes timestamped results to `results/redteam-YYYYMMDD_HHMMSS.json`

---

## CLI Commands

```
skillguard --help
```

### `skillguard discover`

Discover skills, run static analysis, and generate the promptfoo config — without running the actual redteam evaluation.

```bash
skillguard discover --location ~/.claude
```

### `skillguard run`

Full pipeline: discover → static scan → generate config → run promptfoo redteam.

```bash
skillguard run \
  --location "$HOME/.claude" \
  --target-provider anthropic:claude-sonnet-4-6 \
  --target-provider openai:chat:gpt-5.4 \
  --attacker-provider openai:chat:gpt-5-mini \
  --num-tests 5 \
  --strategy-preset local-balanced
```

### `skillguard scan`

Static security scan only — no promptfoo invocation.

```bash
skillguard scan --location ~/.claude
```

### `skillguard eval`

Quality evaluation with improvement suggestions — **completely separate from redteam**.

Evaluates each skill across 5 quality dimensions (scope clarity, instruction safety, output constraints, edge case handling, completeness) using model-graded assertions. Improvement suggestions appear directly in the Promptfoo dashboard.

```bash
# Evaluate all skills across all dimensions
skillguard eval --location ~/.claude

# Evaluate with a specific provider
skillguard eval --location ~/.claude --provider openai:gpt-4o

# Evaluate only specific dimensions
skillguard eval --dimensions scope_clarity,instruction_safety

# Use a different grader model
skillguard eval --attacker-provider openai:gpt-4o
```

Eval-specific options:

| Flag | Default | Description |
|---|---|---|
| `--eval-config PATH` | `./evalconfig.yaml` | Output eval config path |
| `--eval-provider ID` | `anthropic:claude-sonnet-4-6` | Target provider for evaluation |
| `--attacker-provider ID` | same as `--eval-provider` | LLM provider for grading |
| `--dimensions DIMS` | all | Comma-separated quality dimensions |
| `--num-tests N` | `5` | Tests per dimension |

### `skillguard view`

Open the promptfoo interactive report viewer (works for both redteam and eval results).

```bash
skillguard view
```

---

## Common options

All subcommands (`discover`, `run`, `scan`) accept these flags:

| Flag | Default | Description |
|---|---|---|
| `--location PATH` | `~/.skills/skills` | Location scanned for `SKILL.md` files |
| `--config PATH` | `./promptfooconfig.yaml` | Output config path |
| `--target-provider ID` | `anthropic:claude-haiku-4-5-latest` | Provider under test (repeatable) |
| `--attacker-provider ID` | _(unset)_ | Optional attacker/grader provider |
| `--num-tests N` | `10` | Number of attack probes per skill |
| `--plugin-preset NAME` | `technical-minimal` | Plugin bundle |
| `--strategy-preset NAME` | `technical-minimal` | Strategy bundle |
| `--dedupe-mode MODE` | `content` | Dedupe by `content`, `name`, or `off` |
| `--extra-plugins IDS` | _(empty)_ | Comma-separated plugin IDs to append |
| `--exclude-plugins IDS` | _(empty)_ | Comma-separated plugin IDs to remove |
| `--extra-strategies IDS` | _(empty)_ | Comma-separated strategy IDs to append |
| `--exclude-strategies IDS` | _(empty)_ | Comma-separated strategy IDs to remove |

The `run` and `view` subcommands also accept:

| Flag | Default | Description |
|---|---|---|
| `--promptfoo-version VER` | `latest` | Promptfoo version for `npx promptfoo@VER` |

---

## Environment variables

All CLI flags can also be set via environment variables:

| Variable | Corresponding flag |
|---|---|
| `LOCATION` | `--location` |
| `PROMPTFOO_CONFIG` | `--config` |
| `TARGET_PROVIDERS` | `--target-provider` (comma-separated) |
| `LLM_PROVIDER` | `--target-provider` (backward-compatible) |
| `ATTACKER_PROVIDER` | `--attacker-provider` |
| `NUM_TESTS` | `--num-tests` |
| `PROMPTFOO_VERSION` | `--promptfoo-version` |
| `REDTEAM_PLUGIN_PRESET` | `--plugin-preset` |
| `REDTEAM_STRATEGY_PRESET` | `--strategy-preset` |
| `EXTRA_REDTEAM_PLUGINS` | `--extra-plugins` |
| `EXCLUDE_REDTEAM_PLUGINS` | `--exclude-plugins` |
| `EXTRA_REDTEAM_STRATEGIES` | `--extra-strategies` |
| `EXCLUDE_REDTEAM_STRATEGIES` | `--exclude-strategies` |
| `DEDUPE_MODE` | `--dedupe-mode` |
| `PROMPTFOO_REMOTE_GENERATION_URL` | Enables cloud-backed strategies |

---

## Redteam checks performed

By default the tool uses the `technical-minimal` plugin preset and the
`technical-minimal` strategy preset. That keeps the scan focused on whether
an installed skill can subvert the host assistant, reveal hidden setup,
expose internal capabilities, or suggest dangerous system actions.

### Plugin presets

| Preset | Plugins |
|---|---|
| `technical-minimal` (default) | hijacking, prompt-extraction, tool-discovery, shell-injection |
| `technical-core` | Above + sql-injection, special-token-injection, reasoning-dos |
| `balanced` | Broad safety/security coverage for larger scans |
| `security-focused` | Injection + PII + privacy focused |
| `minimal` | injection, hijacking, agency, rbac, debug-access |

### Strategy presets

| Preset | Strategies |
|---|---|
| `technical-minimal` (default) | prompt-injection, mischievous-user |
| `local-safe` | jailbreak, prompt-injection |
| `local-balanced` | jailbreak, prompt-injection, jailbreak:tree, jailbreak:composite |
| `cloud-recommended` | jailbreak:meta, jailbreak:hydra |

---

## Project structure

```
promptfoo-redteam/
├── cli.py               # CLI entry point with subcommands
├── core/
│   ├── __init__.py      # Package init + version
│   ├── discover.py      # Skill discovery + config generation
│   ├── presets.py       # Plugin/strategy presets + constants
│   ├── runner.py        # Preflight checks + promptfoo invocation
│   └── scanner.py       # Static security analysis
├── setup.py             # Package installer
├── .gitignore
└── README.md
```

Generated at runtime and ignored by git:
- `promptfooconfig.yaml`
- `results/static-scan-report.json`
- `results/redteam-YYYYMMDD_HHMMSS.json`
- `.promptfoo/`
- `.promptfoo-prompts/`

---

## Adding a new skill

Drop a new folder with a `SKILL.md` anywhere under `LOCATION`, then
re-run `skillguard run`.

The tool **recursively scans** the full skills tree, so nested project
skills (e.g. `my-project/skills/my-skill/SKILL.md`) are discovered
automatically — no manual config changes needed.

---

## Viewing results

```bash
# Interactive web UI
skillguard view

# Raw JSON
cat results/redteam-*.json | python3 -m json.tool | less

# Static scan only
cat results/static-scan-report.json | python3 -m json.tool
```

---

## Tuning examples

```bash
# Quick scan with fewer tests
skillguard run --num-tests 3

# Stay fully local but broaden jailbreak coverage
skillguard run --strategy-preset local-balanced

# Keep only the most security-relevant plugins
skillguard run --plugin-preset technical-core

# Add/remove specific checks
skillguard run \
  --extra-strategies jailbreak:tree \
  --exclude-plugins competitors,hallucination

# Static scan only (no API calls)
skillguard scan --location ~/.claude
```
