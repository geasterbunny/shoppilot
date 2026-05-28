import sqlite3
conn = sqlite3.connect("shoppilot.db")
conn.execute("UPDATE supplier_products SET image_id = NULL WHERE image_id IS NOT NULL")
conn.commit()
rows = list(conn.execute("SELECT id, idea_id, image_id FROM supplier_products"))
for r in rows:
    print(f"  id={r[0]} idea_id={r[1]} image_id={r[2]}")
print("done — all image_ids nulled")
