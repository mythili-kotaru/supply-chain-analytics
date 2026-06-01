import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Required for async tests
@pytest.fixture
def anyio_backend():
    return "asyncio"

# We can mock the DB pool globally or locally.
# Often it's best to mock asyncpg.create_pool and asyncpg.connect in individual tests
# or use a test database.

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Ensure tests don't accidentally connect to production DBs if env vars are missing"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    monkeypatch.setenv("ALLOCATION_AGENT_URL", "http://test-allocation")
    monkeypatch.setenv("REPLENISHMENT_AGENT_URL", "http://test-replenishment")
