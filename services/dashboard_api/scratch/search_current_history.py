import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            # Only look at USER_INPUT or SYSTEM messages
            if data.get("type") in ["USER_INPUT", "SYSTEM_INSTRUCTIONS"] or data.get("source") in ["USER_EXPLICIT", "SYSTEM"]:
                if any(x in content for x in ["Day 11", "Day 12", "Day 13", "Day 14", "Day 15"]):
                    print(f"=== Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) length={len(content)} ===")
                    # print lines matching Day 11/12/13/14/15
                    for l in content.split('\n'):
                        if any(x in l for x in ["Day 11", "Day 12", "Day 13", "Day 14", "Day 15"]):
                            print(f"  {l[:180]}")
        except Exception:
            pass
