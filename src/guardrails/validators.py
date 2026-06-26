"""
AEGIS Code Validators — Guardrail #4 & #2
- validate_python_code: syntax-check LLM output before uploading to Databricks
- compute_diff: show a line-level diff so every change is visible in logs
"""
import difflib
from loguru import logger


def validate_python_code(code: str, notebook_path: str = "") -> tuple[bool, str]:
    """
    Guardrail #4 — LLM output validation.
    Compile the fixed code to check for syntax errors before uploading.

    Returns:
        (True, "ok")           — code is syntactically valid
        (False, error_message) — code has a syntax error; do NOT upload
    """
    try:
        compile(code, filename=notebook_path or "<notebook>", mode="exec")
        logger.success(f"[Validator] ✅ Fixed code passed syntax check ({len(code)} chars)")
        return True, "ok"
    except SyntaxError as e:
        msg = f"SyntaxError at line {e.lineno}: {e.msg}  →  {e.text!r}"
        logger.error(f"[Validator] ❌ Fixed code FAILED syntax check: {msg}")
        return False, msg
    except Exception as e:
        msg = f"Unexpected validation error: {e}"
        logger.error(f"[Validator] ❌ {msg}")
        return False, msg


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
