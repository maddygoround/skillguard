"""
scanner.py
----------
Static security analysis for discovered skills. Scans skill content for
known injection patterns, exfiltration vectors, obfuscation, and other
suspicious constructs.
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime


# ── Static-scan patterns ─────────────────────────────────────────────────────
# Each entry: (pattern_regex, severity, description)
STATIC_PATTERNS = [
    # Prompt injection indicators
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
     "CRITICAL", "Classic 'ignore previous instructions' injection vector"),
    (r"disregard\s+(all\s+)?(previous|prior|above)",
     "CRITICAL", "Instruction-disregard injection pattern"),
    (r"you\s+are\s+now\s+(?!a\s+(?:helpful|creative|expert))",
     "HIGH", "Identity-override pattern"),
    (r"act\s+as\s+(?:DAN|jailbreak|unrestricted)",
     "HIGH", "Known jailbreak persona trigger"),
    (r"pretend\s+you\s+are\s+no\s+longer",
     "HIGH", "Role-abandonment instruction"),
    # Data exfiltration signals
    (r"(send|post|transmit|exfiltrate|leak)\s+.{0,40}(http[s]?://|api\.)",
     "HIGH", "Potential data exfiltration via HTTP"),
    (r"fetch\s*\(\s*['\"]http",
     "HIGH", "Outbound HTTP fetch instruction"),
    (r"curl\s+-X\s+(POST|PUT)\s+http",
     "HIGH", "curl POST to external URL"),
    (r"eval\s*\(",
     "MEDIUM", "eval() usage – possible code injection"),
    # Encoded / obfuscated content
    (r"base64\.b64decode|atob\(",
     "MEDIUM", "Base64 decode call – possible obfuscation"),
    (r"\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){5,}",
     "MEDIUM", "Long hex escape sequence – possible obfuscation"),
    # Credential harvesting
    (r"(password|secret|api[_\s]?key|token)\s*[:=]\s*\{\{",
     "HIGH", "Possible credential interpolation template"),
    (r"os\.environ\s*\[",
     "MEDIUM", "Environment variable access – verify intent"),
    # Social engineering amplifiers
    (r"must\s+always\s+comply|never\s+refuse",
     "MEDIUM", "Absolute compliance directive – evaluate carefully"),
    (r"override\s+(safety|content)\s+filter",
     "CRITICAL", "Explicit safety-filter override instruction"),
    # Hidden content
    (r"<!--\s*(?!.*-->.*-->).{30,}-->",
     "MEDIUM", "Unusually long HTML comment – possible hidden instruction"),
    (r"\[\s*\]\s*\(\s*javascript:",
     "HIGH", "javascript: URI scheme in markdown link"),
]


def static_scan(skill_name: str, content: str) -> list[dict]:
    """Run regex-based static scan on skill content. Returns list of findings."""
    findings = []
    lines = content.splitlines()
    for lineno, line in enumerate(lines, 1):
        for pattern, severity, desc in STATIC_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({
                    "skill":    skill_name,
                    "line":     lineno,
                    "severity": severity,
                    "pattern":  pattern,
                    "message":  desc,
                    "excerpt":  line.strip()[:120],
                })
    return findings


def run_static_analysis(skills: list[dict]) -> list[dict]:
    """Run static analysis on all skills. Print + return findings."""
    all_findings = []
    for skill in skills:
        content = Path(skill["path"]).read_text(encoding="utf-8", errors="replace")
        findings = static_scan(skill["id"], content)
        all_findings.extend(findings)

    if all_findings:
        print("\n┌─────────────────────────────────────────────────────────────┐")
        print("│          STATIC ANALYSIS – POTENTIAL ISSUES FOUND           │")
        print("└─────────────────────────────────────────────────────────────┘")
        for f in all_findings:
            sev_color = {"CRITICAL": "\033[91m", "HIGH": "\033[93m", "MEDIUM": "\033[33m"}
            reset = "\033[0m"
            color = sev_color.get(f["severity"], "")
            print(f"  {color}[{f['severity']:8s}]{reset}  skill={f['skill']}  line={f['line']}")
            print(f"             {f['message']}")
            print(f"             » {f['excerpt']}")
            print()
    else:
        print("\n  ✅  Static analysis: no suspicious patterns found in any skill.\n")

    return all_findings


def write_static_report(findings: list[dict], output_dir: str):
    """Write static-analysis findings to a JSON report."""
    report_path = Path(output_dir) / "static-scan-report.json"
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_findings": len(findings),
        "counts_by_severity": {
            "CRITICAL": sum(1 for f in findings if f["severity"] == "CRITICAL"),
            "HIGH": sum(1 for f in findings if f["severity"] == "HIGH"),
            "MEDIUM": sum(1 for f in findings if f["severity"] == "MEDIUM"),
        },
        "findings": findings,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"  📄  Static report  → {report_path}")
    return report_path
