import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"

found = 0
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            if "day 1" in content.lower() and "day 2" in content.lower():
                print(f"=== Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) ===")
                # Let's search for lists or markdown tables containing days
                lines = content.split('\n')
                for l in lines:
                    if any(x in l.lower() for x in ["day 1", "day 2", "day 3", "day 4", "day 5", "day 6", "day 7", "day 8", "day 9", "day 10", "day 11", "day 12", "day 13", "day 14"]):
                        print(l[:200])
                print("-" * 50)
                found += 1
                if found > 5:
                    break
        except Exception:
            pass
