"""Debug: check raw Koios response for a sample proposal to see meta_url fields."""
import json
from helpers import koios_get

# Pick a proposal with votes
pid = "gov_action122wue2k65qq8gmpz795z2axt8apka6ay6xt3pwg8jxj5yfkujmtsqvlfpu7"
votes = koios_get("proposal_votes", params={"_proposal_id": pid})

print(f"Total votes: {len(votes)}")
print()

# Show first 5 votes with all fields
for i, v in enumerate(votes[:5]):
    print(f"--- Vote {i+1} ---")
    for k, val in v.items():
        print(f"  {k}: {val}")
    print()

# Count how many have meta_url
with_meta = [v for v in votes if v.get("meta_url")]
without_meta = [v for v in votes if not v.get("meta_url")]
print(f"Votes WITH meta_url: {len(with_meta)}")
print(f"Votes WITHOUT meta_url: {len(without_meta)}")

if with_meta:
    print("\nSample meta_url values:")
    for v in with_meta[:3]:
        print(f"  {v.get('meta_url')} (role={v.get('voter_role')})")
