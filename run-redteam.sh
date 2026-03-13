#!/usr/bin/env bash
# =============================================================================
#  run-redteam.sh  –  One-click promptfoo redteam runner for skills
#
#  Usage:
#    ./run-redteam.sh
#    ./run-redteam.sh --skills-root /path/to/skills --provider openai:gpt-4o
#    SKILLS_ROOT=/path/to/skills LLM_PROVIDER=openai:gpt-4o ./run-redteam.sh
#
#  Required env vars (set at least one API key):
#    ANTHROPIC_API_KEY   – for anthropic:* providers
#    OPENAI_API_KEY      – for openai:* providers
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
banner() { echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

# ── Defaults (override via env) ───────────────────────────────────────────────
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/}"
# HOST_SKILLS_ROOT: the path written into promptfooconfig.yaml.
# Defaults to SKILLS_ROOT (correct when running natively on the host).
# Override only when running this script from inside a VM/container where
# the mounted skills path differs from the path promptfoo sees on the host.
HOST_SKILLS_ROOT="${HOST_SKILLS_ROOT:-$SKILLS_ROOT}"
PROMPTFOO_CONFIG="${PROMPTFOO_CONFIG:-$SCRIPT_DIR/promptfooconfig.yaml}"
LLM_PROVIDER="${LLM_PROVIDER:-anthropic:claude-sonnet-4-6}"
NUM_TESTS="${NUM_TESTS:-10}"
PROMPTFOO_VERSION="${PROMPTFOO_VERSION:-latest}"
REDTEAM_PLUGIN_PRESET="${REDTEAM_PLUGIN_PRESET:-technical-minimal}"
REDTEAM_STRATEGY_PRESET="${REDTEAM_STRATEGY_PRESET:-technical-minimal}"
DEDUPE_MODE="${DEDUPE_MODE:-content}"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

usage() {
  cat <<EOF
Usage:
  ./run-redteam.sh [options]

Options:
  --skills-root PATH         Discovery root for SKILL.md files
  --host-skills-root PATH    Path written into promptfooconfig.yaml
  --config PATH              Output config path
  --provider ID              Promptfoo provider, e.g. anthropic:claude-sonnet-4-6
  --num-tests N              Number of tests per skill
  --promptfoo-version VER    Promptfoo version for npx promptfoo@VER
  --plugin-preset NAME       Plugin preset: technical-minimal, technical-core, balanced, security-focused, minimal
  --strategy-preset NAME     Strategy preset: technical-minimal, local-safe, local-balanced, cloud-recommended
  --dedupe-mode MODE         Dedupe mode: content, name, off
  --help                     Show this help message

Environment variables remain supported and are used as defaults.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skills-root)
      [[ $# -ge 2 ]] || { echo "[ERROR] --skills-root requires a value."; exit 1; }
      SKILLS_ROOT="$2"
      shift 2
      ;;
    --host-skills-root)
      [[ $# -ge 2 ]] || { echo "[ERROR] --host-skills-root requires a value."; exit 1; }
      HOST_SKILLS_ROOT="$2"
      shift 2
      ;;
    --config|--promptfoo-config)
      [[ $# -ge 2 ]] || { echo "[ERROR] --config requires a value."; exit 1; }
      PROMPTFOO_CONFIG="$2"
      shift 2
      ;;
    --provider|--llm-provider)
      [[ $# -ge 2 ]] || { echo "[ERROR] --provider requires a value."; exit 1; }
      LLM_PROVIDER="$2"
      shift 2
      ;;
    --num-tests)
      [[ $# -ge 2 ]] || { echo "[ERROR] --num-tests requires a value."; exit 1; }
      NUM_TESTS="$2"
      shift 2
      ;;
    --promptfoo-version)
      [[ $# -ge 2 ]] || { echo "[ERROR] --promptfoo-version requires a value."; exit 1; }
      PROMPTFOO_VERSION="$2"
      shift 2
      ;;
    --plugin-preset)
      [[ $# -ge 2 ]] || { echo "[ERROR] --plugin-preset requires a value."; exit 1; }
      REDTEAM_PLUGIN_PRESET="$2"
      shift 2
      ;;
    --strategy-preset)
      [[ $# -ge 2 ]] || { echo "[ERROR] --strategy-preset requires a value."; exit 1; }
      REDTEAM_STRATEGY_PRESET="$2"
      shift 2
      ;;
    --dedupe-mode)
      [[ $# -ge 2 ]] || { echo "[ERROR] --dedupe-mode requires a value."; exit 1; }
      DEDUPE_MODE="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo ""
      usage
      exit 1
      ;;
  esac
done

banner
echo -e " ${BOLD}promptfoo-redteam  ·  Skills Security Evaluator${RESET}"
banner
echo -e "  Skills root (discovery) : ${CYAN}$SKILLS_ROOT${RESET}"
echo -e "  Skills root (host/YAML) : ${CYAN}$HOST_SKILLS_ROOT${RESET}"
echo -e "  Config out              : ${CYAN}$PROMPTFOO_CONFIG${RESET}"
echo -e "  Provider                : ${CYAN}$LLM_PROVIDER${RESET}"
echo -e "  Num tests               : ${CYAN}$NUM_TESTS per skill${RESET}"
echo -e "  Promptfoo version       : ${CYAN}$PROMPTFOO_VERSION${RESET}"
echo -e "  Plugin preset           : ${CYAN}$REDTEAM_PLUGIN_PRESET${RESET}"
echo -e "  Strategy preset         : ${CYAN}$REDTEAM_STRATEGY_PRESET${RESET}"
echo -e "  Dedupe mode             : ${CYAN}$DEDUPE_MODE${RESET}"
echo -e "  Results dir             : ${CYAN}$RESULTS_DIR${RESET}"
echo ""

# ── Preflight checks ──────────────────────────────────────────────────────────
echo -e "${BOLD}── Preflight checks ──────────────────────────────────────────────${RESET}"

# Python
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}[ERROR]${RESET} python3 not found. Install Python 3.8+."
  exit 1
fi
echo -e "  ${GREEN}✓${RESET}  python3   $(python3 --version)"

# Node / npx (for promptfoo)
if ! command -v npx &>/dev/null; then
  echo -e "${YELLOW}[WARN]${RESET}  npx not found. Installing Node.js is required for promptfoo."
  echo "         Visit https://nodejs.org/ or run: brew install node"
  exit 1
fi
echo -e "  ${GREEN}✓${RESET}  npx       $(npx --version 2>/dev/null || echo 'found')"

# promptfoo
if ! npx "promptfoo@${PROMPTFOO_VERSION}" --version &>/dev/null 2>&1; then
  echo -e "${YELLOW}[INFO]${RESET}  promptfoo not found globally; will use npx (may download on first run)."
fi

# API key
if [[ "$LLM_PROVIDER" == anthropic:* && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY is not set."
  echo "         Export it: export ANTHROPIC_API_KEY=sk-ant-..."
  exit 1
fi
if [[ "$LLM_PROVIDER" == openai:* && -z "${OPENAI_API_KEY:-}" ]]; then
  echo -e "${RED}[ERROR]${RESET} OPENAI_API_KEY is not set."
  exit 1
fi
echo -e "  ${GREEN}✓${RESET}  API key present"

# Skills root
if [[ ! -d "$SKILLS_ROOT" ]]; then
  echo -e "${RED}[ERROR]${RESET} Skills root not found: $SKILLS_ROOT"
  echo "         Set SKILLS_ROOT env var to the correct path."
  exit 1
fi
echo -e "  ${GREEN}✓${RESET}  Skills root exists"

# ── Step 1: Discover skills & generate config ─────────────────────────────────
echo ""
echo -e "${BOLD}── Step 1: Discover skills & generate promptfoo config ───────────${RESET}"

set +e
SKILLS_ROOT="$SKILLS_ROOT" \
HOST_SKILLS_ROOT="$HOST_SKILLS_ROOT" \
PROMPTFOO_CONFIG="$PROMPTFOO_CONFIG" \
LLM_PROVIDER="$LLM_PROVIDER" \
REDTEAM_PLUGIN_PRESET="$REDTEAM_PLUGIN_PRESET" \
REDTEAM_STRATEGY_PRESET="$REDTEAM_STRATEGY_PRESET" \
DEDUPE_MODE="$DEDUPE_MODE" \
python3 "$SCRIPT_DIR/discover-skills.py" \
  --skills-root "$SKILLS_ROOT" \
  --host-skills-root "$HOST_SKILLS_ROOT" \
  --output "$PROMPTFOO_CONFIG" \
  --provider "$LLM_PROVIDER" \
  --num-tests "$NUM_TESTS" \
  --plugin-preset "$REDTEAM_PLUGIN_PRESET" \
  --strategy-preset "$REDTEAM_STRATEGY_PRESET" \
  --dedupe-mode "$DEDUPE_MODE"
DISCOVER_EXIT=$?
set -e

if [[ $DISCOVER_EXIT -eq 2 ]]; then
  echo -e "\n${YELLOW}[WARN]${RESET} CRITICAL static findings detected. Review static-scan-report.json"
  echo "       Continuing with redteam run..."
elif [[ $DISCOVER_EXIT -ne 0 ]]; then
  echo -e "\n${RED}[ERROR]${RESET} Skill discovery/config generation failed."
  exit "$DISCOVER_EXIT"
fi

# ── Step 2: Run promptfoo redteam ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Step 2: Run promptfoo redteam ─────────────────────────────────${RESET}"

mkdir -p "$RESULTS_DIR"
RESULTS_FILE="$RESULTS_DIR/redteam-${TIMESTAMP}.json"

echo -e "  Running: ${CYAN}npx promptfoo@${PROMPTFOO_VERSION} redteam run --config $PROMPTFOO_CONFIG${RESET}"
echo ""

# Run promptfoo; capture non-zero exit but don't abort (failures are findings)
npx "promptfoo@${PROMPTFOO_VERSION}" redteam run \
  --config "$PROMPTFOO_CONFIG" \
  --output "$RESULTS_FILE" \
  || REDTEAM_EXIT=$?

REDTEAM_EXIT="${REDTEAM_EXIT:-0}"

# ── Step 3: Summary ───────────────────────────────────────────────────────────
echo ""
banner
echo -e " ${BOLD}Run complete${RESET}"
banner

if [[ -f "$RESULTS_FILE" ]]; then
  echo -e "  ${GREEN}✓${RESET}  Results saved → ${CYAN}$RESULTS_FILE${RESET}"
fi

STATIC_REPORT="$RESULTS_DIR/static-scan-report.json"
if [[ -f "$STATIC_REPORT" ]]; then
  echo -e "  ${GREEN}✓${RESET}  Static scan  → ${CYAN}$STATIC_REPORT${RESET}"
fi

echo ""
echo -e "  View interactive report:"
echo -e "    ${BOLD}npx promptfoo@${PROMPTFOO_VERSION} view${RESET}"
echo ""
echo -e "  Or open raw results:"
echo -e "    ${BOLD}cat $RESULTS_FILE | python3 -m json.tool | less${RESET}"
banner

exit $REDTEAM_EXIT
