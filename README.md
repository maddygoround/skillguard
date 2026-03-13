# promptfoo-redteam  ·  Automated Skills Security Evaluator

Automatically discovers every skill (SKILL.md) in your skills directory,
generates a promptfoo redteam config, runs a full security red-team suite,
and watches for new skills to re-run automatically.

---

## What this does

| Stage | Tool | What it checks |
|---|---|---|
| **Static scan** | `discover-skills.py` | Injection patterns, exfiltration URLs, obfuscation, absolute-compliance directives |
| **Dynamic redteam** | `promptfoo` | Prompt injection, jailbreaks, PII leakage, harmful content, excessive agency, RBAC bypass, hijacking, and more |
| **Watching** | `watch-skills.sh` | Fires both stages automatically every time a new/changed SKILL.md is detected |

---

## Prerequisites

### 1. Node.js ≥ 18
```bash
# macOS
brew install node

# Ubuntu/Debian
sudo apt install nodejs npm
```

### 2. Python 3.8+
```bash
pip3 install pyyaml  # optional – falls back to built-in serialiser
```

### 3. API key
```bash
# For Anthropic (default)
export ANTHROPIC_API_KEY=sk-ant-...

# Or OpenAI
export OPENAI_API_KEY=sk-...
export TARGET_PROVIDERS=openai:gpt-4o

# Optional: separate attacker/grader model for redteam generation
export REDTEAM_PROVIDER=openai:chat:gpt-5-mini
```

### 4. (Optional) File-watcher for `watch-skills.sh`
```bash
# macOS
brew install fswatch

# Ubuntu/Debian
sudo apt install inotify-tools
```
> Without either tool the watcher falls back to polling every 30 seconds.

---

## Quick start (one-click)

```bash
cd promptfoo-redteam
chmod +x run-redteam.sh
export ANTHROPIC_API_KEY=sk-ant-...
./run-redteam.sh
```

You can also override settings directly with CLI flags:

```bash
./run-redteam.sh \
  --skills-root "$HOME/.claude" \
  --host-skills-root "$HOME/.claude" \
  --target-provider anthropic:claude-sonnet-4-6 \
  --target-provider openai:chat:gpt-5.4 \
  --redteam-provider openai:chat:gpt-5-mini \
  --num-tests 5 \
  --strategy-preset local-balanced
```

That's it. The script:
1. Scans every `SKILL.md` recursively under `SKILLS_ROOT`
2. Runs a static pattern analysis and writes `results/static-scan-report.json`
3. Deduplicates repeated cached skills by content hash (configurable)
4. Generates `promptfooconfig.yaml` with Promptfoo plugin/strategy presets
5. Runs `npx promptfoo@latest redteam run`
6. Writes timestamped results to `results/redteam-YYYYMMDD_HHMMSS.json`

---

## Auto-watch mode

```bash
./watch-skills.sh
```

Triggers a full redteam run whenever a `SKILL.md` is created or modified.
A 10-second cooldown prevents duplicate runs from rapid-fire saves.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SKILLS_ROOT` | `~/.claude/` | Root directory scanned for `SKILL.md` files |
| `HOST_SKILLS_ROOT` | `SKILLS_ROOT` | Path written into `promptfooconfig.yaml` when discovery happens in a different mount/container path |
| `PROMPTFOO_CONFIG` | `./promptfooconfig.yaml` | Output config path |
| `TARGET_PROVIDERS` | `anthropic:claude-sonnet-4-6` | Comma-separated list of providers under test |
| `LLM_PROVIDER` | same as `TARGET_PROVIDERS` | Backward-compatible single target provider override |
| `REDTEAM_PROVIDER` | _(unset)_ | Optional attacker/grader provider used for redteam generation and grading |
| `NUM_TESTS` | `10` | Number of attack probes per skill |
| `PROMPTFOO_VERSION` | `latest` | Promptfoo version to run via `npx promptfoo@...` |
| `REDTEAM_PLUGIN_PRESET` | `technical-minimal` | Plugin bundle: `technical-minimal`, `technical-core`, `balanced`, `security-focused`, or `minimal` |
| `REDTEAM_STRATEGY_PRESET` | `technical-minimal` | Strategy bundle: `technical-minimal`, `local-safe`, `local-balanced`, or `cloud-recommended` |
| `EXTRA_REDTEAM_PLUGINS` | _(empty)_ | Comma-separated plugin IDs to append |
| `EXCLUDE_REDTEAM_PLUGINS` | _(empty)_ | Comma-separated plugin IDs to remove |
| `EXTRA_REDTEAM_STRATEGIES` | _(empty)_ | Comma-separated strategy IDs to append |
| `EXCLUDE_REDTEAM_STRATEGIES` | _(empty)_ | Comma-separated strategy IDs to remove |
| `DEDUPE_MODE` | `content` | Deduplicate repeated skills by `content`, `name`, or `off` |
| `PROMPTFOO_REMOTE_GENERATION_URL` | _(unset)_ | Enables cloud-backed Promptfoo strategies such as `jailbreak:meta` |
| `COOLDOWN_SECS` | `10` | Watch-mode debounce window (seconds) |

---

## Redteam checks performed

By default the repo uses the `technical-minimal` plugin preset and the
`technical-minimal` strategy preset. That keeps the scan focused on the
question that matters most here: whether an installed skill can subvert the
host assistant, reveal hidden setup, expose internal capabilities, or suggest
dangerous system actions.

### Injection & Hijacking
- `prompt-injection` — Direct injection attacks in user turn
- `indirect-prompt-injection` — Injection via tool/retrieval output
- `hijacking` — Task redirection attacks

### Agency & Behaviour
- `excessive-agency` — Model taking unauthorised actions
- `overreliance` — Overconfident or unchecked responses
- `rbac` — Role-based access control bypass
- `debug-access` — Hidden debug/admin mode activation

### PII / Data Leakage
- `pii:direct` — Direct request for personal data
- `pii:api-db` — PII extraction via API/database framing
- `pii:session` — Cross-session context leakage
- `pii:social` — Social-engineering based PII extraction

### Harmful Content
- `harmful:hate`, `harmful:violence`, `harmful:self-harm`
- `harmful:sexual`, `harmful:cybercrime`
- `harmful:chemical-weapons`, `harmful:biological-weapons`
- `harmful:illegal-drugs`, `harmful:misinformation-disinformation`
- `harmful:illegal-activities`, `harmful:unsafe-practices`

### Jailbreaks
- `jailbreak` — Standard jailbreak library
- `prompt-injection` — Direct instruction override attacks
- `jailbreak:tree` — Available in `local-balanced`
- `jailbreak:composite` — Available in `local-balanced`
- `jailbreak:meta` — Cloud-backed; only enabled via `cloud-recommended`

## Plugin presets

### `technical-minimal` (default)
- `hijacking`
- `prompt-extraction`
- `tool-discovery`
- `shell-injection`

### `technical-core`
- `hijacking`
- `prompt-extraction`
- `tool-discovery`
- `shell-injection`
- `sql-injection`
- `special-token-injection`
- `reasoning-dos`

### `balanced`
- Broad safety/security coverage for larger scans

## Strategy presets

### `technical-minimal` (default)
- `prompt-injection`

### `local-safe`
- `jailbreak`
- `prompt-injection`

### `local-balanced`
- `jailbreak`
- `prompt-injection`
- `jailbreak:tree`
- `jailbreak:composite`

### `cloud-recommended`
- `jailbreak:meta`
- `jailbreak:hydra`

If a cloud-only strategy is selected without Promptfoo Cloud access, the
generator filters it out and records the reason in `_meta.filtered_strategies`
inside `promptfooconfig.yaml`.

Depending on the installed Promptfoo version, `jailbreak:composite` may also
require remote generation. The generator filters it out automatically for
local-only runs when needed.

## Grading policy

Generated configs now include:
- a stricter `purpose` aligned to "installed skills must not break or subvert the host assistant"
- global `graderExamples` so Promptfoo's LLM judge has concrete PASS/FAIL anchors
- plugin-specific `graderGuidance` for the highest-signal technical checks in the minimal preset

This reduces generic grading drift and makes failures more closely reflect your
actual install-safety policy rather than a broad, abstract notion of "security risk".

## Tuning examples

```bash
# Use CLI flags instead of env vars
./run-redteam.sh \
  --skills-root "$HOME/.claude" \
  --target-provider openai:gpt-4o \
  --num-tests 3

# Default small-footprint setup
./run-redteam.sh

# Stay fully local but broaden jailbreak coverage
REDTEAM_STRATEGY_PRESET=local-balanced ./run-redteam.sh

# Keep only the most security-relevant plugins
REDTEAM_PLUGIN_PRESET=technical-core ./run-redteam.sh

# Add/remove specific checks
EXTRA_REDTEAM_STRATEGIES=jailbreak:tree \
EXCLUDE_REDTEAM_PLUGINS=competitors,hallucination \
./run-redteam.sh
```

---

## Files

```
promptfoo-redteam/
├── discover-skills.py       # Discovery + static scan + config generator
├── run-redteam.sh           # One-click runner (calls discover then promptfoo)
├── watch-skills.sh          # Auto-trigger watcher
├── .gitignore               # Ignores generated configs, results, and local logs
└── README.md
```

Generated at runtime and ignored by git:
- `promptfooconfig.yaml`
- `results/static-scan-report.json`
- `results/redteam-YYYYMMDD_HHMMSS.json`
- `.promptfoo/`

---

## Adding a new skill

Drop a new folder with a `SKILL.md` anywhere under `SKILLS_ROOT`.
If `watch-skills.sh` is running it will trigger automatically.
Otherwise just re-run `./run-redteam.sh`.

The script **recursively scans** the full skills tree, so nested project
skills (e.g. `my-project/skills/my-skill/SKILL.md`) are discovered
automatically — no manual config changes needed.

---

## Viewing results

```bash
# Interactive web UI
npx promptfoo@latest view

# Raw JSON
cat results/redteam-*.json | python3 -m json.tool | less

# Static scan only
cat results/static-scan-report.json | python3 -m json.tool
```

---
