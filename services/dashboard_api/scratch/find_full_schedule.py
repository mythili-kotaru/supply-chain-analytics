import json
import re

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
pattern = re.compile(r'Day\s+\d+[:\.\-]', re.IGNORECASE)

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            if pattern.search(content):
                if "import json" in content or "zipfile" in content:
                    continue
                # Print matches in this content
                lines = content.split('\n')
                printed_step = False
                for l in lines:
                    if pattern.search(l):
                        if not printed_step:
                            print(f"=== Step {data.get('step_index')} ({data.get('source')}) ===")
                            printed_step = True
                        print(f"  {l[:200]}")
        except Exception:
            pass
