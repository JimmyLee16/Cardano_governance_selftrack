// verify.js
// Verify PostgreSQL DB row counts
// Equivalent to verify.py

require('dotenv').config();
const { pgConnect, info } = require('./helpers');
const { TABLE_COLUMNS } = require('./config');

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('❌ Thiếu DATABASE_URL trong .env');
  process.exit(1);
}

async function main() {
  info('='.repeat(55));
  info('  PostgreSQL DB Verification');
  info('='.repeat(55));
  info(`${'Table'.padEnd(35)} ${'Rows'.padStart(10)}`);
  info('-'.repeat(55));

  const client = await pgConnect();

  try {
    // Core tables from TABLE_COLUMNS
    const coreTables = Object.keys(TABLE_COLUMNS);
    for (const table of coreTables.sort()) {
      try {
        const res = await client.query(`SELECT count(*)::int as cnt FROM "${table}"`);
        const cnt = res.rows[0].cnt;
        info(`${table.padEnd(35)} ${String(cnt).padStart(10)}`);
      } catch (e) {
        info(`${table.padEnd(35)} ${'ERROR'.padStart(10)}`);
      }
    }

    // Additional tables from Python verify
    const extraTables = [
      'drep_voting_cache',
      'drep_epoch_stats',
      'drep_voting_patterns',
      'proposal_report_insights',
    ];
    for (const table of extraTables) {
      try {
        const res = await client.query(`SELECT count(*)::int as cnt FROM "${table}"`);
        const cnt = res.rows[0].cnt;
        info(`${table.padEnd(35)} ${String(cnt).padStart(10)}`);
      } catch (e) {
        info(`${table.padEnd(35)} ${'ERROR'.padStart(10)}`);
      }
    }

    // ga_* tables
    const gaRes = await client.query(`
      SELECT relname, n_live_tup FROM pg_stat_user_tables
      WHERE relname LIKE 'ga_%' ORDER BY relname
    `);
    const gaTables = gaRes.rows;

    if (gaTables.length > 0) {
      info(`\n--- ga_* tables (${gaTables.length}) ---`);
      let gaTotal = 0;
      for (const row of gaTables) {
        const cnt = parseInt(row.n_live_tup, 10) || 0;
        info(`  ${row.relname.padEnd(33)} ${String(cnt).padStart(10)}`);
        gaTotal += cnt;
      }
      info(`  ${'TOTAL'.padEnd(33)} ${String(gaTotal).padStart(10)}`);
    }

    info('='.repeat(55));
  } finally {
    await client.end();
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { main };