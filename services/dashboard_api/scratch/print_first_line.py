import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if idx >= 10:
            break
        try:
            data = json.loads(line)
            print(f"Index {idx}: Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) content_len={len(data.get('content') or '')}")
        except Exception as e:
            print(f"Error parsing line {idx}: {e}")
