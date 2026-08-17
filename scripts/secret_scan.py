"""Deterministic high-signal secret scan for the repository tree."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    "",
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".in",
    ".js",
    ".json",
    ".lock",
    ".md",
    ".mako",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "coverage",
    "dist",
    "evidence",
    "node_modules",
}
FORBIDDEN_FILENAMES = {".env", "id_rsa", "id_ed25519"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str


def scan_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path.name in FORBIDDEN_FILENAMES:
            findings.append(Finding(path, 0, "forbidden_secret_filename"))
            continue
        if path.suffix not in TEXT_SUFFIXES or path.name == "secret_scan.py":
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding(path, line_number, kind))
    return findings


def repository_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in IGNORED_PARTS for part in path.parts)
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    findings = scan_paths(repository_files(root))
    if findings:
        for finding in findings:
            relative = finding.path.relative_to(root)
            print(f"secret-scan finding: {relative}:{finding.line} ({finding.kind})")
        sys.exit(1)
    print(f"secret-scan pass: {len(repository_files(root))} repository files inspected")


if __name__ == "__main__":
    main()
