import json

json_path = "/Users/mythilikotaru/Library/Application Support/Claude/local-agent-mode-sessions/b90beeaf-7833-4db3-8ec9-a924ae97391b/221f9e6c-ef0e-4bfb-82fd-de0703744deb/local_01e01eaa-3cd3-4711-96db-41398e37df5d.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

prompt = data.get("systemPrompt") or ""
print("System Prompt length:", len(prompt))
if prompt:
    # Search for Day or Week in the system prompt
    for line in prompt.split("\n"):
        if any(x in line.lower() for x in ["day ", "week ", "curriculum", "syllabus", "schedule"]):
            print(line[:150])
