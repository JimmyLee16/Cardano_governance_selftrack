// sync_drep_list.js
// Sync DRep list from Blockfrost → PostgreSQL
// Equivalent to sync_drep_list.py
//
// Blockfrost: GET /api/v0/governance/dreps (paginated)
// Target: drep_list table

require('dotenv').config();
const fetch = require('node-fetch');
const crypto = require('crypto');
const { pgConnect, pgUpsertBatch, info, warn } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const BLOCKFROST_KEY = process.env.BLOCKFROST_PROJECT_ID;
const DATABASE_URL = process.env.DATABASE_URL;
if (!BLOCKFROST_KEY || !DATABASE_URL) {
  console.error('❌ Thiếu BLOCKFROST_PROJECT_ID hoặc DATABASE_URL trong .env');
  process.exit(1);
}

const BLOCKFROST_BASE = 'https://cardano-mainnet.blockfrost.io/api/v0';
const BATCH_SIZE = 25;
const API_DELAY = 500; // ms

const COLUMNS = TABLE_COLUMNS.drep_list;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
}

async function blockfrostGet(endpoint, params = {}) {
  const url = new URL(`${BLOCKFROST_BASE}/${endpoint}`);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }
  const res = await fetch(url.toString(), {
    headers: { project_id: BLOCKFROST_KEY },
  });
  if (!res.ok) {
    throw new Error(`Blockfrost ${endpoint} → HTTP ${res.status}`);
  }
  return res.json();
}

async function blockfrostGetAllPages(endpoint, count = 100, maxPages = 100) {
  const all = [];
  for (let page = 1; page <= maxPages; page++) {
    const data = await blockfrostGet(endpoint, { page, count });
    if (!data || data.length === 0) break;
    all.push(...data);
    if (data.length < count) break;
    await sleep(API_DELAY);
  }
  return all;
}

async function syncDrepList() {
  info('=== Sync: drep_list (Blockfrost → PostgreSQL) ===');

  const client = await pgConnect();

  try {
    // 1. Fetch from Blockfrost
    info('[drep_list] Fetching from Blockfrost...');
    const raw = await blockfrostGetAllPages('governance/dreps', 100, 100);
    info(`[drep_list] Got ${raw.length} DReps from Blockfrost`);

    // 2. Transform (dedup by drep_id)
    const seen = new Set();
    const rows = [];
    for (const d of raw) {
      const did = d.drep_id;
      if (!did || seen.has(did)) continue;
      seen.add(did);
      rows.push({
        id: genUuid(),
        drep_id: did,
        created_at: nowIso(),
        updated_at: nowIso(),
      });
    }
    info(`[drep_list] Transformed ${rows.length} rows`);

    // 3. Upsert to PostgreSQL in batches
    info(`[drep_list] Upserting to PostgreSQL (batch=${BATCH_SIZE})...`);
    let inserted = 0;
    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      try {
        inserted += await pgUpsertBatch(client, 'drep_list', COLUMNS, batch, {
          conflict_cols: ['drep_id'],
          preserve_cols: ['id'],
          do_update: true,
        });
      } catch (e) {
        warn(`[drep_list] Error at batch ${i}: ${e.message}`);
      }
    }
    info(`[drep_list] Inserted ${inserted}/${rows.length}`);

    const cntRes = await client.query('SELECT count(*)::int as cnt FROM drep_list');
    info(`[drep_list] Row count: ${cntRes.rows[0].cnt}`);
    return cntRes.rows[0].cnt;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  syncDrepList().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncDrepList };