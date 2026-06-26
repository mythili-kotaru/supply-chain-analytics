import os
import glob
import json
import re

base_dir = "/Users/mythilikotaru/Library/Application Support/Claude/local-agent-mode-sessions/b90beeaf-7833-4db3-8ec9-a924ae97391b/221f9e6c-ef0e-4bfb-82fd-de0703744deb"

print(f"Scanning directory: {base_dir}")
pattern = re.compile(r'Day\s+(\d+)\b', re.IGNORECASE)

if os.path.exists(base_dir):
    files = glob.glob(os.path.join(base_dir, "local_*.json"))
    print(f"Found {len(files)} files.")
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
                json_str = json.dumps(data)
                # Find all mentions of Day 12, 13, 14
                found_days = set()
                for m in pattern.finditer(json_str):
                    day_num = int(m.group(1))
                    if day_num >= 11 and day_num <= 15:
                        found_days.add(day_num)
                if found_days:
                    print(f"File {os.path.basename(fp)} has references to days: {sorted(list(found_days))}")
                    # Let's search inside historical message text for "Day 13" or "Day 14"
                    history = data.get("history", [])
                    for msg in history:
                        text = msg.get("text", "")
                        if "Day 13" in text or "Day 14" in text:
                            print(f"  [Found text in message from {msg.get('sender')}]:")
                            for line in text.split("\n"):
                                if "Day 13" in line or "Day 14" in line or "Day 12" in line:
                                    print(f"    {line[:150]}")
        except Exception as e:
            print(f"Error scanning {fp}: {e}")
else:
    print("Directory does not exist.")
