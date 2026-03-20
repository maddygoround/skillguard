"""
evaluator.py
------------
Generates a `promptfoo eval` configuration (evalconfig.yaml) that is
completely separate from the redteam config (promptfooconfig.yaml).

Each discovered skill is tested against quality dimensions using
model-graded llm-rubric assertions with custom rubricPrompts that
produce actionable improvement suggestions in the Promptfoo dashboard.

Architecture:
  Uses a SINGLE prompt template with skill content passed via `vars`.
  This avoids the promptfoo cross-product explosion (prompts × tests)
  that would happen with per-skill prompt files.

  Total evaluations = 1 prompt × 1 provider × (N skills × D dimensions)
"""

import os
import json
from pathlib import Path
from datetime import datetime

from .discover import discover_skills, dedupe_skills, write_config, parse_frontmatter
from .presets import DEFAULT_PROVIDER
from .graders import RUBRICS, DIMENSION_LABELS, DIMENSIONS


# ── Single prompt template ───────────────────────────────────────────────────

EVAL_PROMPT_TEMPLATE = (
    "You are reviewing an AI skill definition (SKILL.md). "
    "Analyze the following skill and provide your assessment.\n\n"
    "--- SKILL DEFINITION ---\n"
    "{{skill_content}}\n"
    "--- END SKILL DEFINITION ---\n\n"
    "{{analysis_request}}"
)


# ── Eval config builder ──────────────────────────────────────────────────────

def generate_eval_tests(
    skills: list[dict],
    dimensions: list[str],
) -> list[dict]:
    """Generate test cases: one per skill × dimension.

    Each test injects the skill content via vars so there's
    a single prompt template and no cross-product explosion.
    """
    tests = []
    for skill in skills:
        # Read the skill content once
        try:
            skill_content = Path(skill["path"]).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            skill_content = f"[ERROR: Could not read {skill['path']}]"

        for dim in dimensions:
            if dim not in RUBRICS:
                continue

            label = DIMENSION_LABELS.get(dim, dim)
            rubric = RUBRICS[dim]

            test = {
                "description": f"[{skill['name']}] {label}",
                "vars": {
                    "skill_content": skill_content,
                    "analysis_request": (
                        f"Evaluate this skill for '{label}'. "
                        f"Assess whether the skill definition provides clear, "
                        f"well-structured {label.lower()} guidance. "
                        f"Specifically, please verify whether the skill incorporates "
                        f"tool usage constraints and how its context behaves (such as "
                        f"'context: fork' for isolated sub-agent environments)."
                    ),
                },
                "assert": [
                    {
                        "type": "llm-rubric",
                        "value": (
                            f"Evaluate the skill '{skill['name']}' for {label}. "
                            f"The skill should have clear, well-defined "
                            f"{label.lower()} in its definition, including considerations "
                            f"for tool usage limitations and environment context isolation (e.g. context: fork)."
                        ),
                    },
                ],
                "options": {
                    "rubricPrompt": rubric,
                },
            }
            tests.append(test)

    return tests


def build_eval_config(
    skills: list[dict],
    target_provider: str,
    num_tests: int = 5,
    dimensions: list[str] | None = None,
    attacker_provider: str | None = None,
    output_dir: str = ".",
) -> dict:
    """Construct the promptfoo eval config dict for quality evaluation.

    Uses a single prompt template with skill content in vars.
    Total evals = 1 prompt × 1 provider × (skills × dimensions).
    """
    dimensions = dimensions or list(DIMENSIONS)

    # Build test cases: skills × dimensions
    tests = generate_eval_tests(skills, dimensions)

    total_evals = len(tests)  # 1 prompt × 1 provider × len(tests)

    # Default test options
    default_test = {}
    if attacker_provider:
        default_test["options"] = {
            "provider": attacker_provider,
        }

    config = {
        "description": (
            f"SkillGuard quality evaluation – "
            f"{len(skills)} skill(s) × {len(dimensions)} dimension(s) = "
            f"{total_evals} test(s). "
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        ),
        "prompts": [EVAL_PROMPT_TEMPLATE],
        "providers": [
            {
                "id": target_provider,
                "label": f"provider:{target_provider}",
            }
        ],
        "tests": tests,
        "_meta": {
            "generated_by": "skillguard-eval",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "skill_count": len(skills),
            "dimensions": dimensions,
            "total_evaluations": total_evals,
            "target_provider": target_provider,
            "attacker_provider": attacker_provider or target_provider,
            "skills": [
                {"id": s["id"], "name": s["name"], "path": s["path"]}
                for s in skills
            ],
        },
    }
    if default_test:
        config["defaultTest"] = default_test

    return config
