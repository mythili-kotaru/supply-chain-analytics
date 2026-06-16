import logging
import os
import httpx
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

LANGGRAPH_AGENT_URL = os.getenv("LANGGRAPH_AGENT_URL", "http://langgraph_agent:8004")

class AnalyticsQueryRequest(BaseModel):
    query: str
    role: str = "analyst"

class AnalyticsComparisonStats(BaseModel):
    mode: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    sql_generated: str
    sql_compiled: str
    wren_compiled: bool

class AnalyticsQueryResponse(BaseModel):
    sql_query: str
    results: List[Dict[str, Any]]
    insight: str
    result_count: int
    error: Optional[str] = None
    wren_stats: Optional[AnalyticsComparisonStats] = None
    ddl_stats: Optional[AnalyticsComparisonStats] = None
    token_saving_pct: Optional[float] = None

@router.post("/query", response_model=AnalyticsQueryResponse)
async def execute_analytics_query(request: AnalyticsQueryRequest):
    """
    Proxies a natural language query to the LangGraph agent service.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    try:
        # Use httpx to call the LangGraph agent service
        async with httpx.AsyncClient(timeout=60.0) as client:
            # We use the internal docker network URL
            resp = await client.post(
                f"{LANGGRAPH_AGENT_URL}/analytics/query", 
                json={"query": request.query, "role": request.role}
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Error executing analytics query proxy: {e}")
        raise HTTPException(status_code=500, detail=str(e))
