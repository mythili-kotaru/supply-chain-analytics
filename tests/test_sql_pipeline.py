import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage
from agents.sql_insights.pipeline import run_sql_insights

@pytest.fixture
def mock_db_pool():
    pool_mock = AsyncMock()
    conn_mock = AsyncMock()
    
    # Mock acquire() context manager
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__.return_value = conn_mock
    pool_mock.acquire.return_value = acquire_ctx
    
    # Mock transaction() context manager
    transaction_ctx = AsyncMock()
    conn_mock.transaction.return_value = transaction_ctx
    
    return pool_mock, conn_mock

@pytest.mark.anyio
@patch("agents.sql_insights.pipeline.sql_llm.ainvoke")
@patch("agents.sql_insights.pipeline.formatter_llm.ainvoke")
async def test_run_sql_insights_success(mock_formatter, mock_sql, mock_db_pool):
    pool, conn_mock = mock_db_pool
    
    # Mock Parser (first call to sql_llm)
    parser_response = AIMessage(content='{"query_type": "inventory", "filters": {}, "metrics": [], "sort": null, "limit": 10}')
    
    # Mock SQL Gen (second call to sql_llm)
    sql_gen_response = AIMessage(content="SELECT * FROM inventory LIMIT 10")
    
    mock_sql.side_effect = [parser_response, sql_gen_response]
    
    # Mock Database Fetch
    conn_mock.fetch.return_value = [
        {"product_id": "SKU-1", "stock_level": 100}
    ]
    
    # Mock Formatter
    mock_formatter.return_value = AIMessage(content="There is 100 stock for SKU-1.")
    
    result = await run_sql_insights("What is the stock for SKU-1?", "analyst", pool=pool)
    
    assert result["sql_query"] == "SELECT * FROM inventory LIMIT 10"
    assert result["insight"] == "There is 100 stock for SKU-1."
    assert len(result["results"]) == 1
    assert result["error"] is None

@pytest.mark.anyio
@patch("agents.sql_insights.pipeline.sql_llm.ainvoke")
async def test_run_sql_insights_blocked_query(mock_sql, mock_db_pool):
    pool, _ = mock_db_pool
    
    parser_response = AIMessage(content='{"query_type": "general"}')
    sql_gen_response = AIMessage(content="DROP TABLE inventory")
    mock_sql.side_effect = [parser_response, sql_gen_response]
    
    result = await run_sql_insights("Delete the inventory", "analyst", pool=pool)
    
    assert result["error"] is not None
    assert "blocked" in result["error"].lower() or "rejected" in result["error"].lower()
    assert result["results"] == []
