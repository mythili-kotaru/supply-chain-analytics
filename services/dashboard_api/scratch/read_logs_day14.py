import json
import re

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"
pattern = re.compile(r'\bDay\s+14\b', re.IGNORECASE)

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content") or ""
            source = data.get("source") or ""
            type_ = data.get("type") or ""
            
            if pattern.search(content):
                # Filter out scripts
                if "import json" in content or "zipfile" in content or "xml.etree" in content:
                    continue
                print(f"=== Step {data.get('step_index')} (Source: {source}, Type: {type_}) ===")
                print(content)
                print("-" * 80)
        except Exception:
            pass
