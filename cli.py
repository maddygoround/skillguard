"""
cli.py
------
Main CLI entry point for SkillGuard. Provides subcommands:
  - discover  : Discover skills and generate promptfoo config
  - run       : Full pipeline — discover + static scan + redteam evaluation
  - eval      : Quality evaluation with improvement suggestions (separate from redteam)
  - scan      : Static security scan only (no promptfoo)
  - view      : Open the promptfoo interactive report viewer
"""

import os
import sys
import argparse
from pathlib import Path

from core import __version__
from core.presets import (
    DEFAULT_SKILLS_ROOT,
    DEFAULT_PROVIDER,
    DEFAULT_TARGET_PROVIDERS,
    DEFAULT_REDTEAM_PROVIDER,
    DEFAULT_PLUGIN_PRESET,
    DEFAULT_STRATEGY_PRESET,
    DEFAULT_DEDUPE_MODE,
    DEFAULT_HOST_SKILLS_ROOT,
)
from core.discover import (
    parse_csv,
    discover_skills,
    dedupe_skills,
    resolve_plugin_set,
    resolve_strategy_set,
    build_promptfoo_config,
    write_config,
)
from core.scanner import run_static_analysis, write_static_report
from core.runner import (
    banner,
    preflight_checks,
    run_promptfoo,
    run_promptfoo_eval,
    run_promptfoo_view,
    BOLD, CYAN, RESET, YELLOW, RED,
)
from core.evaluator import build_eval_config
from core.graders import DIMENSIONS, DIMENSION_LABELS


# ── Resolve output paths ────────────────────────────────────────────────────
def _default_config_path() -> str:
    """Return the default config output path (next to the package install or cwd)."""
    return os.environ.get("PROMPTFOO_CONFIG", str(Path.cwd() / "promptfooconfig.yaml"))


def _add_common_args(parser: argparse.ArgumentParser):
    """Add flags shared by discover, run, and scan subcommands."""
    parser.add_argument(
        "--skills-root",
        default=os.environ.get("SKILLS_ROOT", DEFAULT_SKILLS_ROOT),
        help="Root directory to scan for SKILL.md files (default: %(default)s)",
    )
    parser.add_argument(
        "--host-skills-root",
        default=DEFAULT_HOST_SKILLS_ROOT,
        help="Path written into the YAML (for VM/container use). Defaults to --skills-root.",
    )
    parser.add_argument(
        "--config", "--output",
        dest="config",
        default=_default_config_path(),
        help="Output config file path (default: %(default)s)",
    )
    parser.add_argument(
        "--target-provider", "--provider", "--llm-provider",
        action="append",
        dest="target_providers",
        default=None,
        help="Target provider under test. Repeat for multiple providers.",
    )
    parser.add_argument(
        "--redteam-provider",
        default=DEFAULT_REDTEAM_PROVIDER,
        help="Optional attacker/grader provider for redteam generation.",
    )
    parser.add_argument(
        "--num-tests",
        type=int,
        default=int(os.environ.get("NUM_TESTS", "10")),
        help="Number of tests per skill (default: %(default)s)",
    )
    parser.add_argument(
        "--plugin-preset",
        default=DEFAULT_PLUGIN_PRESET,
        help="Plugin preset: technical-minimal, technical-core, balanced, security-focused, minimal (default: %(default)s)",
    )
    parser.add_argument(
        "--strategy-preset",
        default=DEFAULT_STRATEGY_PRESET,
        help="Strategy preset: technical-minimal, local-safe, local-balanced, cloud-recommended (default: %(default)s)",
    )
    parser.add_argument(
        "--extra-plugins",
        default=os.environ.get("EXTRA_REDTEAM_PLUGINS", ""),
        help="Comma-separated extra plugin IDs to append.",
    )
    parser.add_argument(
        "--exclude-plugins",
        default=os.environ.get("EXCLUDE_REDTEAM_PLUGINS", ""),
        help="Comma-separated plugin IDs to remove from the preset.",
    )
    parser.add_argument(
        "--extra-strategies",
        default=os.environ.get("EXTRA_REDTEAM_STRATEGIES", ""),
        help="Comma-separated extra strategy IDs to append.",
    )
    parser.add_argument(
        "--exclude-strategies",
        default=os.environ.get("EXCLUDE_REDTEAM_STRATEGIES", ""),
        help="Comma-separated strategy IDs to remove from the preset.",
    )
    parser.add_argument(
        "--dedupe-mode",
        default=DEFAULT_DEDUPE_MODE,
        help="Deduplicate skills by: content, name, or off (default: %(default)s)",
    )


def _resolve_providers(args) -> list[str]:
    """Resolve the target provider list from CLI args + env."""
    raw = args.target_providers if args.target_providers is not None else [DEFAULT_TARGET_PROVIDERS]
    providers = []
    for value in raw:
        providers.extend(parse_csv(value))
    if not providers:
        providers = [DEFAULT_PROVIDER]
    return providers


def _print_header(args, target_providers: list[str], label: str):
    """Print the run header with configuration details."""
    host_root = args.host_skills_root or args.skills_root
    banner()
    print(f" {BOLD}SkillGuard  ·  {label}{RESET}")
    banner()
    print(f"  Skills root (discovery) : {CYAN}{args.skills_root}{RESET}")
    print(f"  Skills root (host/YAML) : {CYAN}{host_root}{RESET}")
    print(f"  Config out              : {CYAN}{args.config}{RESET}")
    print(f"  Target providers        : {CYAN}{', '.join(target_providers)}{RESET}")
    print(f"  Redteam provider        : {CYAN}{args.redteam_provider or '(default promptfoo attacker/grader)'}{RESET}")
    print(f"  Num tests               : {CYAN}{args.num_tests} per skill{RESET}")
    print(f"  Plugin preset           : {CYAN}{args.plugin_preset}{RESET}")
    print(f"  Strategy preset         : {CYAN}{args.strategy_preset}{RESET}")
    print(f"  Dedupe mode             : {CYAN}{args.dedupe_mode}{RESET}")
    print()


def _run_discovery_pipeline(args, target_providers: list[str]) -> tuple[list[dict], list[dict], int]:
    """Core discovery + static analysis + config generation pipeline.

    Returns: (skills, findings, exit_code)
       exit_code: 0 = clean, 2 = critical static findings.
    """
    host_root = args.host_skills_root or args.skills_root

    # ── Discover skills ──────────────────────────────────────────────────
    print(f"{BOLD}── Discovering skills ───────────────────────────────────────────{RESET}")
    skills = discover_skills(args.skills_root)
    total_found = len(skills)
    try:
        skills, duplicates = dedupe_skills(skills, args.dedupe_mode)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  Found {total_found} skill(s); keeping {len(skills)} after dedupe.\n")
    if duplicates:
        print(f"  ℹ️  Dropped {len(duplicates)} duplicate skill(s) using dedupe mode '{args.dedupe_mode}'.\n")

    # ── Static analysis ──────────────────────────────────────────────────
    print(f"{BOLD}── Static analysis ──────────────────────────────────────────────{RESET}")
    findings = run_static_analysis(skills)

    # ── Generate config ──────────────────────────────────────────────────
    print(f"{BOLD}── Generating promptfoo config ──────────────────────────────────{RESET}")
    try:
        plugins = resolve_plugin_set(
            args.plugin_preset,
            parse_csv(args.extra_plugins),
            parse_csv(args.exclude_plugins),
        )
        strategies, filtered_strategies = resolve_strategy_set(
            args.strategy_preset,
            parse_csv(args.extra_strategies),
            parse_csv(args.exclude_strategies),
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    if filtered_strategies:
        print("  ⚠️  Filtered cloud-only strategies for this local run:")
        for item in filtered_strategies:
            print(f"     - {item['id']}: {item['reason']}")
        print()

    config = build_promptfoo_config(
        skills, target_providers, args.num_tests,
        plugins=plugins,
        strategies=strategies,
        redteam_provider=args.redteam_provider or None,
        output_path=args.config,
        discovery_root=args.skills_root,
        host_root=host_root,
        plugin_preset=args.plugin_preset,
        strategy_preset=args.strategy_preset,
        dedupe_mode=args.dedupe_mode,
        duplicates=duplicates,
        filtered_strategies=filtered_strategies,
    )
    write_config(config, args.config)

    # ── Write static report ──────────────────────────────────────────────
    output_dir = str(Path(args.config).parent / "results")
    os.makedirs(output_dir, exist_ok=True)
    write_static_report(findings, output_dir)

    # ── Determine exit code ──────────────────────────────────────────────
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    exit_code = 0
    if critical:
        print(f"\n  ⚠️   {len(critical)} CRITICAL static finding(s) – review before running redteam!\n",
              file=sys.stderr)
        exit_code = 2

    return skills, findings, exit_code


# ── Subcommand handlers ──────────────────────────────────────────────────────

def cmd_discover(args):
    """Handler for the `discover` subcommand."""
    target_providers = _resolve_providers(args)
    _print_header(args, target_providers, "Skill Discovery & Config Generator")

    _skills, _findings, exit_code = _run_discovery_pipeline(args, target_providers)

    print()
    print("━" * 64)
    print("  Done.  Next step:")
    print(f"    skillguard run --config {args.config}")
    print("━" * 64)

    sys.exit(exit_code)


def cmd_run(args):
    """Handler for the `run` subcommand — full pipeline."""
    target_providers = _resolve_providers(args)
    _print_header(args, target_providers, "Skills Security Evaluator")

    # Preflight
    preflight_checks(
        target_providers=target_providers,
        redteam_provider=args.redteam_provider,
        skills_root=args.skills_root,
        promptfoo_version=args.promptfoo_version,
    )
    print()

    # Discovery pipeline
    _skills, _findings, discover_exit = _run_discovery_pipeline(args, target_providers)

    if discover_exit == 2:
        print(f"\n{YELLOW}[WARN]{RESET} CRITICAL static findings detected. Review static-scan-report.json")
        print("       Continuing with redteam run...")

    # Run promptfoo
    results_dir = str(Path(args.config).parent / "results")
    redteam_exit = run_promptfoo(args.config, results_dir, args.promptfoo_version)

    sys.exit(redteam_exit)


def cmd_scan(args):
    """Handler for the `scan` subcommand — static scan only."""
    target_providers = _resolve_providers(args)

    banner()
    print(f" {BOLD}SkillGuard  ·  Static Security Scan{RESET}")
    banner()
    print(f"  Skills root : {CYAN}{args.skills_root}{RESET}")
    print(f"  Dedupe mode : {CYAN}{args.dedupe_mode}{RESET}")
    print()

    # Discover
    print(f"{BOLD}── Discovering skills ───────────────────────────────────────────{RESET}")
    skills = discover_skills(args.skills_root)
    total_found = len(skills)
    try:
        skills, duplicates = dedupe_skills(skills, args.dedupe_mode)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  Found {total_found} skill(s); keeping {len(skills)} after dedupe.\n")

    # Scan
    print(f"{BOLD}── Static analysis ──────────────────────────────────────────────{RESET}")
    findings = run_static_analysis(skills)

    # Report
    output_dir = str(Path(args.config).parent / "results")
    os.makedirs(output_dir, exist_ok=True)
    write_static_report(findings, output_dir)

    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    if critical:
        print(f"\n  ⚠️   {len(critical)} CRITICAL finding(s) detected.\n", file=sys.stderr)
        sys.exit(2)

    banner()
    print(f" {BOLD}Scan complete — no critical issues.{RESET}")
    banner()


def cmd_eval(args):
    """Handler for the `eval` subcommand — quality evaluation with suggestions."""
    target_provider = args.eval_provider or DEFAULT_PROVIDER
    grader_provider = args.grader_provider

    # Parse dimensions
    if args.dimensions:
        dimensions = [d.strip() for d in args.dimensions.split(",") if d.strip()]
        invalid = [d for d in dimensions if d not in DIMENSIONS]
        if invalid:
            valid_list = ", ".join(DIMENSIONS)
            print(f"{RED}[ERROR]{RESET} Unknown dimensions: {', '.join(invalid)}")
            print(f"        Valid dimensions: {valid_list}")
            sys.exit(1)
    else:
        dimensions = list(DIMENSIONS)

    banner()
    print(f" {BOLD}SkillGuard  ·  Quality Evaluation{RESET}")
    banner()
    print(f"  Skills root     : {CYAN}{args.skills_root}{RESET}")
    print(f"  Eval config     : {CYAN}{args.eval_config}{RESET}")
    print(f"  Provider        : {CYAN}{target_provider}{RESET}")
    print(f"  Grader provider : {CYAN}{grader_provider or '(same as provider)'}{RESET}")
    print(f"  Dimensions      : {CYAN}{', '.join(dimensions)}{RESET}")
    print(f"  Dedupe mode     : {CYAN}{args.dedupe_mode}{RESET}")
    print()

    # Preflight
    preflight_checks(
        target_providers=[target_provider],
        redteam_provider=grader_provider or "",
        skills_root=args.skills_root,
        promptfoo_version=args.promptfoo_version,
    )
    print()

    # Discover skills
    from core.discover import discover_skills, dedupe_skills
    print(f"{BOLD}── Discovering skills ───────────────────────────────────────────{RESET}")
    skills = discover_skills(args.skills_root)
    total_found = len(skills)
    try:
        skills, duplicates = dedupe_skills(skills, args.dedupe_mode)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  Found {total_found} skill(s); keeping {len(skills)} after dedupe.\n")

    if not skills:
        print(f"{RED}[ERROR]{RESET} No skills found. Nothing to evaluate.")
        sys.exit(1)

    # Build eval config
    print(f"{BOLD}── Generating eval config ───────────────────────────────────────{RESET}")
    output_dir = str(Path(args.eval_config).parent)
    config = build_eval_config(
        skills=skills,
        provider=target_provider,
        num_tests=args.num_tests,
        dimensions=dimensions,
        grader_provider=grader_provider,
        output_dir=output_dir,
    )

    from core.discover import write_config
    write_config(config, args.eval_config)

    # Run promptfoo eval
    results_dir = str(Path(args.eval_config).parent / "results")
    eval_exit = run_promptfoo_eval(args.eval_config, results_dir, args.promptfoo_version)

    sys.exit(eval_exit)


def cmd_view(args):
    """Handler for the `view` subcommand."""
    banner()
    print(f" {BOLD}SkillGuard  ·  Interactive Report Viewer{RESET}")
    banner()
    run_promptfoo_view(args.promptfoo_version)


# ── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="skillguard",
        description="SkillGuard — AI Skills Security Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  skillguard discover --skills-root ~/.claude
  skillguard run --target-provider openai:gpt-4o --num-tests 5
  skillguard scan --skills-root ~/.claude
  skillguard view
""",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        description="Available commands (use <command> --help for details):",
    )

    # ── discover ─────────────────────────────────────────────────────────
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover skills and generate promptfoo config",
        description="Scan for SKILL.md files, run static analysis, and generate a promptfoo redteam config.",
    )
    _add_common_args(discover_parser)
    discover_parser.set_defaults(func=cmd_discover)

    # ── run ───────────────────────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run",
        help="Full pipeline: discover + redteam evaluation",
        description="Full pipeline: discover skills → static scan → generate config → run promptfoo redteam.",
    )
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--promptfoo-version",
        default=os.environ.get("PROMPTFOO_VERSION", "latest"),
        help="Promptfoo version for npx promptfoo@VER (default: %(default)s)",
    )
    run_parser.set_defaults(func=cmd_run)

    # ── scan ──────────────────────────────────────────────────────────────
    scan_parser = subparsers.add_parser(
        "scan",
        help="Static security scan only (no promptfoo)",
        description="Run static security analysis on discovered skills without invoking promptfoo.",
    )
    _add_common_args(scan_parser)
    scan_parser.set_defaults(func=cmd_scan)

    # ── eval ──────────────────────────────────────────────────────────────
    eval_parser = subparsers.add_parser(
        "eval",
        help="Quality evaluation with improvement suggestions (separate from redteam)",
        description=(
            "Evaluate skill quality across multiple dimensions and surface "
            "actionable improvement suggestions in the Promptfoo dashboard. "
            "This is completely separate from the redteam pipeline."
        ),
    )
    eval_parser.add_argument(
        "--skills-root",
        default=os.environ.get("SKILLS_ROOT", DEFAULT_SKILLS_ROOT),
        help="Root directory to scan for SKILL.md files (default: %(default)s)",
    )
    eval_parser.add_argument(
        "--eval-config",
        default=os.environ.get("EVAL_CONFIG", str(Path.cwd() / "evalconfig.yaml")),
        help="Output eval config file path (default: %(default)s)",
    )
    eval_parser.add_argument(
        "--eval-provider", "--provider",
        dest="eval_provider",
        default=None,
        help=f"Target provider for evaluation (default: {DEFAULT_PROVIDER})",
    )
    eval_parser.add_argument(
        "--grader-provider",
        default=None,
        help="LLM provider for grading (default: same as --eval-provider)",
    )
    eval_parser.add_argument(
        "--num-tests",
        type=int,
        default=int(os.environ.get("NUM_TESTS", "5")),
        help="Number of tests per dimension (default: %(default)s)",
    )
    eval_parser.add_argument(
        "--dimensions",
        default=None,
        help=(
            "Comma-separated quality dimensions to evaluate. "
            f"Available: {', '.join(DIMENSIONS)} (default: all)"
        ),
    )
    eval_parser.add_argument(
        "--dedupe-mode",
        default=DEFAULT_DEDUPE_MODE,
        help="Deduplicate skills by: content, name, or off (default: %(default)s)",
    )
    eval_parser.add_argument(
        "--promptfoo-version",
        default=os.environ.get("PROMPTFOO_VERSION", "latest"),
        help="Promptfoo version for npx promptfoo@VER (default: %(default)s)",
    )
    eval_parser.set_defaults(func=cmd_eval)

    # ── view ──────────────────────────────────────────────────────────────
    view_parser = subparsers.add_parser(
        "view",
        help="Open the promptfoo interactive report viewer",
        description="Launch the promptfoo web UI to view redteam or eval results interactively.",
    )
    view_parser.add_argument(
        "--promptfoo-version",
        default=os.environ.get("PROMPTFOO_VERSION", "latest"),
        help="Promptfoo version for npx promptfoo@VER (default: %(default)s)",
    )
    view_parser.set_defaults(func=cmd_view)

    # ── Parse + dispatch ─────────────────────────────────────────────────
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
