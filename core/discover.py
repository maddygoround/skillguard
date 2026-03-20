"""
discover.py
-----------
Skill discovery, deduplication, and promptfoo config generation.
All logic is preserved from the original discover-skills.py — only relocated
into this module.
"""

import os
import re
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

# ── YAML writer (no external dependency needed for simple YAML) ──────────────
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from .presets import (
    GENERATED_PROMPTS_DIRNAME,
    REDTEAM_PURPOSE,
    REDTEAM_GRADER_EXAMPLES,
    CLOUD_REQUIRED_STRATEGIES,
    PLUGIN_PRESETS,
    STRATEGY_PRESETS,
)


# ─────────────────────────────────────────────────────────────────────────────
def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a markdown string."""
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_meta = parts[1].strip()
            body = parts[2].strip()
            for line in raw_meta.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def parse_csv(value: str | None) -> list[str]:
    """Parse a comma-separated env/CLI list into clean string items."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_ids(ids: list[str | dict]) -> list[dict]:
    """Convert plugin/strategy entries into promptfoo dict entries without duplicates."""
    seen = set()
    normalized = []
    for item in ids:
        if isinstance(item, str):
            entry = {"id": item}
        elif isinstance(item, dict) and item.get("id"):
            entry = item
        else:
            raise ValueError("Preset entries must be strings or dicts with an 'id' field")

        item_id = entry["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        normalized.append(entry)
    return normalized


def resolve_plugin_set(preset: str, extra: list[str], exclude: list[str]) -> list[dict]:
    """Build the redteam plugin list from preset + overrides."""
    if preset not in PLUGIN_PRESETS:
        valid = ", ".join(sorted(PLUGIN_PRESETS))
        raise ValueError(f"Unknown plugin preset '{preset}'. Valid presets: {valid}")

    excluded = set(exclude)
    preset_entries = []
    for item in PLUGIN_PRESETS[preset]:
        item_id = item if isinstance(item, str) else item.get("id")
        if item_id in excluded:
            continue
        preset_entries.append(item)

    preset_entries.extend(item for item in extra if item not in excluded)
    return normalize_ids(preset_entries)


def cloud_access_available() -> bool:
    """Best-effort detection for cloud-backed promptfoo strategies."""
    return bool(
        os.environ.get("PROMPTFOO_REMOTE_GENERATION_URL")
        or os.environ.get("PROMPTFOO_CLOUD_ENABLED")
    )


def resolve_strategy_set(preset: str, extra: list[str], exclude: list[str]) -> tuple[list[dict], list[dict]]:
    """Build redteam strategies and return any that were filtered out."""
    if preset not in STRATEGY_PRESETS:
        valid = ", ".join(sorted(STRATEGY_PRESETS))
        raise ValueError(f"Unknown strategy preset '{preset}'. Valid presets: {valid}")

    excluded = set(exclude)
    strategy_ids = [item for item in STRATEGY_PRESETS[preset] if item not in excluded]
    strategy_ids.extend(item for item in extra if item not in excluded)

    filtered_out = []
    final_ids = []
    cloud_enabled = cloud_access_available()
    for item in strategy_ids:
        if item in CLOUD_REQUIRED_STRATEGIES and not cloud_enabled:
            filtered_out.append({
                "id": item,
                "reason": CLOUD_REQUIRED_STRATEGIES[item],
            })
            continue
        final_ids.append(item)

    return normalize_ids(final_ids), filtered_out


def dedupe_skills(skills: list[dict], mode: str) -> tuple[list[dict], list[dict]]:
    """Drop duplicate skills to avoid rerunning identical cached copies."""
    if mode == "off":
        return skills, []

    if mode not in {"content", "name"}:
        raise ValueError("DEDUP_MODE must be one of: off, content, name")

    deduped = []
    duplicates = []
    seen = {}
    for skill in skills:
        key = skill["content_hash"] if mode == "content" else skill["name"].strip().lower()
        original = seen.get(key)
        if original is None:
            seen[key] = skill
            deduped.append(skill)
            continue

        duplicates.append({
            "kept_id": original["id"],
            "kept_path": original["path"],
            "dropped_id": skill["id"],
            "dropped_path": skill["path"],
            "mode": mode,
        })

    return deduped, duplicates


def discover_skills(location: str) -> list[dict]:
    """Walk location and return a list of skill metadata dicts."""
    root = Path(location)
    if not root.exists():
        print(f"[ERROR] Location not found: {root}", file=sys.stderr)
        sys.exit(1)

    skills = []
    # Support nested project skill directories: any SKILL.md anywhere
    for skill_md in sorted(root.rglob("SKILL.md")):
        rel = skill_md.relative_to(root)
        skill_dir  = skill_md.parent
        # Derive a readable ID: join path parts with ':'
        parts      = list(rel.parts[:-1])  # exclude SKILL.md itself
        skill_id   = ":".join(parts) if parts else skill_dir.name

        raw = skill_md.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(raw)

        skill = {
            "id":          skill_id,
            "name":        meta.get("name", skill_id),
            "description": meta.get("description", ""),
            "path":        str(skill_md.resolve()),
            "rel_path":    str(skill_md),
            "dir":         str(skill_dir.resolve()),
            "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }
        skills.append(skill)
        print(f"  [FOUND] {skill_id:45s}  {skill_md}")

    return skills


def build_promptfoo_config(skills: list[dict], target_providers: list[str], num_tests: int,
                           plugins: list[dict], strategies: list[dict],
                           attacker_provider: str | None,
                           output_path: str,
                           location: str = "",
                           plugin_preset: str = "", strategy_preset: str = "",
                           dedupe_mode: str = "off", duplicates: list[dict] | None = None,
                           filtered_strategies: list[dict] | None = None) -> dict:
    """Construct the promptfoo redteam config dict.

    location – the path used to find SKILL.md files.
    """
    location = location.rstrip("/")
    duplicates = duplicates or []
    filtered_strategies = filtered_strategies or []

    prompts_dir = Path(output_path).resolve().parent / GENERATED_PROMPTS_DIRNAME
    prompts_dir.mkdir(parents=True, exist_ok=True)

    prompts = []
    prompt_files = {}
    for index, skill in enumerate(skills, start=1):
        raw_prompt = Path(skill["path"]).read_text(encoding="utf-8", errors="replace")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", skill["id"]).strip("-") or f"skill-{index}"
        prompt_path = prompts_dir / f"{index:03d}-{safe_name}.json"
        prompt_payload = [
            {
                "role": "system",
                "content": raw_prompt,
            },
            {
                "role": "user",
                "content": "{{prompt}}",
            },
        ]
        with open(prompt_path, "w", encoding="utf-8") as f:
            json.dump(prompt_payload, f, indent=2, ensure_ascii=False)
            f.write("\n")

        prompt_files[skill["id"]] = str(prompt_path)
        prompts.append({
            "id": f"file://{prompt_path}",
            "label": f"skill:{skill['id']}",
        })

    targets = [
        {
            "id": provider_id,
            "label": f"provider:{provider_id}",
        }
        for provider_id in target_providers
    ]

    config = {
        "description": (
            f"Auto-generated promptfoo redteam config – "
            f"{len(skills)} skills discovered. "
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        ),
        "prompts": prompts,
        "targets": targets,
        "redteam": {
            "purpose": REDTEAM_PURPOSE,
            "injectVar": "prompt",
            "numTests":  num_tests,
            "plugins":   plugins,
            "strategies": strategies,
            "graderExamples": REDTEAM_GRADER_EXAMPLES,
        },
        # Metadata sidebar – tracked for auditing
        "_meta": {
            "generated_by": "skillguard",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "location":  location,
            "skill_count":  len(skills),
            "target_providers": target_providers,
            "attacker_provider": attacker_provider or "",
            "plugin_preset": plugin_preset,
            "strategy_preset": strategy_preset,
            "dedupe_mode": dedupe_mode,
            "deduplicated_count": len(duplicates),
            "filtered_strategies": filtered_strategies,
            "generated_prompt_dir": str(prompts_dir),
            "duplicates": duplicates,
            "skills": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "path": s["path"],
                    "prompt_path": prompt_files[s["id"]],
                }
                for s in skills
            ],
        },
    }
    if attacker_provider:
        config["redteam"]["provider"] = attacker_provider
    return config


def write_config(config: dict, output_path: str):
    """Write config to YAML (or JSON fallback)."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if HAS_YAML:
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        # Minimal YAML serialiser (handles the subset we actually use)
        with open(out, "w", encoding="utf-8") as f:
            f.write(_simple_yaml(config))

    print(f"\n  ✅  Config written → {out}")


def _simple_yaml(obj, indent=0) -> str:
    """Minimal recursive YAML serialiser (no external deps)."""
    pad = "  " * indent
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        # Quote strings that contain special chars or look like booleans
        needs_quote = any(c in obj for c in ':{}[],#&*!|>\'\"@`\n') or obj in ("true","false","null","")
        if needs_quote:
            escaped = obj.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        return obj
    if isinstance(obj, list):
        if not obj:
            return "[]"
        lines = []
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first  = False
                    lines.append(f"{prefix}{k}: {_simple_yaml(v, indent+1)}")
            else:
                lines.append(f"{pad}- {_simple_yaml(item, indent+1)}")
        return "\n".join(lines)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                child = _simple_yaml(v, indent+1)
                lines.append(child)
            else:
                lines.append(f"{pad}{k}: {_simple_yaml(v, indent+1)}")
        return "\n".join(lines)
    return str(obj)
