import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
conn = sqlite3.connect("shoppilot.db")
rows = list(conn.execute(
    "SELECT id, product_type, product_title, description FROM product_ideas WHERE status='approved' ORDER BY id"
))
for r in rows:
    print(f"id={r[0]} type={r[1]}")
    print(f"  title: {r[2]}")
    desc = r[3] or ""
    print(f"  desc:  {desc[:150]}")
    print()
