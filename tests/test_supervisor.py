import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage
from agents.supervisor import supervisor_node
from agents.state import SupplyChainState

@pytest.mark.anyio
@patch("agents.supervisor.supervisor_llm.ainvoke")
async def test_supervisor_routing_sql_insights(mock_ainvoke):
    # Mock the supervisor LLM response returning an intent
    mock_ainvoke.return_value = AIMessage(content='{"intent": "sql_insights", "reasoning": "User asked about revenue."}')
    
    state = SupplyChainState(user_query="What is the revenue for East region?", messages=[], history=[])
    result = await supervisor_node(state)
    
    assert result["next_action"] == "sql_insights"
    assert "Routing to sql_insights" in result["messages"][0].content

@pytest.mark.anyio
@patch("agents.supervisor.supervisor_llm.ainvoke")
async def test_supervisor_routing_allocation(mock_ainvoke):
    mock_ainvoke.return_value = AIMessage(content='{"intent": "allocation", "reasoning": "User wants to allocate stock."}')
    
    state = SupplyChainState(user_query="Allocate stock for SKU-5", messages=[], history=[])
    result = await supervisor_node(state)
    
    assert result["next_action"] == "allocation"

@pytest.mark.anyio
@patch("agents.supervisor.supervisor_llm.ainvoke")
async def test_supervisor_fallback(mock_ainvoke):
    # If LLM returns malformed JSON, it should fallback to sql_insights
    mock_ainvoke.return_value = AIMessage(content='Not JSON format')
    
    state = SupplyChainState(user_query="Hello", messages=[], history=[])
    result = await supervisor_node(state)
    
    assert result["next_action"] == "sql_insights"
