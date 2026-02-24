#!/usr/bin/env python3
"""Validate that case study notebooks follow required patterns.

Notebooks that call any everyrow operation (merge, agent_map, screen, rank,
dedupe) must:
1. Conditionally install everyrow (try/except ImportError + pip install)
2. Conditionally set EVERYROW_API_KEY (check os.environ before setting)
3. Wrap all tool calls inside `async with create_session(name="...") as session:`
   blocks, with `session.get_url()` printed for observability.

Notebooks that don't use any everyrow ops are skipped.
"""

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DOCS_SITE_DIR = SCRIPT_DIR.parent
REPO_ROOT = DOCS_SITE_DIR.parent
NOTEBOOKS_DIR = REPO_ROOT / "docs" / "case_studies"

# everyrow operations that must be wrapped in create_session
EVERYROW_OPS = {"merge", "agent_map", "screen", "rank", "dedupe"}

# Pattern: function call like `await merge(`, `await screen(`, etc.
# Also matches direct calls without await, and _async variants
OP_CALL_RE = re.compile(
    r"\b(?:await\s+)?(?:" + "|".join(EVERYROW_OPS) + r")(?:_async)?\s*\("
)


def get_code_cells(notebook_path: Path) -> list[str]:
    """Extract source code from all code cells in a notebook."""
    with open(notebook_path) as f:
        nb = json.load(f)
    cells = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            source = cell.get("source", [])
            if isinstance(source, list):
                cells.append("".join(source))
            else:
                cells.append(source)
    return cells


def check_conditional_pip_install(code_cells: list[str]) -> list[str]:
    """Check for conditional pip install of everyrow.

    Accepted patterns:
      try:
          import everyrow
      except ImportError:
          %pip install everyrow    (or !pip install everyrow)
    """
    errors = []
    all_code = "\n".join(code_cells)

    has_pip_install = bool(re.search(r"[%!]pip install\b.*\beveryrow\b", all_code))
    has_try_except = bool(
        re.search(
            r"try\s*:.*?import\s+everyrow.*?except\s+(?:Import|Module)(?:Error|NotFoundError)",
            all_code,
            re.DOTALL,
        )
    )

    if not has_pip_install:
        errors.append(
            "Missing `%pip install everyrow`. "
            "Add a setup cell with: try/except ImportError -> %pip install everyrow"
        )
    elif not has_try_except:
        errors.append(
            "pip install everyrow is not conditional. "
            "Wrap it in: try: import everyrow / except ImportError: %pip install everyrow"
        )

    return errors


def check_conditional_api_key(code_cells: list[str]) -> list[str]:
    """Check for conditional EVERYROW_API_KEY setup.

    Accepted pattern:
      if "EVERYROW_API_KEY" not in os.environ:
          os.environ["EVERYROW_API_KEY"] = "..."
    """
    errors = []
    all_code = "\n".join(code_cells)

    has_key_reference = "EVERYROW_API_KEY" in all_code
    has_conditional = bool(
        re.search(
            r'if\s+["\']EVERYROW_API_KEY["\']\s+not\s+in\s+os\.environ',
            all_code,
        )
    )

    if not has_key_reference:
        errors.append(
            "Missing EVERYROW_API_KEY setup. "
            'Add: if "EVERYROW_API_KEY" not in os.environ: os.environ["EVERYROW_API_KEY"] = "..."'
        )
    elif not has_conditional:
        errors.append(
            "EVERYROW_API_KEY is not set conditionally. "
            'Use: if "EVERYROW_API_KEY" not in os.environ: os.environ["EVERYROW_API_KEY"] = "..."'
        )

    return errors


def check_create_session_wrapping(code_cells: list[str]) -> list[str]:
    """Check that everyrow tool calls are wrapped in create_session.

    Requirements:
    - If any everyrow op is called, `create_session(name=` must appear in the notebook
    - `session.get_url()` or `task_id` must be printed for observability
    """
    errors = []
    all_code = "\n".join(code_cells)

    # Find all everyrow op calls
    op_calls = OP_CALL_RE.findall(all_code)
    if not op_calls:
        return []  # No everyrow ops used, nothing to check

    # Check that create_session is used with a name
    has_create_session = bool(re.search(r"create_session\s*\(\s*name\s*=", all_code))
    if not has_create_session:
        errors.append(
            "everyrow operations found but not wrapped in "
            '`async with create_session(name="...") as session:`. '
            "All tool calls must run inside a named session."
        )

    # Check for observability: session.get_url() or task_id printed
    has_observability = bool(
        re.search(r"session\.get_url\(\)|\.task_id|\.session_id", all_code)
    )
    if not has_observability:
        errors.append(
            "Missing session observability. "
            'Add `print(f"Session URL: {session.get_url()}")` inside the create_session block.'
        )

    return errors


def uses_everyrow_ops(code_cells: list[str]) -> bool:
    """Check if any everyrow operations are called in the notebook."""
    all_code = "\n".join(code_cells)
    return bool(OP_CALL_RE.search(all_code))


def validate_notebook(notebook_path: Path) -> list[str]:
    """Validate a notebook's patterns. Returns list of error messages."""
    slug = notebook_path.parent.name
    code_cells = get_code_cells(notebook_path)

    if not code_cells:
        return [f"{slug}: No code cells found"]

    # Only enforce setup and session checks if notebook actually calls everyrow ops
    if not uses_everyrow_ops(code_cells):
        return []

    all_errors = []
    for check_fn in [
        check_conditional_pip_install,
        check_conditional_api_key,
        check_create_session_wrapping,
    ]:
        for error in check_fn(code_cells):
            all_errors.append(f"{slug}: {error}")

    return all_errors


def main() -> int:
    notebooks = sorted(NOTEBOOKS_DIR.glob("*/notebook.ipynb"))

    if not notebooks:
        print(f"No notebooks found in {NOTEBOOKS_DIR}")
        return 1

    all_errors = []
    passed = 0
    for notebook in notebooks:
        errors = validate_notebook(notebook)
        if errors:
            all_errors.extend(errors)
        else:
            passed += 1

    if all_errors:
        print("Notebook pattern validation failed:\n")
        for error in all_errors:
            print(f"  - {error}")
        print(f"\n{len(all_errors)} error(s) across {len(notebooks)} notebooks")
        print(f"{passed}/{len(notebooks)} notebooks passed all checks")
        return 1

    print(f"All {len(notebooks)} notebooks pass pattern checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
