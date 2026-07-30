#!/usr/bin/env python3
"""Render a bundled Markdown work-item template from a JSON object."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TEMPLATES = {
    "epic": "epic.md",
    "issue": "atomic-issue.md",
    "checkpoint": "checkpoint.md",
    "pr": "pull-request.md",
}
TOKEN = re.compile(r"{{([A-Z][A-Z0-9_]*)}}")


def render(template: str, values: dict[str, object]) -> str:
    normalized = {key.upper(): str(value) for key, value in values.items()}
    missing = sorted(set(TOKEN.findall(template)) - set(normalized))
    if missing:
        raise ValueError("missing template values: " + ", ".join(missing))
    return TOKEN.sub(lambda match: normalized[match.group(1)], template)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(TEMPLATES), required=True)
    parser.add_argument("--data", type=Path, required=True, help="JSON object file")
    parser.add_argument("--output", type=Path, help="write output instead of stdout")
    args = parser.parse_args()

    values = json.loads(args.data.read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise SystemExit("--data must contain a JSON object")
    root = Path(__file__).resolve().parents[1]
    template = (root / "assets" / "templates" / TEMPLATES[args.kind]).read_text(
        encoding="utf-8"
    )
    try:
        result = render(template, values)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
