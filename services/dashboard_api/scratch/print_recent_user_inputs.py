import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "USER_INPUT" and data.get("step_index") >= 3000:
                print(f"=== Step {data.get('step_index')} ({data.get('source')}) ===")
                print(data.get("content"))
                print("-" * 50)
        except Exception:
            pass
