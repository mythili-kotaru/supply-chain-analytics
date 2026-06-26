import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("step_index") == 1238:
                print("Step 1238 JSON:")
                print(json.dumps(data, indent=2))
        except Exception as e:
            pass
