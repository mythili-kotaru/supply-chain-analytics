import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from services.allocation_agent.main import app, tasks

@pytest.fixture
def mock_db_pool():
    # Create an AsyncMock for the connection pool and its connections
    pool_mock = AsyncMock()
    conn_mock = AsyncMock()
    
    # Setup acquire() to return our mocked connection in a context manager
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__.return_value = conn_mock
    pool_mock.acquire.return_value = acquire_ctx
    
    # Mock connection transaction
    transaction_ctx = AsyncMock()
    conn_mock.transaction.return_value = transaction_ctx
    
    return pool_mock, conn_mock

@pytest.fixture
def test_app(mock_db_pool):
    pool, _ = mock_db_pool
    # Inject the mocked pool into app state
    app.state.db = pool
    yield app
    # Clean up memory state
    tasks.clear()

@pytest.mark.anyio
async def test_agent_card(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/agent-card")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Allocation Agent"

@pytest.mark.anyio
async def test_create_task(test_app):
    payload = {
        "task_id": "test-task-1",
        "type": "allocation",
        "product_id": "SKU-123"
    }
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/tasks", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "test-task-1"
    assert data["status"] == "pending"
    assert "test-task-1" in tasks

@pytest.mark.anyio
async def test_get_task(test_app):
    # Pre-populate a task
    tasks["test-task-2"] = {"task_id": "test-task-2", "status": "in_progress"}
    
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/tasks/test-task-2")
        
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

@pytest.mark.anyio
async def test_get_missing_task(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/tasks/non-existent")
    assert response.status_code == 404

@pytest.mark.anyio
async def test_execute_direct(test_app, mock_db_pool):
    _, conn_mock = mock_db_pool
    
    payload = {
        "allocation_plan": [
            {
                "product_id": "SKU-1",
                "from_location": "East",
                "to_location": "West",
                "transfer_quantity": 50
            }
        ]
    }
    
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/execute-direct", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["executed"] == 1
    assert "Applied 1 of 1 transfers" in data["message"]
    
    # Verify DB was called to update inventory
    assert conn_mock.execute.call_count == 2
