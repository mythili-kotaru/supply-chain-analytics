"""
routers/reports.py
──────────────────
Endpoints to access generated reports like the Daily Ops Digest.
"""
import os
import glob
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

# The data folder is mounted at /app/data inside the container
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

@router.get("/reports/daily-digest/latest", response_class=HTMLResponse)
async def get_latest_daily_digest():
    """
    Returns the most recently generated Daily Ops Digest HTML report.
    """
    try:
        # Find all daily_digest_*.html files
        pattern = os.path.join(DATA_DIR, "daily_digest_*.html")
        files = glob.glob(pattern)
        
        if not files:
            raise HTTPException(status_code=404, detail="No daily digest reports found.")
            
        # Sort by filename descending (which naturally sorts by date due to YYYYMMDD format)
        latest_file = sorted(files, reverse=True)[0]
        
        with open(latest_file, "r") as f:
            html_content = f.read()
            
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {str(e)}")
