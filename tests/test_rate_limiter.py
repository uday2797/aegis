"""
Tests for guardrails/rate_limiter.py — sliding window, check & record.
Uses monkeypatching of time.monotonic so tests run instantly.
"""
import time
import pytest
from src.guardrails.rate_limiter import RateLimiter, _run_timestamps, DEFAULT_MAX_RUNS


def _clear(job_id):
    """Reset rate-limiter state for a given job between tests."""
    _run_timestamps.pop(str(job_id), None)


class TestRateLimiterCheck:
    def test_first_trigger_is_always_allowed(self):
        _clear("job_check_first")
        ok, reason = RateLimiter.check("job_check_first")
        assert ok is True
        assert reason == "ok"

    def test_trigger_up_to_max_allowed(self):
        _clear("job_check_max")
        for _ in range(DEFAULT_MAX_RUNS - 1):
            RateLimiter.record_trigger("job_check_max")
        ok, _ = RateLimiter.check("job_check_max")
        assert ok is True

    def test_exceeding_max_blocked(self):
        _clear("job_check_block")
        for _ in range(DEFAULT_MAX_RUNS):
            RateLimiter.record_trigger("job_check_block")
        ok, reason = RateLimiter.check("job_check_block")
        assert ok is False
        assert "Rate limit" in reason

    def test_different_jobs_are_independent(self):
        _clear("job_A")
        _clear("job_B")
        for _ in range(DEFAULT_MAX_RUNS):
            RateLimiter.record_trigger("job_A")
        # job_B should still be allowed
        ok, _ = RateLimiter.check("job_B")
        assert ok is True

    def test_string_and_int_ids_treated_equally(self):
        _clear(9999)
        RateLimiter.record_trigger(9999)
        ok_int, _ = RateLimiter.check(9999)
        ok_str, _ = RateLimiter.check("9999")
        assert ok_int == ok_str


class TestRateLimiterRemaining:
    def test_remaining_decreases_after_trigger(self):
        _clear("job_remaining")
        before = RateLimiter.remaining("job_remaining")
        RateLimiter.record_trigger("job_remaining")
        after = RateLimiter.remaining("job_remaining")
        assert after == before - 1

    def test_remaining_never_negative(self):
        _clear("job_neg")
        for _ in range(DEFAULT_MAX_RUNS + 5):
            RateLimiter.record_trigger("job_neg")
        assert RateLimiter.remaining("job_neg") == 0

    def test_remaining_is_max_for_fresh_job(self):
        _clear("job_fresh")
        assert RateLimiter.remaining("job_fresh") == DEFAULT_MAX_RUNS


class TestRateLimiterWindowExpiry:
    def test_old_triggers_outside_window_are_evicted(self, monkeypatch):
        _clear("job_window")
        # Simulate 5 triggers that happened 20 minutes ago
        past = time.monotonic() - 1200  # 20 min ago
        _run_timestamps["job_window"] = [past] * DEFAULT_MAX_RUNS
        # They should be evicted and a new check should pass
        ok, _ = RateLimiter.check("job_window", window_seconds=600)
        assert ok is True
