import os
import logging
import urllib.request
import json

logger = logging.getLogger("notifier")

# The webhook URL can be configured in .env or config.yaml
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def send_alert(message: str):
    """
    Sends a real-time alert to a Slack/Discord webhook.
    Fails silently if SLACK_WEBHOOK_URL is not configured.
    """
    if not SLACK_WEBHOOK_URL:
        return
        
    try:
        payload = {"text": f"🚨 *Supply Chain AI Alert*: {message}"}
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        # Fire and forget with a short timeout
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.getcode() != 200:
                logger.error(f"Failed to send Slack alert. Status: {response.getcode()}")
                
    except Exception as e:
        logger.error(f"Error sending Slack alert: {e}")
