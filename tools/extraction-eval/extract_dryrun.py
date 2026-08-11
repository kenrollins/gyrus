"""M1 extraction dry-run v0 — real conference turns through the gateway."""
import json
import os
import sys
import urllib.request

SYSTEM = """You are the extraction pass of a personal AI agent's long-term memory system. \
The agent (Pip) serves one user, Ken. You receive a window of a real conversation and \
extract ONLY durable memories — things worth knowing 30+ days from now.

Classify each memory into exactly one tier:
- "factual": stable facts about the world, people, organizations, projects, events
- "preference": how Ken likes to work, communicate, or be helped
- "procedural": a method, command, workflow, or configuration that worked or failed
- "open_loop": an unresolved commitment, question, or follow-up either party owes

Discernment rules (the whole point — most of the conversation is NOT memory):
- SKIP pleasantries, one-off logistics, formatting requests bound to this single task,
  and the assistant's own generated prose unless Ken endorsed or corrected it.
- SKIP anything inside a [CONTEXT COMPACTION] block (background reference, not new).
- Each fact must be ATOMIC (one claim), SELF-CONTAINED (explicit names, no pronouns),
  and GROUNDED in the window (no outside knowledge, no embellishment).
- Deduplicate: repeated/duplicated messages yield one memory, not two.
- provenance: "ken_said" if Ken stated it; "observed" if evident from the exchange.

Return ONLY a JSON array (no markdown fences):
[{"tier": "...", "fact": "...", "entities": ["..."], "provenance": "..."}]
Return [] if nothing qualifies."""

window = json.load(open(sys.argv[1]))
convo = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in window["messages"])

body = {
    "model": sys.argv[2] if len(sys.argv) > 2 else "vllm/qwen-35b",
    "temperature": 0.0,
    "max_tokens": 2500,
    "chat_template_kwargs": {"enable_thinking": False},
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Conversation window (session {window['session']}):\n\n{convo}"},
    ],
}
req = urllib.request.Request(
    "http://10.0.13.201:4000/v1/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json",
             "Authorization": f"Bearer {os.environ['GYRUS_KEY']}"},
)
with urllib.request.urlopen(req, timeout=300) as r:
    resp = json.load(r)
text = resp["choices"][0]["message"]["content"].strip()
if text.startswith("```"):
    text = text.strip("`").lstrip("json").strip()
facts = json.loads(text)
print(f"model={body['model']}  extracted={len(facts)}  tokens={resp.get('usage',{}).get('total_tokens')}")
for f in facts:
    print(f"  [{f['tier']:10s}|{f.get('provenance','?'):8s}] {f['fact']}  {{{', '.join(f.get('entities', []))}}}")
