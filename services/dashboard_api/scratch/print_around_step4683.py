import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            step_idx = data.get('step_index')
            if step_idx is not None and 4670 <= step_idx <= 4685:
                print(f"=== Step {step_idx} ({data.get('source')}, {data.get('type')}) length={len(data.get('content') or '')} ===")
                content = data.get("content") or ""
                print(content[:500])
                print("-" * 50)
        except Exception:
            pass
