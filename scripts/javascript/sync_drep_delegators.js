// sync_drep_delegators.js
// Fetch current delegations + historical snapshots from Koios
// Equivalent to sync_drep_delegators.py

require('dotenv').config();
const fetch = require('node-fetch');
const { neonConnect, neonUpsertBatch } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const BLOCKFROST_PROJECT_ID = process.env.BLOCKFROST_PROJECT_ID;
const NEON_CONN = process.env.NEON_CONN;

if (!BLOCKFROST_PROJECT_ID || !NEON_CONN) {
  console.error('❌ Thiếu BLOCKFROST_PROJECT_ID hoặc NEON_CONN trong .env');
  process.exit(1);
}

// Helper: fetch current delegations (epoch_no = current epoch)
async function fetchCurrentDelegations() {
  const url = `https://api.koios.io/?type=delegators&project_id=${BLOCKFROST_PROJECT_ID}`;
  const res = await fetch(url);
  const data = await res.json();
  return data.rows || [];
}

// Helper: fetch historical delegations for specific epoch
async function fetchHistoricalDelegations(epochNo) {
  const url = `https://api.koios.io/?type=delegators&epoch_no=${epochNo}&project_id=${BLOCKFROST_PROJECT_ID}`;
  const res = await fetch(url);
  const data = await res.json();
  return data.rows || [];
}

async function main() {
  console.log('🔄 Bắt đầu fetch DRep delegators...');

  const conn = neonConnect();
  const client = await conn;

  // 1. Fetch current delegations
  console.log('📥 Đang fetch delegations hiện tại...');
  const currentRows = await fetchCurrentDelegations();
  console.log(`📥 Lấy ${currentRows.length} delegation records hiện tại`);

  const currentColumns = TABLE_COLUMNS.drep_delegators;
  const currentValues = currentRows.map(row => ({
    id: row.id ? String(row.id) : uuidv4(), // fallback
    drep_id: row.drep_id || null,
    stake_address: row.stake_address || null,
    stake_address_hex: row.stake_address_hex || null,
    script_hash: row.script_hash || null,
    amount_lovelace: row.amount_lovelace !== undefined ? String(row.amount_lovelace) : null,
    epoch_no: row.epoch_no || 0,
    timestamp: new Date().toISOString(),
    timestamp_epoch: row.epoch_no || 0,
  }));

  if (currentValues.length > 0) {
    await neonUpsertBatch(client, 'drep_delegators', currentColumns, currentValues, {
      conflict_cols: ['drep_id', 'stake_address', 'epoch_no'],
      preserve_cols: ('id',),
      do_update: true,
    });
    console.log(`✅ Upsert ${currentValues.length} delegation hiện tại.`);
  }

  // 2. Fetch historical delegations (last 32 epochs)
  // Neon có drep_delegators_N tables (N=0..31) cho từng epoch
  // Chúng ta chỉ lưu vào drep_delegators với epoch_no khác nhau
  // Hoặc có thể tạo các bảng tách nếu cần.

  // Lấy epoch hiện tại từ database hoặc Koios
  const epochStmt = client.prepare('SELECT epoch_no FROM proposals ORDER BY proposed_epoch DESC LIMIT 1');
  const epochRes = await epochStmt.execute();
  const currentEpoch = epochRes.rows.length > 0 ? epochRes.rows[0].epoch_no : 0;
  console.log(`📅 Epoch hiện tại: ${currentEpoch}`);

  // Fetch historical cho 5 epoch gần nhất (dù có thể fetch hết 32 epoch)
  const historicalEpochs = [];
  for (let i = 0; i < 5; i++) {
    historicalEpochs.push(currentEpoch - i);
  }
  historicalEpochs.push(...historicalEpochs.reverse()); // both directions

  console.log(`🔍 Fetch lịch sử cho ${historicalEpochs.length} epoch gần nhất`);

  for (const epoch of historicalEpochs) {
    if (epoch <= 0) continue;
    const histRows = await fetchHistoricalDelegations(epoch);
    if (histRows.length === 0) continue;

    const histValues = histRows.map(row => ({
      id: String(row.id || uuidv4()),
      drep_id: row.drep_id || null,
      stake_address: row.stake_address || null,
      stake_address_hex: row.stake_address_hex || null,
      script_hash: row.script_hash || null,
      amount_lovelace: row.amount_lovelace !== undefined ? String(row.amount_lovelace) : null,
      epoch_no: epoch,
      timestamp: new Date().toISOString(),
      timestamp_epoch: epoch,
    }));

    // Upsert vào drep_delegators (chỉ lưu epoch_no, trùng lap là được)
    await neonUpsertBatch(client, 'drep_delegators', currentColumns, histValues, {
      conflict_cols: ['drep_id', 'stake_address', 'epoch_no'],
      preserve_cols: ('id',),
      do_update: true,
    });
    console.log(`   ✅ Epoch ${epoch}: ${histValues.length} records upserted.`);
  }

  // Verify
  const verifyStmt = client.prepare('SELECT count(*) as cnt, count(DISTINCT epoch_no) as distinct_epochs FROM drep_delegators');
  const verifyRes = await verifyStmt.execute();
  console.log(`📊 Row count drep_delegators: ${verifyRes.rows[0].cnt}`);
  console.log(`📊 Distinct epochs: ${verifyRes.rows[0].distinct_epochs}`);

  await client.end();
  console.log('✅ sync_drep_delegators.js xong!');
}

// Generate UUID v4 (simple version)
function uuidv4() {
  return '10000000-1000-4000-8000-100000000000'.replace(/[018]/c, c => (c ^ (Math.random() * 16 >> c / 4)).toString(16));
}

main();