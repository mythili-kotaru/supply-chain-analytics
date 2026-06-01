import pytest
from unittest.mock import AsyncMock, patch
from agents.anomaly_detector import run_anomaly_scan

@pytest.fixture
def mock_db_conn():
    conn_mock = AsyncMock()
    return conn_mock

@pytest.mark.anyio
@patch("agents.anomaly_detector.asyncpg.connect")
async def test_run_anomaly_scan_empty(mock_connect, mock_db_conn):
    # Setup mock connection
    mock_connect.return_value = mock_db_conn
    
    # Mock all fetch calls to return empty lists (no anomalies found)
    mock_db_conn.fetch.return_value = []
    
    summary = await run_anomaly_scan("postgresql://fake:fake@localhost/db")
    
    # Verify the results
    assert summary["stock_drop"] == 0
    assert summary["demand_spike"] == 0
    assert summary["mape_regression"] == 0
    assert summary["total_new"] == 0
    
    # Ensure the connection was closed
    mock_db_conn.close.assert_called_once()

@pytest.mark.anyio
@patch("agents.anomaly_detector.asyncpg.connect")
async def test_run_anomaly_scan_with_stock_drop(mock_connect, mock_db_conn):
    mock_connect.return_value = mock_db_conn
    
    # We have 3 fetch calls in run_anomaly_scan:
    # 1. detect_stock_drops
    # 2. detect_demand_spikes
    # 3. detect_mape_regressions
    
    # Mock the return values for the 3 queries
    stock_drop_row = {
        "product_id": "SKU-1",
        "product_name": "Test Product",
        "location": "North",
        "stock_level": 20,
        "reorder_point": 100,
        "stock_pct_of_reorder": 20.0
    }
    
    mock_db_conn.fetch.side_effect = [
        [stock_drop_row], # Stock drops
        [],               # Demand spikes
        []                # MAPE regressions
    ]
    
    # Mock _already_flagged to return False
    mock_db_conn.fetchrow.return_value = None
    
    summary = await run_anomaly_scan("postgresql://fake:fake@localhost/db")
    
    assert summary["stock_drop"] == 1
    assert summary["total_new"] == 1
    
    # Verify the anomaly was inserted
    assert mock_db_conn.fetchrow.call_count >= 1 # First to check if already flagged, then to insert
