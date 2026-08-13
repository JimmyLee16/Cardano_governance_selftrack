# Build a Simple Governance Dashboard

A practical guide to turning the synced Cardano governance data into a simple dashboard for tracking and analysis. No heavy frontend framework required.

---

## 1. What data do you have?

After running the sync pipeline (`python sync_all.py`), PostgreSQL contains:

| Table | Content | Best used for |
|-------|---------|----------------|
| `proposals` | Title, status (active/done), `budget_requested`, `abstract_summary`, epochs | Proposal overview, budget tracking |
| `proposal_voting_summary` | Yes/No/Abstain vote counts + power per proposal (DRep / Pool / Committee) | Voting analysis |
| `drep_list` | Registry of DReps | Counts |
| `drep_info` | DRep stake (`amount`, ADA), name, url, active epoch | DRep power analysis |
| `drep_delegators` | Per-epoch delegation snapshots, `is_whale`, `delegation_type` | Delegation analysis |
| `ga_<md5>_<title>` | Individual votes (voter, role, vote, comment, `block_time`) — 1 table per proposal | Vote detail / timeline |

If you don't want to use PostgreSQL, the same tables can be exported to CSV (one file per table) and loaded straight into pandas.

---

## 2. Choose your tool

| Option | Effort | Best for | Notes |
|--------|--------|----------|-------|
| **Streamlit** (recommended) | ~1 file | Quick interactive dashboard | Pure Python, auto-reload, free hosting on Community Cloud |
| Jupyter + pandas/plotly | Notebook | Exploration / analysis | Great for ad-hoc queries |
| Flask/FastAPI + Chart.js | 2–3 files | Custom web app / embedding | More control, more work |
| Metabase / Superset | Config | No-code BI | Self-hosted, SQL-based questions + dashboards |

This guide uses **Streamlit** — the fastest path from data to dashboard.

---

## 3. Setup

```bash
cd src/Python
pip install streamlit pandas plotly psycopg2-binary python-dotenv
```

Put your dashboard file in the `UI/` folder:

```bash
mkdir -p ../../UI
cd ../../UI
```

Create `app.py` (full sample in §5). Run:

```bash
# from the UI/ folder — .env lives in src/Python/
python -m streamlit run app.py
```

To read env vars, load the same `.env` the sync scripts use:

```python
import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / "src" / "Python" / ".env")
DATABASE_URL = os.environ["DATABASE_URL"]
```

---

## 4. Recommended KPIs & charts

### KPIs (metric cards)
- **Total proposals** (`count(*)` from `proposals`)
- **Active vs done** (`status` distribution)
- **Total budget requested** (`sum(budget_requested)` for active proposals)
- **Number of DReps** (`count(*)` from `drep_info`)
- **Total live DRep stake** (`sum(amount)` from `drep_info`, ADA)
- **Whale delegators** (`count(*)` from `drep_delegators` where `is_whale`)

### Charts
1. **Proposals by status** — bar chart.
2. **Top proposals by budget** — horizontal bar of `budget_requested`.
3. **Vote mix per proposal** — grouped bars of `drep_yes/no/abstain_votes_cast`.
4. **Vote distribution (all)** — pie of total Yes / No / Abstain across summaries.
5. **Top DReps by stake** — bar of `drep_info.amount`.
6. **Delegators: regular vs script** — pie by `delegation_type`; plus whale share.
7. **Vote activity over time** — line of vote count by day, unioning all `ga_*` tables (or by `block_time` in the summary tables if present).

---

## 5. Sample Streamlit app (`UI/app.py`)

```python
import os
import pandas as pd
import psycopg2
import streamlit as st
import plotly.express as px

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / "src" / "Python" / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

st.set_page_config(page_title="Cardano Governance Dashboard", layout="wide")


@st.cache_data(ttl=300)
def query(sql: str, params=None) -> pd.DataFrame:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


# ── Helpers for dynamic ga_* tables ─────────────────────────────
@st.cache_data(ttl=300)
def ga_tables() -> list[str]:
    df = query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name LIKE 'ga_%'"
    )
    return df["table_name"].tolist()


def all_votes_df():
    tables = ga_tables()
    if not tables:
        return pd.DataFrame()
    cols = "block_time, voter_role, vote"
    parts = [f"SELECT {cols} FROM \"{t}\"" for t in tables]
    return query(" UNION ALL ".join(parts))


# ── Load data ───────────────────────────────────────────────────
proposals = query("SELECT * FROM proposals")
summary = query("SELECT * FROM proposal_voting_summary")
drep_info = query("SELECT * FROM drep_info")
delegators = query("SELECT * FROM drep_delegators WHERE is_current")

# ── KPIs ────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total proposals", len(proposals))
c2.metric("Active", int((proposals["status"] == "active").sum()))
c3.metric("Done", int((proposals["status"] == "done").sum()))
c4.metric(
    "Budget requested (ADA)",
    f"{proposals['budget_requested'].fillna(0).sum():,.0f}",
)
c5.metric("DReps", len(drep_info))
c6.metric("DRep stake (ADA)", f"{drep_info['amount'].fillna(0).sum():,.0f}")

# ── Charts ──────────────────────────────────────────────────────
st.subheader("Proposals by status")
fig = px.bar(proposals["status"].value_counts().reset_index(),
             x="status", y="count", title="Proposals by status")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Top proposals by requested budget")
top_budget = proposals.dropna(subset=["budget_requested"]).nlargest(15, "budget_requested")
fig = px.bar(top_budget, x="budget_requested", y="title", orientation="h",
             title="Top 15 by budget (ADA)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Vote mix per proposal (DRep)")
vote_df = summary.melt(
    id_vars=["proposal_id"],
    value_vars=["drep_yes_votes_cast", "drep_no_votes_cast", "drep_abstain_votes_cast"],
    var_name="vote", value_name="count",
).dropna(subset=["count"])
if not vote_df.empty:
    top = vote_df.groupby("proposal_id")["count"].sum().nlargest(10).index
    fig = px.bar(vote_df[vote_df["proposal_id"].isin(top)],
                 x="proposal_id", y="count", color="vote",
                 title="Votes by proposal (top 10)")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Top DReps by stake")
top_dreps = drep_info.nlargest(15, "amount")
fig = px.bar(top_dreps, x="amount", y="drep_id", orientation="h",
             title="Top 15 DReps by stake (ADA)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Delegators: type & whales")
if not delegators.empty:
    fig = px.pie(delegators, names="delegation_type", title="Regular vs script")
    st.plotly_chart(fig, use_container_width=True)
    whale_pct = delegators["is_whale"].mean() * 100
    st.metric("Whale share of delegators", f"{whale_pct:.1f}%")

st.subheader("Vote activity over time")
votes = all_votes_df()
if not votes.empty:
    votes["block_time"] = pd.to_datetime(votes["block_time"], errors="coerce")
    daily = votes.dropna(subset=["block_time"]).groupby(votes["block_time"].dt.date).size()
    st.plotly_chart(px.line(daily, title="Votes per day"), use_container_width=True)
else:
    st.info("No ga_* vote data yet — run `sync_vote_activities`.")
```

---

## 6. Useful raw SQL (for Metabase / Superset / ad-hoc)

```sql
-- Active proposals with budget
SELECT title, status, budget_requested
FROM proposals
WHERE status = 'active'
ORDER BY budget_requested DESC NULLS LAST;

-- Vote summary for one proposal
SELECT * FROM proposal_voting_summary WHERE proposal_id = 'gov_action...';

-- DReps ranked by stake
SELECT drep_id, given_name, amount
FROM drep_info
ORDER BY amount DESC
LIMIT 25;

-- Whale delegation snapshot for current epoch
SELECT drep_id, count(*) AS whales, sum(amount_ada) AS stake_ada
FROM drep_delegators
WHERE is_current AND is_whale
GROUP BY drep_id
ORDER BY stake_ada DESC;

-- Votes on a specific proposal
SELECT voter_role, vote, comment, block_time
FROM "ga_<md5>_<sanitized_id>"
ORDER BY block_time DESC
LIMIT 100;
```

---

## 7. Ideas & roadmap

- **Status tracking**: watch proposals flip `active → done` by epoch; alert on new proposals.
- **Budget analytics**: `budget_requested` vs approved funds; group by `proposal_type`.
- **DRep power shifts**: compare `amount`/`active_epoch` across epochs; detect inactive DReps.
- **Participation**: votes per epoch from `ga_*` `block_time`; active delegators per DRep.
- **Comments**: keyword/topic mining from `ga_*.comment` for sentiment.
- **Deploy**: push to Streamlit Community Cloud / Railway / Dockerfile; add a refresh button that calls `sync_all.py`.

---

> The dashboard reads the same PostgreSQL that the sync pipeline writes. If you prefer CSV/Excel as the source, export each table once (or after every sync) and load those files with `pd.read_csv` instead of `psycopg2`.