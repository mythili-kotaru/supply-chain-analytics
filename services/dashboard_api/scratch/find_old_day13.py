import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            step_idx = data.get('step_index')
            if step_idx is not None and step_idx < 5000:
                content = data.get("content") or ""
                if "Day 13" in content or "Day 14" in content:
                    print(f"=== Step {step_idx} ({data.get('source')}, {data.get('type')}) ===")
                    for l in content.split('\n'):
                        if "Day 13" in l or "Day 14" in l:
                            print(f"  {l[:200]}")
        except Exception:
            pass
