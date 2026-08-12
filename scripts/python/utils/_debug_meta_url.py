"""Debug: check meta_url type and value."""
from helpers import koios_get

pid = "gov_action122wue2k65qq8gmpz795z2axt8apka6ay6xt3pwg8jxj5yfkujmtsqvlfpu7"
votes = koios_get("proposal_votes", params={"_proposal_id": pid})

for i, v in enumerate(votes[:5]):
    mu = v.get("meta_url")
    print(f"Vote {i+1}: meta_url={repr(mu)} type={type(mu)} bool={bool(mu)}")
