"""
pytest shared fixtures for AEGIS test suite.
All fixtures are lightweight — no real Databricks / LLM calls.
"""
import os
import pytest
import yaml


# ── Force simulation mode so no real APIs are hit during tests ───────────────
os.environ.setdefault("SIMULATION_MODE", "true")
os.environ.setdefault("DATABRICKS_HOST", "https://fake.azuredatabricks.net")
os.environ.setdefault("DATABRICKS_TOKEN", "fake-token-for-tests")
os.environ.setdefault("DATABRICKS_USER_EMAIL", "test@example.com")


@pytest.fixture(scope="session")
def config() -> dict:
    """Load the real config.yaml (with env-var expansion) so tests match prod."""
    path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
    with open(path) as f:
        raw = f.read()
    raw = os.path.expandvars(raw)
    return yaml.safe_load(raw)


@pytest.fixture(scope="session")
def policy_config(config) -> dict:
    return config["policy"]


@pytest.fixture(scope="session")
def healing_config(config) -> dict:
    return config["healing"]


@pytest.fixture(scope="session")
def rca_config(config) -> dict:
    return config["rca"]


@pytest.fixture(scope="session")
def knowledge_config(config) -> dict:
    return config["knowledge_store"]
