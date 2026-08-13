// sync_drep_delegators.js
// Sync DRep delegators from Koios → PostgreSQL (upsert)
// Equivalent to sync_drep_delegators.py
//
// Koios: GET /api/v1/drep_delegators?_drep_id={id} (paginated)
//        GET /api/v1/tip (for current epoch)
// Target: drep_delegators (flat, per-epoch snapshots)
//
// Design:
//   - Upsert on (drep_id, stake_address, epoch_no) — no truncate, no data loss.
//   - After a full pass, is_current is normalized so only rows of the current
//     epoch are marked current; older epoch rows flip to false.

require('dotenv').config();
const fetch = require('node-fetch');
const crypto = require('crypto');
const { pgConnect, pgUpsertBatch, info, warn, error } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('❌ Missing DATABASE_URL in .env');
  process.exit(1);
}

const KOIOS_BASE = 'https://api.koios.rest/api/v1';
const API_DELAY = 500; // ms
const PAGE_SIZE = 1000;
const SKIP_DREP_IDS = new Set(['drep_always_abstain', 'drep_always_no_confidence']);

const COLUMNS = TABLE_COLUMNS.drep_delegators;
const CONFLICT_COLS = ['drep_id', 'stake_address', 'epoch_no'];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
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

async function syncDrepDelegators({ force = false } = {}) {
  info('=== Sync: drep_delegators (Koios → PostgreSQL, upsert) ===');

  const client = await pgConnect();

  try {
    // 1. Current epoch
    const tip = await koiosGet('tip');
    const currentEpoch = tip && tip[0] ? tip[0].epoch_no || 0 : 0;
    info(`[drep_delegators] Current epoch: ${currentEpoch}`);

    // 2. DRep IDs
    const listRes = await client.query('SELECT drep_id FROM drep_list ORDER BY drep_id');
    let drepIds = listRes.rows.map(r => r.drep_id);
    drepIds = drepIds.filter(d => !SKIP_DREP_IDS.has(d));
    info(
      `[drep_delegators] Found ${drepIds.length} DReps (skipped ${SKIP_DREP_IDS.size} virtual DReps)`
    );

    let total = 0;
    let errors = 0;

    for (let i = 0; i < drepIds.length; i++) {
      const did = drepIds[i];
      try {
        const drepRows = [];
        let offset = 0;

        while (true) {
          const data = await koiosGet('drep_delegators', {
            _drep_id: did,
            offset,
            limit: PAGE_SIZE,
          });
          if (!data || data.length === 0) break;

          for (const item of data) {
            const amountLovelace = parseInt(item.amount, 10) || 0;
            const scriptHash = item.script_hash;
            const epochItem = item.epoch_no ?? currentEpoch;
            drepRows.push({
              id: genUuid(),
              drep_id: did,
              stake_address: item.stake_address,
              stake_address_hex: item.stake_address_hex,
              script_hash: scriptHash,
              epoch_no: epochItem,
              amount_lovelace: amountLovelace,
              amount_ada: amountLovelace / 1000000,
              is_current: epochItem === currentEpoch,
              delegation_type: scriptHash ? 'script' : 'regular',
              first_seen_epoch: epochItem,
              last_seen_epoch: epochItem,
              delegation_count: 1,
              is_whale: amountLovelace / 1000000 > 1000000,
              is_exchange: false,
              created_at: nowIso(),
              updated_at: nowIso(),
            });
          }

          if (data.length < PAGE_SIZE) break;
          offset += PAGE_SIZE;
          await sleep(API_DELAY);
        }

        if (drepRows.length > 0) {
          await pgUpsertBatch(client, 'drep_delegators', COLUMNS, drepRows, {
            conflict_cols: CONFLICT_COLS,
            preserve_cols: ['id'],
            do_update: true,
          });
          total += drepRows.length;
        }

        if ((i + 1) % 25 === 0 || i === drepIds.length - 1) {
          info(`  [drep_delegators] ${i + 1}/${drepIds.length} DReps, Total ${total}`);
        }
      } catch (e) {
        errors++;
        if (errors <= 5) warn(`  Error for ${did}: ${e.message}`);
        await sleep(API_DELAY);
      }
    }

    info(`[drep_delegators] upserted: ${total}, errors: ${errors}`);

    // 3. Finalize is_current for full pass
    await client.query('UPDATE drep_delegators SET is_current = (epoch_no = $1)', [
      currentEpoch,
    ]);

    const cntRes = await client.query('SELECT count(*)::int as cnt FROM drep_delegators');
    info(`[drep_delegators] Row count: ${cntRes.rows[0].cnt}`);
    return cntRes.rows[0].cnt;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  const force = process.argv.includes('--force');
  syncDrepDelegators({ force }).catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncDrepDelegators };