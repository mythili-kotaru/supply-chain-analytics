import os
import glob

search_paths = ["/Users/mythilikotaru/Downloads", "/Users/mythilikotaru/Desktop", "/Users/mythilikotaru/Documents/supply-chain-ai"]

found = []
for base in search_paths:
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            # Skip node_modules or large dirs to prevent slowdown
            if any(x in root for x in ["node_modules", ".git", ".next"]):
                continue
            for f in files:
                if any(k in f.lower() for k in ["week6", "week_6", "week 6"]):
                    found.append(os.path.join(root, f))

print(f"Found {len(found)} files matching Week 6:")
for p in found:
    print(f"  - {p}")
