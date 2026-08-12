"""Check expiration field type and values in proposals table."""
import psycopg2
from config import NEON_CONN

conn = psycopg2.connect(NEON_CONN)
cur = conn.cursor()

# Check column type
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'proposals' AND column_name IN ('expiration', 'epoch_no', 'status')
    ORDER BY column_name
""")
print("Column types:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} (nullable={r[2]})")

# Check sample values
cur.execute("SELECT proposal_id, expiration, epoch_no, status FROM proposals LIMIT 10")
print("\nSample values:")
for r in cur.fetchall():
    print(f"  pid={r[0][:40]}... expiration={r[1]} epoch_no={r[2]} status={r[3]}")

# Check expiration range
cur.execute("SELECT min(expiration), max(expiration), count(DISTINCT expiration) FROM proposals")
r = cur.fetchone()
print(f"\nExpiration range: min={r[0]}, max={r[1]}, distinct={r[2]}")

# Get current epoch from Koios
from helpers import koios_get
tip = koios_get("tip")
current_epoch = tip[0].get("epoch_no", 0)
print(f"\nCurrent epoch (Koios): {current_epoch}")

# How many proposals are expired?
cur.execute("SELECT count(*) FROM proposals WHERE expiration::integer <= %s", (current_epoch,))
expired = cur.fetchone()[0]
print(f"Expired proposals (expiration <= {current_epoch}): {expired}")

cur.execute("SELECT count(*) FROM proposals WHERE expiration::integer > %s", (current_epoch,))
not_expired = cur.fetchone()[0]
print(f"Active proposals (expiration > {current_epoch}): {not_expired}")

conn.close()
