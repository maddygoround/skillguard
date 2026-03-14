"""
runner.py
---------
Preflight checks and promptfoo invocation — replaces the bash orchestration
logic from run-redteam.sh.
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


# ── Colours ───────────────────────────────────────────────────────────────────
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def banner():
    print(f"\n{BOLD}{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")


def require_api_key_for_provider(provider: str):
    """Check that the relevant API key is set for a given provider string."""
    if not provider:
        return
    if provider.startswith("anthropic:") and not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{RED}[ERROR]{RESET} ANTHROPIC_API_KEY is not set for provider {provider}.")
        print("         Export it: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)
    if provider.startswith("openai:") and not os.environ.get("OPENAI_API_KEY"):
        print(f"{RED}[ERROR]{RESET} OPENAI_API_KEY is not set for provider {provider}.")
        sys.exit(1)


def preflight_checks(target_providers: list[str], redteam_provider: str,
                     skills_root: str, promptfoo_version: str):
    """Run all preflight checks: python3, npx, API keys, skills root."""
    print(f"{BOLD}── Preflight checks ──────────────────────────────────────────────{RESET}")

    # Python (we're already running, but verify version)
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  {GREEN}✓{RESET}  python3   {py_version}")

    # Node / npx (for promptfoo)
    if not shutil.which("npx"):
        print(f"{YELLOW}[WARN]{RESET}  npx not found. Installing Node.js is required for promptfoo.")
        print("         Visit https://nodejs.org/ or run: brew install node")
        sys.exit(1)
    try:
        npx_version = subprocess.run(
            ["npx", "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        npx_version = "found"
    print(f"  {GREEN}✓{RESET}  npx       {npx_version}")

    # promptfoo availability check
    try:
        subprocess.run(
            ["npx", f"promptfoo@{promptfoo_version}", "--version"],
            capture_output=True, text=True, timeout=30
        )
    except Exception:
        print(f"{YELLOW}[INFO]{RESET}  promptfoo not found globally; will use npx (may download on first run).")

    # API keys
    for provider in target_providers:
        require_api_key_for_provider(provider)
    require_api_key_for_provider(redteam_provider)
    print(f"  {GREEN}✓{RESET}  API key present")

    # Skills root
    if not os.path.isdir(skills_root):
        print(f"{RED}[ERROR]{RESET} Skills root not found: {skills_root}")
        print("         Set --skills-root or SKILLS_ROOT env var to the correct path.")
        sys.exit(1)
    print(f"  {GREEN}✓{RESET}  Skills root exists")


def run_promptfoo(config_path: str, results_dir: str,
                  promptfoo_version: str = "latest") -> int:
    """Run promptfoo redteam and save results. Returns exit code."""
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(results_dir, f"redteam-{timestamp}.json")

    print()
    print(f"{BOLD}── Running promptfoo redteam ─────────────────────────────────────{RESET}")
    print(f"  Running: {CYAN}npx promptfoo@{promptfoo_version} redteam run --config {config_path}{RESET}")
    print()

    # Run promptfoo; capture non-zero exit but don't abort (failures are findings)
    result = subprocess.run(
        ["npx", f"promptfoo@{promptfoo_version}", "redteam", "run",
         "--config", config_path,
         "--output", results_file],
    )
    exit_code = result.returncode

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    banner()
    print(f" {BOLD}Run complete{RESET}")
    banner()

    if os.path.isfile(results_file):
        print(f"  {GREEN}✓{RESET}  Results saved → {CYAN}{results_file}{RESET}")

    static_report = os.path.join(results_dir, "static-scan-report.json")
    if os.path.isfile(static_report):
        print(f"  {GREEN}✓{RESET}  Static scan  → {CYAN}{static_report}{RESET}")

    print()
    print("  View interactive report:")
    print(f"    {BOLD}npx promptfoo@{promptfoo_version} view{RESET}")
    print()
    print("  Or open raw results:")
    print(f"    {BOLD}cat {results_file} | python3 -m json.tool | less{RESET}")
    banner()

    return exit_code


def run_promptfoo_view(promptfoo_version: str = "latest"):
    """Open the promptfoo interactive report viewer."""
    print(f"  Opening: {CYAN}npx promptfoo@{promptfoo_version} view{RESET}")
    subprocess.run(["npx", f"promptfoo@{promptfoo_version}", "view"])


def run_promptfoo_eval(config_path: str, results_dir: str,
                       promptfoo_version: str = "latest") -> int:
    """Run promptfoo eval (quality evaluation, NOT redteam). Returns exit code."""
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(results_dir, f"eval-{timestamp}.json")

    print()
    print(f"{BOLD}── Running promptfoo eval ────────────────────────────────────────{RESET}")
    print(f"  Running: {CYAN}npx promptfoo@{promptfoo_version} eval --config {config_path}{RESET}")
    print()

    result = subprocess.run(
        ["npx", f"promptfoo@{promptfoo_version}", "eval",
         "--config", config_path,
         "--output", results_file],
    )
    exit_code = result.returncode

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    banner()
    print(f" {BOLD}Eval complete{RESET}")
    banner()

    if os.path.isfile(results_file):
        print(f"  {GREEN}✓{RESET}  Results saved → {CYAN}{results_file}{RESET}")

    print()
    print("  View interactive report with improvement suggestions:")
    print(f"    {BOLD}npx promptfoo@{promptfoo_version} view{RESET}")
    print()
    print("  Or open raw results:")
    print(f"    {BOLD}cat {results_file} | python3 -m json.tool | less{RESET}")
    banner()

    return exit_code

