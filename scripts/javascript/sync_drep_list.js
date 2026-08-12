// sync_drep_list.js
// Fetch DRep registry from Koios API
// Equivalent to sync_drep_list.py

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

async function fetchDrepList() {
  const url = `https://api.koios.io/?type=stake_distribution&project_id=${BLOCKFROST_PROJECT_ID}`;
  const res = await fetch(url);
  const data = await res.json();
  return data.rows || [];
}

async function main() {
  console.log('🔄 Bắt đầu fetch DRep list từ Koios...');

  try {
    const rows = await fetchDrepList();
    console.log(`📥 Đã lấy ${rows.length} DRep records`);

    if (rows.length === 0) {
      console.warn('⚠️ Không có DRep nào trả về. Kiểm tra BLOCKFROST_PROJECT_ID.');
      process.exit(0);
    }

    const conn = neonConnect();
    const client = await conn;

    // Chuẩn bị dữ liệu upsert
    // TABLE_COLUMNS.drep_list chứa danh sách cột cho drep_list
    const columns = TABLE_COLUMNS.drep_list;
    const values = rows.map(row => {
      // Koios trả về: id, given_name, content_url, https_uris, amount, active_epoch
      return {
        drep_id: row.id,
        given_name: row.given_name || null,
        content_url: row.content_url || null,
        https_uris: JSON.stringify(row.https_uris || []),
        amount: row.amount ? String(row.amount) : null,
        active_epoch: row.active_epoch || null,
      };
    });

    // Batch upsert vào drep_list
    await neonUpsertBatch(client, 'drep_list', columns, values, {
      conflict_cols: ['drep_id'],
      preserve_cols: ('id',),
      do_update: true,
    });

    console.log(`✅ Hoàn tất upsert ${values.length} DRep vào database.`);

    // Verify
    const verifyStmt = client.prepare('SELECT count(*) as cnt FROM drep_list');
    const verifyRes = await verifyStmt.execute();
    const cnt = verifyRes.rows[0].cnt;
    console.log(`📊 Tổng row count drep_list sau upsert: ${cnt}`);

    await client.end();
    console.log('✅ sync_drep_list.js xong!');
  } catch (err) {
    console.error('❌ Lỗi sync_drep_list.js:', err);
    process.exit(1);
  }
}

main();