import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
count = 0
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "USER_INPUT":
                print(f"=== Step {data.get('step_index')} ({data.get('source')}) ===")
                print(data.get("content"))
                print("-" * 50)
                count += 1
                if count >= 10:
                    break
        except Exception:
            pass
