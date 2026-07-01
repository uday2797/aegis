"""
AEGIS Rate Limiter — Guardrail #5
Prevents AEGIS from triggering too many Databricks job runs in a short window.
Uses a simple in-process token-bucket per job_id, persisted across retries.
"""
import time
from collections import defaultdict
from loguru import logger


# Global in-process state (survives across retries within one run)
_run_timestamps: dict[str, list[float]] = defaultdict(list)

# Default policy: max 5 triggered runs per job per 10-minute window
DEFAULT_MAX_RUNS = 5
DEFAULT_WINDOW_SECONDS = 600  # 10 minutes


class RateLimiter:
    """
    Simple sliding-window rate limiter for Databricks job triggers.

    Usage:
        allowed, reason = RateLimiter.check(job_id=123)
        if not allowed:
            logger.warning(reason)
    """

    @staticmethod
    def check(
        job_id: int | str,
        max_runs: int = DEFAULT_MAX_RUNS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> tuple[bool, str]:
        """
        Check whether triggering another run for *job_id* is allowed.

        Returns:
            (True, "ok")                     — trigger is safe
            (False, "<reason string>")        — rate limit exceeded
        """
        key = str(job_id)
        now = time.monotonic()
        cutoff = now - window_seconds

        # Evict stale entries outside the window
        _run_timestamps[key] = [t for t in _run_timestamps[key] if t > cutoff]

        count = len(_run_timestamps[key])
        if count >= max_runs:
            minutes = window_seconds // 60
            reason = (
                f"Rate limit: job {job_id} already triggered {count}/{max_runs} "
                f"runs in the last {minutes} min. Skipping to protect Databricks quota."
            )
            logger.warning(f"[RateLimiter] {reason}")
            return False, reason

        logger.debug(f"[RateLimiter] job {job_id}: {count + 1}/{max_runs} runs in window — allowed")
        return True, "ok"

    @staticmethod
    def record_trigger(job_id: int | str) -> None:
        """Call this immediately after successfully triggering a run."""
        _run_timestamps[str(job_id)].append(time.monotonic())
        logger.debug(f"[RateLimiter] Recorded trigger for job {job_id}")

    @staticmethod
    def check_and_record(
        job_id: int | str,
        max_runs: int = DEFAULT_MAX_RUNS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> tuple[bool, str]:
        """Atomically check and record a trigger. Prefer this over separate check()+record_trigger() calls."""
        allowed, reason = RateLimiter.check(job_id, max_runs, window_seconds)
        if allowed:
            RateLimiter.record_trigger(job_id)
        return allowed, reason

    @staticmethod
    def remaining(job_id: int | str, max_runs: int = DEFAULT_MAX_RUNS, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> int:
        """How many more triggers are allowed in the current window."""
        key = str(job_id)
        now = time.monotonic()
        cutoff = now - window_seconds
        active = [t for t in _run_timestamps.get(key, []) if t > cutoff]
        return max(0, max_runs - len(active))
