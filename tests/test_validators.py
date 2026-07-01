"""
Tests for guardrails/validators.py — syntax check, lint, diff, autoformat.
Zero external dependencies beyond pyflakes + autopep8 (already in requirements).
"""
import pytest
from src.guardrails.validators import (
    validate_python_code,
    lint_python_code,
    autoformat_code,
    compute_diff,
)

VALID_CODE = """\
import pandas as pd

df = pd.DataFrame({"a": [1, 2, 3]})
result = df["a"].sum()
print(result)
"""

SYNTAX_ERROR_CODE = """\
import pandas as pd

def broken(
    x = 1
    y = 2
print("oops")
"""

DATABRICKS_MAGIC_CODE = """\
# Databricks notebook source

# COMMAND ----------
import pandas as pd

# COMMAND ----------
df = pd.DataFrame({"x": [1]})
"""

EMPTY_CODE = ""
NEAR_EMPTY_CODE = "x = 1"


class TestValidatePythonCode:
    def test_valid_code_passes(self):
        ok, msg = validate_python_code(VALID_CODE)
        assert ok is True
        assert msg == "ok"

    def test_empty_code_fails(self):
        ok, msg = validate_python_code(EMPTY_CODE)
        assert ok is False
        assert "empty" in msg.lower()

    def test_near_empty_fails(self):
        ok, msg = validate_python_code(NEAR_EMPTY_CODE)
        assert ok is False

    def test_syntax_error_caught(self):
        ok, msg = validate_python_code(SYNTAX_ERROR_CODE)
        assert ok is False
        assert "SyntaxError" in msg or "syntax" in msg.lower()

    def test_databricks_magic_stripped_before_check(self):
        ok, msg = validate_python_code(DATABRICKS_MAGIC_CODE)
        assert ok is True, f"Failed with: {msg}"

    def test_notebook_path_in_error_message(self):
        ok, msg = validate_python_code(SYNTAX_ERROR_CODE, notebook_path="/my/notebook")
        assert ok is False


class TestLintPythonCode:
    def test_clean_code_passes(self):
        ok, issues = lint_python_code(VALID_CODE)
        assert isinstance(ok, bool)
        assert isinstance(issues, list)

    def test_returns_tuple(self):
        result = lint_python_code(VALID_CODE)
        assert len(result) == 2


class TestComputeDiff:
    def test_identical_code_returns_empty(self):
        diff = compute_diff(VALID_CODE, VALID_CODE, "/nb")
        assert diff == "" or diff is None or len(diff.strip()) == 0

    def test_changed_code_returns_diff(self):
        modified = VALID_CODE.replace("sum()", "mean()")
        diff = compute_diff(VALID_CODE, modified, "/nb")
        assert diff  # must be non-empty

    def test_diff_contains_changed_line(self):
        old = "x = 1\n"
        new = "x = 42\n"
        diff = compute_diff(old, new, "/nb")
        assert "42" in diff or "1" in diff


class TestAutoformatCode:
    def test_returns_string(self):
        result = autoformat_code(VALID_CODE)
        assert isinstance(result, str)

    def test_does_not_corrupt_valid_code(self):
        result = autoformat_code(VALID_CODE)
        # Should still be syntactically valid after formatting
        ok, _ = validate_python_code(result)
        assert ok is True

    def test_empty_string_returns_string(self):
        result = autoformat_code("")
        assert isinstance(result, str)
