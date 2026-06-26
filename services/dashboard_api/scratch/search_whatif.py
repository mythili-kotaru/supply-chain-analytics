import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            if "What-If" in content or "Scenario Sandbox" in content:
                print(f"=== Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) length={len(content)} ===")
                for l in content.split('\n'):
                    if any(x in l for x in ["What-If", "Sandbox", "Day 11", "Day 12", "Day 13"]):
                        print(f"  {l[:180]}")
                print("="*60)
        except Exception:
            pass
