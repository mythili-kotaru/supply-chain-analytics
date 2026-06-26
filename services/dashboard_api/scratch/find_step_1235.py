import json

log_path = "/Users/mythilikotaru/.gemini/antigravity-ide/brain/0ce976cb-6642-4b5b-a395-a1b531a57154/.system_generated/logs/transcript.jsonl"

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if 1230 <= step <= 1240:
                print(f"=== Step {step} ({data.get('source')}, {data.get('type')}) ===")
                # Print keys
                print("Keys:", list(data.keys()))
                if "tool_calls" in data:
                    print("Tool Calls:", json.dumps(data["tool_calls"], indent=2))
                if "content" in data:
                    print("Content length:", len(data["content"]))
                    if len(data["content"]) < 1000:
                        print("Content:", data["content"])
                print("-" * 50)
        except Exception as e:
            pass
