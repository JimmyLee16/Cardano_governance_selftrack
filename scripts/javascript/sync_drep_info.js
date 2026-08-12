// sync_drep_info.js
// Fetch DRep metadata + stake from Blockfrost
// Equivalent to sync_drep_info.py

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

async function fetchDrepInfo(drepId) {
  // Blockfrost API: /drep_addresses/{drep_id}
  // Hoặc dùng /drep_metadata/{drep_id}
  const url = `https://api.blockfrost.io/v1/prisma/drep_metadata/${drepId}?project_id=${BLOCKFROST_PROJECT_ID}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) {
    console.warn(`⚠️ Không lấy được metadata cho DRep ${drepId}: ${res.status}`);
    return null;
  }
  return await res.json();
}

async function main() {
  console.log('🔄 Bắt đầu fetch DRep info + stake...');

  const conn = neonConnect();
  const client = await conn;

  // Lấy danh sách DRep IDs đã có trong database
  const listStmt = client.prepare('SELECT drep_id FROM drep_list');
  const listRes = await listStmt.execute();
  const existingIds = new Set(listRes.rows.map(r => r.drep_id));

  console.log(`📊 Đã có ${existing.size} DRep trong database`);

  // Fetch từ Koios (drep distribution)
  const koiosUrl = `https://api.koios.io/?type=drep_info&project_id=${BLOCKFROST_PROJECT_ID}`;
  const koiosRes = await fetch(koiosUrl);
  const koiosData = await koiosRes.json();
  const koiosRows = koiosData.rows || [];

  console.log(`📥 Lấy ${koiosRows.length} DRep info từ Koios...`);

  const values = [];
  let created = 0, updated = 0;

  for (const row of koiosRows) {
    const drepId = row.id;
    if (existingIds.has(drepId)) continue; // Đã có rồi, skip

    // Fetch metadata từ Blockfrost
    let meta = null;
    try {
      meta = await fetchDrepInfo(drepId);
    } catch (e) {
      console.warn(`⚠️ Skip metadata for ${drepId}: ${e.message}`);
    }

    // Trích xuất các field cần thiết
    const stakeAddr = meta?.stake_address || null;
    const givenName = meta?.given_name || null;
    const contentUrl = meta?.content_url || null;
    const httpsUris = meta?.https_uris || null;
    const amount = meta?.amount ? String(meta.amount) : null;
    const activeEpoch = meta?.active_epoch || null;

    values.push({
      drep_id: drepId,
      given_name: givenName,
      content_url: contentUrl,
      https_uris: JSON.stringify(httpsUris || []),
      amount: amount,
      active_epoch: activeEpoch,
      stake_address: stakeAddr,
    });

    created++;
  }

  if (values.length === 0) {
    console.log('⚠️ Không có DRep mới để upsert.');
    await client.end();
    return;
  }

  // Cột cho drep_info (theo TABLE_COLUMNS.drep_info)
  const columns = TABLE_COLUMNS.drep_info;

  await neonUpsertBatch(client, 'drep_info', columns, values, {
    conflict_cols: ['drep_id'],
    preserve_cols: ('id',),
    do_update: true,
  });

  console.log(`✅ Hoàn tất upsert ${values.length} DRep info.`);

  // Verify count
  const verifyStmt = client.prepare('SELECT count(*) as cnt FROM drep_info');
  const verifyRes = await verifyStmt.execute();
  console.log(`📊 Row count drep_info: ${verifyRes.rows[0].cnt}`);

  await client.end();
  console.log('✅ sync_drep_info.js xong!');
}

main();