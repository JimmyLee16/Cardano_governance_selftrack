"""Debug: test IPFS fetch with a real meta_url from Koios."""
from helpers import fetch_ipfs_metadata, fetch_json, IPFS_GATEWAY

# Test URLs from Koios
test_urls = [
    "https://most-brass-sun.quicknode-ipfs.com/ipfs/QmRcQjh3FQNAEkATTQhVjDgaA9zNCQkXKEKXMPtF2CkDdw",
    "https://most-brass-sun.quicknode-ipfs.com/ipfs/QmWSMH4FRfAd8WjzwQDa9XDn4QRXdVM9vHCBCyijL4Vxjf",
    "https://most-brass-sun.quicknode-ipfs.com/ipfs/QmQVvvKMhGex9qJFaCVtuomQMYWrCzs8PKPEdYdwFkiUv4",
]

print(f"IPFS_GATEWAY = {IPFS_GATEWAY}")
print()

for url in test_urls:
    print(f"Testing: {url}")
    try:
        # Direct fetch
        data = fetch_json(url, timeout=30)
        print(f"  Raw response type: {type(data)}")
        if isinstance(data, dict):
            print(f"  Keys: {list(data.keys())}")
            body = data.get("body", data)
            if isinstance(body, dict):
                print(f"  body keys: {list(body.keys())}")
                print(f"  body.comment: {body.get('comment', 'N/A')[:100] if body.get('comment') else 'None'}")
                print(f"  body.rationale: {body.get('rationale', 'N/A')[:100] if body.get('rationale') else 'None'}")
            print(f"  root comment: {str(data.get('comment', ''))[:100]}")
            print(f"  root rationale: {str(data.get('rationale', ''))[:100]}")
        else:
            print(f"  Data: {str(data)[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # Now test via fetch_ipfs_metadata
    comment = fetch_ipfs_metadata(url, voter_role="DRep")
    print(f"  fetch_ipfs_metadata result: {repr(comment[:200])}")
    print()

# Also test with ipfs:// prefix
print("Testing ipfs:// prefix:")
comment = fetch_ipfs_metadata("ipfs://QmRcQjh3FQNAEkATTQhVjDgaA9zNCQkXKEKXMPtF2CkDdw", voter_role="DRep")
print(f"  Result: {repr(comment[:200])}")
