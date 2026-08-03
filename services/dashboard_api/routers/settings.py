"""
routers/settings.py
───────────────────
Endpoints to access system configuration and scheduler settings.
"""
import os
import yaml
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

@router.get("/settings/config", response_model=Dict[str, Any])
async def get_system_config():
    """
    Returns the current background scheduler configuration parsed from config.yaml.
    This allows the dashboard UI to display the active intervals for all AI agents.
    """
    try:
        if not os.path.exists(CONFIG_PATH):
            return {
                "inventory_interval_seconds": 60,
                "mape_interval_minutes": 5,
                "supplier_evaluation_interval_minutes": 60,
                "drift_agent_interval_hours": 24,
                "daily_digest_interval_hours": 24,
                "_source": "defaults (file not found)"
            }
            
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f) or {}
            
        config["_source"] = "config.yaml"
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")
