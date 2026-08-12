"""Check status distribution in proposals table."""
import psycopg2
from config import NEON_CONN

conn = psycopg2.connect(NEON_CONN)
cur = conn.cursor()

cur.execute("SELECT status, count(*) FROM proposals GROUP BY status ORDER BY count(*) DESC")
rows = cur.fetchall()
print("Status distribution in proposals table:")
for status, count in rows:
    print(f"  {status}: {count}")

print()
cur.execute("SELECT proposal_id, status, activities_table_name FROM proposals WHERE status NOT IN ('active','voting') ORDER BY status, proposal_id")
non_active = cur.fetchall()
print(f"Non-active/voting proposals: {len(non_active)}")
for pid, status, tbl in non_active[:20]:
    print(f"  [{status}] {pid[:60]}... -> {tbl}")
if len(non_active) > 20:
    print(f"  ... and {len(non_active) - 20} more")

conn.close()
