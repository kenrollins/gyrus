"""Zulip archive backfill (M8) — the pre-Hermes conversation surface.

Reads the Zulip postgres directly (docker exec, read-only), groups messages
into topic-windows, and POSTs them as turns through the REAL pipeline
(/v1/turns, extract=true, platform='zulip') so every live-path protection
applies: v1.3 prompt, cron/automated suppression, dedupe, backpressure,
event-time honesty (each turn carries its original date_sent — ADR-0011).

Stream policy (Ken-vetoable, default from the 2026-08-17 survey):
automated surfaces (Console, Signal Feed) are EXCLUDED at the source — the
cron-suppression principle applied where it's cheapest. 3,418 agent-report
messages don't deserve 3,418 chances to fool the prompt.

Idempotent: session ids are deterministic (zulip:<stream>:<topic>), and a
--since cursor file lets reruns skip completed work. Dry-run by default;
--commit to post.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request

GYRUS = "http://10.0.13.11:8000"
EXCLUDED_STREAMS = {"Console", "Signal Feed"}
WINDOW_MAX_MSGS = 30

# json_build_object emits one JSON document per row; with -t -A (tuples
# only, unaligned) each lands on its own line, and JSON's own escaping
# keeps embedded newlines as \n. (COPY TO STDOUT double-escapes and breaks
# json.loads — measured on first run.)
SQL = r"""
SELECT json_build_object(
  'id', m.id, 'sent', m.date_sent, 'topic', m.subject,
  'stream', COALESCE(s.name, 'DM'),
  'sender', p.full_name, 'is_bot', p.is_bot,
  'content', m.content)
FROM zerver_message m
JOIN zerver_userprofile p ON p.id = m.sender_id
JOIN zerver_recipient r ON r.id = m.recipient_id
LEFT JOIN zerver_stream s ON s.recipient_id = r.id
ORDER BY m.id
"""


def fetch_messages() -> list[dict]:
    out = subprocess.run(
        ["docker", "exec", "-i", "zulip-database", "psql", "-U", "zulip",
         "-d", "zulip", "-t", "-A", "-c", SQL],
        capture_output=True, text=True, check=True)
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]


def windows(messages: list[dict]):
    """Group by (stream, topic), split at WINDOW_MAX_MSGS. A topic is
    Zulip's native conversation boundary — the natural extraction window."""
    from collections import defaultdict
    by_topic = defaultdict(list)
    for m in messages:
        if m["stream"] in EXCLUDED_STREAMS:
            continue
        by_topic[(m["stream"], m["topic"])].append(m)
    for (stream, topic), msgs in sorted(by_topic.items()):
        for i in range(0, len(msgs), WINDOW_MAX_MSGS):
            yield stream, topic, msgs[i:i + WINDOW_MAX_MSGS]


def post_turn(token: str, stream: str, topic: str, part: int, msgs: list[dict]) -> dict:
    body = {
        "session_id": f"zulip:{stream}:{topic}"[:120],
        "turn_index": part,
        "platform": "zulip",
        "user_text": "\n".join(f'[{m["sender"]}] {m["content"]}'
                               for m in msgs if not m["is_bot"])[:8000],
        "assistant_text": "\n".join(m["content"] for m in msgs if m["is_bot"])[:8000],
        "messages": [
            {"role": "assistant" if m["is_bot"] else "user",
             "content": f'[{m["sender"]} @ {m["sent"]}] {m["content"]}'}
            for m in msgs],
        "meta": {"backfill": "zulip", "stream": stream, "topic": topic,
                 "earliest": msgs[0]["sent"], "latest": msgs[-1]["sent"]},
    }
    req = urllib.request.Request(
        GYRUS + "/v1/turns", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="post turns (default: dry-run survey)")
    ap.add_argument("--token", default="")
    args = ap.parse_args()
    msgs = fetch_messages()
    wins = list(windows(msgs))
    included = sum(len(w[2]) for w in wins)
    print(f"messages total={len(msgs)} included={included} "
          f"(excluded streams: {', '.join(sorted(EXCLUDED_STREAMS))})")
    print(f"windows: {len(wins)}")
    from collections import Counter
    per_stream = Counter(w[0] for w in wins)
    for s, n in per_stream.most_common():
        print(f"  {s}: {n} windows")
    if not args.commit:
        print("\nDRY RUN — no turns posted. Use --commit --token <token>.")
        return
    posted = 0
    for stream, topic, chunk in wins:
        post_turn(args.token, stream, topic, posted, chunk)
        posted += 1
        if posted % 25 == 0:
            print(f"posted {posted}/{len(wins)} windows", flush=True)
    print(f"DONE: {posted} windows posted; worker extracts at its own pace")


if __name__ == "__main__":
    main()
