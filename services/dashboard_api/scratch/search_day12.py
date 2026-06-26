import json
import re

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
pattern = re.compile(r'Day\s+12', re.IGNORECASE)

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            if pattern.search(content):
                print(f"=== Step {data.get('step_index')} ({data.get('source')}) ===")
                # Print lines containing the match
                lines = content.split('\n')
                for l in lines:
                    if pattern.search(l):
                        print(f"  {l}")
        except Exception as e:
            pass
