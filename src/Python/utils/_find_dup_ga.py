import psycopg2
import re
from config import DATABASE_URL

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Get all ga_* table names
cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename LIKE 'ga_%'
    ORDER BY tablename
""")
tables = [r[0] for r in cur.fetchall()]

# Group by proposal_id suffix
groups = {}
for t in tables:
    m = re.match(r'^ga_[0-9a-f]{10}_(.+)$', t)
    if m:
        suffix = m.group(1)
        groups.setdefault(suffix, []).append(t)

dups = {k: v for k, v in groups.items() if len(v) > 1}

print(f"Total ga_* tables: {len(tables)}")
print(f"Unique proposal_ids (by suffix): {len(groups)}")
print(f"Duplicate groups: {len(dups)}")
print(f"Extra tables from duplicates: {len(tables) - len(groups)}")
print()

# Only show summary of duplicates
if dups:
    print("=== DUPLICATE TABLES (same proposal_id, multiple ga_* tables) ===")
    for pid, tbls in sorted(dups.items()):
        print(f"  {pid}: {len(tbls)} tables")
        for t in tbls:
            print(f"    - {t}")
    print()

# Check proposals table registration
cur.execute("""
    SELECT proposal_id, activities_table_name
    FROM proposals
    WHERE activities_table_name IS NOT NULL
""")
prop_rows = cur.fetchall()
actual_tables = set(tables)
registered = set()
for pid, tbl_name in prop_rows:
    if tbl_name:
        registered.add(tbl_name)
        if tbl_name not in actual_tables:
            print(f"REGISTERED BUT MISSING IN DB: {pid} -> {tbl_name}")

unregistered = actual_tables - registered
print(f"Tables in DB but NOT registered in proposals.proposals: {len(unregistered)}")
if unregistered:
    for t in sorted(unregistered):
        print(f"  - {t}")

conn.close()