import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if idx >= 15:
            break
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            print(f"=== Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) length={len(content)} ===")
            if "curriculum" in content.lower() or "schedule" in content.lower() or "day" in content.lower():
                print(content[:2000])
                print("\n" + "="*40 + "\n")
        except Exception as e:
            pass
