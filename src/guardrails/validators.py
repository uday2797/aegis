"""
AEGIS Code Validators — Guardrail #4 & #2
- validate_python_code: syntax-check LLM output before uploading to Databricks
- lint_python_code: pyflakes static analysis + empty-code guard
- autoformat_code: autopep8 PEP8 formatting before upload
- compute_diff: show a line-level diff so every change is visible in logs
"""
import ast
import difflib
import io
import re
from loguru import logger


# Databricks magic lines are not valid Python — strip before any analysis
_DATABRICKS_MAGIC_RE = re.compile(
    r"^(# MAGIC|# COMMAND -{3,}|# Databricks notebook source|# dbtitle|# DBTITLE)",
    re.MULTILINE,
)


def _strip_databricks_magic(code: str) -> str:
    """Remove Databricks notebook magic lines so linters see pure Python."""
    lines = code.splitlines()
    clean = [
        line for line in lines
        if not _DATABRICKS_MAGIC_RE.match(line.strip())
    ]
    return "\n".join(clean)


def validate_python_code(code: str, notebook_path: str = "") -> tuple[bool, str]:
    """
    Guardrail #4 — LLM output validation.
    Checks:
      1. Code is non-empty (guards against GPT returning nothing)
      2. Syntactically valid Python (compile)

    Returns:
        (True, "ok")           — code is valid
        (False, error_message) — code has a problem; do NOT upload
    """
    # Guard: empty or near-empty output from LLM
    stripped = code.strip()
    if len(stripped) < 50:
        msg = f"LLM returned empty or near-empty code ({len(stripped)} chars) — refusing upload"
        logger.error(f"[Validator] ❌ {msg}")
        return False, msg

    clean = _strip_databricks_magic(stripped)
    try:
        compile(clean, filename=notebook_path or "<notebook>", mode="exec")
        logger.success(f"[Validator] ✅ Syntax check passed ({len(stripped)} chars)")
        return True, "ok"
    except SyntaxError as e:
        msg = f"SyntaxError at line {e.lineno}: {e.msg}  →  {e.text!r}"
        logger.error(f"[Validator] ❌ Syntax check FAILED: {msg}")
        return False, msg
    except Exception as e:
        msg = f"Unexpected validation error: {e}"
        logger.error(f"[Validator] ❌ {msg}")
        return False, msg


def lint_python_code(code: str, notebook_path: str = "") -> tuple[bool, list[str]]:
    """
    Guardrail #4b — Static analysis / lint.
    Runs pyflakes on the fixed code to catch undefined names, unused imports, etc.
    Falls back to ast-based undefined-name check if pyflakes is not installed.

    Returns:
        (True, [])              — no lint issues
        (False, [issue, ...])   — lint warnings/errors found
    """
    clean = _strip_databricks_magic(code.strip())
    issues: list[str] = []

    # ── Try pyflakes first (most complete) ──────────────────────────────
    try:
        from pyflakes import api as pyflakes_api
        from pyflakes.checker import Checker  # noqa: F401

        buf = io.StringIO()
        warning_count = pyflakes_api.check(clean, filename=notebook_path or "<notebook>")
        if warning_count > 0:
            # pyflakes prints to stdout; capture via check_source
            from pyflakes import api
            result = api.check(clean, filename=notebook_path or "<notebook>")
            issues.append(f"pyflakes: {result} issue(s) detected")
        if issues:
            logger.warning(f"[Linter] ⚠️  {len(issues)} pyflakes issue(s) in {notebook_path}")
        else:
            logger.success(f"[Linter] ✅ pyflakes: no issues")
        return len(issues) == 0, issues

    except ImportError:
        pass  # pyflakes not installed, fall through to ast-based check

    # ── AST-based fallback: check for obvious undefined names ────────────
    try:
        tree = ast.parse(clean)
        defined: set[str] = set()
        used: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    defined.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    used.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in getattr(node, "names", []):
                    defined.add(alias.asname or alias.name.split(".")[0])

        # Built-ins and Databricks globals that are always available
        builtins = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
        databricks_globals = {
            "spark", "sc", "dbutils", "display", "displayHTML",
            "sqlContext", "glueContext", "args",
        }
        potentially_undefined = used - defined - builtins - databricks_globals
        if potentially_undefined:
            issues.append(f"Possibly undefined names: {', '.join(sorted(potentially_undefined)[:10])}")
            logger.warning(f"[Linter] ⚠️  AST check: {issues[-1]}")
        else:
            logger.success("[Linter] ✅ AST check: no obvious undefined names")

    except Exception as e:
        logger.debug(f"[Linter] AST check skipped: {e}")

    return len(issues) == 0, issues


def autoformat_code(code: str) -> str:
    """
    PEP8 auto-formatting using autopep8 (if installed).
    Strips trailing whitespace and normalises indentation at minimum.
    Databricks magic lines are preserved as-is.

    Returns:
        Formatted code string.
    """
    try:
        import autopep8

        # Split magic vs. real Python lines
        lines = code.splitlines(keepends=True)
        magic_positions: dict[int, str] = {}
        python_lines: list[str] = []

        for i, line in enumerate(lines):
            if _DATABRICKS_MAGIC_RE.match(line.strip()):
                magic_positions[len(python_lines)] = line
            else:
                python_lines.append(line)

        python_src = "".join(python_lines)
        formatted_python = autopep8.fix_code(
            python_src,
            options={"max_line_length": 120, "aggressive": 1},
        )

        # Re-insert magic lines at original positions
        result_lines = formatted_python.splitlines(keepends=True)
        for pos in sorted(magic_positions):
            result_lines.insert(pos, magic_positions[pos])

        formatted = "".join(result_lines)
        logger.success("[Formatter] ✅ autopep8 PEP8 formatting applied")
        return formatted

    except ImportError:
        logger.debug("[Formatter] autopep8 not installed — skipping auto-format")
    except Exception as e:
        logger.warning(f"[Formatter] autopep8 failed: {e} — returning original")

    # Minimal fallback: strip trailing whitespace per line
    return "\n".join(line.rstrip() for line in code.splitlines())


def compute_diff(original: str, fixed: str, notebook_path: str = "") -> str:
    """
    Guardrail #2 — Notebook diff review.
    Generate a unified diff between original and fixed code.
    The diff is logged before any upload so there is an explicit record of what changed.

    Returns:
        The unified diff string (empty string if no changes).
    """
    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        original_lines,
        fixed_lines,
        fromfile=f"original/{notebook_path}",
        tofile=f"fixed/{notebook_path}",
        lineterm="",
    ))

    if not diff_lines:
        logger.warning(f"[Diff] No changes detected in {notebook_path} — LLM returned identical code!")
        return ""

    diff_text = "\n".join(diff_lines)
    added   = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    logger.info(
        f"[Diff] 📝 Changes for {notebook_path}: "
        f"+{added} lines added, -{removed} lines removed"
    )
    # Log first 80 lines of diff to avoid flooding output
    preview = "\n".join(diff_lines[:80])
    if len(diff_lines) > 80:
        preview += f"\n... ({len(diff_lines) - 80} more lines)"
    logger.debug(f"[Diff]\n{preview}")

    return diff_text
