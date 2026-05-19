import sys, json

lines = [
    "def extract(text):",
    "    if not text.startswith('{'):",
    "        start_idx = text.find('{')",
    "        end_idx = text.rfind('}')",
    "        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:",
    "            text = text[start_idx:end_idx+1]",
    "    return text",
    "",
    "print('Hello')"
]
with open("test.py", "w") as f:
    f.write("\n".join(lines))
