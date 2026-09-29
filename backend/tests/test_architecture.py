"""Enforces the dependency rules from CLAUDE.md section 3.

The pure core (domain, detection, investigation) must not import I/O libraries, and each
external library is confined to one package. Do not weaken these rules to make a change pass.
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "sentinel"
STDLIB = set(sys.stdlib_module_names)

# package -> (allowed internal prefixes, allowed third-party top-level modules)
PURE_PACKAGES = {
    "domain": ({"sentinel.domain"}, {"pydantic"}),
    "detection": ({"sentinel.domain", "sentinel.detection"}, set()),
}
# stdlib modules that mean I/O and are forbidden in the pure core
FORBIDDEN_STDLIB_IN_CORE = {"sqlite3", "socket", "http", "urllib", "subprocess", "requests"}

# external library -> packages allowed to import it
CONFINED = {
    "boto3": {"collectors/aws"},
    "botocore": {"collectors/aws"},
    "sqlite3": {"store"},
    "fastapi": {"api", "main.py", "openapi_export.py"},
    "httpx": {"investigation/providers"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _files():
    return sorted(PACKAGE.rglob("*.py"))


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(PACKAGE)))
def test_import_rules(path: Path):
    rel = path.relative_to(PACKAGE).as_posix()
    top = rel.split("/")[0]
    for name in _imports(path):
        root = name.split(".")[0]
        if top in PURE_PACKAGES:
            internal, third_party = PURE_PACKAGES[top]
            if root == "sentinel":
                assert any(name.startswith(p) for p in internal), f"{rel} imports {name}"
            elif root in STDLIB:
                assert root not in FORBIDDEN_STDLIB_IN_CORE, f"{rel} does I/O via {name}"
            else:
                assert root in third_party, f"{rel} imports third-party {name}"
        if root in CONFINED:
            allowed = CONFINED[root]
            assert any(rel.startswith(a) for a in allowed), f"{rel} may not import {root}"
