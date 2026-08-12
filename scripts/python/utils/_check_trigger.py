import psycopg2
from config import NEON_CONN

conn = psycopg2.connect(NEON_CONN)
cur = conn.cursor()

# Get trigger function definition
cur.execute("""
    SELECT pg_get_functiondef(oid) FROM pg_proc
    WHERE proname = 'create_proposal_activities_table'
""")
row = cur.fetchone()
if row:
    print("=== create_proposal_activities_table() function ===")
    print(row[0])

print("\n")

# Check how many proposals exist total
cur.execute("SELECT count(*) FROM proposals")
total_proposals = cur.fetchone()[0]
print(f"Total proposals in proposals table: {total_proposals}")

# Check how many have activities_table_name set
cur.execute("SELECT count(*) FROM proposals WHERE activities_table_name IS NOT NULL")
registered = cur.fetchone()[0]
print(f"Proposals with activities_table_name set: {registered}")

# Show some registered ones
cur.execute("""
    SELECT proposal_id, activities_table_name 
    FROM proposals 
    WHERE activities_table_name IS NOT NULL 
    LIMIT 25
""")
print("\n=== Registered activities_table_name in proposals ===")
for r in cur.fetchall():
    print(f"  {r[0]} -> {r[1]}")

conn.close()
