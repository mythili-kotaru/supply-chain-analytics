import json

json_path = "/Users/mythilikotaru/Library/Application Support/Claude/local-agent-mode-sessions/b90beeaf-7833-4db3-8ec9-a924ae97391b/221f9e6c-ef0e-4bfb-82fd-de0703744deb/local_01e01eaa-3cd3-4711-96db-41398e37df5d.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find references inside history messages
history = data.get("history", [])
print(f"Total messages in history: {len(history)}")
for idx, msg in enumerate(history):
    text = msg.get("text", "")
    if "Day 13" in text or "Day 14" in text or "Day 12" in text or "curriculum" in text.lower():
        print(f"=== Message {idx} ({msg.get('sender')}) ===")
        # Print lines that contain Day 11, 12, 13, 14
        for line in text.split("\n"):
            if any(x in line for x in ["Day 11", "Day 12", "Day 13", "Day 14"]):
                print(line[:150])
