"""
The repo-boundary rule, enforced.

`scripts/llm_panel/` is a peer of `backend/`, not a part of it. It reaches the
platform over HTTP only. The moment one module does `from app.models...`, the
panel stops being extractable and starts being a second copy of the backend's
assumptions — and nothing would fail until someone tried to move it.

This is the test that fails instead.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "llm_panel"
FORBIDDEN_ROOTS = {"app", "backend", "alembic"}


def _module_files() -> list[Path]:
    files = sorted(PACKAGE_DIR.rglob("*.py"))
    assert files, f"No modules found under {PACKAGE_DIR}"
    return files


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        # Relative imports (node.level > 0) have no module root to check.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_module_does_not_import_from_the_backend(path: Path) -> None:
    roots = _imported_roots(ast.parse(path.read_text(), filename=str(path)))
    forbidden = roots & FORBIDDEN_ROOTS
    assert not forbidden, (
        f"{path.name} imports {sorted(forbidden)}. The panel talks to the "
        "platform over HTTP only — see llm_panel/platform_client.py."
    )
