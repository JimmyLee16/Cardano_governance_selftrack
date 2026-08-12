// sync_epoch.js
// Sync epoch info from Koios → PostgreSQL
// Equivalent to sync_epoch.py
//
// Koios: GET /api/v1/tip
// Updates: proposals.epoch_no, proposals.status (expired → done, in-window → active)

require('dotenv').config();
const fetch = require('node-fetch');
const { pgConnect, info, error } = require('./helpers');

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('❌ Thiếu DATABASE_URL trong .env');
  process.exit(1);
}

const KOIOS_BASE = 'https://api.koios.rest/api/v1';

async function jsonGet(url, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

async function koiosGet(endpoint) {
  return jsonGet(`${KOIOS_BASE}/${endpoint}`, { Accept: 'application/json' });
}

async function syncEpoch() {
  info('=== Sync: epoch (Koios → PostgreSQL) ===');

  const client = await pgConnect();

  try {
    // 1. Get current epoch from Koios
    const tip = await koiosGet('tip');
    if (!tip || !tip[0]) {
      error('[epoch] Failed to get tip from Koios');
      return 0;
    }
    const currentEpoch = tip[0].epoch_no || 0;
    info(`[epoch] Current epoch: ${currentEpoch}`);

    // 2. Update epoch_no for all proposals
    const epochRes = await client.query(
      'UPDATE proposals SET epoch_no = $1 WHERE epoch_no IS NULL OR epoch_no != $1',
      [currentEpoch]
    );
    info(`[epoch] Updated epoch_no for ${epochRes.rowCount} proposals`);

    // 3. Mark expired proposals as done
    const doneRes = await client.query(
      "UPDATE proposals SET status = 'done' WHERE expiration IS NOT NULL AND expiration <> '' AND expiration::integer <= $1 AND (status != 'done' OR status IS NULL)",
      [currentEpoch]
    );
    info(`[epoch] Marked ${doneRes.rowCount} proposals as done (expired)`);

    // 4. Mark in-window proposals as active
    const activeRes = await client.query(
      "UPDATE proposals SET status = 'active' WHERE expiration IS NOT NULL AND expiration <> '' AND expiration::integer > $1 AND (status != 'active' OR status IS NULL)",
      [currentEpoch]
    );
    info(`[epoch] Marked ${activeRes.rowCount} proposals as active (in voting window)`);

    info(`[epoch] Done! Epoch=${currentEpoch}`);
    return currentEpoch;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  syncEpoch().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncEpoch };