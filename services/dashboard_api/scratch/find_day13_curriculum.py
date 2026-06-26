import json
import re

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            # Find steps where Day 13 is mentioned in USER_INPUT or CONVERSATION_HISTORY or where it has bullet points outlining Day 13.
            if "Day 13" in content:
                # Let's count how many times "Day 13" or "Day 14" occurs. If there are multiple occurrences in a list form, print it.
                if len(re.findall(r'Day\s+\d+', content)) > 3 and data.get("source") != "MODEL":
                    print(f"=== Step {data.get('step_index')} ({data.get('source')}, {data.get('type')}) length={len(content)} ===")
                    print(content)
                    print("="*60)
        except Exception:
            pass
