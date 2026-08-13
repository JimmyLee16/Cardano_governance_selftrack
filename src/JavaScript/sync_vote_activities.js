// sync_vote_activities.js
// Sync vote activities from Koios + IPFS → PostgreSQL ga_* tables
// Equivalent to sync_vote_activities.py
//
// Koios: GET /api/v1/proposal_votes?_proposal_id={id}
// IPFS: Fetch metadata for comment
// Target: ga_* tables (one per proposal) in PostgreSQL
// Reads proposals with activities_table_name from proposals table.

require('dotenv').config();
const fetch = require('node-fetch');
const crypto = require('crypto');
const { pgConnect, pgUpsertBatch, fetchIpfsMetadata, info, warn, error } = require('./helpers');
const { ga_table: GA_TABLE_COLUMNS } = require('./config');

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('❌ Missing DATABASE_URL in .env');
  process.exit(1);
}

const KOIOS_BASE = 'https://api.koios.rest/api/v1';
const BATCH_SIZE = 25;
const API_DELAY = 500; // ms

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
}

function toIso(blockTime) {
  if (typeof blockTime === 'number') {
    return new Date(blockTime * 1000).toISOString();
  }
  return String(blockTime);
}

async function koiosGet(endpoint, params = {}) {
  const url = new URL(`${KOIOS_BASE}/${endpoint}`);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }
  const res = await fetch(url.toString(), {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Koios ${endpoint} → HTTP ${res.status}`);
  }
  return res.json();
}

async function syncVoteActivities({ onlyActive = false } = {}) {
  info('=== Sync: vote_activities (Koios+IPFS → ga_* tables) ===');

  const client = await pgConnect();

  try {
    // 1. Get proposals with activities_table_name from PostgreSQL
    const q = onlyActive
      ? `SELECT proposal_id, activities_table_name FROM proposals
         WHERE activities_table_name IS NOT NULL
         AND status IN ('voting','active') ORDER BY proposal_id`
      : `SELECT proposal_id, activities_table_name FROM proposals
         WHERE activities_table_name IS NOT NULL ORDER BY proposal_id`;
    const res = await client.query(q);
    const proposals = res.rows
      .map(r => [r.proposal_id, r.activities_table_name])
      .filter(([pid]) => !String(pid).startsWith('final_verify_v3'));

    info(`[vote_activities] Found ${proposals.length} proposals with ga_* tables`);

    let totalVotes = 0;
    let errors = 0;
    let totalSkipped = 0;

    for (let idx = 0; idx < proposals.length; idx++) {
      const [pid, tableName] = proposals[idx];
      info(`\n  [${idx + 1}/${proposals.length}] ${pid} → ${tableName}`);

      try {
        // 2. Fetch votes from Koios
        const votes = await koiosGet('proposal_votes', { _proposal_id: pid });
        if (!votes || votes.length === 0) {
          info('    No votes found');
          continue;
        }
        info(`    Got ${votes.length} votes from Koios`);

        // 3. Check current row count + votes that already have comments
        const countRes = await client.query(`SELECT count(*)::int AS cnt FROM "${tableName}"`);
        const currentCount = countRes.rows[0].cnt;

        const existingWithComments = new Set();
        if (currentCount > 0) {
          const cRes = await client.query(
            `SELECT voter_id, block_time FROM "${tableName}" WHERE comment IS NOT NULL AND comment != ''`
          );
          for (const r of cRes.rows) {
            existingWithComments.add(`${r.voter_id}|${String(r.block_time)}`);
          }
        }

        if (currentCount === votes.length && existingWithComments.size >= votes.length) {
          info(`    Already up-to-date (${currentCount} rows, all have comments), skipping`);
          continue;
        }

        const newCount = votes.length - currentCount;
        if (currentCount < votes.length) {
          info(`    ${newCount} new votes to upsert (DB=${currentCount}, Koios=${votes.length})`);
        } else {
          info(`    Upserting ${votes.length} votes (DB=${currentCount}, Koios=${votes.length})`);
        }
        if (existingWithComments.size) {
          info(`    ${existingWithComments.size} votes already have comments (will skip IPFS)`);
        }

        // 4. Process votes
        const rows = [];
        let skipped = 0;
        for (const v of votes) {
          const btIso = toIso(v.block_time);
          const voterId = v.voter_id;
          const metaUrl = v.meta_url;

          // Skip IPFS fetch if vote already has comment in DB
          if (existingWithComments.has(`${voterId}|${btIso}`)) {
            skipped++;
            continue;
          }

          let comment = '';
          if (metaUrl) {
            comment = (await fetchIpfsMetadata(metaUrl, v.voter_role)) || '';
          }

          rows.push({
            id: genUuid(),
            block_time: btIso,
            voter_role: v.voter_role,
            voter_id: voterId,
            vote: v.vote,
            meta_url: metaUrl,
            comment,
            processed_at: nowIso(),
            created_at: nowIso(),
            updated_at: nowIso(),
          });
        }

        // 5. Insert in batches
        let inserted = 0;
        for (let i = 0; i < rows.length; i += BATCH_SIZE) {
          const batch = rows.slice(i, i + BATCH_SIZE);
          try {
            const batchCols = GA_TABLE_COLUMNS.filter(c => batch.every(r => c in r));
            inserted += await pgUpsertBatch(client, tableName, batchCols, batch, {
              conflict_cols: ['voter_id', 'block_time'],
              preserve_cols: ['id'],
              do_update: true,
            });
          } catch (e) {
            error(`    Insert error at batch ${i}: ${e.message}`);
          }
        }

        totalVotes += inserted;
        totalSkipped += skipped;
        info(`    Inserted ${inserted}/${rows.length}, skipped ${skipped}`);
      } catch (e) {
        errors++;
        error(`    Error: ${e.message}`);
      }

      await sleep(API_DELAY);
    }

    info(
      `\n[vote_activities] Total votes inserted: ${totalVotes}, skipped: ${totalSkipped}, errors: ${errors}`
    );
    return totalVotes;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  const onlyActive = process.argv.includes('--active-only');
  syncVoteActivities({ onlyActive }).catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncVoteActivities };