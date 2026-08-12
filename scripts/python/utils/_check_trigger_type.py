"""Check actual trigger type in DB and verify proposal count."""
import psycopg2
from config import NEON_CONN

conn = psycopg2.connect(NEON_CONN)
cur = conn.cursor()

# 1. Check trigger type
cur.execute("""
    SELECT tgname, tgtype, tgenabled, pg_get_triggerdef(oid)
    FROM pg_trigger
    WHERE tgrelid = 'proposals'::regclass AND NOT tgisinternal
    ORDER BY tgname
""")
triggers = cur.fetchall()
print("=== Triggers on proposals table ===")
for t in triggers:
    print(f"  {t[0]}: type={t[1]}, enabled={t[2]}")
    print(f"    def: {t[3]}")
print()

# 2. Exact proposal count
cur.execute("SELECT count(*) FROM proposals")
total = cur.fetchone()[0]
print(f"Total proposals: {total}")

# 3. Count by activities_table_name status
cur.execute("SELECT count(*) FROM proposals WHERE activities_table_name IS NOT NULL")
registered = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM proposals WHERE activities_table_name IS NULL")
unregistered = cur.fetchone()[0]
print(f"  With activities_table_name: {registered}")
print(f"  Without activities_table_name (NULL): {unregistered}")
print()

# 4. Count proposals that have NO matching ga_* table at all
cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename LIKE 'ga_%'
""")
all_ga = {r[0] for r in cur.fetchall()}

import re, hashlib
cur.execute("SELECT proposal_id FROM proposals")
pids = [r[0] for r in cur.fetchall()]

no_table = []
has_table = []
for pid in pids:
    sanitized = re.sub(r"[^a-zA-Z0-9]", "", pid)[:40]
    expected = f"ga_{hashlib.md5(pid.encode()).hexdigest()[:10]}_{sanitized}"
    if expected in all_ga:
        has_table.append((pid, expected))
    else:
        no_table.append(pid)

print(f"Proposals with matching ga_* table in DB: {len(has_table)}")
print(f"Proposals with NO ga_* table at all: {len(no_table)}")
if no_table:
    print("  (These need ga_* table creation)")
    for p in no_table[:10]:
        print(f"    - {p[:60]}...")
    if len(no_table) > 10:
        print(f"    ... and {len(no_table) - 10} more")

conn.close()
