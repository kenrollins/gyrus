import json
import sqlite3

c = sqlite3.connect("/home/agent/.hermes/state.db")
sid = c.execute(
    "SELECT id FROM sessions WHERE id LIKE '20260805_114%'"
).fetchone()[0]
rows = c.execute(
    """SELECT role, content FROM messages
       WHERE session_id=? AND role IN ('user','assistant') AND content != ''
       ORDER BY CAST(timestamp AS INTEGER), id LIMIT 40""",
    (sid,),
).fetchall()
out = [{"role": r, "content": t[:1500]} for r, t in rows]
print(json.dumps({"session": sid, "messages": out}))
