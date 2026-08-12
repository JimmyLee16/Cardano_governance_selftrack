// js/helpers.js
// Core helpers for Node.js backend
// Generic PostgreSQL - works with any provider (Railway, Render, local, Docker, etc.)
// Requires: pg, node-fetch

const { Pool } = require('pg');
const fetch = require('node-fetch');
require('dotenv').config();

// ============================================================
// 1. PostgreSQL Connection (generic)
// ============================================================

let pool = null;

function pgConnect() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error('❌ DATABASE_URL not set in .env');
  }

  // Create pool if not exists (singleton pattern)
  if (!pool) {
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false }, // Most cloud PG requires SSL
      max: 20,
      idleTimeoutMillis: 30000,
    });
  }

  return pool.connect(); // Returns client
}

function pgClose() {
  if (pool) {
    pool.end();
    pool = null;
  }
}

// ============================================================
// 2. Fetch IPFS metadata (same as Python fetch_ipfs_metadata)
// Priority: body.comment → body.rationale → root comment → root rationale
// ============================================================

/**
 * Get comment from meta_url (IPFS URL)
 * @param {string} meta_url - IPFS metadata URL (https://ipfs.io/ipfs/Qm...)
 * @param {string} [voter_role] - Voter role (optional)
 * @returns {Promise<string|null>} - Comment text or null
 */
async function fetchIpfsMetadata(meta_url, voter_role = null) {
  if (!meta_url) return null;

  try {
    // Decode URL if needed (Koios may encode)
    const cleanUrl = meta_url.startsWith('ipfs://')
      ? `https://ipfs.io/ipfs/${meta_url.replace('ipfs://', '')}`
      : meta_url;

    const res = await fetch(cleanUrl);
    if (!res.ok) {
      console.warn(`⚠️ IPFS fetch not ok: ${res.status} for ${cleanUrl}`);
      return null;
    }

    const data = await res.json();

    // Priority order (same as Python):
    // 1. metaData.body.comment
    // 2. metaData.body.rationale
    // 3. metaData.comment
    // 4. metaData.rationale
    // 5. Return empty string if not found

    let comment = null;

    // Try priorities in correct order
    if (data?.metaData?.body?.comment) {
      comment = String(data.metaData.body.comment);
    } else if (data?.metaData?.body?.rationale) {
      comment = String(data.metaData.body.rationale);
    } else if (data?.metaData?.comment) {
      comment = String(data.metaData.comment);
    } else if (data?.metaData?.rationale) {
      comment = String(data.metaData.rationale);
    }

    // If still null, check root level fields
    if (!comment) {
      if (data?.comment) comment = String(data.comment);
      if (data?.rationale) comment = String(data.rationale);
    }

    // Trim and validate
    if (comment && comment.trim()) {
      return comment.trim();
    }

    return null;
  } catch (err) {
    console.error(`❌ Error fetching IPFS metadata ${meta_url}:`, err.message);
    return null;
  }
}

/**
 * Helper wrapper: get comment, return null if empty
 * @param {string} meta_url
 * @param {string} voter_role
 * @returns {Promise<string|null>}
 */
async function getCommentFromMetaUrl(meta_url, voter_role = null) {
  const comment = await fetchIpfsMetadata(meta_url, voter_role);
  return comment ? comment.trim() : null;
}

// ============================================================
// 3. Batch Upsert into PostgreSQL
// ============================================================

/**
 * Perform batch upsert into PostgreSQL table
 * Equivalent to pg_upsert_batch from Python
 *
 * @param {object} client - pg client from pgConnect()
 * @param {string} table_name - Table name (e.g. 'ga_abc123_xyz')
 * @param {array} batch_cols - Array of column names (e.g. config.drep_list)
 * @param {array} rows - Array of objects with data to upsert
 * @param {object} options - Options
 * @param {array} options.conflict_cols - Column(s) for conflict detection (UNIQUE constraint)
 * @param {array} options.preserve_cols - Column(s) to preserve on update (DEFAULT: 'id')
 * @param {boolean} options.do_update - Whether to UPDATE on conflict
 * @returns {Promise<number>} - Number of rows affected
 */
async function pgUpsertBatch(client, table_name, batch_cols, rows, options = {}) {
  const {
    conflict_cols = ['voter_id', 'block_time'], // default for ga_* tables
    preserve_cols = ['id'], // column(s) to preserve (usually ID)
    do_update = true,
  } = options;

  if (rows.length === 0) {
    console.warn('⚠️ Rows empty, nothing to upsert.');
    return 0;
  }

  // Validate: check each row has all keys in batch_cols
  for (const row of rows) {
    const missing = batch_cols.filter(c => !(c in row));
    if (missing.length > 0) {
      throw new Error(
        `❌ Row missing required columns: ${missing.join(', ')}. Available: ${batch_cols.join(', ')}`
      );
    }
  }

  // Build dynamic query
  // Format: INSERT INTO table (cols) VALUES ($1, $2, ...) ON CONFLICT conflict_cols DO UPDATE SET col = EXCLUDED.col
  const colPlaceholders = batch_cols.map((_, i) => `$${i + 1}`).join(', ');

  // UPDATE SET only includes columns NOT in conflict_cols and preserve_cols.
  // If no columns left to update → DO NOTHING (same as Python helpers.py).
  const conflictSet = new Set(conflict_cols.map(c => c.toLowerCase()));
  const preserveSet = new Set(preserve_cols.map(c => c.toLowerCase()));
  const updateCols = batch_cols.filter(
    c => !conflictSet.has(c.toLowerCase()) && !preserveSet.has(c.toLowerCase())
  );

  let query;
  if (do_update && updateCols.length > 0) {
    const updateSet = updateCols.map(c => `${c} = EXCLUDED.${c}`).join(', ');
    query = `INSERT INTO ${table_name} (${batch_cols.join(', ')}) VALUES (${colPlaceholders}) ON CONFLICT (${conflict_cols.join(', ')}) DO UPDATE SET ${updateSet}`;
  } else {
    query = `INSERT INTO ${table_name} (${batch_cols.join(', ')}) VALUES (${colPlaceholders}) ON CONFLICT (${conflict_cols.join(', ')}) DO NOTHING`;
  }

  // Execute batch: each row = 1 query, or use execute many values at once
  // Safe way: execute each row (pg manages transaction)
  const valuesPromises = rows.map(row =>
    client.query(query, batch_cols.map(col => row[col]))
  );

  try {
    await Promise.all(valuesPromises);
    // console.log(`✅ Upsert ${rows.length} rows into ${table_name}`);
    return rows.length;
  } catch (err) {
    console.error(`❌ Error upsert batch into ${table_name}:`, err.message);
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
// 5. Export all
// ============================================================

module.exports = {
  pgConnect,
  pgClose,
  fetchIpfsMetadata,
  getCommentFromMetaUrl,
  pgUpsertBatch,
  info,
  warn,
  error,
};

// If run directly (node helpers.js) -> self-test
if (require.main === module) {
  console.log('🔧 helpers.js loaded. Testing pgConnect...');
  // Don't call pgConnect here to avoid auto-connection
}