// sync_drep_info.js
// Sync DRep info from Blockfrost → PostgreSQL (incremental)
// Equivalent to sync_drep_info.py
//
// Blockfrost: GET /api/v0/governance/dreps/{id} + /metadata
// Target: drep_info table
// Reads drep_id list from PostgreSQL drep_list table.

require('dotenv').config();
const fetch = require('node-fetch');
const crypto = require('crypto');
const { pgConnect, pgUpsertBatch, info, warn } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const BLOCKFROST_KEY = process.env.BLOCKFROST_PROJECT_ID;
const DATABASE_URL = process.env.DATABASE_URL;
if (!BLOCKFROST_KEY || !DATABASE_URL) {
  console.error('❌ Missing BLOCKFROST_PROJECT_ID or DATABASE_URL in .env');
  process.exit(1);
}

const BLOCKFROST_BASE = 'https://cardano-mainnet.blockfrost.io/api/v0';
const KOIOS_BASE = 'https://api.koios.rest/api/v1';
const API_DELAY = 500; // ms
const BATCH_SIZE = 25;
const DREPS_PER_RUN = 50;

const COLUMNS = TABLE_COLUMNS.drep_info;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
}

async function jsonGet(url, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`${url} → HTTP ${res.status}`);
  }
  return res.json();
}

async function blockfrostGet(endpoint) {
  const url = `${BLOCKFROST_BASE}/${endpoint}`;
  return jsonGet(url, { project_id: BLOCKFROST_KEY });
}

function normalize(val) {
  if (val && typeof val === 'object') {
    return val['@value'] || val.contentUrl;
  }
  return val;
}

function extractUris(body) {
  const uris = [];
  const refs = body.references;
  if (Array.isArray(refs)) {
    for (const ref of refs) {
      if (ref && typeof ref.uri === 'string' && ref.uri.startsWith('https://')) {
        uris.push(ref.uri);
      }
    }
  } else if (refs && typeof refs.uri === 'string' && refs.uri.startsWith('https://')) {
    uris.push(refs.uri);
  }
  return uris;
}

async function buildRow(did) {
  const drepInfo = await blockfrostGet(`governance/dreps/${did}`);
  let meta = {};
  try {
    meta = await blockfrostGet(`governance/dreps/${did}/metadata`);
  } catch (e) {
    warn(`[drep_info] Metadata fetch failed for ${did}: ${e.message}`);
  }

  const body = ((meta.json_metadata || {}).body) || {};

  const amountRaw = drepInfo.amount || '0';
  let amountAda = 0;
  try {
    amountAda = Math.round(parseInt(amountRaw, 10) * 1e-6 * 100) / 100;
  } catch (e) {
    amountAda = 0;
  }

  const row = {
    id: genUuid(),
    drep_id: did,
    amount: amountAda,
    active_epoch: drepInfo.active_epoch,
    last_active_epoch: drepInfo.last_active_epoch,
    url: meta.url,
    payment_address: normalize(body.paymentAddress),
    given_name: normalize(body.givenName),
    content_url: null,
    https_uris: extractUris(body).join(', ') || null,
    metadata_fetched_at: nowIso(),
    created_at: nowIso(),
    updated_at: nowIso(),
  };

  // Extract content_url from image
  const img = body.image;
  if (img && typeof img === 'object') {
    row.content_url = img.contentUrl || img['@value'];
  } else if (typeof img === 'string') {
    row.content_url = img;
  }

  return row;
}

async function syncDrepInfo({ drepsPerRun = DREPS_PER_RUN } = {}) {
  info('=== Sync: drep_info (Blockfrost → PostgreSQL, incremental) ===');

  const client = await pgConnect();

  try {
    // 1. Current epoch (Koios tip)
    let currentEpoch = 0;
    try {
      const tip = await jsonGet(`${KOIOS_BASE}/tip`, {
        Accept: 'application/json',
      });
      currentEpoch = tip && tip[0] ? tip[0].epoch_no || 0 : 0;
    } catch (e) {
      warn(`[drep_info] Failed to fetch tip, assuming epoch 0: ${e.message}`);
    }

    // 2. Full drep_id list from PostgreSQL drep_list
    const listRes = await client.query('SELECT drep_id FROM drep_list ORDER BY drep_id');
    const drepIds = listRes.rows.map(r => r.drep_id);

    // 3. Checkpoint: in-memory per-epoch (JS has no file checkpoint yet).
    //    Simpler approach: process the first `drepsPerRun` DReps not yet in drep_info.
    const doneRes = await client.query('SELECT DISTINCT drep_id FROM drep_info');
    const done = new Set(doneRes.rows.map(r => r.drep_id));
    const todo = drepIds.filter(d => !done.has(d));
    const sliceTodo = todo.slice(0, drepsPerRun);
    const remainingAfter = todo.length - sliceTodo.length;

    info(
      `[drep_info] epoch=${currentEpoch} total=${drepIds.length} ` +
        `already_done=${done.size} processing=${sliceTodo.length} remaining=${remainingAfter}`
    );
    if (sliceTodo.length === 0) {
      info('[drep_info] All DReps already synced for this epoch.');
      return 0;
    }

    // 4. Fetch + build rows, flush in chunks
    let allRows = [];
    let processedNow = 0;
    let errors = 0;

    const flush = async rows => {
      try {
        await pgUpsertBatch(client, 'drep_info', COLUMNS, rows, {
          conflict_cols: ['drep_id'],
          preserve_cols: ['id'],
          do_update: true,
        });
      } catch (e) {
        warn(`[drep_info] Insert error: ${e.message}`);
      }
    };

    for (let i = 0; i < sliceTodo.length; i++) {
      const did = sliceTodo[i];
      try {
        const row = await buildRow(did);
        allRows.push(row);
        processedNow++;
      } catch (e) {
        errors++;
        if (errors <= 5) warn(`[drep_info] Error for ${did}: ${e.message}`);
      }

      if (allRows.length >= BATCH_SIZE) {
        await flush(allRows);
        allRows = [];
        info(`  [drep_info] ${i + 1}/${sliceTodo.length} (-${remainingAfter} left)`);
      }

      await sleep(API_DELAY);
    }

    if (allRows.length) {
      await flush(allRows);
      allRows = [];
    }

    info(`\n[drep_info] Processed ${processedNow} this run. Remaining ${remainingAfter} in this epoch.`);

    const cntRes = await client.query('SELECT count(*)::int as cnt FROM drep_info');
    info(`[drep_info] Row count: ${cntRes.rows[0].cnt}`);
    return cntRes.rows[0].cnt;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  syncDrepInfo().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncDrepInfo };