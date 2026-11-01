"""Render an IAM policy template from infra/policies/ for pasting into the IAM console.

    python scripts/render_policy.py infra/policies/operator-terraform.json \
        --account-id 123456789012 > "$TEMP/operator-terraform.rendered.json"

Same rules as Terraform's templatefile(): ${name} is replaced by a variable, and $${...}
becomes a literal ${...} (an IAM policy variable such as ${aws:username}). Unknown
variables are an error, so a typo never reaches IAM.

The output contains your account id: write it OUTSIDE the repository and do not commit it.
Standard library only; reads a file and prints JSON, nothing else (no AWS call).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_VARIABLE = re.compile(r"(?<!\$)\$\{([a-z_]+)\}")


def render(template: str, variables: dict[str, str]) -> str:
    used = set(_VARIABLE.findall(template))
    missing = used - set(variables)
    if missing:
        raise KeyError(f"template variables without a value: {sorted(missing)}")
    rendered = _VARIABLE.sub(lambda m: variables[m.group(1)], template)
    return rendered.replace("$${", "${")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("template", type=Path)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--region", default="eu-west-3")
    parser.add_argument("--log-group-name", default="/cloudops-sentinel/dev/access")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[0-9]{12}", args.account_id):
        parser.error("--account-id must be 12 digits")
    variables = {
        "account_id": args.account_id,
        "region": args.region,
        "log_group_name": args.log_group_name,
    }
    document = json.loads(render(args.template.read_text(encoding="utf-8"), variables))
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
