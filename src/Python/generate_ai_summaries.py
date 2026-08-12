"""Generate AI summaries + extract budget_requested for proposals via any OpenAI-compatible API.
Updates abstract_summary and budget_requested in PostgreSQL.

Works with: OpenAI, Azure OpenAI, NIM, Groq, Together, OpenRouter, Ollama, vLLM, LM Studio, etc.
Configure via env vars: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL.

Usage:
    python generate_ai_summaries.py --dry-run    # preview (default, all rows)
    python generate_ai_summaries.py --apply       # write to DB (all rows, overwrite)
    python generate_ai_summaries.py --apply --skip-existing   # only rows where fields are NULL

Flags:
    --skip-existing : Skip rows that already have BOTH abstract_summary AND budget_requested.
                      Only process rows missing at least one of them.
                      Use this for incremental runs after new proposals are synced.
"""

import sys
import os
import time
import json
import re
import requests
import psycopg2
from datetime import datetime, timezone

# Force UTF-8 on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from helpers import pg_connect, get_logger
from config import API_DELAY

# ── OpenAI-compatible API Config (from env) ────────────────────────────
# Defaults match OpenAI's public API; override for other providers.
#   OpenAI:       OPENAI_BASE_URL=https://api.openai.com/v1  OPENAI_MODEL=gpt-4o-mini
#   NIM:          OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1  OPENAI_MODEL=nvidia/nemotron-3-ultra-550b-a55b
#   Ollama:       OPENAI_BASE_URL=http://localhost:11434/v1  OPENAI_MODEL=llama3.1
#   vLLM:         OPENAI_BASE_URL=http://localhost:8000/v1   OPENAI_MODEL=<served-model>
#   Groq:         OPENAI_BASE_URL=https://api.groq.com/openai/v1  OPENAI_MODEL=llama-3.3-70b-versatile
#   Together:     OPENAI_BASE_URL=https://api.together.xyz/v1    OPENAI_MODEL=meta-llama/Llama-3-70b-chat-hf
#   OpenRouter:   OPENAI_BASE_URL=https://openrouter.ai/api/v1  OPENAI_MODEL=anthropic/claude-3.5-sonnet
API_KEY    = os.environ.get("OPENAI_API_KEY", "")
API_BASE   = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_MODEL  = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
API_URL    = f"{API_BASE}/chat/completions"

# Skip non-governance proposals
SKIP_PREFIXES = ("final_verify_v3_",)

def is_skippable(pid):
    if not pid:
        return False
    return any(pid.lower().startswith(p) for p in SKIP_PREFIXES)


def generate_summary_and_budget(title, abstract, api_key, retries=3):
    """Call OpenAI-compatible chat completions API to generate summary + extract budget.
    Returns dict: {"summary": str, "budget_requested": float|None}
    """
    if not abstract or len(abstract.strip()) < 20:
        return None

    # Truncate abstract to ~3000 chars to save tokens
    abstract_trunc = abstract[:3000]
    if len(abstract) > 3000:
        abstract_trunc += "..."

    prompt = f"""Analyze this Cardano governance proposal and return a JSON object.

Title: {title}

Abstract:
{abstract_trunc}

Return a JSON object with exactly these fields:
{{
  "summary": "200-400 character plain text summary. Include WHO proposes, WHAT they request, WHY it matters. Do NOT start with 'This proposal'. No markdown.",
  "budget_requested": <number in ADA, or null>
}}

For budget_requested:
- Extract the specific ADA amount the proposal requests from the Treasury
- Examples: "requests 500,000 ADA" → 500000, "₳9,832,979" → 9832979, "Withdraw 120,000,000 ada" → 120000000, "10M ADA" → 10000000
- If the proposal sets a Net Change Limit, use that amount
- If no specific budget amount is mentioned, return null
- Return ONLY the number (in ADA, not lovelace), no currency symbol or unit

Return ONLY the JSON object, no other text."""

    payload = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": "You are a JSON-only responder. Output ONLY a valid JSON object. No reasoning, no markdown, no explanation. Just the JSON."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(retries):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=90)
            if r.status_code == 429 or r.status_code == 503:
                wait = 5 * (attempt + 1)
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Parse JSON from response — model may wrap in ```json blocks
            # Try direct parse first
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block or mixed text
                # Find first { and last }
                match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        # Try removing markdown fences
                        cleaned = content.replace("```json", "").replace("```", "").strip()
                        result = json.loads(cleaned)
                else:
                    raise

            summary = (result.get("summary") or "").strip()
            budget = result.get("budget_requested")

            # Clean summary
            if summary:
                # Truncate to 500 chars max (DB column constraint)
                if len(summary) > 500:
                    summary = summary[:497] + "..."

            # Clean budget
            if budget is not None:
                try:
                    budget = float(budget)
                    if budget <= 0:
                        budget = None
                except (ValueError, TypeError):
                    budget = None

            return {"summary": summary, "budget_requested": budget}

        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
            else:
                raise
    return None


def get_proposals_needing_update(conn, skip_existing=False):
    """Get proposals that need summary and/or budget extraction.
    If skip_existing=True, only return rows where abstract_summary IS NULL OR budget_requested IS NULL.
    Returns: list of (proposal_id, title, abstract, has_summary, has_budget)
    """
    query = """
        SELECT proposal_id, title, abstract,
               (abstract_summary IS NOT NULL AND abstract_summary != '') AS has_summary,
               (budget_requested IS NOT NULL) AS has_budget
        FROM proposals
        WHERE abstract IS NOT NULL AND abstract != ''
    """
    if skip_existing:
        query += "  AND (abstract_summary IS NULL OR abstract_summary = '' OR budget_requested IS NULL)\n"
    query += "  ORDER BY proposal_id"
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def update_db(conn, proposal_id, summary, budget, has_summary, has_budget, dry_run, logger):
    """Update abstract_summary and/or budget_requested in PostgreSQL.
    Only updates fields that are currently NULL/empty (skip existing logic per-field).
    Returns (status, conn) — conn may be reconnected if SSL dropped.
    """
    if dry_run:
        updates = []
        if summary and not has_summary:
            updates.append("summary")
        if budget is not None and not has_budget:
            updates.append(f"budget={budget:,.0f}")
        return "would_update" if updates else "skip", conn

    sets = []
    params = []
    if summary and not has_summary:
        sets.append("abstract_summary = %s")
        params.append(summary)
    if budget is not None and not has_budget:
        sets.append("budget_requested = %s")
        params.append(budget)

    if not sets:
        return "skip", conn

    sets.append("updated_at = %s")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(proposal_id)

    for attempt in range(3):
        try:
            if conn.closed:
                logger.info(f"  Reconnecting to DB (attempt {attempt+1})...")
                conn = pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE proposals SET {', '.join(sets)} WHERE proposal_id = %s",
                    params
                )
            conn.commit()
            return "updated", conn
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            if attempt < 2:
                logger.warning(f"  DB retry {attempt+1} for {proposal_id[:40]}: {e}")
                time.sleep(2)
                try:
                    conn = pg_connect()
                except Exception:
                    pass
            else:
                logger.error(f"  DB update failed for {proposal_id}: {e}")
                return "error", conn
    return "error", conn


def main():
    dry_run = "--apply" not in sys.argv
    skip_existing = "--skip-existing" in sys.argv

    mode = "DRY-RUN" if dry_run else "APPLY"
    scope = "NULL-only (skip existing)" if skip_existing else "ALL (overwrite)"

    logger = get_logger()
    logger.info("=" * 60)
    logger.info(f"  AI Summary + Budget Generation [{mode}] → PostgreSQL")
    logger.info(f"  API: {API_BASE}")
    logger.info(f"  Model: {API_MODEL}")
    logger.info(f"  Scope: {scope}")
    logger.info("=" * 60)

    # Check API key
    if not API_KEY:
        logger.error("OPENAI_API_KEY not set in environment")
        sys.exit(1)
    logger.info(f"API key loaded: {API_KEY[:12]}...")

    # 1. Get proposals needing update
    conn = pg_connect()
    logger.info("\nConnected to PostgreSQL")
    proposals = get_proposals_needing_update(conn, skip_existing=skip_existing)
    if skip_existing:
        logger.info(f"Proposals needing summary/budget (NULL only): {len(proposals)}")
    else:
        logger.info(f"Proposals with abstract: {len(proposals)}")

    # Filter skippable
    proposals = [(pid, title, abstract, hs, hb) for pid, title, abstract, hs, hb in proposals if not is_skippable(pid)]
    logger.info(f"After filtering test proposals: {len(proposals)}")

    if not proposals:
        logger.info("Nothing to process. Exiting.")
        conn.close()
        return

    # 2. Generate + update
    stats = {
        "generated": 0, "failed": 0, "skipped_no_abstract": 0,
        "summary_updated": 0, "budget_updated": 0, "budget_null": 0,
        "db_updated": 0, "db_error": 0, "db_skip": 0,
    }

    for i, (pid, title, abstract, has_summary, has_budget) in enumerate(proposals, 1):
        display_title = (title or pid)[:50]
        needs_summary = not has_summary
        needs_budget = not has_budget
        logger.info(f"\n[{i}/{len(proposals)}] {display_title}...")
        logger.info(f"  Needs: {'summary ' if needs_summary else ''}{'budget' if needs_budget else ''}")

        # Generate summary + budget
        try:
            result = generate_summary_and_budget(title or pid, abstract, API_KEY)
        except Exception as e:
            logger.error(f"  API call failed: {e}")
            stats["failed"] += 1
            time.sleep(2)
            continue

        if not result:
            logger.warning(f"  No result generated (abstract too short?)")
            stats["skipped_no_abstract"] += 1
            continue

        summary = result.get("summary", "")
        budget = result.get("budget_requested")

        stats["generated"] += 1
        if summary:
            logger.info(f"  Summary ({len(summary)} chars): {summary[:80]}...")
        if budget is not None:
            logger.info(f"  Budget: {budget:,.0f} ADA")
        else:
            logger.info(f"  Budget: null (no amount found)")

        # Track what will be updated
        if summary and needs_summary:
            stats["summary_updated"] += 1
        if budget is not None and needs_budget:
            stats["budget_updated"] += 1
        elif budget is None and needs_budget:
            stats["budget_null"] += 1

        # Update DB
        res, conn = update_db(conn, pid, summary, budget, has_summary, has_budget, dry_run, logger)
        if res == "updated":
            stats["db_updated"] += 1
            logger.info(f"  DB: updated")
        elif res == "would_update":
            stats["db_updated"] += 1
            logger.info(f"  DB: would_update")
        elif res == "skip":
            stats["db_skip"] += 1
            logger.info(f"  DB: skip (already has data)")
        else:
            stats["db_error"] += 1

        # Rate limit: wait between API calls
        if i < len(proposals):
            time.sleep(1)

        # Progress
        if i % 10 == 0:
            logger.info(f"  --- Progress: {i}/{len(proposals)} ---")

    # 3. Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"  Final Summary [{mode}]")
    logger.info(f"{'='*60}")
    logger.info(f"Total proposals processed: {len(proposals)}")
    logger.info(f"  API calls succeeded:  {stats['generated']}")
    logger.info(f"  API calls failed:     {stats['failed']}")
    logger.info(f"  Skipped (no abstract):{stats['skipped_no_abstract']}")
    logger.info(f"  Summaries to update:  {stats['summary_updated']}")
    logger.info(f"  Budgets to update:    {stats['budget_updated']}")
    logger.info(f"  Budgets null (no $):  {stats['budget_null']}")
    logger.info(f"  DB updated:           {stats['db_updated']}")
    logger.info(f"  DB skipped:           {stats['db_skip']}")
    logger.info(f"  DB errors:            {stats['db_error']}")

    conn.close()
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
