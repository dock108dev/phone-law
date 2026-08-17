"""Reject content-like fields, credentials, and URLs from captured application logs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = {
    "authorization": re.compile(r"authorization", re.IGNORECASE),
    "audio": re.compile(r"audio", re.IGNORECASE),
    "caller": re.compile(r"caller", re.IGNORECASE),
    "phone": re.compile(r"phone", re.IGNORECASE),
    "provider_url": re.compile(r"provider.?url", re.IGNORECASE),
    "secret": re.compile(r"secret", re.IGNORECASE),
    "transcript": re.compile(r"transcript", re.IGNORECASE),
    "url": re.compile(r"(?:https?|postgres(?:ql)?(?:\+psycopg)?):\/\/", re.IGNORECASE),
}


def inspect(content: str) -> list[str]:
    return [name for name, pattern in FORBIDDEN.items() if pattern.search(content)]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: inspect_logs.py PATH")
    path = Path(sys.argv[1])
    content = path.read_text(encoding="utf-8")
    findings = inspect(content)
    if findings:
        raise SystemExit("log inspection failed: " + ",".join(sorted(findings)))
    print(f"log-inspection pass: {len(content.splitlines())} operational log lines inspected")


if __name__ == "__main__":
    main()
