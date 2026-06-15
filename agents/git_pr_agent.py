"""
agents/git_pr_agent.py
───────────────────────
Git PR Agent — automates code-level modifications, Git branch management, and PR creation.
"""

import os
import json
import subprocess
import time
import logging
import httpx

logger = logging.getLogger(__name__)

REPO_DIR = "/Users/mythilikotaru/Documents/supply-chain-ai"
CONFIG_FILE = os.path.join(REPO_DIR, "data/supplier_configs.json")


def update_supplier_json(supplier_id: str, lead_time_days: int, defect_rate: float) -> None:
    """Reads, updates, and writes back the supplier config JSON file."""
    if not os.path.exists(CONFIG_FILE):
        # Create empty template if missing
        configs = {}
    else:
        with open(CONFIG_FILE, "r") as f:
            configs = json.load(f)

    if supplier_id not in configs:
        configs[supplier_id] = {}

    configs[supplier_id]["lead_time_days"] = lead_time_days
    configs[supplier_id]["defect_rate"] = defect_rate

    with open(CONFIG_FILE, "w") as f:
        json.dump(configs, f, indent=2)
    logger.info(f"Updated {CONFIG_FILE} for supplier {supplier_id}")


async def create_github_pr(
    supplier_id: str,
    supplier_name: str,
    lead_time_days: int,
    defect_rate: float,
    queue=None
) -> dict:
    """
    Executes Git commands to create a branch, commit, push, and create a GitHub PR.
    """
    timestamp = int(time.time())
    branch_name = f"update-supplier-{supplier_id.lower()}-{timestamp}"
    commit_msg = f"config(supplier): update {supplier_name} ({supplier_id}) parameters"

    # Step 1: Update JSON file
    if queue:
        await queue.put({"event": "thought", "message": "Updating supplier configuration file..."})
    update_supplier_json(supplier_id, lead_time_days, defect_rate)

    # Step 2: Git commands
    try:
        if queue:
            await queue.put({"event": "thought", "message": f"Checking out new Git branch: {branch_name}"})
        
        # Stash current changes if any local changes might conflict, but main branch is clean.
        # Create new branch from main
        subprocess.run(["git", "checkout", "-b", branch_name], cwd=REPO_DIR, check=True, capture_output=True)

        if queue:
            await queue.put({"event": "thought", "message": f"Adding changes to index..."})
        subprocess.run(["git", "add", "data/supplier_configs.json"], cwd=REPO_DIR, check=True, capture_output=True)

        if queue:
            await queue.put({"event": "thought", "message": f"Committing changes: '{commit_msg}'"})
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_DIR, check=True, capture_output=True)

        if queue:
            await queue.put({"event": "thought", "message": f"Pushing branch to origin..."})
        # Note: This will push the branch using credentials already present on the user's system
        subprocess.run(["git", "push", "origin", branch_name], cwd=REPO_DIR, check=True, capture_output=True)

        # Restore original branch main locally to avoid leaving the repo in a dirty state
        subprocess.run(["git", "checkout", "main"], cwd=REPO_DIR, check=True, capture_output=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e.cmd} — stdout: {e.stdout.decode()} — stderr: {e.stderr.decode()}")
        # Safely try to recover back to main branch
        subprocess.run(["git", "checkout", "main"], cwd=REPO_DIR, capture_output=True)
        return {
            "success": False,
            "error": f"Git command failed: {e.stderr.decode()}",
            "pr_url": None
        }

    # Step 3: PR Creation Link
    pr_web_url = f"https://github.com/mythili-kotaru/supply-chain-analytics/pull/new/{branch_name}"
    
    # Try calling GitHub API if token exists
    github_token = os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    pr_api_url = None
    
    if github_token:
        if queue:
            await queue.put({"event": "thought", "message": "Authenticating with GitHub and raising PR..."})
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "title": commit_msg,
            "head": branch_name,
            "base": "main",
            "body": f"Automated configuration update for supplier **{supplier_name}** ({supplier_id}).\n\n### Changes proposed:\n- **Lead Time**: {lead_time_days} days\n- **Defect Rate**: {defect_rate * 100:.2f}%"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.github.com/repos/mythili-kotaru/supply-chain-analytics/pulls",
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )
                if resp.status_code == 211 or resp.status_code == 201:
                    pr_data = resp.json()
                    pr_web_url = pr_data.get("html_url", pr_web_url)
                    pr_api_url = pr_data.get("url")
                    if queue:
                        await queue.put({"event": "thought", "message": f"Successfully created GitHub PR: {pr_web_url}"})
                else:
                    logger.warning(f"GitHub API returned status {resp.status_code}: {resp.text}")
                    if queue:
                        await queue.put({"event": "thought", "message": f"GitHub API failed to create PR (status {resp.status_code}). Fallback web link generated."})
        except Exception as api_err:
            logger.error(f"Failed to post PR to GitHub API: {api_err}")
            if queue:
                await queue.put({"event": "thought", "message": "GitHub API offline or error. Fallback web link generated."})

    else:
        if queue:
            await queue.put({"event": "thought", "message": "No GITHUB_TOKEN configured. Fallback web link generated."})

    return {
        "success": True,
        "branch_name": branch_name,
        "commit_msg": commit_msg,
        "pr_url": pr_web_url,
        "pr_api_url": pr_api_url
    }
