#!/usr/bin/env python3
"""Check local documentation links without crawling remote sites or private exports."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    paths = [ROOT / "README.md", ROOT / "farmer-extension/README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in paths:
        for match in re.finditer(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            target = unquote(match.group(1).split("#", 1)[0])
            if not target or re.match(r"^[a-z]+:|^/", target):
                continue
            if not (path.parent / target).exists():
                errors.append(f"{path.relative_to(ROOT)}: {target}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: local links in {len(paths)} documentation files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
