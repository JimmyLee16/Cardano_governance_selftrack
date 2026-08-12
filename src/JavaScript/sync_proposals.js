// sync_proposals.js
// Sync proposals from Koios → PostgreSQL
// Equivalent to sync_proposals.py
//
// Koios: GET /api/v1/proposal_list
// Target: proposals table

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
const PROPOSAL_TRIGGERS = [
  'trg_create_proposal_activities_table',
  'trg_create_proposal_summary_entry',
];

const COLUMNS = TABLE_COLUMNS.proposals;

async function jsonGet(url, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

async function koiosGet(endpoint) {
  return jsonGet(`${KOIOS_BASE}/${endpoint}`, { Accept: 'application/json' });
}

function genUuid() {
  return crypto.randomUUID();
}

function nowIso() {
  return new Date().toISOString();
}

async function syncProposals() {
  info('=== Sync: proposals (Koios → PostgreSQL) ===');

  const client = await pgConnect();

  try {
    // 1. Fetch from Koios
    info('[proposals] Fetching from Koios...');
    const raw = await koiosGet('proposal_list');
    info(`[proposals] Got ${raw.length} proposals from Koios`);

    // 2. Transform
    const seenIds = new Set();
    const rows = [];
    for (const p of raw) {
      const pid = p.proposal_id;
      if (!pid || seenIds.has(pid)) continue;
      seenIds.add(pid);

      const body = (p.meta_json || {}).body || {};
      const abstractParts = [];
      if (body.abstract) abstractParts.push(body.abstract);
      if (body.rationale) abstractParts.push(`RATIONALE:\n${body.rationale}`);
      if (body.motivation) abstractParts.push(`MOTIVATION:\n${body.motivation}`);

      const refs = body.references || [];
      const firstUri = refs.length > 0 && refs[0].uri ? refs[0].uri : null;
      const authors = (p.meta_json || {}).authors || [];
      const authorName = authors.length > 0 ? authors[0].name : null;

      rows.push({
        id: genUuid(),
        proposal_id: pid,
        title: body.title || pid,
        abstract: abstractParts.length > 0 ? abstractParts.join('\n\n') : null,
        first_reference_uri: firstUri,
        author_name: authorName,
        proposal_index: p.proposal_index,
        proposal_tx_hash: p.proposal_tx_hash,
        proposed_epoch: p.proposed_epoch,
        expiration: p.expiration,
        proposal_type: p.proposal_type,
        epoch_no: null,
        status: null,
        data_fetched_at: nowIso(),
        created_at: nowIso(),
        updated_at: nowIso(),
        activities_table_created: false,
        activities_table_name: null,
        abstract_summary: (body.abstract || '').slice(0, 500) || null,
        slug: null,
      });
    }
    info(`[proposals] Transformed ${rows.length} rows`);

    // 3. Find existing proposal_ids
    const existingRes = await client.query('SELECT proposal_id FROM proposals');
    const existingIds = new Set(existingRes.rows.map(r => r.proposal_id));

    // 4. Split new vs existing
    const newRows = rows.filter(row => !existingIds.has(row.proposal_id));
    const existingRows = rows.filter(row => existingIds.has(row.proposal_id));
    info(`[proposals] ${newRows.length} new to insert, ${existingRows.length} existing to update`);

    // 5. Drop triggers before insert (to prevent orphan ga_* tables)
    let triggersDropped = false;
    if (newRows.length > 0) {
      info(`[proposals] Dropping triggers before insert (${newRows.length} new)...`);
      for (const tg of PROPOSAL_TRIGGERS) {
        await client.query(
          `DROP TRIGGER IF EXISTS ${tg} ON proposals`
        );
      }
      triggersDropped = true;
    }

    // 6. Insert new proposals (no trigger = no orphan ga_* tables)
    let inserted = 0;
    for (let i = 0; i < newRows.length; i += BATCH_SIZE) {
      const batch = newRows.slice(i, i + BATCH_SIZE);
      try {
        inserted += await pgUpsertBatch(client, 'proposals', COLUMNS, batch, {
          conflict_cols: ['proposal_id'],
          do_update: false,
        });
      } catch (e) {
        error(`[proposals] Error at batch ${i}: ${e.message}`);
      }
      const pct = Math.min(100, Math.round(((i + batch.length) * 100) / newRows.length));
      process.stdout.write(`\r  [proposals] Insert ${pct}% (PostgreSQL=${inserted})`);
    }
    info(`\n[proposals] Inserted ${inserted}/${newRows.length} new`);

    // 7. Update existing proposals (UPDATE, not INSERT → no trigger)
    const updateFields = [
      'title', 'abstract', 'first_reference_uri', 'author_name',
      'proposal_index', 'proposal_tx_hash', 'proposed_epoch', 'expiration',
      'proposal_type', 'data_fetched_at', 'updated_at', 'abstract_summary',
    ];
    let updated = 0;
    for (let i = 0; i < existingRows.length; i++) {
      const row = existingRows[i];
      try {
        const setClause = updateFields.map(c => `${c} = $${updateFields.indexOf(c) + 1}`).join(', ');
        const values = updateFields.map(c => row[c]);
        await client.query(
          `UPDATE proposals SET ${setClause} WHERE proposal_id = $${updateFields.length + 1}`,
          [...values, row.proposal_id]
        );
        updated++;
      } catch (e) {
        error(`[proposals] Update error for ${row.proposal_id}: ${e.message}`);
      }
      if ((i + 1) % 25 === 0 || i === existingRows.length - 1) {
        process.stdout.write(`\r  [proposals] Update ${i + 1}/${existingRows.length} (PostgreSQL=${updated})`);
      }
    }
    info(`\n[proposals] Updated ${updated}/${existingRows.length}`);

    // 8. Recreate triggers
    if (triggersDropped) {
      info('[proposals] Recreating triggers...');
      await client.query(`
        CREATE TRIGGER trg_create_proposal_activities_table
        BEFORE INSERT ON proposals FOR EACH ROW
        EXECUTE FUNCTION create_proposal_activities_table()
      `);
      await client.query(`
        CREATE TRIGGER trg_create_proposal_summary_entry
        AFTER INSERT ON proposals FOR EACH ROW
        EXECUTE FUNCTION create_proposal_summary_entry()
      `);
    } else {
      info('[proposals] Triggers untouched (no inserts)');
    }

    // 9. Ensure ga_* tables for proposals missing them
    info('[proposals] Ensuring ga_* tables for proposals missing them...');
    const missingRes = await client.query(
      "SELECT proposal_id FROM proposals WHERE activities_table_name IS NULL OR activities_table_created = FALSE"
    );
    const missing = missingRes.rows.map(r => r.proposal_id);

    let created = 0;
    for (let idx = 0; idx < missing.length; idx++) {
      const pid = missing[idx];
      try {
        const sanitized = pid.replace(/[^a-zA-Z0-9]/g, '').slice(0, 40);
        const tableName = `ga_${crypto.createHash('md5').update(pid).digest('hex').slice(0, 10)}_${sanitized}`;
        const md5Short = crypto.createHash('md5').update(pid).digest('hex').slice(0, 8);

        await client.query(`
          CREATE TABLE IF NOT EXISTS "${tableName}" (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            block_time TIMESTAMP WITH TIME ZONE NULL,
            voter_role VARCHAR(50) NULL,
            voter_id VARCHAR(255) NULL,
            vote VARCHAR(50) NULL,
            meta_url TEXT NULL,
            comment TEXT NULL,
            processed_at TIMESTAMP WITH TIME ZONE NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
          )
        `);
        await client.query(`
          CREATE UNIQUE INDEX IF NOT EXISTS "idx_${md5Short}_voter_block_time" ON "${tableName}"(voter_id, block_time);
          CREATE INDEX IF NOT EXISTS "idx_${md5Short}_voter_id" ON "${tableName}"(voter_id);
          CREATE INDEX IF NOT EXISTS "idx_${md5Short}_voter_role" ON "${tableName}"(voter_role);
          CREATE INDEX IF NOT EXISTS "idx_${md5Short}_block_time" ON "${tableName}"(block_time DESC);
          CREATE INDEX IF NOT EXISTS "idx_${md5Short}_vote" ON "${tableName}"(vote)
        `);
        await client.query(
          'UPDATE proposals SET activities_table_name = $1, activities_table_created = TRUE WHERE proposal_id = $2',
          [tableName, pid]
        );
        created++;
      } catch (e) {
        error(`[proposals] Failed to create ga_* table for ${pid}: ${e.message}`);
      }
      process.stdout.write(`\r  [proposals] tables ${idx + 1}/${missing.length} created=${created}`);
    }
    info(`\n[proposals] Created ${created}/${missing.length} ga_* tables`);

    // 10. Verify
    const cntRes = await client.query('SELECT count(*)::int as cnt FROM proposals');
    info(`[proposals] Row count: ${cntRes.rows[0].cnt}`);
    return cntRes.rows[0].cnt;
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  syncProposals().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { syncProposals };