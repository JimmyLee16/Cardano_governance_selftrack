// sync_voting_summary.js
// Sync voting summary from Koios → PostgreSQL
// Equivalent to sync_voting_summary.py
//
// Koios: GET /api/v1/proposal_voting_summary?_proposal_id={id}
// Target: proposal_voting_summary table
// Reads proposal_ids from PostgreSQL proposals table.

require('dotenv').config();
const fetch = require('node-fetch');
const crypto = require('crypto');
const { pgConnect, pgUpsertBatch, info, warn, error } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('❌ Thiếu DATABASE_URL trong .env');
  process.exit(1);
}

const KOIOS_BASE = 'https://api.koios.rest/api/v1';
const BATCH_SIZE = 25;
const API_DELAY = 500;

const COLUMNS = TABLE_COLUMNS.proposal_voting_summary;

async function jsonGet(url, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

async function koiosGet(endpoint, params = {}) {
  const url = new URL(`${KOIOS_BASE}/${endpoint}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  return jsonGet(url.toString(), { Accept: 'application/json' });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
}

async function syncVotingSummary() {
  info('=== Sync: proposal_voting_summary (Koios → PostgreSQL) ===');

  const client = await pgConnect();

  try {
    // 1. Get active proposal IDs
    const propRes = await client.query(
      "SELECT proposal_id FROM proposals WHERE status IN ('voting','active') ORDER BY proposal_id"
    );
    let proposalIds = propRes.rows.map(r => r.proposal_id);
    proposalIds = proposalIds.filter(pid => !pid.startsWith('final_verify_v3'));
    info(`[voting_summary] Found ${proposalIds.length} active proposals`);

    let allRows = [];
    let errors = 0;

    for (let i = 0; i < proposalIds.length; i++) {
      const pid = proposalIds[i];
      try {
        const data = await koiosGet('proposal_voting_summary', { _proposal_id: pid });
        if (!data || !Array.isArray(data) || data.length === 0) continue;

        const d = data[0];
        allRows.push({
          id: genUuid(),
          proposal_id: pid,
          proposal_type: d.proposal_type,
          epoch_no: d.epoch_no,
          drep_yes_votes_cast: d.drep_yes_votes_cast || 0,
          drep_active_yes_vote_power: d.drep_active_yes_vote_power || 0,
          drep_yes_vote_power: d.drep_yes_vote_power || 0,
          drep_yes_pct: d.drep_yes_pct || 0,
          drep_no_votes_cast: d.drep_no_votes_cast || 0,
          drep_active_no_vote_power: d.drep_active_no_vote_power || 0,
          drep_no_vote_power: d.drep_no_vote_power || 0,
          drep_no_pct: d.drep_no_pct || 0,
          drep_abstain_votes_cast: d.drep_abstain_votes_cast || 0,
          drep_active_abstain_vote_power: d.drep_active_abstain_vote_power || 0,
          drep_abstain_vote_power: d.drep_abstain_vote_power || 0,
          drep_always_abstain_vote_power: d.drep_always_abstain_vote_power || 0,
          drep_always_no_confidence_vote_power: d.drep_always_no_confidence_vote_power || 0,
          pool_yes_votes_cast: d.pool_yes_votes_cast || 0,
          pool_active_yes_vote_power: d.pool_active_yes_vote_power || 0,
          pool_yes_vote_power: d.pool_yes_vote_power || 0,
          pool_yes_pct: d.pool_yes_pct || 0,
          pool_no_votes_cast: d.pool_no_votes_cast || 0,
          pool_active_no_vote_power: d.pool_active_no_vote_power || 0,
          pool_no_vote_power: d.pool_no_vote_power || 0,
          pool_no_pct: d.pool_no_pct || 0,
          pool_abstain_votes_cast: d.pool_abstain_votes_cast || 0,
          pool_active_abstain_vote_power: d.pool_active_abstain_vote_power || 0,
          pool_passive_always_abstain_votes_assigned: d.pool_passive_always_abstain_votes_assigned || 0,
          pool_passive_always_abstain_vote_power: d.pool_passive_always_abstain_vote_power || 0,
          pool_passive_always_no_confidence_votes_assigned: d.pool_passive_always_no_confidence_votes_assigned || 0,
          pool_passive_always_no_confidence_vote_power: d.pool_passive_always_no_confidence_vote_power || 0,
          committee_yes_votes_cast: d.committee_yes_votes_cast || 0,
          committee_yes_pct: d.committee_yes_pct || 0,
          committee_no_votes_cast: d.committee_no_votes_cast || 0,
          committee_no_pct: d.committee_no_pct || 0,
          committee_abstain_votes_cast: d.committee_abstain_votes_cast || 0,
          data_fetched_at: nowIso(),
          created_at: nowIso(),
          updated_at: nowIso(),
        });

        // Flush batch
        if (allRows.length >= BATCH_SIZE) {
          try {
            await pgUpsertBatch(client, 'proposal_voting_summary', COLUMNS, allRows, {
              conflict_cols: ['proposal_id'],
              preserve_cols: ['id', 'created_at'],
              do_update: true,
            });
          } catch (e) {
            error(`[voting_summary] Insert error: ${e.message}`);
          }
          allRows = [];
        }
      } catch (e) {
        errors++;
        if (errors <= 5) warn(`[voting_summary] Error for ${pid}: ${e.message}`);
      }

      if ((i + 1) % 10 === 0 || i === proposalIds.length - 1) {
        process.stdout.write(`\r  [voting_summary] ${i + 1}/${proposalIds.length}, errors=${errors}`);
      }
      await sleep(API_DELAY);
    }

    // Flush remaining
    if (allRows.length > 0) {
      try {
        await pgUpsertBatch(client, 'proposal_voting_summary', COLUMNS, allRows, {
          conflict_cols: ['proposal_id'],
          preserve_cols: ['id', 'created_at'],
          do_update: true,
        });
      } catch (e) {
        error(`[voting_summary] Final insert error: ${e.message}`);
      }
    }

    info(`\n[voting_summary] Done, errors=${errors}`);
    const cntRes = await client.query('SELECT count(*)::int as cnt FROM proposal_voting_summary');
    info(`[voting_summary] Row count: ${cntRes.rows[0].cnt}`);
    return cntRes.rows[0].cnt;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  syncVotingSummary().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncVotingSummary };