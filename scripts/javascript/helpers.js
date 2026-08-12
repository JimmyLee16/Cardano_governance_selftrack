// js/helpers.js
// Core helpers for Node.js backend
// Tương đương helpers.py: neonConnect, fetchIpfsMetadata, neonUpsertBatch, v.v.
// Cần cài: pg (pg), node-fetch

const { Pool } = require('pg');
const fetch = require('node-fetch');
require('dotenv').config();

// ============================================================
// 1. Kết nối Neon PostgreSQL
// ============================================================

let pool = null;

function neonConnect() {
  const connectionString = process.env.NEON_CONN;
  if (!connectionString) {
    throw new Error('❌ NEON_CONN not set in .env');
  }

  // Tạo pool nếu chưa có (singleton pattern)
  if (!pool) {
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false }, // Neon cần SSL
      max: 20,
      idleTimeoutMillis: 30000,
    });
  }

  return pool.connect(); // Trả về client
}

function neonClose() {
  if (pool) {
    pool.end();
    pool = null;
  }
}

// ============================================================
// 2. Fetch IPFS metadata (giống Python fetch_ipfs_metadata)
// Priority: body.comment → body.rationale → root comment → root rationale
// ============================================================

/**
 * Lấy comment từ meta_url (URL IPFS)
 * @param {string} meta_url - URL IPFS metadata (https://ipfs.io/ipfs/Qm...)
 * @param {string} [voter_role] - Vai trò voter (tùy chọn)
 * @returns {Promise<string|null>} - Comment text hoặc null
 */
async function fetchIpfsMetadata(meta_url, voter_role = null) {
  if (!meta_url) return null;

  try {
    // Decode URL nếu cần (theo Koios có thể encode)
    const cleanUrl = meta_url.startsWith('ipfs://')
      ? `https://ipfs.io/ipfs/${meta_url.replace('ipfs://', '')}`
      : meta_url;

    const res = await fetch(cleanUrl);
    if (!res.ok) {
      console.warn(`⚠️ IPFS fetch không ok: ${res.status} cho ${cleanUrl}`);
      return null;
    }

    const data = await res.json();

    // Priority order (giống Python):
    // 1. metaData.body.comment
    // 2. metaData.body.rationale
    // 3. metaData.comment
    // 4. metaData.rationale
    // 5. Trả về str rỗng nếu không tìm thấy

    let comment = null;

    // Thử các priority theo đúng order
    if (data?.metaData?.body?.comment) {
      comment = String(data.metaData.body.comment);
    } else if (data?.metaData?.body?.rationale) {
      comment = String(data.metaData.body.rationale);
    } else if (data?.metaData?.comment) {
      comment = String(data.metaData.comment);
    } else if (data?.metaData?.rationale) {
      comment = String(data.metaData.rationale);
    }

    // Nếu vẫn null, kiểm tra fields gốc (root level)
    if (!comment) {
      if (data?.comment) comment = String(data.comment);
      if (data?.rationale) comment = String(data.rationale);
    }

    // Trim và validate
    if (comment && comment.trim()) {
      return comment.trim();
    }

    return null;
  } catch (err) {
    console.error(`❌ Lỗi fetch IPFS metadata ${meta_url}:`, err.message);
    return null;
  }
}

/**
 * Helper wrapper: lấy comment, trả về None nếu rỗng
 * @param {string} meta_url 
 * @param {string} voter_role 
 * @returns {Promise<string|null>}
 */
async function getCommentFromMetaUrl(meta_url, voter_role = null) {
  const comment = await fetchIpfsMetadata(meta_url, voter_role);
  return comment ? comment.trim() : null;
}

// ============================================================
// 3. Batch Upsert into Neon PostgreSQL
// ============================================================

/**
 * Thực hiện upsert batch vào table PostgreSQL
 * Equivalent to neon_upsert_batch từ Python
 *
 * @param {object} client - pg client từ neonConnect()
 * @param {string} table_name - Tên table (ví dụ: 'ga_abc123_xyz')
 * @param {array} batch_cols - Mảng tên cột (ví dụ: config.drep_list)
 * @param {array} rows - Mảng object chứa dữ liệu cần upsert
 * @param {object} options - Các tùy chọn
 * @param {array} options.conflict_cols - Cột(s) để detect conflict (UNIQUE constraint)
 * @param {array} options.preserve_cols - Cột(s) giữ nguyên khi update (DEFAULT: 'id')
 * @param {boolean} options.do_update - Có thực hiện UPDATE khi conflict hay không
 * @returns {Promise<void>}
 */
async function neonUpsertBatch(client, table_name, batch_cols, rows, options = {}) {
  const {
    conflict_cols = ['voter_id', 'block_time'], // mặc định cho ga_* tables
    preserve_cols = 'id', // cột nào giữ nguyên (thường là ID)
    do_update = true,
  } = options;

  if (rows.length === 0) {
    console.warn('⚠️ Rows rỗng, không có gì upsert.');
    return;
  }

  // Validate: kiểm tra mỗi row có tất cả keys trong batch_cols không
  for (const row of rows) {
    const missing = batch_cols.filter(c => !(c in row));
    if (missing.length > 0) {
      throw new Error(
        `❌ Row missing required columns: ${missing.join(', ')}. Available: ${batch_cols.join(', ')}`
      );
    }
  }

  // Xây dựng câu query dynamic
  // Format: INSERT INTO table (cols) VALUES ($1, $2, ...) ON CONFLICT conflict_cols DO UPDATE SET cols = EXCLUDED.cols
  const colPlaceholders = batch_cols.map((_, i) => `$${i + 1}`).join(', ');
  const updateSet = batch_cols
    .map(
      (col, i) =>
        `${col} = EXCLUDED.${col}${
          preserve_cols.includes(col) ? '' : ' NULL' // Nếu không trong preserve_cols thì set NULL (không khuyến khích)
        }`
    )
    .join(', ');

  const query = do_update
    ? `INSERT INTO ${table_name} (${batch_cols.join(', ')}) VALUES (${colPlaceholders}) ON CONFLICT (${conflict_cols.join(', ')}) DO UPDATE SET ${updateSet}`
    : `INSERT INTO ${table_name} (${batch_cols.join(', ')}) VALUES (${colPlaceholders})`;

  // Execute batch: mỗi row là 1 query, hoặc dùng execute nhiều values cùng 1 lúc
  // Cách an toàn: execute từng row một (pg tự quản lý transaction)
  const valuesPromises = rows.map(row =>
    client.query(query, batch_cols.map(col => row[col]))
  );

  try {
    await Promise.all(valuesPromises);
    // console.log(`✅ Upsert ${rows.length} rows vào ${table_name}`);
  } catch (err) {
    console.error(`❌ Lỗi upsert batch vào ${table_name}:`, err.message);
    throw err;
  }
}

// ============================================================
// 4. Logging helpers
// ============================================================

function info(msg, ...args) {
  const timestamp = new Date().toLocaleString('en-US', {
    timeZone: 'UTC',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  console.log(`[${timestamp}] INFO: ${msg}`, ...args);
}

function warn(msg, ...args) {
  const timestamp = new Date().toLocaleString('en-US', {
    timeZone: 'UTC',
  });
  console.warn(`[${timestamp}] WARN: ${msg}`, ...args);
}

function error(msg, ...args) {
  const timestamp = new Date().toLocaleString('en-US', {
    timeZone: 'UTC',
  });
  console.error(`[${timestamp}] ERROR: ${msg}`, ...args);
}

// ============================================================
// 5. Export tất cả
// ============================================================

module.exports = {
  neonConnect,
  neonClose,
  fetchIpfsMetadata,
  getCommentFromMetaUrl,
  neonUpsertBatch,
  info,
  warn,
  error,
};

// Nếu chạy trực tiếp (node helpers.js) -> self-test
if (require.main === module) {
  console.log('🔧 helpers.js loaded. Testing neonConnect...');
  // Không gọi neonConnect ở đây để tránh kết nối tự động
}